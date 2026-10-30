"""Агент: текст требований -> LLM строит модель -> checker проверяет -> LLM объясняет.

LLM вызывает check_behavior через tool calling. При MODEL_INVALID модель исправляется
(до MAX_REPAIRS раз). После вердикта инструмент отключается, LLM только объясняет.
"""

import json
import logging
import os
import re
import ssl
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app import config
from app.agent.prompts import (
    EXPLAIN_RESULT_PROMPT,
    FIX_MODEL_PROMPT,
    SYSTEM_PROMPT,
    TOOL_CHECK_BEHAVIOR,
)
from app.clients.checker_client import CheckerError, check_model

logger = logging.getLogger("agent")

MAX_REPAIRS = 3  # validator проверяет в 2 этапа, на кривую модель уходит 2-3 попытки
MAX_LLM_CALLS = 7
MAX_HISTORY_MESSAGES = 10
LAST_MESSAGE_LIMIT = 20_000  # текст из файла может быть длинным
OLD_USER_MESSAGE_LIMIT = 4_000
OLD_ASSISTANT_MESSAGE_LIMIT = 1_500
MAX_ERRORS_FOR_LLM = 15

NO_TOOLS_HINT = (
    "\n\nИнструмент check_behavior в этом режиме недоступен: пришли модель целиком одним блоком "
    "```json```, система сама отправит её на проверку и вернёт результат."
)


@dataclass
class AgentReply:
    text: str
    model: dict | None = None  # последняя модель, отправленная в checker
    check_result: dict | None = None
    usage: dict = field(default_factory=dict)  # llm_calls, prompt_tokens, completion_tokens


