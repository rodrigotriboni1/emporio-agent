import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from emporio import services
from emporio.agent import INPUT_TOO_LONG, TURN_LIMIT_REACHED, Deps, agent

models.ALLOW_MODEL_REQUESTS = False

TZ = timezone(timedelta(hours=-4))
DEPS = Deps(now=lambda: datetime(2026, 3, 25, 10, 0, tzinfo=TZ))
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(services, "HANDOFFS_PATH", tmp_path / "handoffs.jsonl")
    monkeypatch.setattr(services, "_failures", {})


def counting(respond):
    calls = []

    def model(messages, info: AgentInfo) -> ModelResponse:
        calls.append(info)
        return respond(messages, info)

    return FunctionModel(model), calls


def reply(messages, info) -> ModelResponse:
    return ModelResponse(parts=[TextPart("ok")])


@pytest.mark.parametrize("model", [None, "openrouter:google/gemini-3.8-flash"])
def test_imports_without_api_key(model):
    env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "MODEL")}
    if model:
        env["MODEL"] = model
    run = subprocess.run([sys.executable, "-c", "import emporio.agent"], env=env, cwd=ROOT)
    assert run.returncode == 0


def test_exactly_the_four_tools_with_spec_parameters():
    model, calls = counting(reply)
    with agent.override(model=model):
        agent.run_sync("oi", deps=DEPS)
    tools = {t.name: t.parameters_json_schema for t in calls[0].function_tools}
    expected = {
        "search_products": {"query", "category", "max_price"},
        "get_policy": {"topic"},
        "get_order": {"order_id", "phone_or_email"},
        "handoff_to_human": {"reason", "summary"},
    }
    assert {name: set(schema["properties"]) for name, schema in tools.items()} == expected
    for schema in tools.values():
        assert all(p["type"] == "string" for p in schema["properties"].values())
        assert "customer" not in str(schema) and "ctx" not in str(schema)


def test_tools_run_end_to_end_under_test_model():
    with agent.override(model=TestModel()):
        result = agent.run_sync("oi", deps=DEPS)
    assert result.output
    assert services.HANDOFFS_PATH.exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert "handoffs.jsonl" not in status.stdout


@pytest.mark.parametrize(
    ("prompt", "history", "blocked"),
    [
        ("a" * 2001, None, True),
        ("a" * 2000, None, False),
        (None, [ModelRequest(parts=[UserPromptPart("a" * 2001)])], True),
    ],
)
def test_input_cap(prompt, history, blocked):
    model, calls = counting(reply)
    with agent.override(model=model):
        result = agent.run_sync(prompt, message_history=history, deps=DEPS)
    if blocked:
        assert result.output == INPUT_TOO_LONG
        assert calls == []
    else:
        assert result.output == "ok"
        assert len(calls) == 1


def test_request_limit_ends_turn_with_fixed_text():
    def loop(messages, info) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart("get_policy", {"topic": "hours"})])

    model, calls = counting(loop)
    with agent.override(model=model):
        result = agent.run_sync("que horas abre?", deps=DEPS)
    assert result.output == TURN_LIMIT_REACHED
    assert len(calls) == 10
    assert "3321-4500" in TURN_LIMIT_REACHED
    assert "segunda a sexta das 9h às 18h" in TURN_LIMIT_REACHED
    assert "sábados das 9h às 13h" in TURN_LIMIT_REACHED


def test_tool_log_masks_then_truncates(capsys):
    reason = "Lucas Mendes da Silva, (67) 99812-3456, lucas.mendes@jmail.com"
    summary = "x" * 1000

    def handoff(messages, info) -> ModelResponse:
        if len(messages) == 1:
            args = {"reason": reason, "summary": summary}
            return ModelResponse(parts=[ToolCallPart("handoff_to_human", args)])
        return ModelResponse(parts=[TextPart("ok")])

    with agent.override(model=FunctionModel(handoff)):
        agent.run_sync("quero falar com alguém", deps=DEPS)
    line = next(x for x in capsys.readouterr().err.splitlines() if x.startswith("[tool]"))
    assert "handoff_to_human" in line
    assert "Lucas ***" in line and "l***@jmail.com" in line
    for secret in ("Mendes da Silva", "99812-3456", "lucas.mendes@jmail.com"):
        assert secret not in line
    assert "x" * 256 in line and "x" * 257 not in line


def test_usage_line_after_run(capsys):
    with agent.override(model=FunctionModel(reply)):
        agent.run_sync("oi", deps=DEPS)
    err = capsys.readouterr().err
    assert re.search(r"\[turn\] requests=\d+ input_tokens=\d+ output_tokens=\d+", err)
