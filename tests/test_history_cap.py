from datetime import datetime, timedelta, timezone

from pydantic_ai import models
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from emporio.agent import HISTORY_TOO_LONG, MAX_HISTORY_CHARS, Deps, agent

models.ALLOW_MODEL_REQUESTS = False

DEPS = Deps(now=lambda: datetime(2026, 3, 25, 10, 0, tzinfo=timezone(timedelta(hours=-4))))


def run(history):
    calls = []

    def model(messages, info: AgentInfo) -> ModelResponse:
        calls.append(info)
        return ModelResponse(parts=[TextPart("ok")])

    with agent.override(model=FunctionModel(model)):
        result = agent.run_sync("oi", message_history=history, deps=DEPS)
    return result.output, len(calls)


def chat(turns: int, size: int) -> list:
    history = []
    for _ in range(turns):
        history.append(ModelRequest(parts=[UserPromptPart("a" * size)]))
        history.append(ModelResponse(parts=[TextPart("b" * size)]))
    return history


def test_long_chat_history_is_capped_without_model_call():
    history = chat(turns=11, size=1999)
    assert 2 * 11 * 1999 > MAX_HISTORY_CHARS
    assert run(history) == (HISTORY_TOO_LONG, 0)


def test_large_tool_return_counts_toward_the_cap():
    history = [
        ModelRequest(parts=[UserPromptPart("quero um violão")]),
        ModelResponse(parts=[ToolCallPart("search_products", {"query": "violão"}, "c1")]),
        ModelRequest(parts=[ToolReturnPart("search_products", "x" * 40_001, "c1")]),
        ModelResponse(parts=[TextPart("Temos estes.")]),
    ]
    assert run(history) == (HISTORY_TOO_LONG, 0)


def test_history_under_the_cap_reaches_the_model():
    assert run(chat(turns=3, size=1999)) == ("ok", 1)
