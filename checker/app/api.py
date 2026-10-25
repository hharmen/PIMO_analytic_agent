"""HTTP API для Model Checker (FastAPI).

POST /check  - проверить модель. Тело: CheckRequest, ответ: CheckResult
GET  /health - жив ли сервис, есть ли Java и tla2tools.jar
GET  /schema - JSON Schema модели и результата + пример модели (для промпта LLM)

"""

import json
import os
import shutil
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.checker import check_behavior
from app.runner import JAVA_BIN, TLA2TOOLS_JAR
from app.schemas import BehavioralModel, CheckRequest, CheckResult

app = FastAPI(title="Model Checker", version="0.1.0")

_tlc_slots = threading.Semaphore(int(os.environ.get("CHECKER_MAX_PARALLEL", "2")))

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "model_broken.json"


@app.post("/check", response_model=CheckResult, response_model_exclude_none=True)
def check(request: CheckRequest) -> CheckResult:
    with _tlc_slots:
        return check_behavior(request.model, request.property_ids, request.timeout_seconds)


@app.get("/health")
def health() -> JSONResponse:
    java_ok = shutil.which(JAVA_BIN) is not None
    jar_ok = Path(TLA2TOOLS_JAR).is_file()
    body = {"status": "ok" if java_ok and jar_ok else "broken", "java": java_ok, "tla2tools_jar": jar_ok}
    return JSONResponse(body, status_code=200 if java_ok and jar_ok else 503)


@app.get("/schema")
def schema() -> dict:
    return {
        "behavioral_model": BehavioralModel.model_json_schema(),
        "check_result": CheckResult.model_json_schema(),
        "example": json.loads(EXAMPLE_PATH.read_text(encoding="utf-8")),
    }
