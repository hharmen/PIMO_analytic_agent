"""Тесты агента с подменённой LLM. test_with_real_checker нужен запущенный checker."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app import config
from app.agent import service
from app.clients.checker_client import CheckerError

# acceptance-тест 1 из ТЗ
BROKEN_MODEL = {
    "name": "Request",
    "variables": [
        {"name": "status", "type": "enum", "values": ["Created", "Approved", "Cancelled", "Executed"]},
        {"name": "approved", "type": "boolean"},
        {"name": "cancelled", "type": "boolean"},
    ],
    "initial": {"status": "Created", "approved": False, "cancelled": False},
    "transitions": [
        {"name": "Approve", "guard": {"eq": [{"var": "status"}, "Created"]},
         "effects": [{"set": ["status", "Approved"]}, {"set": ["approved", True]}]},
        {"name": "Cancel", "guard": {"in": [{"var": "status"}, ["Created", "Approved"]]},
         "effects": [{"set": ["status", "Cancelled"]}, {"set": ["cancelled", True]}]},
        {"name": "Execute", "guard": {"var": "approved"}, "effects": [{"set": ["status", "Executed"]}]},
    ],
    "properties": [
        {"id": "P1", "type": "forbidden_state",
         "expression": {"and": [{"eq": [{"var": "status"}, "Executed"]}, {"var": "cancelled"}]}},
    ],
}

VIOLATED = {
    "status": "PROPERTY_VIOLATED",
    "engine": "TLC",
    "results": [{
        "property_id": "P1", "property_type": "forbidden_state", "status": "PROPERTY_VIOLATED",
        "message": "Найден путь из 3 шагов",
        "counterexample": {"steps": [
            {"number": 0, "state": {"status": "Created", "approved": False, "cancelled": False}},
            {"number": 1, "transition": "Approve", "state": {"status": "Approved", "approved": True, "cancelled": False}},
            {"number": 2, "transition": "Cancel", "state": {"status": "Cancelled", "approved": True, "cancelled": True}},
            {"number": 3, "transition": "Execute", "state": {"status": "Executed", "approved": True, "cancelled": True}},
        ]},
        "statistics": {"states_generated": 6}, "engine_output": "много текста TLC",
    }],
    "errors": [],
}
INVALID = {"status": "MODEL_INVALID", "results": [], "errors": [{"path": "initial.cancelled", "message": "Нет начального значения"}]}


def tool_call(model, call_id="call_1"):
    function = SimpleNamespace(name="check_behavior", arguments=json.dumps({"model": model}))
    return SimpleNamespace(content=None, tool_calls=[SimpleNamespace(id=call_id, function=function)])


def text(content):
    return SimpleNamespace(content=content, tool_calls=None)


class FakeLLM:
    """Отдаёт заготовленные ответы по очереди."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=10)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.replies.pop(0))], usage=usage)


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_USE_TOOLS", True)

    def install(replies, checker_results=None):
        llm = FakeLLM(replies)
        monkeypatch.setattr(service, "get_llm_client", lambda: llm)
        sent = []
        results = list(checker_results or [])

        def fake_check(model, *args, **kwargs):
            sent.append(model)
            outcome = results.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(service, "check_model", fake_check)
        return llm, sent

    return install


def test_repair_then_violation_then_explanation(fake):
    llm, sent = fake(
        [tool_call({"variables": []}), tool_call(BROKEN_MODEL, "call_2"), text("1. Заявка создана...")],
        [INVALID, VIOLATED],
    )
    reply = service.run_agent([{"role": "user", "content": "Заявку можно отменить до исполнения"}])

    assert reply.text == "1. Заявка создана..."
    assert reply.model == BROKEN_MODEL and reply.check_result["status"] == "PROPERTY_VIOLATED"
    assert len(sent) == 2
    assert [c["tool_choice"] for c in llm.calls] == ["auto", "auto", "none"]
    assert reply.usage == {"llm_calls": 3, "prompt_tokens": 300, "completion_tokens": 30}

    tool_messages = [m for m in llm.calls[-1]["messages"] if m["role"] == "tool"]
    assert "initial.cancelled: Нет начального значения" in tool_messages[0]["content"]
    assert "много текста TLC" not in tool_messages[1]["content"]
    assert "Execute: status=Executed" in tool_messages[1]["content"]


