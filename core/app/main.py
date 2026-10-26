"""Core API: вход для фронтенда. Аутентификация, чаты, сообщения, вызов агента и checker'а."""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.chats.router import router as chats_router
from app.config import CHECKER_URL, CORS_ORIGINS, FILE_SERVICE_URL
from app.db.session import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables() 
    yield


app = FastAPI(title="Core API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chats_router)


@app.get("/health", tags=["service"])
def health() -> dict:
    """Core жив + видит ли он соседние сервисы."""
    return {
        "status": "ok",
        "checker": _ping(f"{CHECKER_URL}/health"),
        "file_service": _ping(f"{FILE_SERVICE_URL}/health"),
    }


def _ping(url: str) -> bool:
    try:
        return httpx.get(url, timeout=3).status_code == 200
    except httpx.HTTPError:
        return False
