"""Доступ к агенту: срок и лимит запросов в сутки, их выдаёт администратор.

Войти и смотреть историю можно всегда (если аккаунт не заблокирован), а вот запросы к агенту
и загрузка файлов (OCR тоже тратит ключ LLM) - только с выданным доступом.
Сутки считаются по Москве. Администраторы работают без ограничений.
"""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.models import Chat, Message, User
from app.db.session import get_db

# в Москве нет перехода на летнее время, поэтому достаточно фиксированного смещения
MSK = timezone(timedelta(hours=3), "МСК")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def day_start(now: datetime) -> datetime:
    """Начало текущих суток по Москве (в UTC)."""
    msk_midnight = datetime.combine(now.astimezone(MSK).date(), time(), MSK)
    return msk_midnight.astimezone(timezone.utc)


def end_of_day(day: date) -> datetime:
    """Доступ «до 30.11 включительно» = до 00:00 МСК 1 декабря."""
    return datetime.combine(day + timedelta(days=1), time(), MSK).astimezone(timezone.utc)


def requests_today(db: Session, user_id: int, now: datetime | None = None) -> int:
    """Сколько сообщений пользователь отправил агенту за текущие сутки."""
    since = day_start(now or now_utc())
    return db.scalar(
        select(func.count(Message.id)).join(Chat, Chat.id == Message.chat_id)
        .where(Chat.user_id == user_id, Message.role == "user", Message.created_at >= since)
    )


def access_state(user: User, used_today: int, now: datetime | None = None) -> str:
    """unlimited | none | expired | limit_reached | ok"""
    now = now or now_utc()
    if user.is_admin:
        return "unlimited"
    if user.access_until is None:
        return "none"
    if user.access_until <= now:
        return "expired"
    if user.daily_limit is not None and used_today >= user.daily_limit:
        return "limit_reached"
    return "ok"


def access_info(db: Session, user: User) -> dict:
    used = requests_today(db, user.id)
    return {
        "state": access_state(user, used),
        "access_until": user.access_until,
        "daily_limit": user.daily_limit,
        "used_today": used,
    }


def _msk_date(moment: datetime) -> str:
    # последний момент доступа - за секунду до конца срока
    return (moment - timedelta(seconds=1)).astimezone(MSK).strftime("%d.%m.%Y")


def require_agent_access(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """Зависимость для запросов, которые тратят ключ LLM. Ошибка - с кодом, чтобы фронт понял причину."""
    used = requests_today(db, user.id)
    state = access_state(user, used)
    if state in ("ok", "unlimited"):
        return user
    if state == "none":
        code, http, message = "access_not_granted", status.HTTP_403_FORBIDDEN, \
            "Доступ к агенту ещё не выдан. Обратитесь к администратору."
    elif state == "expired":
        code, http, message = "access_expired", status.HTTP_403_FORBIDDEN, \
            f"Доступ к агенту закончился {_msk_date(user.access_until)}. Обратитесь к администратору."
    else:
        code, http, message = "daily_limit_reached", status.HTTP_429_TOO_MANY_REQUESTS, \
            f"Лимит {user.daily_limit} запросов на сегодня исчерпан. Новые запросы - после 00:00 МСК."
    raise HTTPException(http, detail={"code": code, "message": message})
