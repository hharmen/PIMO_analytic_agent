"""Совместимое расширение существующей PostgreSQL/SQLite без удаления данных."""

from sqlalchemy import Connection, inspect, text


def add_user_access_flags(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("users")}
    for name, default in (("is_admin", "FALSE"), ("is_active", "TRUE")):
        if name not in columns:
            # Both identifiers and defaults are fixed constants, never user input.
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} BOOLEAN NOT NULL DEFAULT {default}"))


def add_message_file_link(connection: Connection) -> None:
    # сообщение помнит, из какого загруженного файла взят текст (File Service)
    columns = {column["name"] for column in inspect(connection).get_columns("messages")}
    if "file_id" not in columns:
        connection.execute(text("ALTER TABLE messages ADD COLUMN file_id INTEGER REFERENCES files(id)"))


def add_user_agent_access(connection: Connection) -> None:
    # срок доступа к агенту и лимит запросов в сутки; у существующих аккаунтов доступа нет, пока его не выдаст админ
    columns = {column["name"] for column in inspect(connection).get_columns("users")}
    timestamp = "TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME"
    for name, sql_type in (("access_until", timestamp), ("daily_limit", "INTEGER")):
        if name not in columns:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))
