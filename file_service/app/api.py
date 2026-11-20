"""File Service: принимает файл, хранит его в S3 (MinIO) и извлекает текст для агента.

POST   /files                 - загрузить файл (multipart, поле file) -> метаданные + текст + предупреждения
GET    /files/{id}            - метаданные + текст
GET    /files/{id}/download   - исходный файл
DELETE /files/{id}            - удалить
GET    /health

Сервис не знает о пользователях: кому принадлежит файл, хранит Core.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse

from app import config
from app.extract import SUPPORTED, SUPPORTED_TEXT, ExtractError, extension, extract
from app.ocr import ocr_enabled
from app.storage import NotFound, make_storage

app = FastAPI(title="File Service", version="0.1.0")
storage = make_storage()

CONTENT_TYPES = {
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

FILE_ID = re.compile(r"^[0-9a-f]{32}$")


def _check_id(file_id: str) -> None:
    # id идёт в путь объекта - пропускаем только то, что сами выдали
    if not FILE_ID.match(file_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")


def _read_meta(file_id: str) -> dict:
    _check_id(file_id)
    try:
        return json.loads(storage.get(f"{file_id}/meta.json"))
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден") from None


@app.post("/files", status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile) -> dict:
    filename = (file.filename or "file").replace("\\", "/").rsplit("/", 1)[-1][:200]
    ext = extension(filename)
    if ext not in SUPPORTED:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, SUPPORTED_TEXT)

    limit = config.MAX_FILE_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Файл больше {config.MAX_FILE_MB} МБ")

    try:
        extracted = extract(filename, data)
    except ExtractError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    text = extracted.text
    if len(text) > config.MAX_TEXT_CHARS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"В файле {len(text)} символов текста, максимум {config.MAX_TEXT_CHARS}. "
            "Оставьте в файле только описание поведения системы",
        )

    file_id = uuid.uuid4().hex
    meta = {
        "id": file_id,
        "filename": filename,
        "content_type": CONTENT_TYPES[ext],
        "size": len(data),
        "chars": len(text),
        "warnings": extracted.warnings,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.put(f"{file_id}/original", data, meta["content_type"])
    storage.put(f"{file_id}/text.txt", text.encode("utf-8"), "text/plain; charset=utf-8")
    storage.put(f"{file_id}/meta.json", json.dumps(meta, ensure_ascii=False).encode("utf-8"), "application/json")
    return {**meta, "text": text}


@app.get("/files/{file_id}")
def get_file(file_id: str) -> dict:
    meta = _read_meta(file_id)
    text = storage.get(f"{file_id}/text.txt").decode("utf-8")
    return {**meta, "text": text}


@app.get("/files/{file_id}/download")
def download(file_id: str) -> Response:
    meta = _read_meta(file_id)
    data = storage.get(f"{file_id}/original")
    # имя может быть по-русски - отдаём в формате RFC 5987
    disposition = f"attachment; filename*=UTF-8''{quote(meta['filename'])}"
    return Response(data, media_type=meta["content_type"], headers={"Content-Disposition": disposition})


@app.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(file_id: str) -> Response:
    _read_meta(file_id)
    storage.delete_prefix(file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/health")
def health() -> JSONResponse:
    ok = storage.ok()
    body = {
        "status": "ok" if ok else "broken",
        "storage": "s3" if config.S3_ENDPOINT else "local",
        "ocr": ocr_enabled(),
    }
    return JSONResponse(body, status_code=200 if ok else 503)