def test_plain_question_without_check(fake):
    llm, sent = fake([text("Привет! Пришлите описание требований.")])
    reply = service.run_agent([{"role": "user", "content": "привет"}])
    assert reply.text.startswith("Привет") and reply.model is None and reply.check_result is None
    assert sent == []


def test_repairs_are_limited(fake):
    llm, sent = fake(
        [tool_call({}, f"c{i}") for i in range(4)] + [text("Не получилось построить модель")],
        [INVALID] * 4,
    )
    reply = service.run_agent([{"role": "user", "content": "что-то"}])
    assert len(sent) == service.MAX_REPAIRS + 1
    assert llm.calls[-1]["tool_choice"] == "none"
    assert reply.check_result["status"] == "MODEL_INVALID"


def test_checker_down(fake):
    llm, sent = fake([tool_call(BROKEN_MODEL)], [CheckerError("Сервис проверки недоступен")])
    reply = service.run_agent([{"role": "user", "content": "требования"}])
    assert "недоступен" in reply.text and reply.check_result is None


def test_json_in_text_when_tools_are_off(fake, monkeypatch):
    llm, sent = fake(
        [text("Вот модель:\n```json\n" + json.dumps(BROKEN_MODEL) + "\n```"), text("Объяснение")],
        [VIOLATED],
    )
    monkeypatch.setattr(config, "LLM_USE_TOOLS", False)
    reply = service.run_agent([{"role": "user", "content": "требования"}])
    assert sent == [BROKEN_MODEL] and reply.text == "Объяснение"
    assert "tools" not in llm.calls[0]
    assert "PROPERTY_VIOLATED" in llm.calls[1]["messages"][-1]["content"]


def test_empty_llm_text_uses_fallback(fake):
    fake([tool_call(BROKEN_MODEL), text("")], [VIOLATED])
    reply = service.run_agent([{"role": "user", "content": "требования"}])
    assert "P1" in reply.text and "Approve" in reply.text


def test_not_configured(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    reply = service.run_agent([{"role": "user", "content": "требования"}])
    assert "LLM_API_KEY" in reply.text and reply.check_result is None


def test_trim_history():
    history = [{"role": "assistant", "content": "x"}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "a" * 10_000} for i in range(15)
    ]
    trimmed = service.trim_history(history)
    assert trimmed[0]["role"] == "user"
    assert len(trimmed) <= service.MAX_HISTORY_MESSAGES
    assert len(trimmed[-1]["content"]) == 10_000
    assert all(len(m["content"]) < 5_000 for m in trimmed[:-1])


def _checker_is_up() -> bool:
    try:
        return httpx.get(f"{config.CHECKER_URL}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _checker_is_up(), reason="checker не запущен (CHECKER_URL)")
def test_with_real_checker(monkeypatch):
    """Acceptance-тесты 1 и 2 из ТЗ через настоящий TLC."""
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_USE_TOOLS", True)

    llm = FakeLLM([tool_call(BROKEN_MODEL), text("нарушение")])
    monkeypatch.setattr(service, "get_llm_client", lambda: llm)
    reply = service.run_agent([{"role": "user", "content": "требования"}])
    assert reply.check_result["status"] == "PROPERTY_VIOLATED"
    steps = reply.check_result["results"][0]["counterexample"]["steps"]
    assert [s.get("transition") for s in steps] == [None, "Approve", "Cancel", "Execute"]

    fixed = json.loads(json.dumps(BROKEN_MODEL))
    fixed["transitions"][1]["effects"].append({"set": ["approved", False]})
    llm = FakeLLM([tool_call(fixed), text("всё хорошо")])
    monkeypatch.setattr(service, "get_llm_client", lambda: llm)
    assert service.run_agent([{"role": "user", "content": "требования"}]).check_result["status"] == "PROPERTY_HOLDS"
