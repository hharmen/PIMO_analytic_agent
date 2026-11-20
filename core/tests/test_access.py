"""Доступ к агенту: срок и лимит в сутки выдаёт админ."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text

from app.access import rules
from app.agent.service import AgentReply
from app.chats import router as chats_router
from app.db.models import User
from app.db.session import SessionLocal
from tests.conftest import grant_access, register_and_login


@pytest.fixture(autouse=True)
def fake_agent(monkeypatch):
    monkeypatch.setattr(chats_router, "run_agent", lambda history: AgentReply(text="Ок"))


def new_user(client, access=False):
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    headers = register_and_login(client, email, access=access)
    return headers, client.get("/auth/me", headers=headers).json()["id"]


def make_admin(client):
    headers, user_id = new_user(client)
    with SessionLocal() as db:
        db.get(User, user_id).is_admin = True
        db.commit()
    return headers


def send(client, headers):
    chat = client.post("/chats", headers=headers).json()
    return client.post(f"/chats/{chat['id']}/messages", headers=headers, json={"content": "Заявку можно отменить"})


def test_new_account_can_log_in_but_has_no_agent_access(client):
    headers, _ = new_user(client)
    me = client.get("/auth/me", headers=headers).json()
    assert me["agent_access"] == {"state": "none", "access_until": None, "daily_limit": None, "used_today": 0}
    r = send(client, headers)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "access_not_granted"
    # сообщение не сохраняется, чат остаётся пустым
    chat_id = client.get("/chats", headers=headers).json()[0]["id"]
    assert client.get(f"/chats/{chat_id}/messages", headers=headers).json() == []
    # загрузка файла тоже требует доступа (OCR тратит ключ LLM)
    r = client.post("/files", headers=headers, files={"file": ("a.txt", b"text", "text/plain")})
    assert r.status_code == 403


def test_daily_limit(client):
    headers, user_id = new_user(client)
    grant_access(user_id, daily_limit=2)
    assert send(client, headers).status_code == 201
    assert send(client, headers).status_code == 201
    r = send(client, headers)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "daily_limit_reached"
    assert "00:00 МСК" in r.json()["detail"]["message"]
    access = client.get("/auth/me", headers=headers).json()["agent_access"]
    assert access["state"] == "limit_reached" and access["used_today"] == 2


def test_expired_access_keeps_history(client):
    headers, user_id = new_user(client)
    grant_access(user_id)
    assert send(client, headers).status_code == 201
    grant_access(user_id, days=-1)
    r = send(client, headers)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "access_expired"
    assert "закончился" in r.json()["detail"]["message"]
    chats = client.get("/chats", headers=headers).json()
    assert any(client.get(f"/chats/{c['id']}/messages", headers=headers).json() for c in chats)


def test_admin_has_no_limits(client):
    headers = make_admin(client)
    assert client.get("/auth/me", headers=headers).json()["agent_access"]["state"] == "unlimited"
    assert send(client, headers).status_code == 201


def test_admin_grants_and_revokes_access(client):
    admin = make_admin(client)
    headers, user_id = new_user(client)
    until = date.today() + timedelta(days=7)
    r = client.put(f"/admin/users/{user_id}/access", headers=admin,
                   json={"access_until_date": until.isoformat(), "daily_limit": 5})
    assert r.status_code == 200
    assert r.json()["daily_limit"] == 5 and r.json()["requests_today"] == 0
    # доступ до конца выбранного дня по Москве: 00:00 МСК следующего дня = 21:00 UTC выбранного
    assert datetime.fromisoformat(r.json()["access_until"]) == datetime.combine(until, datetime.min.time(), timezone.utc) + timedelta(hours=21)
    assert send(client, headers).status_code == 201
    listed = client.get("/admin/users", headers=admin, params={"q": ""}).json()["items"]
    assert next(u for u in listed if u["id"] == user_id)["requests_today"] == 1

    r = client.put(f"/admin/users/{user_id}/access", headers=admin, json={"access_until_date": None, "daily_limit": None})
    assert r.status_code == 200 and r.json()["access_until"] is None
    assert send(client, headers).status_code == 403
    actions = [a["action"] for a in client.get("/admin/audit", headers=admin).json()["items"][:2]]
    assert actions == ["revoke_access", "grant_access"]


def test_access_endpoint_rules(client):
    admin = make_admin(client)
    headers, user_id = new_user(client)
    other_admin_id = client.get("/auth/me", headers=make_admin(client)).json()["id"]
    body = {"access_until_date": date.today().isoformat(), "daily_limit": 5}
    assert client.put(f"/admin/users/{user_id}/access", headers=headers, json=body).status_code == 403
    assert client.put(f"/admin/users/{other_admin_id}/access", headers=admin, json=body).status_code == 409
    assert client.put(f"/admin/users/{user_id}/access", headers=admin, json={**body, "daily_limit": 0}).status_code == 422
    assert client.put("/admin/users/999999/access", headers=admin, json=body).status_code == 404


def test_day_starts_at_moscow_midnight():
    # 20:59 UTC = 23:59 МСК - ещё те же сутки; 21:00 UTC - уже новые
    assert rules.day_start(datetime(2026, 11, 20, 20, 59, tzinfo=timezone.utc)) == datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)
    assert rules.day_start(datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)) == datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)


def test_old_database_gets_access_columns(tmp_path, monkeypatch):
    from app.db import session

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), password_hash VARCHAR(255), created_at DATETIME)"))
        conn.execute(text("INSERT INTO users (email, password_hash) VALUES ('old@example.com', 'x')"))
    monkeypatch.setattr(session, "engine", engine)
    session.create_tables()
    columns = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"access_until", "daily_limit"} <= columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT email, access_until, daily_limit FROM users")).one() == ("old@example.com", None, None)
