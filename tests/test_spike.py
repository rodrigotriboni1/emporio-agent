import importlib.util
from pathlib import Path

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from emporio import agent as agent_module
from emporio import services

models.ALLOW_MODEL_REQUESTS = False

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("spike", ROOT / "scripts" / "spike.py")
spike = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spike)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(services, "HANDOFFS_PATH", tmp_path / "handoffs.jsonl")
    monkeypatch.setattr(services, "_failures", {})


def test_turn_with_expected_tool_and_valid_args_is_measured():
    def model(messages, info) -> ModelResponse:
        if len(messages) == 1:
            call = ToolCallPart("get_policy", {"topic": "hours"})
            return ModelResponse(
                parts=[call], usage=RequestUsage(input_tokens=100, output_tokens=7)
            )
        return ModelResponse(
            parts=[TextPart("9h")], usage=RequestUsage(input_tokens=150, output_tokens=3)
        )

    name, text, check = next(p for p in spike.prompts() if p[0] == "hours")
    row, result = spike.run_turn(FunctionModel(model), name, text, check)
    assert result is not None
    assert (row.called, row.args_valid) == (True, True)
    assert (row.requests, row.input_tokens, row.output_tokens) == (2, 250, 10)
    assert row.max_output == 7
    assert row.cost is None and spike._cost(row.cost) == "n/a"
    assert row.error is None


def test_stopped_turn_passes_and_restores_limit():
    def loop(messages, info) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart("get_policy", {"topic": "hours"})])

    assert spike.stopped_turn(FunctionModel(loop)) == (True, True)
    assert agent_module.MAX_REQUESTS == 10


def test_order_follow_up_without_get_order_on_turn_two_is_wrong():
    email = "someone@example.com"

    def model(messages, info) -> ModelResponse:
        if len(messages) == 1:
            args = {"order_id": "#8", "phone_or_email": " Someone@Example.com "}
            return ModelResponse(parts=[ToolCallPart("get_order", args)])
        return ModelResponse(parts=[TextPart("Seu pedido está a caminho.")])

    first, second = spike.order_follow_up(FunctionModel(model), email)
    assert (first.called, first.args_valid) == (True, True)
    assert (second.called, second.args_valid) == (False, False)
    assert second.error is None


def _summary(model, accuracy, latency, cost, ok=True):
    return spike.Summary(model, accuracy, 1.0, latency, cost, history_valid=ok, stop_ok=ok)


def test_default_choice_rule():
    summaries = [
        _summary("a", 1.0, 5.0, 0.01, ok=False),
        _summary("b", 0.9, 1.0, 0.01),
        _summary("c", 0.9, 1.0, 0.005),
        _summary("d", 0.9, 2.0, 0.001),
    ]
    assert spike.choose_default(summaries).model == "c"
    assert spike.choose_default([_summary("a", 1.0, 1.0, None, ok=False)]) is None


@pytest.mark.parametrize(
    ("largest", "expected"), [(0, 1024), (300, 1024), (600, 1536), (1024, 2048)]
)
def test_max_tokens_rule(largest, expected):
    assert spike.choose_max_tokens(largest) == expected
