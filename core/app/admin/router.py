from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access.rules import day_start, end_of_day, now_utc
from app.admin.schemas import AdminSummary, AdminUserOut, AuditPage, UserAccessUpdate, UserPage, UserStatusUpdate
from app.auth.deps import get_current_admin
from app.db.models import AdminAudit, Chat, CheckRun, Message, User
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


def user_query():
    # Aggregate each table independently: joining raw rows would multiply counts.
    chats = select(Chat.user_id, func.count().label("chat_count")).group_by(Chat.user_id).subquery()
    messages = (
        select(Chat.user_id, func.count(Message.id).label("message_count"), func.max(Message.created_at).label("last_activity_at"))
        .join(Message, Message.chat_id == Chat.id).group_by(Chat.user_id).subquery()
    )
    checks = (
        select(Chat.user_id, func.count(CheckRun.id).label("check_count"))
        .join(CheckRun, CheckRun.chat_id == Chat.id).group_by(Chat.user_id).subquery()
    )
    # запросы к агенту за текущие сутки по Москве - то же, что считает лимит (app/access/rules.py)
    today = (
        select(Chat.user_id, func.count(Message.id).label("requests_today"))
        .join(Message, Message.chat_id == Chat.id)
        .where(Message.role == "user", Message.created_at >= day_start(now_utc()))
        .group_by(Chat.user_id).subquery()
    )
    return (
        select(User.id, User.email, User.created_at, User.is_admin, User.is_active,
               User.access_until, User.daily_limit,
               func.coalesce(chats.c.chat_count, 0).label("chat_count"),
               func.coalesce(messages.c.message_count, 0).label("message_count"),
               func.coalesce(checks.c.check_count, 0).label("check_count"), messages.c.last_activity_at,
               func.coalesce(today.c.requests_today, 0).label("requests_today"))
        .outerjoin(chats, chats.c.user_id == User.id)
        .outerjoin(messages, messages.c.user_id == User.id)
        .outerjoin(checks, checks.c.user_id == User.id)
        .outerjoin(today, today.c.user_id == User.id)
    )


@router.get("/summary", response_model=AdminSummary)
def summary(db: Session = Depends(get_db)):
    def count(model, *conditions):
        return db.scalar(select(func.count()).select_from(model).where(*conditions))

    return {
        "users": count(User), "active_users": count(User, User.is_active.is_(True)),
        "blocked_users": count(User, User.is_active.is_(False)), "admins": count(User, User.is_admin.is_(True)),
        "chats": count(Chat), "messages": count(Message), "checks": count(CheckRun),
        "checks_by_status": dict(db.execute(select(CheckRun.status, func.count()).group_by(CheckRun.status)).all()),
    }


@router.get("/users", response_model=UserPage)
def list_users(
    q: str = Query("", max_length=255),
    state: Literal["all", "active", "blocked"] = "all",
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    if q.strip():
        conditions.append(User.email.icontains(q.strip(), autoescape=True))
    if state != "all":
        conditions.append(User.is_active.is_(state == "active"))
    total = db.scalar(select(func.count()).select_from(User).where(*conditions))
    items = db.execute(user_query().where(*conditions).order_by(User.id.desc()).limit(limit).offset(offset)).mappings().all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def set_user_status(
    user_id: int, body: UserStatusUpdate, admin: User = Depends(get_current_admin), db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(404, "Пользователь не найден")
    if user.id == admin.id or user.is_admin:
        raise HTTPException(409, "Администраторов нельзя блокировать через панель")
    if user.is_active != body.is_active:
        user.is_active = body.is_active
        db.add(AdminAudit(
            actor_id=admin.id, actor_email=admin.email, target_id=user.id, target_email=user.email,
            action="unblock_user" if body.is_active else "block_user",
        ))
        db.commit()
    return db.execute(user_query().where(User.id == user_id)).mappings().one()


@router.put("/users/{user_id}/access", response_model=AdminUserOut)
def set_user_access(
    user_id: int, body: UserAccessUpdate, admin: User = Depends(get_current_admin), db: Session = Depends(get_db),
):
    """Срок доступа к агенту и лимит запросов в сутки. Только администратор, у администраторов ограничений нет."""
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(404, "Пользователь не найден")
    if user.is_admin:
        raise HTTPException(409, "У администраторов доступ без ограничений")
    access_until = end_of_day(body.access_until_date) if body.access_until_date else None
    if (user.access_until, user.daily_limit) != (access_until, body.daily_limit):
        user.access_until = access_until
        user.daily_limit = body.daily_limit
        db.add(AdminAudit(
            actor_id=admin.id, actor_email=admin.email, target_id=user.id, target_email=user.email,
            action="grant_access" if access_until else "revoke_access",
        ))
        db.commit()
    return db.execute(user_query().where(User.id == user_id)).mappings().one()


@router.get("/audit", response_model=AuditPage)
def audit(
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(AdminAudit))
    items = list(db.scalars(select(AdminAudit).order_by(AdminAudit.id.desc()).offset(offset).limit(limit)))
    return {"items": items, "total": total, "limit": limit, "offset": offset}
