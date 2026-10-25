"""Validator: проверяет модель ДО запуска TLC.

Возвращает список проблем (Issue): путь до места ошибки и понятный текст.
По этому списку LLM исправляет свой JSON, поэтому сообщение говорит
не только "что не так", но и "как правильно".
"""

import difflib
import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas import BehavioralModel, Issue, Variable

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


ENUM_VALUE_RE = re.compile(r"^[A-Za-z0-9_]+$")

MAX_INT_RANGE = 1000

RESERVED_NAMES = {
    "ASSUME", "ASSUMPTION", "AXIOM", "CASE", "CHOOSE", "CONSTANT", "CONSTANTS", "DOMAIN",
    "ELSE", "ENABLED", "EXCEPT", "EXTENDS", "IF", "IN", "INSTANCE", "LET", "LOCAL",
    "MODULE", "OTHER", "SUBSET", "THEN", "THEOREM", "UNCHANGED", "UNION", "VARIABLE",
    "VARIABLES", "WITH", "ACTION", "BY", "COROLLARY", "DEF", "DEFINE", "DEFS", "HAVE",
    "HIDE", "LAMBDA", "LEMMA", "NEW", "OBVIOUS", "OMITTED", "ONLY", "PICK", "PROOF",
    "PROPOSITION", "PROVE", "QED", "RECURSIVE", "STATE", "SUFFICES", "TAKE", "TEMPORAL",
    "USE", "WITNESS", "TRUE", "FALSE", "BOOLEAN", "STRING",
    "Nat", "Int", "Seq", "Len", "Append", "Head", "Tail", "SubSeq", "SelectSeq",
    "Cardinality", "IsFiniteSet", "Print", "PrintT", "Assert", "JavaTime", "TLCGet",
    "TLCSet", "Permutations", "SortSeq", "RandomElement", "Any", "ToString", "TLCEval",
    "Model", "Init", "Next", "Spec", "vars", "TypeOK", "StateLimit", "Finished",
}
RESERVED_PREFIXES = ("Prop_", "WF_", "SF_")

ALL_OPS = ("var", "and", "or", "not", "eq", "neq", "lt", "le", "gt", "ge", "in")
EFFECT_OPS = ("set", "inc", "dec")
TYPE_NAMES = {"enum": "строку (enum)", "boolean": "boolean", "integer": "integer"}

PYDANTIC_MESSAGES = {
    "missing": "Обязательное поле отсутствует",
    "extra_forbidden": "Лишнее поле: в схеме его нет (возможно, опечатка в названии)",
    "string_type": "Ожидается строка",
    "int_type": "Ожидается целое число",
    "int_parsing": "Ожидается целое число",
    "int_from_float": "Ожидается целое число, а не дробное",
    "list_type": "Ожидается список [...]",
    "dict_type": "Ожидается объект {...}",
    "model_type": "Ожидается объект {...}",
}


def _check_variables(model: BehavioralModel, issues: list[Issue]) -> dict[str, Variable]:
    """Проверяет объявления переменных. Возвращает словарь имя -> переменная."""
    variables: dict[str, Variable] = {}
    if not model.variables:
        issues.append(Issue(path="variables", message="Нужна хотя бы одна переменная"))

    for i, var in enumerate(model.variables):
        path = f"variables[{i}]"
        _check_name(var.name, path + ".name", issues)
        if var.name in variables:
            issues.append(Issue(path=path + ".name", message=f"Переменная '{var.name}' объявлена дважды"))
            continue
        variables[var.name] = var

        if var.type == "enum":
            if not var.values:
                issues.append(Issue(path=path + ".values", message='У enum нужен непустой список values, например ["Created", "Approved"]'))
            else:
                for j, value in enumerate(var.values):
                    if not ENUM_VALUE_RE.match(value):
                        issues.append(Issue(
                            path=f"{path}.values[{j}]",
                            message=f"Значение '{value}': используйте латиницу, цифры и _ без пробелов (например InProgress). Русский текст можно положить в description",
                        ))
                if len(set(var.values)) != len(var.values):
                    issues.append(Issue(path=path + ".values", message="Значения enum повторяются"))
            if var.min is not None or var.max is not None:
                issues.append(Issue(path=path, message="min и max бывают только у integer"))

        elif var.type == "boolean":
            if var.values is not None or var.min is not None or var.max is not None:
                issues.append(Issue(path=path, message="У boolean не должно быть values, min, max: значения всегда true и false"))

        else: 
            if var.values is not None:
                issues.append(Issue(path=path + ".values", message="values бывают только у enum"))
            if var.min is None or var.max is None:
                issues.append(Issue(path=path, message='У integer обязательны min и max (домен должен быть конечным), например "min": 0, "max": 3'))
            elif var.min > var.max:
                issues.append(Issue(path=path, message=f"min ({var.min}) больше max ({var.max})"))
            elif var.max - var.min + 1 > MAX_INT_RANGE:
                issues.append(Issue(path=path, message=f"Слишком большой диапазон {var.min}..{var.max}: допустимо не больше {MAX_INT_RANGE} значений"))
    return variables


