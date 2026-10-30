

import os

APP_ENV = os.environ.get("APP_ENV", "dev")

CHECKER_URL = os.environ.get("CHECKER_URL", "http://localhost:8001")
FILE_SERVICE_URL = os.environ.get("FILE_SERVICE_URL", "http://localhost:8002")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")

# --- аутентификация ---
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))
BCRYPT_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", "12"))

if APP_ENV == "production" and JWT_SECRET in ("", "change-me"):
    raise RuntimeError("В production нужно задать настоящий JWT_SECRET (длинная случайная строка)")
if not JWT_SECRET:
    JWT_SECRET = "dev-only-secret-do-not-use-in-production"

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if origin.strip()
]

# --- LLM ---
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "90"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "3000"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))
# false - если модель не умеет tool calling
LLM_USE_TOOLS = os.environ.get("LLM_USE_TOOLS", "true").lower() not in ("0", "false", "no")
# сертификат сервера LLM, которому доверяет только клиент LLM (см. README)
LLM_CA_FILE = os.environ.get("LLM_CA_FILE", "")
