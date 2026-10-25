"""Core API"""

import httpx
from fastapi import FastAPI

from app.config import CHECKER_URL, FILE_SERVICE_URL

app = FastAPI(title="Core API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    """Core жив + видит ли он соседние сервисы внутри docker compose."""
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
