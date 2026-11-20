"""Зависимость get_current_user: защищает эндпоинты, которым нужен вход.

Использование:
    @router.get("/something")
    def handler(user: User = Depends(get_current_user)): ...
Если токена нет или он плохой, до тела handler дело не дойдёт: клиент получит 401.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import AccessTokenError, decode_access_token
from app.db.models import User
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False, description="JWT из POST /auth/login")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    def unauthorized(code: str = "invalid_token") -> HTTPException:
        message = "Сессия истекла. Войдите снова." if code == "token_expired" else "Сессия недействительна. Войдите снова."
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": code, "message": message},
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    if credentials is None:
        raise unauthorized("authentication_required")
    try:
        user_id = decode_access_token(credentials.credentials)
    except AccessTokenError as exc:
        raise unauthorized(exc.code) from exc
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized()
    return user