@dataclass
class _RunState:
    model: dict | None = None
    check_result: dict | None = None
    invalid_count: int = 0
    checker_error: str | None = None
    truncated: bool = False  # последний ответ LLM обрезан по max_tokens
    usage: dict = field(default_factory=lambda: {"llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0})

    @property
    def has_verdict(self) -> bool:
        return self.check_result is not None and self.check_result.get("status") != "MODEL_INVALID"

    @property
    def can_check(self) -> bool:
        return not self.has_verdict and self.invalid_count <= MAX_REPAIRS


def run_agent(history: list[dict]) -> AgentReply:
    """history: [{"role": "user"|"assistant", "content": ...}], новое сообщение последним."""
    missing = missing_llm_settings()
    if missing:
        return AgentReply(text=f"Агент не настроен: задайте переменные окружения {', '.join(missing)}.")
    client = get_llm_client()
    system = SYSTEM_PROMPT if config.LLM_USE_TOOLS else SYSTEM_PROMPT + NO_TOOLS_HINT
    messages: list[dict] = [{"role": "system", "content": system}, *trim_history(history)]
    state = _RunState()

    for _ in range(MAX_LLM_CALLS):
        allow_tools = config.LLM_USE_TOOLS and state.can_check
        msg = _call_llm(client, messages, allow_tools, state)

        if allow_tools and msg.tool_calls:
            messages.append(_assistant_tool_message(msg))
            for call in msg.tool_calls:
                messages.append({"role": "tool", "tool_call_id": call.id, "content": _handle_tool_call(call, state)})
            if state.checker_error:
                return _finish(state, f"Не удалось запустить проверку: {state.checker_error}")
            continue

        text = (msg.content or "").strip()

        # модель пришла текстом (LLM без tool calling)
        model = _extract_model_from_text(text) if state.can_check else None
        if model is not None:
            messages.append({"role": "assistant", "content": text})
            result_for_llm = _run_check(model, state)
            if state.checker_error:
                return _finish(state, f"Не удалось запустить проверку: {state.checker_error}")
            template = FIX_MODEL_PROMPT if state.can_check else EXPLAIN_RESULT_PROMPT
            messages.append({"role": "user", "content": template.format(result=result_for_llm)})
            continue

        return _finish(state, text or fallback_text(state))

    logger.warning("agent: превышен лимит вызовов LLM (%s)", MAX_LLM_CALLS)
    return _finish(state, fallback_text(state))


def _finish(state: _RunState, text: str) -> AgentReply:
    logger.info(
        "agent: llm_calls=%s prompt_tokens=%s completion_tokens=%s status=%s",
        state.usage["llm_calls"],
        state.usage["prompt_tokens"],
        state.usage["completion_tokens"],
        state.check_result.get("status") if state.check_result else None,
    )
    return AgentReply(text=text, model=state.model, check_result=state.check_result, usage=state.usage)


def missing_llm_settings(names: tuple[str, ...] = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")) -> list[str]:
    return [name for name in names if not getattr(config, name)]


def llm_ssl_context() -> ssl.SSLContext | None:
    """Доверять только сертификатам из LLM_CA_FILE (системные не подключаются).

    PARTIAL_CHAIN нужен, чтобы в файле мог лежать сам сертификат сервера, без корневого.
    """
    if not config.LLM_CA_FILE:
        return None
    if not os.path.isfile(config.LLM_CA_FILE):
        raise RuntimeError(f"Не найден файл сертификата LLM_CA_FILE={config.LLM_CA_FILE} (см. README)")
    context = ssl.create_default_context(cafile=config.LLM_CA_FILE)
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return context


@lru_cache
def get_llm_client():
    """Клиент к OpenAI-совместимому API (LiteLLM МАИ)."""
    missing = missing_llm_settings(("LLM_BASE_URL", "LLM_API_KEY"))
    if missing:
        raise RuntimeError(f"Агент не настроен: задайте переменные окружения {', '.join(missing)}")
    from openai import DefaultHttpxClient, OpenAI

    context = llm_ssl_context()
    http_client = DefaultHttpxClient(verify=context) if context else None
    return OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        timeout=config.LLM_TIMEOUT,
        max_retries=1,
        http_client=http_client,
    )


def _call_llm(client, messages: list[dict], allow_tools: bool, state: _RunState):
    kwargs: dict[str, Any] = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": config.LLM_TEMPERATURE,
        "max_tokens": config.LLM_MAX_TOKENS,
    }
    if config.LLM_USE_TOOLS:
        # tools нужны и после вердикта: в истории уже есть вызовы инструмента
        kwargs["tools"] = [TOOL_CHECK_BEHAVIOR]
        kwargs["tool_choice"] = "auto" if allow_tools else "none"

    response = client.chat.completions.create(**kwargs)
    state.usage["llm_calls"] += 1
    state.truncated = getattr(response.choices[0], "finish_reason", None) == "length"
    if response.usage:
        state.usage["prompt_tokens"] += response.usage.prompt_tokens or 0
        state.usage["completion_tokens"] += response.usage.completion_tokens or 0
    return response.choices[0].message


def _assistant_tool_message(msg) -> dict:
    return {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": _arguments_as_text(call.function.arguments)},
            }
            for call in msg.tool_calls
        ],
    }


def _arguments_as_text(arguments: Any) -> str:
    return arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)


def _handle_tool_call(call, state: _RunState) -> str:
    """Возвращает содержимое сообщения role=tool."""
    if call.function.name != "check_behavior":
        return json.dumps({"error": f"Неизвестный инструмент {call.function.name}"}, ensure_ascii=False)
    try:
        args = call.function.arguments
        args = json.loads(args) if isinstance(args, str) else args
        model = args.get("model", args) if isinstance(args, dict) else args  # бывает без обёртки model
        if isinstance(model, str):  # некоторые модели присылают объект строкой
            model = json.loads(model)
    except json.JSONDecodeError as exc:
        if state.truncated:
            return _invalid(state, "Ответ обрезан по лимиту длины. Пришли модель короче: без description, "
                                   "source_ref - 2-5 слов, без лишних свойств.")
        return _invalid(state, f"Аргументы не являются корректным JSON: {exc}")
    if not isinstance(model, dict):
        return _invalid(state, "model должен быть JSON-объектом {...}, а не строкой или списком")
    return _run_check(model, state)


def _invalid(state: _RunState, message: str) -> str:
    state.invalid_count += 1
    return json.dumps({"status": "MODEL_INVALID", "errors": [message]}, ensure_ascii=False)


