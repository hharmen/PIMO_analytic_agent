"""Форматы ответов для /files/*."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    size: int = Field(description="Размер файла в байтах")
    chars: int = Field(description="Длина извлечённого текста")
    created_at: datetime


class FileWithText(FileOut):
    text: str = Field(description="Текст, извлечённый из файла. Его можно отправить агенту сообщением")
    warnings: list[str] = Field(
        default_factory=list, description="Что проверить в тексте: страницы, распознанные OCR или пропущенные"
    )
