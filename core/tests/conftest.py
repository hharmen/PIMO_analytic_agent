import os
import tempfile

# Настройки ставим ДО импорта приложения: оно читает их при импорте
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["BCRYPT_ROUNDS"] = "4"  # быстрее в тестах

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def register_and_login(client, email="user@example.com", password="password123", access=True) -> dict:
    """Регистрирует пользователя и возвращает заголовок авторизации.

    access=True - сразу выдать доступ к агенту на 30 дней без лимита (как сделал бы админ).
    """
    client.post("/auth/register", json={"email": email, "password": password})
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    if access:
        grant_access(client.get("/auth/me", headers=headers).json()["id"])
    return headers


def grant_access(user_id: int, days: int = 30, daily_limit: int | None = None) -> None:
    from datetime import datetime, timedelta, timezone

    from app.db.models import User
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        user = db.get(User, user_id)
        user.access_until = datetime.now(timezone.utc) + timedelta(days=days)
        user.daily_limit = daily_limit
        db.commit()
