import subprocess

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.checker import check_behavior
from app.runner import run_tlc
from app.schemas import Status
from app.validator import validate_model


@pytest.mark.parametrize("change", [
    lambda m: m["initial"].update(x=True),
    lambda m: m["transitions"][0].update(guard={"var": "missing"}),
    lambda m: m.update(properties=[]),
    lambda m: m["transitions"][0]["effects"].append({"set": ["x", 1]}),
])
def test_invalid_model_never_starts_java(model, monkeypatch, change):
    def unexpected(*args):
        pytest.fail("Невалидная модель дошла до TLC")
    monkeypatch.setattr("app.checker.run_tlc", unexpected)
    change(model)
    result = check_behavior(model)
    assert result.status == Status.MODEL_INVALID
    assert result.errors


def test_unknown_property(model):
    assert check_behavior(model, ["missing"]).status == Status.MODEL_INVALID


def test_timeout_never_means_holds(model, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=b"partial output")
    monkeypatch.setattr("app.runner.subprocess.run", timeout)
    result = check_behavior(model)
    assert result.status == Status.TIMEOUT


def test_missing_java(model, monkeypatch):
    monkeypatch.setattr("app.runner.JAVA_BIN", "/nonexistent/java")
    assert check_behavior(model).status == Status.ENGINE_ERROR


def test_missing_jar(monkeypatch):
    monkeypatch.setattr("app.runner.TLA2TOOLS_JAR", "/nonexistent/tla.jar")
    assert run_tlc("", "").error


def test_http_contract(model, monkeypatch):
    monkeypatch.setattr("app.runner.JAVA_BIN", "/nonexistent/java")
    with TestClient(app) as client:
        assert client.post("/check", json={"model": model, "timeout_seconds": 0}).status_code == 422
        response = client.post("/check", json={"model": model})
        assert response.status_code == 200
        assert response.json()["status"] == "ENGINE_ERROR"


def test_schema_endpoint():
    with TestClient(app) as client:
        response = client.get("/schema")
        assert response.status_code == 200
        parsed, issues = validate_model(response.json()["example"])
        assert parsed is not None and not issues
