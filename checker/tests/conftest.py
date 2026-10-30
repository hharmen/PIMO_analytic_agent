import pytest


@pytest.fixture
def model():
    """Конечный счётчик: 0 -> 1 -> 2, без LLM и внешних сервисов."""
    return {
        "variables": [{"name": "x", "type": "integer", "min": 0, "max": 2}],
        "initial": {"x": 0},
        "transitions": [{
            "name": "Advance", "guard": {"lt": [{"var": "x"}, 2]},
            "effects": [{"inc": ["x", 1]}], "source_ref": "REQ-STEP",
        }],
        "properties": [{
            "id": "Safe", "type": "invariant",
            "expression": {"le": [{"var": "x"}, 2]}, "source_ref": "REQ-SAFE",
        }],
    }
