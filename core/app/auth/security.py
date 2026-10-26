"""Пароли и токены. Здесь нет ни FastAPI, ни БД: только криптография."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import BCRYPT_ROUNDS, JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET


def hash_password(password: str) -> str:
    """Превращает пароль в хеш для хранения в БД. Обратно пароль из хеша получить нельзя."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Подходит ли введённый пароль к сохранённому хешу."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


DUMMY_HASH = hash_password("dummy-password-for-timing")


def create_access_token(user_id: int) -> str:
    """Выпускает JWT. В поле sub лежит id пользователя (по стандарту это строка)."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Возвращает id пользователя из токена или None, если токен подделан, повреждён или просрочен."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
