"""Назначение роли существующему аккаунту: python -m app.admin.cli grant EMAIL."""

import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AdminAudit, User
from app.db.session import SessionLocal, create_tables


def change_admin_role(db: Session, email: str, grant: bool) -> User:
    # Serialize CLI role changes too, so two simultaneous revokes cannot remove
    # the last two administrators. SQLite is used locally with one CLI process.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(724609184)"))
    user = db.scalar(select(User).where(User.email == email.strip().lower()).with_for_update())
    if user is None:
        raise ValueError("Пользователь не найден. Сначала зарегистрируйтесь через интерфейс.")
    if grant and not user.is_active:
        raise ValueError("Заблокированный аккаунт нельзя назначить администратором. Сначала разблокируйте его.")
    if user.is_admin == grant:
        return user
    if not grant:
        admins = db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True), User.is_active.is_(True)))
        if admins <= 1:
            raise ValueError("Нельзя снять роль с последнего действующего администратора.")
    user.is_admin = grant
    db.add(AdminAudit(actor_id=None, actor_email="server-cli", target_id=user.id, target_email=user.email,
                      action="grant_admin" if grant else "revoke_admin"))
    db.commit()
    return user


def main():
    parser = argparse.ArgumentParser(description="Назначить или снять роль администратора у существующего пользователя")
    parser.add_argument("action", choices=["grant", "revoke"])
    parser.add_argument("email")
    args = parser.parse_args()
    create_tables()
    with SessionLocal() as db:
        try:
            user = change_admin_role(db, args.email, args.action == "grant")
        except ValueError as exc:
            parser.exit(1, f"{exc}\n")
        print(f"{user.email}: {'администратор' if user.is_admin else 'пользователь'}")


if __name__ == "__main__":
    main()
