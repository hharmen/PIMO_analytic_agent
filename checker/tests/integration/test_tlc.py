"""Реальный Java/TLC: запускать из checker, python -m pytest tests -q."""
import pytest
import json
from pathlib import Path

from app.checker import check_behavior
from app.schemas import Status


@pytest.mark.parametrize("filename,expected", [
    ("model_broken.json", Status.PROPERTY_VIOLATED),
    ("model_fixed.json", Status.PROPERTY_HOLDS),
])
def test_examples(filename, expected):
    path = Path(__file__).resolve().parents[2] / "examples" / filename
    result = check_behavior(json.loads(path.read_text(encoding="utf-8")))
    assert result.status == expected, result.model_dump()


@pytest.mark.parametrize("kind,target,expected", [
    ("invariant", 2, Status.PROPERTY_HOLDS),
    ("invariant", 1, Status.PROPERTY_VIOLATED),
    ("forbidden_state", 2, Status.PROPERTY_VIOLATED),
    ("reachable", 2, Status.PROPERTY_HOLDS),
    ("reachable", 0, Status.PROPERTY_HOLDS),
])
def test_property_semantics(model, kind, target, expected):
    prop = model["properties"][0]
    prop.update(type=kind, expression={"le" if kind == "invariant" else "eq": [{"var": "x"}, target]})
    result = check_behavior(model)
    assert result.status == expected, result.model_dump()
    item = result.results[0]
    if kind == "reachable":
        assert item.witness.steps[-1].state == {"x": target}
    elif expected == Status.PROPERTY_VIOLATED:
        steps = item.counterexample.steps
        assert [s.state["x"] for s in steps] == [0, 1, 2]
        assert [s.transition for s in steps] == [None, "Advance", "Advance"]
        assert item.related_requirements == ["REQ-SAFE", "REQ-STEP"]
    else:
        assert item.statistics.distinct_states == 3


def test_unreachable_goal(model):
    model["transitions"][0]["guard"] = {"lt": [{"var": "x"}, 1]}
    model["properties"][0].update(type="reachable", expression={"eq": [{"var": "x"}, 2]})
    assert check_behavior(model).status == Status.PROPERTY_VIOLATED


@pytest.mark.parametrize("normal_end", [False, True])
def test_deadlock_and_normal_termination(model, normal_end):
    prop = {"id": "NoDeadlock", "type": "deadlock_free"}
    if normal_end:
        prop["final_states"] = {"eq": [{"var": "x"}, 2]}
    model["properties"] = [prop]
    result = check_behavior(model)
    assert result.status == (Status.PROPERTY_HOLDS if normal_end else Status.PROPERTY_VIOLATED), result.model_dump()
    if not normal_end:
        assert result.results[0].counterexample.steps[-1].state == {"x": 2}


def test_domain_overflow_is_model_invalid(model):
    model["transitions"][0].pop("guard")
    result = check_behavior(model)
    assert result.status == Status.MODEL_INVALID, result.model_dump()
    assert result.results[0].counterexample.steps[-1].state == {"x": 3}
    assert result.errors[0].path == "transitions[0].guard"


def test_state_limit_never_means_holds(model, monkeypatch):
    monkeypatch.setattr("app.checker.MAX_STATES", 2)
    result = check_behavior(model)
    assert result.status == Status.STATE_LIMIT_REACHED, result.model_dump()


def test_separate_results_and_selection(model):
    model["properties"].append({"id": "Goal", "type": "forbidden_state", "expression": {"eq": [{"var": "x"}, 2]}})
    result = check_behavior(model)
    assert [r.status for r in result.results] == [Status.PROPERTY_HOLDS, Status.PROPERTY_VIOLATED]
    assert result.status == Status.PROPERTY_VIOLATED
    selected = check_behavior(model, ["Safe"])
    assert selected.status == Status.PROPERTY_HOLDS
    assert [r.property_id for r in selected.results] == ["Safe"]