def _check_initial(model: BehavioralModel, variables: dict[str, Variable], issues: list[Issue]) -> None:
    """У каждой переменной есть начальное значение, и оно из её домена."""
    for name, var in variables.items():
        if name not in model.initial:
            issues.append(Issue(path="initial", message=f"Нет начального значения для переменной '{name}'"))
        else:
            _check_value(var, model.initial[name], f"initial.{name}", issues)
    for name in model.initial:
        if name not in variables:
            issues.append(Issue(path=f"initial.{name}", message=_unknown_var_text(name, variables)))


def _check_transitions(model: BehavioralModel, variables: dict[str, Variable], issues: list[Issue]) -> None:
    if not model.transitions:
        issues.append(Issue(path="transitions", message="Нужен хотя бы один переход"))
    seen: set[str] = set()
    for i, tr in enumerate(model.transitions):
        path = f"transitions[{i}]"
        _check_name(tr.name, path + ".name", issues)
        if tr.name in seen:
            issues.append(Issue(path=path + ".name", message=f"Переход '{tr.name}' объявлен дважды"))
        seen.add(tr.name)
        if tr.name in variables:
            issues.append(Issue(path=path + ".name", message=f"Имя '{tr.name}' уже занято переменной, назовите переход иначе"))
        if tr.guard is not None:
            _check_condition(tr.guard, path + ".guard", variables, issues)
        _check_effects(tr.effects, path + ".effects", variables, issues)


def _check_effects(effects: list[dict], path: str, variables: dict[str, Variable], issues: list[Issue]) -> None:
    if not effects:
        issues.append(Issue(path=path, message="Переход без effects ничего не меняет. Добавьте хотя бы одно изменение"))
    assigned: set[str] = set() 
    for j, effect in enumerate(effects):
        p = f"{path}[{j}]"
        if len(effect) != 1 or next(iter(effect)) not in EFFECT_OPS:
            issues.append(Issue(path=p, message='Effect - объект с одним ключом: {"set": ["x", значение]}, {"inc": ["x", 1]} или {"dec": ["x", 1]}'))
            continue
        op, args = next(iter(effect.items()))
        if not isinstance(args, list) or len(args) != 2:
            issues.append(Issue(path=f"{p}.{op}", message=f'Ожидается {{"{op}": ["имя_переменной", значение]}}'))
            continue
        name, value = args
        var = _find_var(name, f"{p}.{op}[0]", variables, issues)
        if var is None:
            continue
        if name in assigned:
            issues.append(Issue(path=f"{p}.{op}[0]", message=f"Переменная '{name}' меняется в этом переходе дважды"))
        assigned.add(name)

        if op == "set":
            _check_value(var, value, f"{p}.set[1]", issues)
        elif var.type != "integer":
            issues.append(Issue(path=f"{p}.{op}[0]", message=f"{op} работает только с integer, а '{name}' - {var.type}. Используйте set"))
        elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            issues.append(Issue(path=f"{p}.{op}[1]", message=f"Для {op} нужно положительное целое число, например 1"))


def _check_properties(model: BehavioralModel, variables: dict[str, Variable], issues: list[Issue]) -> None:
    if not model.properties:
        issues.append(Issue(path="properties", message="Нужно хотя бы одно свойство для проверки"))
    seen: set[str] = set()
    for i, prop in enumerate(model.properties):
        path = f"properties[{i}]"
        _check_name(prop.id, path + ".id", issues)
        if prop.id in seen:
            issues.append(Issue(path=path + ".id", message=f"Свойство '{prop.id}' объявлено дважды"))
        seen.add(prop.id)

        if prop.type == "deadlock_free":
            if prop.expression is not None:
                issues.append(Issue(path=path + ".expression", message="Для deadlock_free expression не нужен. Нормальные конечные состояния задаются в final_states"))
            if prop.final_states is not None:
                _check_condition(prop.final_states, path + ".final_states", variables, issues)
        else:
            if prop.expression is None:
                issues.append(Issue(path=path + ".expression", message=f"Для {prop.type} нужно поле expression"))
            else:
                _check_condition(prop.expression, path + ".expression", variables, issues)
            if prop.final_states is not None:
                issues.append(Issue(path=path + ".final_states", message="final_states бывает только у deadlock_free"))


