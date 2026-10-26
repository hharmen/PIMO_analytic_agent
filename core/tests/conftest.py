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


def register_and_login(client, email="user@example.com", password="password123") -> dict:
    """Регистрирует пользователя и возвращает заголовок авторизации."""
    client.post("/auth/register", json={"email": email, "password": password})
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