def _run_check(model: Any, state: _RunState) -> str:
    """Проверяет модель, сохраняет результат в state, возвращает сжатый результат для LLM."""
    try:
        result = check_model(model)
    except CheckerError as exc:
        state.checker_error = str(exc)
        return json.dumps({"status": "ENGINE_ERROR", "errors": [str(exc)]}, ensure_ascii=False)
    state.model = model if isinstance(model, dict) else None
    state.check_result = result
    if result.get("status") == "MODEL_INVALID":
        state.invalid_count += 1
    return json.dumps(compact_result(result), ensure_ascii=False)


def compact_result(result: dict) -> dict:
    """Убирает из ответа checker'а то, что LLM не нужно (статистика, вывод TLC, witness)."""
    out: dict[str, Any] = {"status": result.get("status")}
    errors = result.get("errors") or []
    if errors:
        out["errors"] = [f"{e.get('path')}: {e.get('message')}" for e in errors[:MAX_ERRORS_FOR_LLM]]
    properties = []
    for item in result.get("results") or []:
        prop: dict[str, Any] = {
            "id": item.get("property_id"),
            "type": item.get("property_type"),
            "status": item.get("status"),
            "message": item.get("message"),
        }
        if item.get("counterexample"):
            prop["counterexample"] = compact_trace(item["counterexample"])
        if item.get("related_requirements"):
            prop["requirements"] = item["related_requirements"][:6]
        properties.append(prop)
    if properties:
        out["properties"] = properties
    return out


def compact_trace(trace: dict) -> list[str]:
    """Первое состояние целиком, дальше только изменившиеся переменные."""
    lines: list[str] = []
    previous: dict = {}
    for step in trace.get("steps") or []:
        state = step.get("state") or {}
        if not lines:
            lines.append("Начало: " + _format_state(state))
        else:
            changed = {k: v for k, v in state.items() if previous.get(k) != v}
            lines.append(f"{step.get('transition')}: " + (_format_state(changed) or "без изменений"))
        previous = state
    return lines


def _format_state(state: dict) -> str:
    return ", ".join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in state.items())


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_model_from_text(text: str) -> dict | None:
    """JSON-модель из блока ```json``` или из всего текста."""
    candidates = _JSON_BLOCK_RE.findall(text)
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("model"), dict):
            data = data["model"]
        if isinstance(data, dict) and "variables" in data and "transitions" in data:
            return data
    return None


def trim_history(history: list[dict]) -> list[dict]:
    """Последние сообщения чата, старые обрезаются."""
    recent = list(history[-MAX_HISTORY_MESSAGES:])
    while recent and recent[0].get("role") != "user":
        recent.pop(0)
    trimmed = []
    for index, message in enumerate(recent):
        role = message.get("role")
        if index == len(recent) - 1:
            limit = LAST_MESSAGE_LIMIT
        elif role == "user":
            limit = OLD_USER_MESSAGE_LIMIT
        else:
            limit = OLD_ASSISTANT_MESSAGE_LIMIT
        content = message.get("content") or ""
        if len(content) > limit:
            content = content[:limit] + "\n…[обрезано]"
        trimmed.append({"role": role, "content": content})
    return trimmed


def fallback_text(state: _RunState) -> str:
    """Текст из результата checker'а, если LLM вернула пустой ответ."""
    result = state.check_result
    if result is None:
        return "Не удалось построить модель по этому описанию. Попробуйте сформулировать требования подробнее."
    status = result.get("status")
    if status == "MODEL_INVALID":
        errors = compact_result(result).get("errors", [])
        return "Не удалось построить корректную модель. Ошибки:\n" + "\n".join(f"- {e}" for e in errors[:5])
    if status == "PROPERTY_HOLDS":
        return "Проверка пройдена: в построенной модели ни одно свойство не нарушено."
    lines = [f"Результат проверки: {status}."]
    for prop in compact_result(result).get("properties", []):
        if prop["status"] != "PROPERTY_HOLDS":
            lines.append(f"\nСвойство {prop['id']}: {prop['message']}")
            for number, step in enumerate(prop.get("counterexample", []), start=1):
                lines.append(f"{number}. {step}")
    return "\n".join(lines)
