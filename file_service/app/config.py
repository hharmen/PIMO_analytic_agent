import os

# лимиты: размер файла и длина извлечённого текста (столько агент принимает в одном сообщении)
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "10"))
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "20000"))

# S3 (MinIO). Если S3_ENDPOINT не задан - файлы лежат в папке FILES_DIR (запуск без Docker, тесты)
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")  # например minio:9000, без http://
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "pimo-files")
S3_SECURE = os.environ.get("S3_SECURE", "false").lower() in ("1", "true", "yes")

FILES_DIR = os.environ.get("FILES_DIR", "./data")

# OCR: страницы PDF без текста и картинки распознаёт модель LiteLLM МАИ.
# Без LLM_API_KEY распознавание выключено, сканы дают ошибку или предупреждение.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_CA_FILE = os.environ.get("LLM_CA_FILE", "")
OCR_MODEL = os.environ.get("OCR_MODEL", "hunyuan-ocr")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "qwen3.8-27b")  # отдельные картинки: текст или схема
OCR_TIMEOUT = float(os.environ.get("OCR_TIMEOUT", "120"))
OCR_MAX_PAGES = int(os.environ.get("OCR_MAX_PAGES", "20"))  # больше страниц не распознаём: долго и дорого
OCR_PARALLEL = int(os.environ.get("OCR_PARALLEL", "4"))
