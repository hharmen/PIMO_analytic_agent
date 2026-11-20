"""Загрузка файлов с требованиями (TXT, MD, DOCX, PDF).

Сам файл и извлечённый текст хранит File Service (в S3), Core помнит, чей это файл.
Фронт кладёт текст в поле ввода, пользователь проверяет его и отправляет агенту
вместе с file_id - так в истории чата видно, из какого файла пришли требования.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.clients import file_client
from app.clients.file_client import FileServiceError
from app.config import MAX_UPLOAD_MB
from app.db.models import Message, UploadedFile, User
from app.db.session import get_db
from app.files.schemas import FileOut, FileWithText

router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(get_current_user)])


def get_own_file(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UploadedFile:
    """Файл по id, только если он принадлежит пользователю (чужой = 404, как с чатами)."""
    item = db.get(UploadedFile, file_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    return item


def _service_error(exc: FileServiceError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


@router.post("", response_model=FileWithText, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Принимает файл, возвращает извлечённый из него текст."""
    limit = MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Файл больше {MAX_UPLOAD_MB} МБ")
    try:
        stored = file_client.upload_file(
            file.filename or "file", data, file.content_type or "application/octet-stream"
        )
    except FileServiceError as exc:
        raise _service_error(exc) from None

    item = UploadedFile(
        user_id=user.id,
        storage_id=stored["id"],
        filename=stored["filename"],
        content_type=stored["content_type"],
        size=stored["size"],
        chars=stored["chars"],
    )
    db.add(item)
    db.commit()
    return {**FileOut.model_validate(item).model_dump(), "text": stored["text"], "warnings": stored.get("warnings", [])}


@router.get("", response_model=list[FileOut])
def list_files(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[UploadedFile]:
    """Загруженные файлы пользователя, новые сверху."""
    return list(db.scalars(select(UploadedFile).where(UploadedFile.user_id == user.id).order_by(UploadedFile.id.desc())))


@router.get("/{file_id}", response_model=FileWithText)
def get_file(item: UploadedFile = Depends(get_own_file)) -> dict:
    try:
        stored = file_client.get_file(item.storage_id)
    except FileServiceError as exc:
        raise _service_error(exc) from None
    return {**FileOut.model_validate(item).model_dump(), "text": stored["text"], "warnings": stored.get("warnings", [])}


@router.get("/{file_id}/download")
def download(item: UploadedFile = Depends(get_own_file)) -> Response:
    """Исходный файл."""
    try:
        stored = file_client.download_file(item.storage_id)
    except FileServiceError as exc:
        raise _service_error(exc) from None
    disposition = f"attachment; filename*=UTF-8''{quote(item.filename)}"
    return Response(stored.content, media_type=item.content_type, headers={"Content-Disposition": disposition})


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(item: UploadedFile = Depends(get_own_file), db: Session = Depends(get_db)) -> Response:
    try:
        file_client.delete_file(item.storage_id)
    except FileServiceError as exc:
        if exc.status_code != 404:  # в хранилище уже нет - просто удаляем запись
            raise _service_error(exc) from None
    # сообщения остаются, просто без ссылки на файл
    db.execute(update(Message).where(Message.file_id == item.id).values(file_id=None))
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
