from app import config
from tests.conftest import make_docx, make_pdf

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_upload_get_download_delete(client):
    data = make_docx(["Заявку можно отменить."])
    r = client.post("/files", files={"file": ("бизнес-план.docx", data, DOCX)})
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "бизнес-план.docx"
    assert body["text"] == "Заявку можно отменить."
    assert body["size"] == len(data) and body["chars"] == len(body["text"])

    file_id = body["id"]
    assert client.get(f"/files/{file_id}").json()["text"] == body["text"]

    download = client.get(f"/files/{file_id}/download")
    assert download.status_code == 200 and download.content == data
    assert "UTF-8''" in download.headers["content-disposition"]

    assert client.delete(f"/files/{file_id}").status_code == 204
    assert client.get(f"/files/{file_id}").status_code == 404


def test_path_in_filename_is_dropped(client):
    r = client.post("/files", files={"file": ("../../etc/plan.txt", b"text", "text/plain")})
    assert r.status_code == 201 and r.json()["filename"] == "plan.txt"


def test_unsupported_type_415(client):
    r = client.post("/files", files={"file": ("plan.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_too_large_413(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_MB", 1)
    r = client.post("/files", files={"file": ("a.txt", b"x" * (1024 * 1024 + 1), "text/plain")})
    assert r.status_code == 413


def test_too_much_text_422(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_TEXT_CHARS", 10)
    r = client.post("/files", files={"file": ("a.txt", b"x" * 11, "text/plain")})
    assert r.status_code == 422 and "11 символов" in r.json()["detail"]


def test_bad_id_404(client):
    assert client.get("/files/..%2F..%2Fsecret").status_code == 404
    assert client.get("/files/" + "0" * 32).status_code == 404


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["storage"] == "local" and r.json()["ocr"] is False


def test_scanned_pdf_returns_warnings(client, fake_ocr):
    r = client.post("/files", files={"file": ("scan.pdf", make_pdf(None), "application/pdf")})
    assert r.status_code == 201
    assert r.json()["text"] == "Распознанная страница 1"
    assert r.json()["warnings"] == ["Распознано с изображения (OCR): стр. 1. Проверьте текст, возможны ошибки"]
