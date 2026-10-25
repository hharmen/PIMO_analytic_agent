"""Compiler: JSON-модель -> текст Model.tla и Model.cfg для TLC.

Один вызов compile_model() готовит файлы для проверки ОДНОГО свойства.
Модель уже прошла validator.py, поэтому здесь ошибок не ищем.
Образец результата: docs/tla_demo/Model.tla.
"""

from typing import Any

from app.schemas import BehavioralModel, Property, Transition, Variable

DEFAULT_MAX_STATES = 1_000_000

TLA_OPS = {"eq": "=", "neq": "#", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}


def compile_model(model: BehavioralModel, prop: Property, max_states: int = DEFAULT_MAX_STATES) -> tuple[str, str]:
    """Возвращает (текст Model.tla, текст Model.cfg) для проверки свойства prop."""
    names = [var.name for var in model.variables]
    lines = [
        "---- MODULE Model ----",
        "\\* Файл сгенерирован из JSON-модели (checker/app/compiler.py).",
        "EXTENDS Integers, TLC",
        "",
        "VARIABLES " + ", ".join(names),
        "",
        "\\* Все переменные вместе: нужны для UNCHANGED и Spec",
        f"vars == <<{', '.join(names)}>>",
        "",
    ]
    lines.append("\\* Допустимые значения переменных (домены)")
    lines.append("TypeOK ==")
    for var in model.variables:
        lines.append(f"    /\\ {var.name} \\in {_domain(var)}")
    lines.append("")

    lines.append("\\* Начальное состояние")
    lines.append("Init ==")
    for var in model.variables:
        lines.append(f"    /\\ {var.name} = {_literal(model.initial[var.name])}")
    lines.append("")

    for tr in model.transitions:
        lines.append(f"\\* Переход {tr.name}")
        lines.append(f"{tr.name} ==")
        lines += _transition_body(tr, names)
        lines.append("")

    has_finished = prop.type == "deadlock_free" and prop.final_states is not None
    if has_finished:
        lines.append("\\* Нормальные конечные состояния: остановка в них не тупик")
        lines.append(f"Finished == {compile_expr(prop.final_states)}")
        lines.append("")

    lines.append("\\* Один шаг системы: срабатывает любой разрешённый переход")
    lines.append("Next ==")
    for tr in model.transitions:
        lines.append(f"    \\/ {tr.name}")
    if has_finished:
        lines.append("    \\/ (Finished /\\ UNCHANGED vars)")
    lines.append("")
    lines.append("Spec == Init /\\ [][Next]_vars")
    lines.append("")

    lines += _property_lines(prop)

    lines.append("\\* Лимит: TLC остановит перебор после стольких разных состояний")
    lines.append(f'StateLimit == TLCGet("distinct") < {max_states}')
    lines.append("")
    lines.append("====")
    tla = "\n".join(lines) + "\n"

    cfg_lines = [
        "\\* Настройки запуска TLC (сгенерировано compiler.py)",
        "SPECIFICATION Spec",
        "INVARIANT TypeOK",
    ]
    if prop.type != "deadlock_free":
        cfg_lines.append(f"INVARIANT Prop_{prop.id}")
    cfg_lines.append("CONSTRAINT StateLimit")
    cfg_lines.append("CHECK_DEADLOCK TRUE" if prop.type == "deadlock_free" else "CHECK_DEADLOCK FALSE")
    cfg = "\n".join(cfg_lines) + "\n"

    return tla, cfg


def _transition_body(tr: Transition, names: list[str]) -> list[str]:
    """Тело перехода: guard, затем новые значения (со штрихом), затем UNCHANGED."""
    lines = []
    if tr.guard is not None:
        lines.append(f"    /\\ {_part(tr.guard)}")

    changed = []
    for effect in tr.effects:
        op, (name, value) = next(iter(effect.items()))
        if op == "set":
            new_value = _literal(value)
        elif op == "inc":
            new_value = f"{name} + {value}"
        else: 
            new_value = f"{name} - {value}"
        lines.append(f"    /\\ {name}' = {new_value}")
        changed.append(name)
    unchanged = [name for name in names if name not in changed]
    if unchanged:
        lines.append(f"    /\\ UNCHANGED <<{', '.join(unchanged)}>>")
    return lines


def _property_lines(prop: Property) -> list[str]:
    """Определение свойства. TLC проверяет его как инвариант (истинно в каждом состоянии)."""
    name = f"Prop_{prop.id}"
    if prop.type == "invariant":
        return [
            f"\\* Свойство {prop.id} (invariant): истинно во всех достижимых состояниях",
            f"{name} == {compile_expr(prop.expression)}",
            "",
        ]
    if prop.type == "forbidden_state":
        return [
            f"\\* Свойство {prop.id} (forbidden_state): это состояние не должно быть достижимо",
            f"{name} == ~({compile_expr(prop.expression)})",
            "",
        ]
    if prop.type == "reachable":
        return [
            f"\\* Свойство {prop.id} (reachable): нарушение этой строки = цель достигнута",
            f"{name} == ~({compile_expr(prop.expression)})",
            "",
        ]
    return [
        f"\\* Свойство {prop.id} (deadlock_free): тупики ищет сам TLC (CHECK_DEADLOCK TRUE)",
        "",
    ]


def compile_expr(expr: dict[str, Any]) -> str:
    """JSON-выражение -> строка TLA+. Пример: {"eq": [{"var": "x"}, 1]} -> 'x = 1'."""
    op, args = next(iter(expr.items()))
    if op == "var":
        return args
    if op == "and":
        return " /\\ ".join(_part(sub) for sub in args)
    if op == "or":
        return " \\/ ".join(_part(sub) for sub in args)
    if op == "not":
        return f"~({compile_expr(args)})"
    if op == "in":
        values = ", ".join(_literal(v) for v in args[1])
        return f"{args[0]['var']} \\in {{{values}}}"
    # eq, neq, lt, le, gt, ge
    return f"{_operand(args[0])} {TLA_OPS[op]} {_operand(args[1])}"


def _part(expr: dict[str, Any]) -> str:
    """Вложенные and/or берём в скобки: TLA+ не разрешает смешивать /\\ и \\/ без скобок."""
    text = compile_expr(expr)
    if next(iter(expr)) in ("and", "or"):
        return f"({text})"
    return text


def _operand(x: Any) -> str:
    """Операнд сравнения: {"var": "x"} -> x, литерал -> литерал TLA+."""
    if isinstance(x, dict):
        return x["var"]
    return _literal(x)


def _literal(value: Any) -> str:
    """Значение JSON -> литерал TLA+: true -> TRUE, "Created" -> "Created", 3 -> 3."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    return f'"{value}"'


def _domain(var: Variable) -> str:
    """Множество допустимых значений переменной в TLA+."""
    if var.type == "enum":
        return "{" + ", ".join(_literal(v) for v in var.values) + "}"
    if var.type == "boolean":
        return "BOOLEAN"
    return f"{var.min}..{var.max}"


if __name__ == "__main__":

    import json
    import sys

    from app.validator import validate_model

    model, issues = validate_model(json.load(open(sys.argv[1], encoding="utf-8")))
    if issues:
        for issue in issues:
            print(issue.path, "->", issue.message)
        sys.exit(1)
    for prop in model.properties:
        tla_text, cfg_text = compile_model(model, prop)
        print(f"===== Свойство {prop.id}: Model.tla =====\n{tla_text}")
        print(f"===== Свойство {prop.id}: Model.cfg =====\n{cfg_text}")
