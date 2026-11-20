"""Извлечение текста из TXT, MD, DOCX, PDF и картинок.

Страницы PDF без текстового слоя (сканы, фото) и картинки распознаются через OCR (app/ocr.py).
"""

import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from app import config
from app.ocr import OcrError, describe_image, ocr_enabled, recognize, to_png

IMAGES = {".png", ".jpg", ".jpeg"}
SUPPORTED = {".txt", ".md", ".docx", ".pdf"} | IMAGES
SUPPORTED_TEXT = "Поддерживаются файлы TXT, MD, DOCX, PDF и картинки PNG, JPG"

# если на странице PDF меньше символов - считаем, что текста нет (у сканов бывает только номер страницы)
MIN_PAGE_CHARS = 10
# картинки меньше этого (в пунктах, 72 на дюйм) - логотипы и иконки, о них не предупреждаем
MIN_IMAGE_WIDTH, MIN_IMAGE_HEIGHT = 100, 50

# DOCX - это zip; защита от "zip-бомбы" (маленький файл, огромный после распаковки)
MAX_UNZIPPED_BYTES = 100 * 1024 * 1024


class ExtractError(Exception):
    """Файл не удалось превратить в текст. Сообщение показывается пользователю."""


@dataclass
class Extracted:
    text: str
    warnings: list[str] = field(default_factory=list)  # что пользователю стоит проверить


def extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def extract(filename: str, data: bytes) -> Extracted:
    ext = extension(filename)
    warnings: list[str] = []
    if ext in (".txt", ".md"):
        text = _from_txt(data)
    elif ext == ".docx":
        text = _from_docx(data)
    elif ext == ".pdf":
        text = _from_pdf(data, warnings)
    elif ext in IMAGES:
        text = _from_image(data, warnings)
    else:
        raise ExtractError(SUPPORTED_TEXT)
    text = _normalize(text)
    if not text:
        raise ExtractError("В файле нет текста")
    return Extracted(text, warnings)


def extract_text(filename: str, data: bytes) -> str:
    return extract(filename, data).text


def _from_txt(data: bytes) -> str:
    if b"\0" in data:
        raise ExtractError("Файл не похож на текстовый")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # старые файлы из Windows часто в cp1251
        try:
            return data.decode("cp1251")
        except UnicodeDecodeError:
            raise ExtractError("Не удалось определить кодировку. Сохраните файл в UTF-8") from None


def _from_docx(data: bytes) -> str:
    from docx import Document
    from docx.table import Table

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNZIPPED_BYTES:
                raise ExtractError("DOCX слишком большой после распаковки")
        document = Document(io.BytesIO(data))
    except ExtractError:
        raise
    except Exception:
        raise ExtractError("Не удалось прочитать DOCX. Если это старый формат DOC - пересохраните в DOCX") from None

    lines = []
    # абзацы и таблицы в том порядке, в каком они идут в документе
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            lines.extend(_table_lines(block))
        else:
            lines.append(block.text)
    return "\n".join(lines)


def _table_lines(table) -> list[str]:
    lines = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            text = " ".join(cell.text.split())
            # объединённые ячейки python-docx отдаёт несколько раз подряд
            if text and (not cells or cells[-1] != text):
                cells.append(text)
        if cells:
            lines.append(" | ".join(cells))
    return lines


def _from_pdf(data: bytes, warnings: list[str]) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractError("PDF защищён паролем")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ExtractError:
        raise
    except Exception:
        raise ExtractError("Не удалось прочитать PDF") from None

    empty = [i for i, text in enumerate(pages) if len("".join(text.split())) < MIN_PAGE_CHARS]
    if empty and not ocr_enabled():
        if len(empty) == len(pages):
            raise ExtractError("В PDF нет текстового слоя (похоже на скан), а распознавание не настроено")
        warnings.append(f"Без текста {_pages(empty)} (сканы или картинки): их содержимое не попало в текст, "
                        "распознавание не настроено")
    elif empty:
        _ocr_pdf_pages(data, pages, empty, warnings)

    # картинки внутри текстовых страниц не распознаём (схемы OCR всё равно не поймёт) - честно предупреждаем
    with_images = [i for i in _pages_with_images(data) if i not in empty]
    if with_images:
        warnings.append(f"На {_pages(with_images)} есть изображения (схемы, фото): их содержимое не распознаётся. "
                        "Если там требования - опишите их текстом")

    if not "".join(pages).strip():
        raise ExtractError("Не удалось распознать текст в PDF")
    return "\n".join(pages)


def _ocr_pdf_pages(data: bytes, pages: list[str], empty: list[int], warnings: list[str]) -> None:
    """Страницы без текста рисуем картинками и распознаём. Результат пишем прямо в pages."""
    import pypdfium2 as pdfium

    todo, skipped = empty[: config.OCR_MAX_PAGES], empty[config.OCR_MAX_PAGES :]
    # рисуем по очереди (pdfium не любит потоки), распознаём параллельно - это самое долгое
    document = pdfium.PdfDocument(data)
    try:
        images = [to_png(document[i].render(scale=2).to_pil()) for i in todo]
    finally:
        document.close()

    def run(png: bytes) -> str | None:
        try:
            return recognize(png)
        except OcrError:
            return None

    with ThreadPoolExecutor(max_workers=config.OCR_PARALLEL) as pool:
        results = list(pool.map(run, images))

    done = [i for i, text in zip(todo, results) if text]
    failed = [i for i, text in zip(todo, results) if not text]
    for i, text in zip(todo, results):
        if text:
            pages[i] = text
    if done:
        warnings.append(f"Распознано с изображения (OCR): {_pages(done)}. Проверьте текст, возможны ошибки")
    if failed:
        warnings.append(f"Не удалось распознать {_pages(failed)}: их содержимое не попало в текст")
    if skipped:
        warnings.append(f"Не распознавались {_pages(skipped)}: страниц без текста больше {config.OCR_MAX_PAGES}")


def _pages_with_images(data: bytes) -> list[int]:
    """Номера страниц (с 0), где есть крупные картинки."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    result = []
    try:
        document = pdfium.PdfDocument(data)
    except Exception:
        return result  # pdfium не открыл - просто без предупреждения, текст уже извлечён
    try:
        for index in range(len(document)):
            for image in document[index].get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE], max_depth=15):
                left, bottom, right, top = image.get_bounds()
                if right - left >= MIN_IMAGE_WIDTH and top - bottom >= MIN_IMAGE_HEIGHT:
                    result.append(index)
                    break
    finally:
        document.close()
    return result


def _from_image(data: bytes, warnings: list[str]) -> str:
    from PIL import Image

    if not ocr_enabled():
        raise ExtractError("Распознавание текста на картинках не настроено")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:
        raise ExtractError("Не удалось открыть картинку") from None
    try:
        text, is_diagram = describe_image(to_png(image))
    except OcrError as exc:
        raise ExtractError(f"Не удалось распознать картинку: {exc}") from None
    if is_diagram:
        warnings.append("На картинке схема - модель описала её словами. Проверьте состояния и переходы: "
                        "модель могла что-то пропустить или понять не так")
    else:
        warnings.append("Текст распознан с изображения: проверьте его, возможны ошибки")
    return text


def _pages(indexes: list[int]) -> str:
    return "стр. " + ", ".join(str(i + 1) for i in indexes)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
