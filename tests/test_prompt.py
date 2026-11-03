from datetime import datetime, timedelta, timezone

from emporio.prompt import instructions

NOW = datetime(2026, 3, 25, 10, 0, tzinfo=timezone(timedelta(hours=-4)))


def test_instructions_carry_date_slogan_language_and_sections():
    text = instructions(NOW)
    assert text.startswith("Today is Wednesday, 25/03/2026, 10:00")
    assert "Sua música começa aqui." in text
    assert "PT-BR" in text
    headings = ("1. Persona (F1)", "2. Grounding (F2)", "3. Tool routing (F3)", "4. Scope (F4)")
    for heading in headings:
        assert f"\n{heading}\n" in text
