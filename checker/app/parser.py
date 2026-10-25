"""Parser: разбирает текстовый вывод TLC и выбирает статус результата.

Две функции:
1) parse_tlc_output(): текст TLC -> факты (что случилось, трасса, статистика).
   Ничего не знает о типах свойств, поэтому её легко тестировать на сохранённых выводах.
2) make_result(): факты + тип свойства -> PropertyResult со статусом из ТЗ.
"""

import re
from dataclasses import dataclass, field

from app.runner import RunResult
from app.schemas import (
    BehavioralModel, Issue, Property, PropertyResult, Statistics, Status, Step, Trace,
)

INVARIANT_RE = re.compile(r"^Error: Invariant (\w+) is violated")
STATE_HEADER_RE = re.compile(r"^State (\d+): <(.+)>")
VAR_LINE_RE = re.compile(r"^(?:/\\ )?(\w+) = (.+)$")
STATS_RE = re.compile(r"([\d,]+) states generated, ([\d,]+) distinct states found")
DEPTH_RE = re.compile(r"The depth of the complete state graph search is ([\d,]+)")
NO_ERROR_TEXT = "Model checking completed. No error has been found."


@dataclass
class TlcReport:
    """Факты из вывода TLC."""

    outcome: str 
    violated_invariant: str | None = None 
    trace: list[Step] = field(default_factory=list)
    statistics: Statistics = field(default_factory=Statistics)


def parse_tlc_output(output: str) -> TlcReport:
    """Текст TLC -> TlcReport."""
    lines = output.splitlines()
    trace = _parse_trace(lines)
    stats = _parse_statistics(output)

    for line in lines:
        match = INVARIANT_RE.match(line)
        if match:
            return TlcReport("invariant_violated", match.group(1), trace, stats)
        if line.startswith("Error: Deadlock reached"):
            return TlcReport("deadlock", None, trace, stats)

    if NO_ERROR_TEXT in output:
        return TlcReport("no_error", statistics=stats)
    return TlcReport("error", statistics=stats)


def _parse_trace(lines: list[str]) -> list[Step]:
    """Собирает шаги трассы. TLC нумерует состояния с 1, мы с 0."""
    steps: list[Step] = []
    current: Step | None = None 

    for line in lines:
        header = STATE_HEADER_RE.match(line)
        if header:
            number = int(header.group(1)) - 1
            action = header.group(2).split(" ")[0]
            current = Step(number=number, transition=None if number == 0 else action, state={})
            steps.append(current)
        elif "is violated by the initial state" in line:
            current = Step(number=0, transition=None, state={})
            steps.append(current)
        elif current is not None:
            var_line = VAR_LINE_RE.match(line)
            if var_line:
                current.state[var_line.group(1)] = _parse_value(var_line.group(2))
            elif line.strip() == "":
                current = None 
    return steps


def _parse_value(text: str) -> str | bool | int:
    """Значение TLA+ -> значение JSON: TRUE -> true, "Created" -> "Created", 3 -> 3."""
    text = text.strip()
    if text == "TRUE":
        return True
    if text == "FALSE":
        return False
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    try:
        return int(text)
    except ValueError:
        return text 


def _parse_statistics(output: str) -> Statistics:
    stats = Statistics()
    found = STATS_RE.findall(output)
    if found:
        generated, distinct = found[-1]  # последняя такая строка - итоговая
        stats.states_generated = int(generated.replace(",", ""))
        stats.distinct_states = int(distinct.replace(",", ""))
    depth = DEPTH_RE.findall(output)
    if depth:
        stats.depth = int(depth[-1].replace(",", ""))
    return stats

