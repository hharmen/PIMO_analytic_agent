"""check_behavior: соединяет шаги validator -> compiler -> runner -> parser.

Это и есть инструмент, который вызывает агент (через POST /check).
Каждое свойство проверяется отдельным запуском TLC: так у каждого свойства
свой статус и свой контрпример, и одно нарушение не скрывает другие.
"""

import os
from typing import Any

from app.compiler import DEFAULT_MAX_STATES, compile_model
from app.parser import make_result, parse_tlc_output
from app.runner import run_tlc
from app.schemas import BehavioralModel, CheckResult, Issue, Property, PropertyResult, Status
from app.validator import validate_model

MAX_STATES = int(os.environ.get("CHECKER_MAX_STATES", DEFAULT_MAX_STATES))

STATUS_PRIORITY = [
    Status.MODEL_INVALID,
    Status.PROPERTY_VIOLATED,
    Status.ENGINE_ERROR,
    Status.TIMEOUT,
    Status.STATE_LIMIT_REACHED,
]


def check_behavior(data: Any, property_ids: list[str] | None = None, timeout_seconds: int = 30) -> CheckResult:
    """Проверяет JSON-модель. Никогда не бросает исключений: любой сбой -> статус в ответе."""
    model, issues = validate_model(data)
    if model is None:
        return CheckResult(status=Status.MODEL_INVALID, errors=issues)

    props = model.properties
    if property_ids:
        known = [p.id for p in props]
        unknown = [pid for pid in property_ids if pid not in known]
        if unknown:
            issue = Issue(path="property_ids", message=f"Нет свойств {', '.join(unknown)}. Есть: {', '.join(known)}")
            return CheckResult(status=Status.MODEL_INVALID, errors=[issue])
        props = [p for p in props if p.id in property_ids]

    results = [_check_property(model, prop, timeout_seconds) for prop in props]

    errors = [issue for result in results for issue in result.errors]
    return CheckResult(status=_overall_status(results), results=results, errors=errors)


def _check_property(model: BehavioralModel, prop: Property, timeout_seconds: int) -> PropertyResult:
    try:
        tla_text, cfg_text = compile_model(model, prop, MAX_STATES) 
        run = run_tlc(tla_text, cfg_text, timeout_seconds) 
        report = parse_tlc_output(run.output) 
        return make_result(model, prop, run, report, MAX_STATES) 
    except Exception as exc: 
        return PropertyResult(
            property_id=prop.id,
            property_type=prop.type,
            status=Status.ENGINE_ERROR,
            message=f"Внутренняя ошибка checker: {type(exc).__name__}: {exc}",
        )


def _overall_status(results: list[PropertyResult]) -> Status:
    statuses = {result.status for result in results}
    for status in STATUS_PRIORITY:
        if status in statuses:
            return status
    return Status.PROPERTY_HOLDS
