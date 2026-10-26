"""Клиент к Model Checker. Агент вызывает check_model() как инструмент check_behavior."""

import httpx

from app.config import CHECKER_URL


class CheckerError(Exception):
    """Checker недоступен или ответил не так как ожидалось"""


def check_model(model: dict, timeout_seconds: int = 30, property_ids: list[str] | None = None) -> dict:
    """Отправляет JSON-модель в checker и возвращает его ответ (CheckResult) как словарь.
    """
    properties = model.get("properties") if isinstance(model, dict) else None
    count = len(properties) if isinstance(properties, list) and properties else 1
    body: dict = {"model": model, "timeout_seconds": timeout_seconds}
    if property_ids is not None:
        body["property_ids"] = property_ids
    try:
        response = httpx.post(f"{CHECKER_URL}/check", json=body, timeout=timeout_seconds * count + 15)
    except httpx.HTTPError as exc:
        raise CheckerError(f"Сервис проверки недоступен ({type(exc).__name__})") from exc
    if response.status_code != 200:
        raise CheckerError(f"Сервис проверки вернул ошибку {response.status_code}: {response.text[:300]}")
    return response.json()
