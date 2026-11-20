"""Совместимое расширение существующей PostgreSQL/SQLite без удаления данных."""

from sqlalchemy import Connection, inspect, text


def add_user_access_flags(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("users")}
    for name, default in (("is_admin", "FALSE"), ("is_active", "TRUE")):
        if name not in columns:
            # Both identifiers and defaults are fixed constants, never user input.
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} BOOLEAN NOT NULL DEFAULT {default}"))
