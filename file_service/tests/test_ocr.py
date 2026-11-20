import pytest

from app import ocr


@pytest.mark.parametrize("answer, expected", [
    ("СХЕМА\nИз Created по Approve в Approved", ("Из Created по Approve в Approved", True)),
    ("ТЕКСТ\nЗаявку можно отменить.", ("Заявку можно отменить.", False)),
    ("**Схема:**\nНачальное состояние Created", ("Начальное состояние Created", True)),
    ("Заявку можно отменить.", ("Заявку можно отменить.", False)),  # без метки - текст как есть
    ("СХЕМА", ("СХЕМА", False)),  # одна метка без содержимого
])
def test_split_kind(answer, expected):
    assert ocr.split_kind(answer) == expected


def test_describe_falls_back_to_ocr(monkeypatch):
    def ask(model, prompt, png):
        if model == ocr.config.IMAGE_MODEL:
            raise ocr.OcrError("qwen недоступна")
        return "текст от OCR"

    monkeypatch.setattr(ocr, "_ask", ask)
    assert ocr.describe_image(b"png") == ("текст от OCR", False)