def _check_condition(expr: Any, path: str, variables: dict[str, Variable], issues: list[Issue]) -> None:
    """Проверяет логическое выражение (guard, expression свойства)."""
    if not isinstance(expr, dict) or len(expr) != 1:
        issues.append(Issue(path=path, message='Выражение - объект с одним ключом, например {"eq": [{"var": "status"}, "Created"]}'))
        return
    op, args = next(iter(expr.items()))

    if op == "var":
        var = _find_var(args, path + ".var", variables, issues)
        if var is not None and var.type != "boolean":
            issues.append(Issue(path=path, message=f"'{var.name}' - {var.type}, а не boolean. Используйте eq или in"))
    elif op in ("and", "or"):
        if not isinstance(args, list) or not args:
            issues.append(Issue(path=f"{path}.{op}", message=f'Ожидается непустой список выражений: {{"{op}": [выражение1, выражение2]}}'))
            return
        for i, sub in enumerate(args):
            _check_condition(sub, f"{path}.{op}[{i}]", variables, issues)
    elif op == "not":
        _check_condition(args, path + ".not", variables, issues)
    elif op in ("eq", "neq", "lt", "le", "gt", "ge"):
        _check_comparison(op, args, path, variables, issues)
    elif op == "in":
        _check_in(args, path, variables, issues)
    else:
        issues.append(Issue(path=path, message=f"Неизвестная операция '{op}'. Допустимы: {', '.join(ALL_OPS)}"))


def _check_comparison(op: str, args: Any, path: str, variables: dict[str, Variable], issues: list[Issue]) -> None:
    """eq, neq, lt, le, gt, ge: ровно два операнда совместимых типов."""
    if not isinstance(args, list) or len(args) != 2:
        issues.append(Issue(path=f"{path}.{op}", message=f'Ожидается список из двух операндов: {{"{op}": [{{"var": "x"}}, значение]}}'))
        return
    left = _operand(args[0], f"{path}.{op}[0]", variables, issues)
    right = _operand(args[1], f"{path}.{op}[1]", variables, issues)
    if left is None or right is None:
        return
    (left_type, left_var), (right_type, right_var) = left, right

    if left_var is None and right_var is None:
        issues.append(Issue(path=f"{path}.{op}", message='Сравниваются две константы. Хотя бы один операнд должен быть {"var": ...}'))
        return
    if left_type != right_type:
        issues.append(Issue(path=f"{path}.{op}", message=f"Нельзя сравнивать {TYPE_NAMES[left_type]} и {TYPE_NAMES[right_type]}"))
        return
    if op not in ("eq", "neq"):
        if left_type != "integer":
            issues.append(Issue(path=f"{path}.{op}", message=f"Операция {op} работает только с integer"))
        return
    if left_var is not None and right_var is None:
        _check_value(left_var, args[1], f"{path}.{op}[1]", issues)
    if right_var is not None and left_var is None:
        _check_value(right_var, args[0], f"{path}.{op}[0]", issues)


def _check_in(args: Any, path: str, variables: dict[str, Variable], issues: list[Issue]) -> None:
    """in: [{"var": x}, [значения...]]"""
    good_form = (
        isinstance(args, list) and len(args) == 2
        and isinstance(args[0], dict) and list(args[0]) == ["var"]
        and isinstance(args[1], list) and len(args[1]) > 0
    )
    if not good_form:
        issues.append(Issue(path=path + ".in", message='Ожидается {"in": [{"var": "status"}, ["Created", "Approved"]]}'))
        return
    var = _find_var(args[0]["var"], f"{path}.in[0].var", variables, issues)
    if var is None:
        return
    for j, value in enumerate(args[1]):
        _check_value(var, value, f"{path}.in[1][{j}]", issues)


