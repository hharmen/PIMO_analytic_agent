"""Распознавание картинок через модели LiteLLM МАИ.

- recognize: OCR (hunyuan-ocr) - для страниц-сканов в PDF, только переписывает текст.
- describe_image: qwen3.8-27b - для отдельных картинок. Текст переписывает, а схему (диаграмму
  состояний, процесс) описывает словами: OCR схему не понимает, теряет стрелки.

Модели МАИ не принимают PDF целиком (vLLM понимает только картинки), поэтому
страницу без текста мы сами рисуем картинкой и отправляем её сюда.
"""

import base64
import io
import ssl
from functools import lru_cache

import httpx

from app import config

PROMPT = (
    "Распознай весь текст на изображении и перепиши его дословно, сохраняя абзацы. "
    "Таблицы перепиши строками, ячейки раздели символом |. Без комментариев от себя."
)
DESCRIBE_PROMPT = (
    "Первой строкой ответа напиши ровно одно слово: ТЕКСТ, если на изображении в основном текст, "
    "или СХЕМА, если это схема (диаграмма состояний, блок-схема, процесс со стрелками).\n"
    "Если ТЕКСТ - со второй строки перепиши весь текст дословно, сохраняя абзацы, таблицы строками через |.\n"
    "Если СХЕМА - со второй строки опиши её словами как требования: начальное состояние; для каждой стрелки - "
    "из какого состояния, по какому событию, в какое, с условием и изменениями, если они подписаны; "
    "ограничения, если указаны.\n"
    "Пиши только то, что есть на изображении, ничего не добавляй от себя."
)
MAX_SIDE = 2000  # большие фото уменьшаем: модели хватает, а запрос легче


class OcrError(Exception):
    """OCR недоступен или ничего не распознал"""


def ocr_enabled() -> bool:
    return bool(config.LLM_BASE_URL and config.LLM_API_KEY and config.OCR_MODEL)


@lru_cache
def _ssl_context() -> ssl.SSLContext | bool:
    # тот же закреплённый сертификат сервера МАИ, что и у Core (см. README)
    if not config.LLM_CA_FILE:
        return True
    context = ssl.create_default_context(cafile=config.LLM_CA_FILE)
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return context


def to_png(image) -> bytes:
    """PIL-картинку -> PNG, при необходимости уменьшив."""
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def recognize(png: bytes) -> str:
    """OCR: дословный текст с картинки."""
    return _ask(config.OCR_MODEL, PROMPT, png)


def describe_image(png: bytes) -> tuple[str, bool]:
    """Текст или описание схемы. Возвращает (текст, это_схема). Если qwen не ответил - обычный OCR."""
    try:
        answer = _ask(config.IMAGE_MODEL, DESCRIBE_PROMPT, png)
    except OcrError:
        return recognize(png), False
    return split_kind(answer)


def split_kind(answer: str) -> tuple[str, bool]:
    """Отделяет первую строку-метку ТЕКСТ/СХЕМА. Если модель метку не поставила - считаем текстом."""
    first, _, rest = answer.partition("\n")
    label = first.strip(" *#:.").upper()
    if label in ("ТЕКСТ", "СХЕМА") and rest.strip():
        return rest.strip(), label == "СХЕМА"
    return answer.strip(), False


def _ask(model: str, prompt: str, png: bytes) -> str:
    if not ocr_enabled():
        raise OcrError("распознавание не настроено")
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 6000,  # у "думающей" qwen размышления тоже считаются
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
        ]}],
    }
    try:
        response = httpx.post(
            f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            timeout=config.OCR_TIMEOUT,
            verify=_ssl_context(),
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise OcrError(f"сервис распознавания не ответил ({type(exc).__name__})") from exc
    # "думающие" модели иногда присылают размышления в <think>...</think>
    text = text.split("</think>")[-1].strip()
    if not text:
        raise OcrError("текст не найден")
    return text
