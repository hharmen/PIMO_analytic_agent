import io
import os
import tempfile

# без S3_ENDPOINT файлы пишутся во временную папку
os.environ.pop("S3_ENDPOINT", None)
os.environ.pop("LLM_API_KEY", None)  # OCR в тестах только через подмену (фикстура fake_ocr)
os.environ["FILES_DIR"] = tempfile.mkdtemp(prefix="pimo-files-")

import pytest
from fastapi.testclient import TestClient

from app.api import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def make_docx(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    from docx import Document

    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                grid.cell(r, c).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_pdf(*pages: str | None, image_size: dict[int, int] | None = None) -> bytes:
    """Минимальный PDF: по странице на аргумент. Строка латиницы - текстовая страница, None - пустая (как скан).

    image_size: {номер страницы с 0: сторона квадратной картинки в пунктах} - добавить картинку на страницу.
    """
    image_size = image_size or {}
    count = len(pages)
    # объекты: 1 каталог, 2 список страниц, 3 шрифт, 4 картинка 2x2, дальше пары "страница + её содержимое"
    page_ids = [5 + 2 * i for i in range(count)]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % i for i in page_ids), count),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray /BitsPerComponent 8 "
        b"/Length 4 >>\nstream\n\x80\x80\x80\x80\nendstream",
    ]
    for number, (page_id, text) in enumerate(zip(page_ids, pages)):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
        if number in image_size:
            side = image_size[number]
            stream += f" q {side} 0 0 {side} 72 300 cm /Im1 Do Q".encode()
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                       b"/Resources << /Font << /F1 3 0 R >> /XObject << /Im1 4 0 R >> >> >>" % (page_id + 1))
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def make_png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def fake_ocr(monkeypatch):
    """Включает OCR и подменяет модель: возвращает 'распознанный' текст, страницы считает."""
    from app import config, extract

    calls = []

    def recognize(png: bytes) -> str:
        calls.append(png)
        return f"Распознанная страница {len(calls)}"

    monkeypatch.setattr(extract, "ocr_enabled", lambda: True)
    monkeypatch.setattr(extract, "recognize", recognize)
    monkeypatch.setattr(extract, "describe_image", lambda png: (recognize(png), False))
    monkeypatch.setattr(config, "OCR_PARALLEL", 1)  # по одному потоку - номера страниц предсказуемы
    return calls
