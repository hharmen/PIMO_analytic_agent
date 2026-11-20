from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys
from uuid import uuid4

import jwt
import pytest

from app.auth import security
from app.db.models import User
from app.db.session import SessionLocal
from tests.conftest import register_and_login


def claims():
    now = datetime.now(timezone.utc)
    return {"sub": "1", "iat": now, "exp": now + timedelta(minutes=60)}


def assert_unauthorized(response, code="invalid_token"):
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == code
    assert 'Bearer error="invalid_token"' == response.headers["WWW-Authenticate"]


def test_token_lifetime_uses_configured_minutes(monkeypatch):
    monkeypatch.setattr(security, "JWT_EXPIRE_MINUTES", 45)
    payload = jwt.decode(security.create_access_token(17), security.JWT_SECRET, algorithms=[security.JWT_ALGORITHM])
    assert payload["sub"] == "17"
    assert payload["exp"] - payload["iat"] == 45 * 60


@pytest.mark.parametrize("missing", ["sub", "iat", "exp"])
def test_token_requires_identity_issue_time_and_expiry(client, missing):
    payload = claims()
    del payload[missing]
    token = jwt.encode(payload, security.JWT_SECRET, algorithm=security.JWT_ALGORITHM)
    assert_unauthorized(client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}))


@pytest.mark.parametrize("subject", [None, [], {}, True, 1, "", "-1", "0", "1.0", " 1", "١", "9" * 1000, str(2**63)])
def test_malformed_subject_is_401_not_server_error(client, subject):
    token = jwt.encode({**claims(), "sub": subject}, security.JWT_SECRET, algorithm=security.JWT_ALGORITHM)
    assert_unauthorized(client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}))


@pytest.mark.parametrize("overrides", [{"exp": None}, {"exp": []}, {"exp": "later"}, {"iat": None}, {"iat": []}])
def test_malformed_timestamps_are_rejected(client, overrides):
    token = jwt.encode({**claims(), **overrides}, security.JWT_SECRET, algorithm=security.JWT_ALGORITHM)
    assert_unauthorized(client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}))


@pytest.mark.parametrize(
    "key,algorithm",
    [("wrong-secret-for-signature-check-123", "HS256"), (security.JWT_SECRET, "HS384"), ("", "none")],
    ids=["wrong-signature", "wrong-algorithm", "unsigned"],
)
def test_wrong_signature_or_algorithm_is_rejected(client, key, algorithm):
    token = jwt.encode(claims(), key, algorithm=algorithm)
    assert_unauthorized(client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}))


def test_expired_token_returns_a_specific_error_before_handler_runs(client, monkeypatch):
    from app.chats import router as chats_router

    def forbidden_agent_call(*args):
        pytest.fail("An unauthorized request must not reach the agent")

    monkeypatch.setattr(chats_router, "run_agent", forbidden_agent_call)
    valid = register_and_login(client, f"{uuid4().hex}@example.com")
    chat = client.post("/chats", headers=valid).json()
    payload = jwt.decode(valid["Authorization"].split()[1], security.JWT_SECRET, algorithms=[security.JWT_ALGORITHM])
    payload["exp"] = int(datetime.now(timezone.utc).timestamp()) - 1
    expired = {"Authorization": "Bearer " + jwt.encode(payload, security.JWT_SECRET, algorithm=security.JWT_ALGORITHM)}
    for method, path, kwargs in [
        ("get", "/auth/me", {}),
        ("get", "/chats", {}),
        ("post", f"/chats/{chat['id']}/messages", {"json": {"content": "Do not save this message"}}),
        ("delete", f"/chats/{chat['id']}", {}),
    ]:
        assert_unauthorized(getattr(client, method)(path, headers=expired, **kwargs), "token_expired")
    assert client.get(f"/chats/{chat['id']}/messages", headers=valid).json() == []


def test_deleted_user_cannot_reuse_a_correctly_signed_unexpired_token(client):
    headers = register_and_login(client, f"{uuid4().hex}@example.com")
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        db.delete(db.get(User, user_id))
        db.commit()
    assert_unauthorized(client.get("/auth/me", headers=headers))
    assert_unauthorized(client.get("/chats", headers=headers))
    assert_unauthorized(client.post("/chats", headers=headers, json={}))


@pytest.mark.parametrize("secret,valid", [("", False), ("change-me", False), ("short-value", False), ("test-only-production-secret-of-adequate-length", True)])
def test_production_rejects_missing_default_or_short_signing_secret(secret, valid):
    result = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        env={**os.environ, "APP_ENV": "production", "JWT_SECRET": secret},
        capture_output=True, text=True, timeout=10,
    )
    assert (result.returncode == 0) is valid
    if not valid:
        assert "JWT_SECRET" in result.stderr
