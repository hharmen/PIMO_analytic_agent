"""Форматы запросов и ответов для /auth/*."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class Credentials(BaseModel):
    """Тело запроса для регистрации и логина."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=255, pattern=EMAIL_PATTERN, examples=["user@example.com"])
    password: str = Field(min_length=8, max_length=72, examples=["my-secret-password"])

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("Пароль слишком длинный (не больше 72 байт, для кириллицы это около 36 символов)")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime
    is_admin: bool
    is_active: bool
    access_until: datetime | None = Field(None, description="До какого момента выдан доступ к агенту; null - не выдан")
    daily_limit: int | None = Field(None, description="Запросов к агенту в сутки (МСК); null - без лимита")


class AgentAccess(BaseModel):
    state: Literal["unlimited", "none", "expired", "limit_reached", "ok"] = Field(
        description="unlimited - администратор; none - доступ не выдан; expired - срок истёк; "
        "limit_reached - лимит на сегодня исчерпан; ok - можно отправлять"
    )
    access_until: datetime | None
    daily_limit: int | None
    used_today: int = Field(description="Запросов к агенту за текущие сутки по Москве")


class MeOut(UserOut):
    agent_access: AgentAccess


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
