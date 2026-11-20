import pytest

from app import config, extract as extract_module
from app.extract import ExtractError, OcrError, extract, extract_text
from tests.conftest import make_docx, make_pdf, make_png

TEXT = "Заявку можно отменить до исполнения."


def test_txt_utf8_with_bom():
    assert extract_text("a.txt", ("﻿" + TEXT).encode("utf-8")) == TEXT


def test_txt_cp1251():
    assert extract_text("a.TXT", TEXT.encode("cp1251")) == TEXT


def test_txt_binary_rejected():
    with pytest.raises(ExtractError):
        extract_text("a.txt", b"\x00\x01\x02")


def test_normalize_blank_lines_and_spaces():
    assert extract_text("a.md", b"one  \r\n\r\n\r\n\r\ntwo\xc2\xa0x\n") == "one\n\ntwo x"


def test_docx_paragraphs_and_table_in_order():
    data = make_docx([TEXT, "Состояния:"], table=[["Состояние", "Описание"], ["Created", "Создана"]])
    assert extract_text("plan.docx", data) == f"{TEXT}\nСостояния:\nСостояние | Описание\nCreated | Создана"


def test_docx_broken():
    with pytest.raises(ExtractError, match="DOCX"):
        extract_text("plan.docx", b"not a zip")


def test_pdf_text():
    assert extract_text("plan.pdf", make_pdf("Order can be cancelled")) == "Order can be cancelled"


def test_pdf_without_text_layer_is_scan_when_ocr_off():
    with pytest.raises(ExtractError, match="скан"):
        extract_text("scan.pdf", make_pdf(None))


def test_pdf_partly_scanned_warns_when_ocr_off():
    result = extract("plan.pdf", make_pdf("Order can be cancelled", None, None))
    assert result.text == "Order can be cancelled"
    assert result.warnings == ["Без текста стр. 2, 3 (сканы или картинки): их содержимое не попало в текст, "
                               "распознавание не настроено"]


def test_pdf_scanned_pages_go_to_ocr_in_order(fake_ocr):
    result = extract("plan.pdf", make_pdf(None, "Order can be cancelled", None))
    assert len(fake_ocr) == 2  # только страницы без текста
    assert result.text.split("\n") == ["Распознанная страница 1", "Order can be cancelled", "Распознанная страница 2"]
    assert result.warnings == ["Распознано с изображения (OCR): стр. 1, 3. Проверьте текст, возможны ошибки"]


def test_images_on_text_pages_are_reported():
    # стр. 1: текст + крупная картинка, стр. 2: текст + иконка (не считается), стр. 3: только текст
    data = make_pdf("Order can be cancelled", "Order can be approved", "Order can be executed",
                    image_size={0: 300, 1: 20})
    result = extract("plan.pdf", data)
    assert "Order can be cancelled" in result.text
    assert result.warnings == ["На стр. 1 есть изображения (схемы, фото): их содержимое не распознаётся. "
                               "Если там требования - опишите их текстом"]


def test_scanned_page_with_image_is_not_reported_twice(fake_ocr):
    # страница без текста целиком ушла в OCR - отдельно про её картинки не пишем
    result = extract("scan.pdf", make_pdf(None, image_size={0: 300}))
    assert result.warnings == ["Распознано с изображения (OCR): стр. 1. Проверьте текст, возможны ошибки"]


def test_pdf_ocr_failure_and_page_limit(monkeypatch):
    def recognize(png):
        raise OcrError("нет связи")

    monkeypatch.setattr(extract_module, "ocr_enabled", lambda: True)
    monkeypatch.setattr(extract_module, "recognize", recognize)
    monkeypatch.setattr(config, "OCR_MAX_PAGES", 1)
    result = extract("plan.pdf", make_pdf("Order can be cancelled", None, None))
    assert result.text == "Order can be cancelled"
    assert result.warnings == [
        "Не удалось распознать стр. 2: их содержимое не попало в текст",
        "Не распознавались стр. 3: страниц без текста больше 1",
    ]


def test_pdf_all_pages_failed_ocr(monkeypatch):
    monkeypatch.setattr(extract_module, "ocr_enabled", lambda: True)
    monkeypatch.setattr(extract_module, "recognize", lambda png: (_ for _ in ()).throw(OcrError("x")))
    with pytest.raises(ExtractError, match="Не удалось распознать"):
        extract("scan.pdf", make_pdf(None))


def test_image_goes_to_ocr(fake_ocr):
    result = extract("photo.PNG", make_png())
    assert result.text == "Распознанная страница 1"
    assert result.warnings[0].startswith("Текст распознан с изображения")


def test_image_with_diagram(fake_ocr, monkeypatch):
    monkeypatch.setattr(extract_module, "describe_image", lambda png: ("Из Created по Approve в Approved", True))
    result = extract("board.jpg", make_png())
    assert result.text == "Из Created по Approve в Approved"
    assert result.warnings[0].startswith("На картинке схема")


def test_image_without_ocr():
    with pytest.raises(ExtractError, match="не настроено"):
        extract("photo.png", make_png())


def test_broken_image(fake_ocr):
    with pytest.raises(ExtractError, match="открыть"):
        extract("photo.jpg", b"not an image")


def test_unsupported_extension():
    with pytest.raises(ExtractError):
        extract_text("plan.doc", b"x")


def test_empty_file():
    with pytest.raises(ExtractError, match="нет текста"):
        extract_text("a.txt", b"  \n ")