def _operand(x: Any, path: str, variables: dict[str, Variable], issues: list[Issue]) -> tuple[str, Variable | None] | None:
    """Операнд сравнения: {"var": ...} или литерал. Возвращает (тип, переменная или None)."""
    if isinstance(x, dict):
        if list(x) != ["var"]:
            issues.append(Issue(path=path, message='Операнд - это {"var": "имя"} или литерал (строка, true/false, число). Вложенные выражения здесь нельзя'))
            return None
        var = _find_var(x["var"], path + ".var", variables, issues)
        return (var.type, var) if var is not None else None
    if isinstance(x, bool):
        return ("boolean", None)
    if isinstance(x, int):
        return ("integer", None)
    if isinstance(x, str):
        return ("enum", None)
    issues.append(Issue(path=path, message=f'Недопустимый операнд {_show(x)}: нужен {{"var": ...}}, строка, true/false или целое число'))
    return None


def _check_name(name: str, path: str, issues: list[Issue]) -> None:
    if not NAME_RE.match(name):
        issues.append(Issue(path=path, message=f"Имя '{name}' не подходит: нужны латинские буквы, цифры и _, первая - буква (например Approve, is_paid)"))
    elif name in RESERVED_NAMES or name.startswith(RESERVED_PREFIXES):
        issues.append(Issue(path=path, message=f"Имя '{name}' зарезервировано в TLA+ или в компиляторе, выберите другое"))


def _find_var(name: Any, path: str, variables: dict[str, Variable], issues: list[Issue]) -> Variable | None:
    """Ищет переменную по имени. Если её нет, добавляет проблему и возвращает None."""
    if not isinstance(name, str):
        issues.append(Issue(path=path, message='Ссылка на переменную пишется так: {"var": "status"}'))
        return None
    if name not in variables:
        issues.append(Issue(path=path, message=_unknown_var_text(name, variables)))
        return None
    return variables[name]


def _check_value(var: Variable, value: Any, path: str, issues: list[Issue]) -> None:
    """Проверяет, что литерал подходит к типу и домену переменной."""
    if var.type == "enum":
        allowed = var.values or []
        if not isinstance(value, str) or value not in allowed:
            issues.append(Issue(path=path, message=f"Значение {_show(value)} не подходит для '{var.name}'. Допустимо одно из: {', '.join(allowed)}"))
    elif var.type == "boolean":
        if not isinstance(value, bool):
            issues.append(Issue(path=path, message=f"'{var.name}' - boolean, значение должно быть true или false, а не {_show(value)}"))
    else: 
        if isinstance(value, bool) or not isinstance(value, int):
            issues.append(Issue(path=path, message=f"'{var.name}' - integer, нужно целое число, а не {_show(value)}"))
        elif var.min is not None and var.max is not None and not var.min <= value <= var.max:
            issues.append(Issue(path=path, message=f"Значение {value} вне домена '{var.name}': {var.min}..{var.max}"))


def _unknown_var_text(name: str, variables: dict[str, Variable]) -> str:
    text = f"Неизвестная переменная '{name}'. Объявлены: {', '.join(variables) or 'нет'}"
    similar = difflib.get_close_matches(name, list(variables), n=1)
    if similar:
        text += f". Возможно, имелась в виду '{similar[0]}'"
    return text


def _show(value: Any) -> str:
    """Показывает значение так, как оно выглядит в JSON: true, "Created", 3."""
    return json.dumps(value, ensure_ascii=False, default=str)


def _issues_from_pydantic(error: ValidationError) -> list[Issue]:
    """Переводит ошибки Pydantic в наш формат Issue."""
    issues = []
    for err in error.errors():
        if err["type"] == "literal_error":
            expected = err["ctx"]["expected"].replace(" or ", ", ")
            message = f"Недопустимое значение {_show(err['input'])}. Допустимо: {expected}"
        else:
            message = PYDANTIC_MESSAGES.get(err["type"], err["msg"])
        issues.append(Issue(path=_format_loc(err["loc"]), message=message))
    return issues


def _format_loc(loc: tuple) -> str:
    """('transitions', 0, 'name') -> 'transitions[0].name'"""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        elif path:
            path += f".{part}"
        else:
            path = str(part)
    return path or "(весь документ)"




def validate_model(data: Any) -> tuple[BehavioralModel | None, list[Issue]]:
    """Главная функция. Возвращает (модель, []) или (None, список проблем)."""
    try:
        model = BehavioralModel.model_validate(data)
    except ValidationError as error:
        return None, _issues_from_pydantic(error)
    issues: list[Issue] = []
    variables = _check_variables(model, issues)
    _check_initial(model, variables, issues)
    _check_transitions(model, variables, issues)
    _check_properties(model, variables, issues)

    if issues:
        return None, issues
    return model, []
