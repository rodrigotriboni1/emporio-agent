import builtins
import os

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from emporio import cli
from emporio.agent import agent

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.delenv("EMPORIO_NOW", raising=False)
    monkeypatch.delenv("PYDANTIC_AI_NO_BANNER", raising=False)


def script(monkeypatch, lines, end=EOFError):
    feed = iter(lines)

    def fake_input(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise end from None

    monkeypatch.setattr(builtins, "input", fake_input)


def test_error_becomes_generic_message_and_history_carries(monkeypatch, capsys):
    seen = []

    def model(messages, info) -> ModelResponse:
        seen.append(messages)
        if len(seen) == 1:
            raise RuntimeError("provider exploded")
        return ModelResponse(parts=[TextPart(f"resposta {len(seen)}")])

    script(monkeypatch, ["primeira pergunta", "", "segunda", "terceira"])
    with agent.override(model=FunctionModel(model)):
        cli.main()
    out, err = capsys.readouterr()
    assert cli.GENERIC_ERROR in out
    assert "provider exploded" in err and "provider exploded" not in out
    assert "[error]" in err
    assert "Mel: resposta 2" in out and "Mel: resposta 3" in out
    # The failed turn is dropped; the answered one is carried into the next call.
    assert "primeira pergunta" not in str(seen[1])
    assert "segunda" in str(seen[2]) and "resposta 2" in str(seen[2])
    assert "PYDANTIC_AI_NO_BANNER" in os.environ


@pytest.mark.parametrize("end", [EOFError, KeyboardInterrupt])
def test_exits_normally_at_the_prompt(monkeypatch, capsys, end):
    script(monkeypatch, [], end=end)
    assert cli.main() is None
    assert "Ctrl+D" in capsys.readouterr().out


def test_ctrl_c_during_a_turn_exits_normally(monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(agent, "run_sync", interrupted)
    script(monkeypatch, ["oi"])
    assert cli.main() is None


def test_invalid_clock_stops_startup(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "amanha")
    with pytest.raises(SystemExit) as stop:
        cli.main()
    assert "EMPORIO_NOW" in str(stop.value.code) and "amanha" in str(stop.value.code)
