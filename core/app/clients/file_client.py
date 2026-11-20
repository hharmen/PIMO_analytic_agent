"""Клиент к File Service."""

import httpx

from app.config import FILE_SERVICE_URL

TIMEOUT = 600  # скан на 20 страниц распознаётся через OCR несколько минут


class FileServiceError(Exception):
    """File Service недоступен или отказал. status_code - что вернуть пользователю."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _raise_for(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    if response.status_code in (404, 413, 415, 422):
        # понятные пользователю ошибки (не тот формат, скан, слишком большой) передаём как есть
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise FileServiceError(str(detail or "Файл не принят"), response.status_code)
    raise FileServiceError(f"Сервис файлов вернул ошибку {response.status_code}")


def _call(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        response = httpx.request(method, f"{FILE_SERVICE_URL}{path}", timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError as exc:
        raise FileServiceError(f"Сервис файлов недоступен ({type(exc).__name__})") from exc
    _raise_for(response)
    return response


def upload_file(filename: str, data: bytes, content_type: str) -> dict:
    """Возвращает {id, filename, content_type, size, chars, text}."""
    return _call("POST", "/files", files={"file": (filename, data, content_type)}).json()


def get_file(file_id: str) -> dict:
    return _call("GET", f"/files/{file_id}").json()


def download_file(file_id: str) -> httpx.Response:
    return _call("GET", f"/files/{file_id}/download")


def delete_file(file_id: str) -> None:
    _call("DELETE", f"/files/{file_id}")