def make_result(model: BehavioralModel, prop: Property, run: RunResult, report: TlcReport, max_states: int) -> PropertyResult:
    """Выбирает статус по правилам ТЗ. TIMEOUT и STATE_LIMIT_REACHED никогда не HOLDS."""
    order = [var.name for var in model.variables]
    for step in report.trace:
        step.state = {name: step.state[name] for name in order if name in step.state}
    trace = Trace(steps=report.trace) if report.trace else None
    base = {
        "property_id": prop.id,
        "property_type": prop.type,
        "statistics": report.statistics,
        "related_requirements": _related_requirements(model, prop, report.trace),
    }

    if run.error:
        return PropertyResult(**base, status=Status.ENGINE_ERROR, message=run.error)

    if run.timed_out:
        return PropertyResult(
            **base, status=Status.TIMEOUT,
            message=f"TLC не уложился в таймаут ({run.seconds:.0f} с). Ответ неизвестен: это НЕ значит, что свойство выполнено",
        )

    if report.outcome == "invariant_violated" and report.violated_invariant == "TypeOK":
        issue = _type_ok_issue(model, report.trace)
        return PropertyResult(**base, status=Status.MODEL_INVALID, message=issue.message, counterexample=trace, errors=[issue])

    if report.outcome == "invariant_violated" and report.violated_invariant == f"Prop_{prop.id}":
        if prop.type == "reachable":
            return PropertyResult(
                **base, status=Status.PROPERTY_HOLDS, witness=trace,
                message=f"Цель достижима: путь из {len(report.trace) - 1} шагов (см. witness)",
            )
        return PropertyResult(
            **base, status=Status.PROPERTY_VIOLATED, counterexample=trace,
            message=f"Найден путь из {len(report.trace) - 1} шагов, нарушающий свойство (см. counterexample)",
        )

    if report.outcome == "deadlock" and prop.type == "deadlock_free":
        return PropertyResult(
            **base, status=Status.PROPERTY_VIOLATED, counterexample=trace,
            message="Найден тупик: из последнего состояния трассы нельзя сделать ни одного перехода",
        )

    if report.outcome == "no_error":
        distinct = report.statistics.distinct_states or 0
        if distinct >= max_states:
            return PropertyResult(
                **base, status=Status.STATE_LIMIT_REACHED,
                message=f"Перебор остановлен на лимите {max_states} состояний. Ответ неизвестен: уменьшите домены переменных",
            )
        if prop.type == "reachable":
            return PropertyResult(
                **base, status=Status.PROPERTY_VIOLATED,
                message="Цель недостижима: ни один путь из начального состояния туда не ведёт",
            )
        if prop.type == "deadlock_free":
            message = "Тупиков нет: из каждого достижимого состояния есть переход или это нормальный конец"
        else:
            message = "Свойство выполняется во всех достижимых состояниях"
        return PropertyResult(
            **base, status=Status.PROPERTY_HOLDS,
            message=f"{message} (проверено состояний: {distinct}). Это верно только для этой конечной модели, а не доказательство корректности системы",
        )

    return PropertyResult(
        **base, status=Status.ENGINE_ERROR,
        message=f"Ошибка движка TLC (код выхода {run.exit_code}). Это не ошибка модели: передайте engine_output разработчику",
        engine_output=run.output[-3000:], 
    )


def _type_ok_issue(model: BehavioralModel, trace: list[Step]) -> Issue:
    """Объясняет, какой переход вывел какую переменную за домен."""
    last = trace[-1] if trace else None
    bad = []
    for var in model.variables:
        value = last.state.get(var.name) if last else None
        if var.type == "integer" and isinstance(value, int) and not var.min <= value <= var.max:
            bad.append(f"{var.name} = {value} (домен {var.min}..{var.max})")

    names = [tr.name for tr in model.transitions]
    if last is None or last.transition not in names:
        return Issue(path="transitions", message="Переменная вышла за свой домен: " + ", ".join(bad))
    index = names.index(last.transition)
    return Issue(
        path=f"transitions[{index}].guard",
        message=(
            f"После перехода {last.transition} {', '.join(bad)}. Добавьте в guard ограничение, "
            'например {"lt": [{"var": "x"}, max]} перед inc (см. counterexample)'
        ),
    )


def _related_requirements(model: BehavioralModel, prop: Property, trace: list[Step]) -> list[str]:
    """source_ref свойства и переходов из трассы: связь результата с исходным текстом."""
    refs = []
    if prop.source_ref:
        refs.append(prop.source_ref)
    used = {step.transition for step in trace}
    for tr in model.transitions:
        if tr.name in used and tr.source_ref and tr.source_ref not in refs:
            refs.append(tr.source_ref)
    return refs
