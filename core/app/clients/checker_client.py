
import httpx

from app.config import CHECKER_URL


def check_model(model: dict, timeout_seconds: int = 30) -> dict:
    """Отправляет JSON-модель в checker и возвращает его ответ (CheckResult)"""
    response = httpx.post(
        f"{CHECKER_URL}/check",
        json={"model": model, "timeout_seconds": timeout_seconds},
        timeout=timeout_seconds * 5,
    )
    response.raise_for_status()
    return response.json()
