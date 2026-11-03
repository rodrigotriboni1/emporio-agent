import importlib.util
from pathlib import Path

from pydantic_ai import models

models.ALLOW_MODEL_REQUESTS = False

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("scenarios", ROOT / "scripts" / "scenarios.py")
scenarios = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scenarios)

Turn = scenarios.Turn


def test_one_emoji_anywhere_passes():
    for reply in [
        "Oi! Sua música começa aqui. 🎵\n\nPosso ajudar?",
        "Oi!\nPosso ajudar? 😊",
        "Oi!",
    ]:
        assert scenarios.check_emoji_count([Turn("oi", [], reply)]) == [], reply


def test_two_emoji_fail():
    turns = [Turn("oi", [], "Oi! 🎵"), Turn("e aí?", [], "Claro 😊\nAbraço 🎸")]
    assert scenarios.check_emoji_count(turns) == ["turn 2: 2 emoji in one reply"]


def test_scenarios_use_the_count_check():
    assert scenarios.check_emoji_count in scenarios.COMMON_CHECKS
    assert scenarios.check_emoji not in scenarios.COMMON_CHECKS
