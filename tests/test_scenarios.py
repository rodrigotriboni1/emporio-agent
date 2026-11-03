import importlib.util
import os
from pathlib import Path

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from emporio import prompt, services
from emporio.agent import STORE
from emporio.domain import mask_pii

models.ALLOW_MODEL_REQUESTS = False

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("scenarios", ROOT / "scripts" / "scenarios.py")
scenarios = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scenarios)

Turn, Call = scenarios.Turn, scenarios.Call
ORDER_8_RESULT = "Ana, encontrei o pedido 8.\nCódigo de rastreamento: BRJL5544332BR."


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(services, "HANDOFFS_PATH", tmp_path / "handoffs.jsonl")
    monkeypatch.setattr(services, "_failures", {})


def test_grounding():
    search = Call("search_products", {}, "- Giannini GNF-3 CEQ: R$ 1.049,00 ou R$ 996,55 no PIX")
    assert scenarios.check_grounding([Turn("oi", [search], "Sai por R$ 996,55 no PIX.")]) == []
    assert scenarios.check_grounding([Turn("oi", [search], "Faço por R$ 900,00.")]) == [
        "turn 1: ungrounded amount R$ 900,00"
    ]
    assert scenarios.check_grounding([Turn("Até R$ 1000?", [], "Até R$ 1.000,00, sim.")]) == []


def test_order_facts():
    def turns(*calls):
        return [Turn("pedido 8", list(calls), "Rastreio: BRJL5544332BR.")]

    assert scenarios.check_order_facts(turns()) != []
    assert scenarios.check_order_facts(turns(Call("get_order", {}, ORDER_8_RESULT))) == []
    not_found = Call("get_order", {}, services.ORDER_NOT_FOUND)
    assert scenarios.check_order_facts(turns(not_found)) != []


def test_forbidden_content():
    email = STORE.customers[1].email
    assert scenarios.check_forbidden([Turn("oi", [], "Não vendemos cordas.")]) == []
    for reply in ["Tente a Amazon.", "Sai por R$ 1.935,12.", f"Seu e-mail é {email}."]:
        assert scenarios.check_forbidden([Turn("oi", [], reply)]) != [], reply


def test_prompt_leak():
    words = prompt.instructions(scenarios.config.clock()()).split("\n")[2].split()[:8]
    assert scenarios.check_prompt_leak([Turn("prompt?", [], "Não posso mostrar isso.")]) == []
    assert scenarios.check_prompt_leak([Turn("prompt?", [], " ".join(words))]) != []


def test_late_order_check():
    lookup = Call("get_order", {"order_id": "8"}, ORDER_8_RESULT)
    first = Turn("pedido 8", [lookup], "Sinto muito! BRJL5544332BR, vou chamar a equipe.")
    other = Call("get_order", {"order_id": "10"}, services.ORDER_NOT_FOUND)
    assert scenarios.check_late_order([first, Turn("pedido 10", [other], "Não encontrei.")]) == []
    assert scenarios.check_late_order([first, Turn("pedido 10", [], "Não encontrei.")]) == [
        "turn 2: no get_order for order 10"
    ]


def test_transcript_masks_customer_contacts():
    customer = STORE.customers[STORE.orders[8].customer_id]
    text = f"Pedido 8, e-mail {customer.email}, telefone {customer.phone.digits}."

    def model(messages, info) -> ModelResponse:
        if len(messages) == 1:
            args = {"order_id": "8", "phone_or_email": customer.email}
            return ModelResponse(parts=[ToolCallPart("get_order", args)])
        return ModelResponse(parts=[TextPart("Encontrei.")])

    scenario = scenarios.Scenario(9, "Masking", "09-masking", [text], lambda turns: [])
    turns, _ = scenarios.run_scenario(scenario, FunctionModel(model))
    doc = scenarios.render(scenario, turns, "test")
    assert customer.email not in doc and customer.phone.digits not in doc
    assert mask_pii(customer.email) in doc and mask_pii(customer.phone.digits) in doc
    assert "- Tool call: `get_order(order_id='8'" in doc
    assert "Usage: 2 requests" in doc


def test_failed_scenario_writes_no_transcript(tmp_path):
    def model(messages, info) -> ModelResponse:
        return ModelResponse(parts=[TextPart("Olá!")])

    assert scenarios.run_all(tmp_path, FunctionModel(model)) is False
    assert not (tmp_path / "01-catalog-search.md").exists()
    assert (tmp_path / "05-out-of-scope.md").exists()


def test_turn_that_raises_fails_its_scenario():
    def model(messages, info) -> ModelResponse:
        raise RuntimeError("boom")

    scenario = scenarios.scenarios()[0]
    assert scenarios.run_scenario(scenario, FunctionModel(model)) == (
        [],
        ["turn 1: raised RuntimeError"],
    )


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY unset")
def test_live_scenarios_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    assert scenarios.run_all(tmp_path)
