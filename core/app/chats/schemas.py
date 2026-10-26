"""Форматы запросов и ответов для /chats/*."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatCreate(BaseModel):
    title: str | None = Field(None, max_length=200, description="Название чата. Если не задано, станет первым сообщением")


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(max_length=50_000, description="Текст сообщения (например, требования)")

    @field_validator("content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Сообщение не может быть пустым")
        return value


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class SendMessageOut(BaseModel):
    """Ответ на отправку сообщения: и то, что отправил пользователь, и то, что ответил ассистент."""

    user_message: MessageOut
    assistant_message: MessageOut
    check_run: "CheckRunOut | None" = Field(
        None, description="Результат проверки модели, если агент её запускал; иначе null"
    )


class CheckCreate(BaseModel):
    """Ручной запуск проверки (без агента): удобно для отладки и демонстрации checker'а."""

    model: dict[str, Any] = Field(description="JSON-модель поведения (формат checker/app/schemas.py)")
    property_ids: list[str] | None = Field(None, description="Какие свойства проверять; пусто = все")
    timeout_seconds: int = Field(30, ge=1, le=300)


class CheckRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str = Field(description="Общий статус: PROPERTY_HOLDS, PROPERTY_VIOLATED, MODEL_INVALID, TIMEOUT, ...")
    model_json: dict[str, Any] = Field(description="Модель, которую проверяли")
    result_json: dict[str, Any] = Field(description="Полный ответ checker'а (CheckResult)")
    created_at: datetime


SendMessageOut.model_rebuild()
