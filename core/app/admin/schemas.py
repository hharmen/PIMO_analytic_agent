from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictBool

from app.auth.schemas import UserOut


class AdminUserOut(UserOut):
    chat_count: int
    message_count: int
    check_count: int
    last_activity_at: datetime | None


class UserPage(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class UserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: StrictBool


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
