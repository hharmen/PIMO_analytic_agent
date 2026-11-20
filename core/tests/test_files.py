"""Тесты /files. File Service подменяется словарём в памяти."""

import uuid

import httpx
import pytest

from app.clients import file_client
from app.clients.file_client import FileServiceError
from tests.conftest import register_and_login


@pytest.fixture()
def fake_service(monkeypatch):
    stored: dict[str, dict] = {}

    def upload_file(filename, data, content_type):
        if filename.endswith(".exe"):
            raise FileServiceError("Поддерживаются файлы TXT, MD, DOCX и PDF", 415)
        warnings = ["Распознано с изображения (OCR): стр. 1. Проверьте текст"] if filename == "scan.pdf" else []
        item = {"id": uuid.uuid4().hex, "filename": filename, "content_type": "text/plain; charset=utf-8",
                "size": len(data), "chars": len(data.decode()), "text": data.decode(), "data": data,
                "warnings": warnings}
        stored[item["id"]] = item
        return item

    def get_file(file_id):
        return stored[file_id]

    def download_file(file_id):
        return httpx.Response(200, content=stored[file_id]["data"])

    def delete_file(file_id):
        del stored[file_id]

    for name, fn in [("upload_file", upload_file), ("get_file", get_file),
                     ("download_file", download_file), ("delete_file", delete_file)]:
        monkeypatch.setattr(file_client, name, fn)
    return stored


def _email() -> str:
    return f"{uuid.uuid4().hex[:8]}@example.com"


def test_upload_returns_text_and_is_listed(client, fake_service):
    headers = register_and_login(client, _email())
    text = "Заявку можно отменить до исполнения."
    r = client.post("/files", headers=headers, files={"file": ("план.txt", text.encode(), "text/plain")})
    assert r.status_code == 201
    body = r.json()
    assert body["text"] == text and body["filename"] == "план.txt"

    listed = client.get("/files", headers=headers).json()
    assert [f["id"] for f in listed] == [body["id"]]
    assert "text" not in listed[0]

    assert client.get(f"/files/{body['id']}", headers=headers).json()["text"] == text
    download = client.get(f"/files/{body['id']}/download", headers=headers)
    assert download.content == text.encode()
    assert "UTF-8''" in download.headers["content-disposition"]


def test_service_errors_are_passed_to_user(client, fake_service):
    headers = register_and_login(client, _email())
    r = client.post("/files", headers=headers, files={"file": ("virus.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415 and "DOCX" in r.json()["detail"]


def test_service_down_is_502(client, monkeypatch):
    monkeypatch.setattr(file_client, "FILE_SERVICE_URL", "http://127.0.0.1:1")
    headers = register_and_login(client, _email())
    r = client.post("/files", headers=headers, files={"file": ("a.txt", b"text", "text/plain")})
    assert r.status_code == 502


def test_foreign_file_is_404_and_delete(client, fake_service):
    owner = register_and_login(client, _email())
    other = register_and_login(client, _email())
    file_id = client.post("/files", headers=owner, files={"file": ("a.txt", b"text", "text/plain")}).json()["id"]

    assert client.get(f"/files/{file_id}", headers=other).status_code == 404
    assert client.get(f"/files/{file_id}/download", headers=other).status_code == 404
    assert client.delete(f"/files/{file_id}", headers=other).status_code == 404

    assert client.delete(f"/files/{file_id}", headers=owner).status_code == 204
    assert client.get(f"/files/{file_id}", headers=owner).status_code == 404
    assert fake_service == {}


def test_files_require_login(client):
    assert client.get("/files").status_code == 401
    assert client.post("/files", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 401


def test_message_keeps_link_to_file(client, fake_service, monkeypatch):
    from app.agent.service import AgentReply
    from app.chats import router as chats_router

    monkeypatch.setattr(chats_router, "run_agent", lambda history: AgentReply(text="Ок"))
    headers = register_and_login(client, _email())
    uploaded = client.post("/files", headers=headers, files={"file": ("план.txt", "Требования".encode(), "text/plain")}).json()
    chat = client.post("/chats", headers=headers).json()

    r = client.post(f"/chats/{chat['id']}/messages", headers=headers,
                    json={"content": uploaded["text"], "file_id": uploaded["id"]})
    assert r.status_code == 201
    assert r.json()["user_message"]["file"] == {"id": uploaded["id"], "filename": "план.txt"}
    assert r.json()["assistant_message"]["file"] is None

    history = client.get(f"/chats/{chat['id']}/messages", headers=headers).json()
    assert history[0]["file"]["filename"] == "план.txt"

    # файл удалили - сообщение в истории остаётся, без ссылки
    assert client.delete(f"/files/{uploaded['id']}", headers=headers).status_code == 204
    history = client.get(f"/chats/{chat['id']}/messages", headers=headers).json()
    assert history[0]["content"] == "Требования" and history[0]["file"] is None


def test_cannot_attach_foreign_file(client, fake_service):
    owner = register_and_login(client, _email())
    other = register_and_login(client, _email())
    file_id = client.post("/files", headers=owner, files={"file": ("a.txt", b"text", "text/plain")}).json()["id"]
    chat = client.post("/chats", headers=other).json()
    r = client.post(f"/chats/{chat['id']}/messages", headers=other, json={"content": "text", "file_id": file_id})
    assert r.status_code == 404


def test_old_database_gets_new_column(tmp_path, monkeypatch):
    """База, созданная до появления messages.file_id: колонка добавляется при старте, данные остаются."""
    from sqlalchemy import create_engine, inspect, text

    from app.db import session

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), "
                          "password_hash VARCHAR(255), created_at DATETIME)"))
        conn.execute(text("CREATE TABLE chats (id INTEGER PRIMARY KEY, user_id INTEGER, title VARCHAR(200), created_at DATETIME)"))
        conn.execute(text("CREATE TABLE messages (id INTEGER PRIMARY KEY, chat_id INTEGER, role VARCHAR(20), "
                          "content TEXT, created_at DATETIME)"))
        conn.execute(text("INSERT INTO messages (chat_id, role, content) VALUES (1, 'user', 'старое сообщение')"))

    monkeypatch.setattr(session, "engine", engine)
    session.create_tables()
    session.create_tables()  # повторный старт ничего не ломает

    assert "file_id" in {c["name"] for c in inspect(engine).get_columns("messages")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT content, file_id FROM messages")).one() == ("старое сообщение", None)


def test_ocr_warnings_are_returned(client, fake_service):
    headers = register_and_login(client, _email())
    r = client.post("/files", headers=headers, files={"file": ("scan.pdf", "текст".encode(), "application/pdf")})
    assert r.status_code == 201
    assert r.json()["warnings"] == ["Распознано с изображения (OCR): стр. 1. Проверьте текст"]
    assert client.get(f"/files/{r.json()['id']}", headers=headers).json()["warnings"] == r.json()["warnings"]
