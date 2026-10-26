"""Форматы запросов и ответов для /auth/*."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class Credentials(BaseModel):
    """Тело запроса для регистрации и логина."""

    email: str = Field(max_length=255, pattern=EMAIL_PATTERN, examples=["user@example.com"])
    password: str = Field(min_length=8, max_length=72, examples=["my-secret-password"])

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("Пароль слишком длинный (не больше 72 байт, для кириллицы это около 36 символов)")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
