"""Таблицы БД.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db.session import Base


class UTCDateTime(TypeDecorator):
    """DateTime, который всегда хранит и возвращает время в UTC с указанием пояса.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)

    chats: Mapped[list["Chat"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    files: Mapped[list["UploadedFile"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    user: Mapped[User] = relationship(back_populates="chats")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="Message.id"
    )
    check_runs: Mapped[list["CheckRun"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="CheckRun.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" или "assistant"
    content: Mapped[str] = mapped_column(Text)
    # файл, из которого взят текст сообщения (если требования пришли файлом)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    chat: Mapped[Chat] = relationship(back_populates="messages")
    file: Mapped["UploadedFile | None"] = relationship()


class CheckRun(Base):
    """Один вызов checker'а: какую модель отправили и что получили."""

    __tablename__ = "check_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), index=True)
    model_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40))  # общий статус из result_json
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    chat: Mapped[Chat] = relationship(back_populates="check_runs")


class AdminAudit(Base):
    """Снимки участников сохраняют смысл записи даже после удаления аккаунта."""

    __tablename__ = "admin_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None]
    actor_email: Mapped[str] = mapped_column(String(255))
    target_id: Mapped[int]
    target_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


class UploadedFile(Base):
    """Файл, загруженный пользователем. Сам файл и текст лежат в File Service (S3), здесь - чей он."""

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    storage_id: Mapped[str] = mapped_column(String(64))  # id в File Service
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int]
    chars: Mapped[int]  # длина извлечённого текста
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    user: Mapped[User] = relationship(back_populates="files")
