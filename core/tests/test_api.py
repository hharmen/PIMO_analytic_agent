import json
import pathlib
import uuid

import httpx
import pytest

from app.agent.service import AgentReply
from app.chats import router as chats_router
from app.clients.checker_client import CheckerError
from tests.conftest import register_and_login

EXAMPLES = pathlib.Path(__file__).resolve().parents[2] / "checker" / "examples"


def uniq() -> str:
    return f"{uuid.uuid4().hex[:8]}@example.com"



def test_register_login_me(client):
    email = uniq()
    r = client.post("/auth/register", json={"email": email.upper(), "password": "password123"})
    assert r.status_code == 201
    assert r.json()["email"] == email
    assert "password" not in json.dumps(r.json()) 

    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == email


def test_duplicate_email_is_409(client):
    email = uniq()
    body = {"email": email, "password": "password123"}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json={**body, "email": email.upper()}).status_code == 409


def test_wrong_password_and_unknown_user_look_identical(client):
    email = uniq()
    client.post("/auth/register", json={"email": email, "password": "password123"})
    wrong = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
    unknown = client.post("/auth/login", json={"email": uniq(), "password": "password123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "password": "password123"},
        {"email": uniq(), "password": "short"},
        {"email": uniq(), "password": "я" * 40}, 
    ],
)
def test_bad_credentials_rejected(client, body):
    assert client.post("/auth/register", json=body).status_code == 422


def test_protected_endpoints_need_token(client):
    for method, url in [("get", "/chats"), ("post", "/chats"), ("get", "/chats/1/messages"), ("get", "/auth/me")]:
        r = getattr(client, method)(url)
        assert r.status_code == 401, url
    bad = {"Authorization": "Bearer garbage"}
    assert client.get("/chats", headers=bad).status_code == 401


def test_expired_token_rejected(client, monkeypatch):
    from app.auth import security

    h = register_and_login(client, uniq())
    monkeypatch.setattr(security, "JWT_EXPIRE_MINUTES", -1) 
    email = uniq()
    client.post("/auth/register", json={"email": email, "password": "password123"})
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/auth/me", headers=h).status_code == 200  




def test_chat_lifecycle_and_messages(client):
    h = register_and_login(client, uniq())
    chat = client.post("/chats", headers=h).json()
    assert chat["title"] == "Новый чат"

    r = client.post(f"/chats/{chat['id']}/messages", headers=h, json={"content": "Заявка создаётся и согласуется"})
    assert r.status_code == 201
    body = r.json()
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["check_run"] is None

    msgs = client.get(f"/chats/{chat['id']}/messages", headers=h).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert client.get("/chats", headers=h).json()[0]["title"] == "Заявка создаётся и согласуется"

    assert client.delete(f"/chats/{chat['id']}", headers=h).status_code == 204
    assert client.get(f"/chats/{chat['id']}/messages", headers=h).status_code == 404


def test_users_cannot_see_each_others_chats(client):
    alice, bob = register_and_login(client, uniq()), register_and_login(client, uniq())
    chat = client.post("/chats", headers=alice, json={"title": "secret"}).json()
    assert client.get("/chats", headers=bob).json() == []
    for method, url in [
        ("get", f"/chats/{chat['id']}/messages"),
        ("post", f"/chats/{chat['id']}/messages"),
        ("get", f"/chats/{chat['id']}/checks"),
        ("delete", f"/chats/{chat['id']}"),
    ]:
        kwargs = {"json": {"content": "hi"}} if method == "post" else {}
        r = getattr(client, method)(url, headers=bob, **kwargs)
        assert r.status_code == 404, (method, url)
    assert client.get(f"/chats/{chat['id']}/messages", headers=alice).status_code == 200  


def test_blank_message_rejected(client):
    h = register_and_login(client, uniq())
    chat = client.post("/chats", headers=h).json()
    assert client.post(f"/chats/{chat['id']}/messages", headers=h, json={"content": "   "}).status_code == 422


def test_agent_crash_keeps_user_message(client, monkeypatch):
    h = register_and_login(client, uniq())
    chat = client.post("/chats", headers=h).json()

    def boom(history):
        raise RuntimeError("LLM упала")

    monkeypatch.setattr(chats_router, "run_agent", boom)
    r = client.post(f"/chats/{chat['id']}/messages", headers=h, json={"content": "привет"})
    assert r.status_code == 500
    assert [m["role"] for m in client.get(f"/chats/{chat['id']}/messages", headers=h).json()] == ["user"]


def test_agent_check_result_is_saved(client, monkeypatch):
    h = register_and_login(client, uniq())
    chat = client.post("/chats", headers=h).json()
    fake = AgentReply(text="Нашёл проблему", model={"variables": []}, check_result={"status": "PROPERTY_VIOLATED"})
    seen = {}

    def fake_agent(history):
        seen["history"] = history
        return fake

    monkeypatch.setattr(chats_router, "run_agent", fake_agent)
    body = client.post(f"/chats/{chat['id']}/messages", headers=h, json={"content": "текст"}).json()
    assert seen["history"] == [{"role": "user", "content": "текст"}]  # агент видит новое сообщение последним
    assert body["check_run"]["status"] == "PROPERTY_VIOLATED"
    assert len(client.get(f"/chats/{chat['id']}/checks", headers=h).json()) == 1



def test_manual_check_saved(client, monkeypatch):
    h = register_and_login(client, uniq())
    chat = client.post("/chats", headers=h).json()
    monkeypatch.setattr(chats_router, "check_model", lambda m, t, p: {"status": "PROPERTY_HOLDS", "results": []})
    r = client.post(f"/chats/{chat['id']}/checks", headers=h, json={"model": {"x": 1}})
    assert r.status_code == 201 and r.json()["status"] == "PROPERTY_HOLDS"
    assert r.json()["model_json"] == {"x": 1}


def test_checker_down_is_502(client, monkeypatch):
    h = register_and_login(client, uniq())
    chat = client.post("/chats", headers=h).json()

    def down(m, t, p):
        raise CheckerError("Сервис проверки недоступен")

    monkeypatch.setattr(chats_router, "check_model", down)
    assert client.post(f"/chats/{chat['id']}/checks", headers=h, json={"model": {}}).status_code == 502


def _checker_alive() -> bool:
    try:
        return httpx.get("http://localhost:8001/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _checker_alive(), reason="checker не запущен на localhost:8001")
def test_real_checker_end_to_end(client):
    """Сквозной тест: Core -> настоящий checker -> TLC. Нужен запущенный checker."""
    h = register_and_login(client, uniq())
    chat = client.post("/chats", headers=h).json()
    model = json.loads((EXAMPLES / "model_broken.json").read_text(encoding="utf-8"))
    r = client.post(f"/chats/{chat['id']}/checks", headers=h, json={"model": model})
    assert r.status_code == 201
    result = r.json()["result_json"]
    assert r.json()["status"] == "PROPERTY_VIOLATED"
    violated = [p for p in result["results"] if p["status"] == "PROPERTY_VIOLATED"]
    assert violated and violated[0]["counterexample"]["steps"]

    fixed = json.loads((EXAMPLES / "model_fixed.json").read_text(encoding="utf-8"))
    assert client.post(f"/chats/{chat['id']}/checks", headers=h, json={"model": fixed}).json()["status"] == "PROPERTY_HOLDS"

    broken_json = {"variables": []}
    assert client.post(f"/chats/{chat['id']}/checks", headers=h, json={"model": broken_json}).json()["status"] == "MODEL_INVALID"
    assert len(client.get(f"/chats/{chat['id']}/checks", headers=h).json()) == 3
