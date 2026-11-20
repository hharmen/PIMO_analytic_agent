"""Хранилище файлов: S3 (MinIO) или локальная папка.

У каждого загруженного файла три объекта:
  {id}/original   - исходный файл как есть
  {id}/text.txt   - извлечённый текст
  {id}/meta.json  - имя, тип, размер, дата
"""

import io
from pathlib import Path

from app import config


class NotFound(Exception):
    """Объекта с таким ключом нет"""


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self.root / key
        if not path.is_file():
            raise NotFound(key)
        return path.read_bytes()

    def delete_prefix(self, prefix: str) -> None:
        folder = self.root / prefix
        if folder.is_dir():
            for path in folder.iterdir():
                path.unlink()
            folder.rmdir()

    def ok(self) -> bool:
        return True


class S3Storage:
    def __init__(self):
        from minio import Minio

        self.bucket = config.S3_BUCKET
        self.client = Minio(
            config.S3_ENDPOINT,
            access_key=config.S3_ACCESS_KEY,
            secret_key=config.S3_SECRET_KEY,
            secure=config.S3_SECURE,
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        # бакет создаём при первом обращении: MinIO может стартовать позже нас
        if not self._bucket_ready:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            self._bucket_ready = True

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._ensure_bucket()
        self.client.put_object(self.bucket, key, io.BytesIO(data), len(data), content_type=content_type)

    def get(self, key: str) -> bytes:
        from minio.error import S3Error

        self._ensure_bucket()
        try:
            response = self.client.get_object(self.bucket, key)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                raise NotFound(key) from exc
            raise
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete_prefix(self, prefix: str) -> None:
        self._ensure_bucket()
        for obj in self.client.list_objects(self.bucket, prefix=f"{prefix}/"):
            self.client.remove_object(self.bucket, obj.object_name)

    def ok(self) -> bool:
        try:
            self._ensure_bucket()
            return True
        except Exception:
            return False


def make_storage():
    return S3Storage() if config.S3_ENDPOINT else LocalStorage(config.FILES_DIR)
