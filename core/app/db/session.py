"""Подключение к БД и сессии.

"""

from collections.abc import Iterator

from sqlalchemy import create_engine
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

    Base.metadata.create_all(engine)
