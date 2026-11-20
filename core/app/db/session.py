"""Подключение к БД и сессии.

"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Общий родитель всех таблиц."""


def get_db() -> Iterator[Session]:

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:

    from app.db import models
    from app.db.migrations import add_user_access_flags

    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Serialize startup schema changes across multiple Core processes.
            connection.execute(text("SELECT pg_advisory_xact_lock(724609183)"))
        Base.metadata.create_all(connection)
        add_user_access_flags(connection)
