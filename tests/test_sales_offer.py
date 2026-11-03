import importlib.util
from pathlib import Path

from pydantic_ai import models

models.ALLOW_MODEL_REQUESTS = False

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("scenarios", ROOT / "scripts" / "scenarios.py")
scenarios = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scenarios)

Turn = scenarios.Turn
OFFER = "Quer que eu encaminhe você para o nosso time para fechar a compra?"
NO_INTENT = "sales offer without buying intent"
REPEATED = "sales offer repeated"


def test_one_offer_after_buying_intent():
    turns = [Turn("Quero comprar o Takamine GD20", [], OFFER)]
    assert scenarios.check_sales_offer(turns) == []


def test_offer_without_buying_intent():
    turns = [Turn("Que horas a loja abre?", [], OFFER)]
    assert scenarios.check_sales_offer(turns) == [f"turn 1: {NO_INTENT}"]


def test_offer_repeated():
    turns = [
        Turn("Como faço para comprar?", [], OFFER),
        Turn("Dá pra reservar um pra mim?", [], "Posso finalizar a compra com o time?"),
    ]
    assert scenarios.check_sales_offer(turns) == [f"turn 2: {REPEATED}"]


def test_no_offer():
    turns = [Turn("Que horas a loja abre?", [], "Abrimos às 09:00.")]
    assert scenarios.check_sales_offer(turns) == []


def test_buying_intent_patterns():
    for text in [
        "Quero comprar o Takamine GD20",
        "Como faço para comprar?",
        "Dá pra reservar um pra mim?",
    ]:
        assert scenarios.BUYING_INTENT.search(text), text
    for text in scenarios.scenarios()[1].messages:
        assert not scenarios.BUYING_INTENT.search(text), text


def test_old_scenario_2_transcript_fails():
    # The three offers from examples/02-… before the prompt change.
    replies = [
        "Valor R$ 2.199,00. Quer que eu encaminhe você para o nosso time para fechar a compra?",
        "Agora estamos abertos. Precisa de mais alguma coisa?",
        "Se quiser, posso já encaminhar você ao nosso time para fechar a compra do Takamine GD20.",
        "Quer que eu encaminhe você ao time para fechar a compra? 🙂",
    ]
    messages = scenarios.scenarios()[1].messages
    turns = [Turn(text, [], reply) for text, reply in zip(messages, replies, strict=True)]
    assert scenarios.check_sales_offer(turns) == [
        f"turn 1: {NO_INTENT}",
        f"turn 3: {NO_INTENT}",
        f"turn 3: {REPEATED}",
        f"turn 4: {NO_INTENT}",
        f"turn 4: {REPEATED}",
    ]
    assert scenarios.check_price_and_store_info(turns) != []
