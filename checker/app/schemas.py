"""Pydantic-схемы: контракт JSON между LLM-агентом и Model Checker.

Форма данных: какие поля есть и какого они типа.
Смысловые проверки (существует ли переменная, входит ли значение в домен)
делает validator.py, там же формируются понятные сообщения об ошибках.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Value = str | bool | int

EXPRESSION_HELP = (
    "Выражение. Варианты: "
    '{"var": "x"} - значение переменной (для boolean можно использовать как условие); '
    '{"eq": [A, B]}, {"neq": [A, B]} - равно / не равно; '
    '{"lt"|"le"|"gt"|"ge": [A, B]} - сравнение целых чисел (<, <=, >, >=); '
    '{"in": [{"var": "x"}, [v1, v2]]} - значение входит в список; '
    '{"and": [e1, e2, ...]}, {"or": [e1, e2, ...]}, {"not": e} - логика. '
    'A и B - это {"var": ...} или литерал: строка, true/false, целое число.'
)

PropertyType = Literal["invariant", "forbidden_state", "reachable", "deadlock_free"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")



class Variable(StrictModel):
    """Переменная состояния. Набор значений всех переменных = одно состояние."""

    name: str = Field(description="Имя: латиница, цифры, _, начинается с буквы")
    type: Literal["enum", "boolean", "integer"]
    values: list[str] | None = Field(None, description="Только для enum: список значений (латиница)")
    min: int | None = Field(None, description="Только для integer: минимум")
    max: int | None = Field(None, description="Только для integer: максимум")
    description: str | None = None
    source_ref: str | None = Field(None, description="Ссылка на исходное требование")


class Transition(StrictModel):
    """Переход (событие): если guard истинен, применяются effects."""

    name: str = Field(description="Имя: латиница, цифры, _, начинается с буквы")
    guard: dict[str, Any] | None = Field(
        None, description="Условие срабатывания. Если не задано, переход разрешён всегда. " + EXPRESSION_HELP
    )
    effects: list[dict[str, Any]] = Field(
        description=(
            'Изменения: {"set": ["x", значение]} - присвоить литерал; '
            '{"inc": ["x", n]} / {"dec": ["x", n]} - увеличить / уменьшить integer на n. '
            "Переменные, которые не упомянуты, не меняются."
        )
    )
    description: str | None = None
    source_ref: str | None = Field(None, description="Ссылка на исходное требование")


class Property(StrictModel):
    """Свойство, которое нужно проверить."""

    id: str = Field(description="Идентификатор: латиница, цифры, _, например P1")
    type: PropertyType = Field(
        description=(
            "invariant - expression истинно во всех достижимых состояниях; "
            "forbidden_state - состояние из expression никогда не достигается; "
            "reachable - состояние из expression достижимо хотя бы одним путём; "
            "deadlock_free - нет состояний, из которых нельзя сделать ни одного перехода"
        )
    )
    expression: dict[str, Any] | None = Field(
        None, description="Нужно для invariant, forbidden_state, reachable. " + EXPRESSION_HELP
    )
    final_states: dict[str, Any] | None = Field(
        None,
        description=(
            "Только для deadlock_free, необязательно: нормальные конечные состояния "
            "(например, Executed или Cancelled). Остановка в них не считается тупиком. "
            + EXPRESSION_HELP
        ),
    )
    description: str | None = None
    source_ref: str | None = Field(None, description="Ссылка на исходное требование")


class BehavioralModel(StrictModel):
    """Формальная модель поведения системы. Её строит LLM из текста требований."""

    name: str | None = None
    description: str | None = None
    variables: list[Variable]
    initial: dict[str, Any] = Field(
        description="Начальное значение для каждой переменной: строка (enum), true/false (boolean) или целое (integer)"
    )
    transitions: list[Transition]
    properties: list[Property]


class CheckRequest(BaseModel):

    model: dict[str, Any] = Field(description="BehavioralModel, схема: GET /schema")
    property_ids: list[str] | None = Field(None, description="Какие свойства проверить. Пусто = все")
    timeout_seconds: int = Field(30, ge=1, le=300, description="Таймаут TLC на одно свойство, секунд")



class Status(StrEnum):
    PROPERTY_HOLDS = "PROPERTY_HOLDS"
    PROPERTY_VIOLATED = "PROPERTY_VIOLATED"
    MODEL_INVALID = "MODEL_INVALID"
    TIMEOUT = "TIMEOUT" 
    STATE_LIMIT_REACHED = "STATE_LIMIT_REACHED"
    ENGINE_ERROR = "ENGINE_ERROR"


class Issue(BaseModel):
    path: str = Field(description='Где ошибка, например "transitions[2].guard.eq[0]"')
    message: str = Field(description="Что не так и как исправить")


class Step(BaseModel):
    number: int = Field(description="Номер шага, начиная с 0")
    transition: str | None = Field(None, description="Каким переходом пришли. У шага 0 нет")
    state: dict[str, Value]


class Trace(BaseModel):
    steps: list[Step]


class Statistics(BaseModel):
    states_generated: int | None = None
    distinct_states: int | None = None
    depth: int | None = None


class PropertyResult(BaseModel):
    """Результат проверки одного свойства."""

    property_id: str
    property_type: PropertyType
    status: Status
    message: str = Field(description="Короткое пояснение по-русски")
    counterexample: Trace | None = Field(None, description="Путь до нарушения (PROPERTY_VIOLATED)")
    witness: Trace | None = Field(None, description="Пример пути до цели (reachable + PROPERTY_HOLDS)")
    statistics: Statistics | None = None
    related_requirements: list[str] = Field(default_factory=list, description="source_ref связанных элементов")
    errors: list[Issue] = Field(default_factory=list, description="Проблемы модели, найденные во время прогона")
    engine_output: str | None = Field(None, description="Конец вывода TLC при ENGINE_ERROR, для отладки")


class CheckResult(BaseModel):
    """Ответ check_behavior и POST /check."""

    status: Status = Field(description="Общий статус: HOLDS, только если ВСЕ свойства HOLDS")
    engine: str = "TLC"
    results: list[PropertyResult] = Field(default_factory=list)
    errors: list[Issue] = Field(default_factory=list, description="Список проблем при MODEL_INVALID")
