
import os

CHECKER_URL = os.environ.get("CHECKER_URL", "http://localhost:8001")
FILE_SERVICE_URL = os.environ.get("FILE_SERVICE_URL", "http://localhost:8002")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
