from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.auth.schemas import UserOut


class AdminUserOut(UserOut):
    chat_count: int
    message_count: int
    check_count: int
    last_activity_at: datetime | None
    requests_today: int = Field(description="Запросов к агенту за текущие сутки по Москве")


class UserPage(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class UserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: StrictBool


class UserAccessUpdate(BaseModel):
    """Доступ к агенту. access_until_date: null - закрыть доступ; дата - доступ до конца этого дня по Москве."""

    model_config = ConfigDict(extra="forbid")
    access_until_date: date | None
    daily_limit: int | None = Field(None, ge=1, le=10_000, description="Запросов в сутки; null - без лимита")


class AdminSummary(BaseModel):
    users: int
    active_users: int
    blocked_users: int
    admins: int
    chats: int
    messages: int
    checks: int
    checks_by_status: dict[str, int]


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: int | None
    actor_email: str
    target_id: int
    target_email: str
    action: str
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
    limit: int
    offset: int
