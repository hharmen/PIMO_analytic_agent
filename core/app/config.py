

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

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
