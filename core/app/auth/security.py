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


class AccessTokenError(ValueError):
    def __init__(self, code: str = "invalid_token"):
        self.code = code
        super().__init__(code)


def decode_access_token(token: str) -> int:
    """Проверяет подпись, обязательные claims, срок и формат id пользователя."""
    try:
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "iat", "exp"]}
        )
        subject = payload["sub"]
        # Keep ids inside the database's signed integer range. Reject malformed
        # signed claims as 401 instead of letting DB conversion raise a 500.
        if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal() or len(subject) > 19:
            raise AccessTokenError()
        user_id = int(subject)
        if not 0 < user_id <= 2**63 - 1:
            raise AccessTokenError()
        return user_id
    except jwt.ExpiredSignatureError as exc:
        raise AccessTokenError("token_expired") from exc
    except (jwt.PyJWTError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AccessTokenError() from exc
