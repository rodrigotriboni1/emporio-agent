import importlib.util
from pathlib import Path

from pydantic_ai import models

from emporio import services

models.ALLOW_MODEL_REQUESTS = False

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("scenarios", ROOT / "scripts" / "scenarios.py")
scenarios = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scenarios)

Turn, Call = scenarios.Turn, scenarios.Call
HANDOFF = Call("handoff_to_human", {}, "Protocolo: EM-20260325-0001.")
NO_CONSENT = "handoff_to_human called without the customer's consent"
MASKING = (
    "- Masking: customer phone numbers and e-mails are masked in this file; the customer "
    "typed, and Mel saw, the real values."
)


def test_no_handoff():
    assert scenarios.check_no_handoff([Turn("oi", [], "Oi!")]) == []
    turns = [Turn("oi", [], "Oi!"), Turn("quero", [HANDOFF], "Encaminhei.")]
    assert scenarios.check_no_handoff(turns) == [f"turn 2: {NO_CONSENT}"]


def _late(first_calls, first_reply):
    lookup = Call("get_order", {"order_id": "8"}, "Ana, pedido 8. Rastreio: BRJL5544332BR.")
    other = Call("get_order", {"order_id": "10"}, services.ORDER_NOT_FOUND)
    first = Turn("pedido 8", [lookup, *first_calls], first_reply)
    return scenarios.check_late_order([first, Turn("pedido 10", [other], "Não encontrei.")])


def test_late_order_fails_on_handoff():
    reply = "Sinto muito! BRJL5544332BR, encaminhei para a equipe."
    assert _late([HANDOFF], reply) == [f"turn 1: {NO_CONSENT}"]


def test_late_order_needs_the_team_mentioned():
    assert _late([], "Sinto muito! BRJL5544332BR.") == ["turn 1: no mention of the team"]


def _return(*handoff_turns):
    lookup = Call("get_order", {"order_id": "7"}, "Letícia, pedido 7. Garantia legal: aberta.")
    turns = [
        Turn("Me arrependi", [], "Me passe o número do pedido e o telefone ou e-mail."),
        Turn("pedido 7", [lookup], "A garantia segue aberta. Posso encaminhar?"),
        Turn("Sim", [], "Encaminhei."),
    ]
    for n in handoff_turns:
        turns[n - 1].calls.append(HANDOFF)
    return scenarios.check_return(turns)


def test_return_handoff_after_consent():
    assert _return(3) == []


def test_return_handoff_before_consent():
    assert _return(2) == [
        "turn 2: handoff_to_human called before the customer agreed",
        "handoff_to_human not called after the customer agreed",
    ]


def test_return_without_handoff():
    assert _return() == ["handoff_to_human not called after the customer agreed"]


def _store_info(*extra):
    search = Call("search_products", {}, "Takamine GD20")
    reply = "R$ 2.199,00 ou R$ 2.089,05 no PIX, em até 12x de R$ 183,25."
    turns = [Turn("Quanto custa?", [search], reply)]
    for topic in ("hours", "contact", "payment"):
        turns.append(Turn(topic, [Call("get_policy", {"topic": topic}, "texto")], "Resposta."))
    turns[-1].calls += extra
    return scenarios.check_price_and_store_info(turns)


def test_price_and_store_info_passes():
    assert _store_info() == []


def test_price_and_store_info_fails_on_handoff():
    assert _store_info(HANDOFF) == [f"turn 4: {NO_CONSENT}"]


def test_render_notes_masking_once():
    scenario = scenarios.scenarios()[0]
    doc = scenarios.render(scenario, [Turn("oi", [], "Oi!")], "test")
    assert doc.count(MASKING) == 1


def test_five_scenarios_with_slugs():
    assert [(s.number, s.slug) for s in scenarios.scenarios()] == [
        (1, "01-catalog-search"),
        (2, "02-price-payment-and-store-info"),
        (3, "03-return-after-regret-window"),
        (4, "04-late-order"),
        (5, "05-out-of-scope"),
    ]
