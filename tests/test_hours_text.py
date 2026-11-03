from datetime import datetime, time, timedelta, timezone

import pytest

from emporio.domain import closes_at
from emporio.services import get_policy
from emporio.store import load_store

TZ = timezone(timedelta(hours=-4))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=TZ)


@pytest.fixture(scope="module")
def store():
    return load_store()


@pytest.mark.parametrize(
    ("now", "ending"),
    [
        (at(25, 10), "Agora estamos abertos até as 18:00."),
        (at(27, 17, 59), "Agora estamos abertos até as 18:00."),
        (at(27, 18), "Agora estamos fechados. Próxima abertura: sábado, 28/03/2026 às 09:00."),
        (at(28, 10), "Agora estamos abertos até as 13:00."),
        (at(28, 12, 59), "Agora estamos abertos até as 13:00."),
        (
            at(28, 13),
            "Agora estamos fechados. Próxima abertura: segunda-feira, 30/03/2026 às 09:00.",
        ),
        (
            at(29, 11),
            "Agora estamos fechados. Próxima abertura: segunda-feira, 30/03/2026 às 09:00.",
        ),
    ],
)
def test_hours_text(store, now, ending):
    text = get_policy(store, "hours", now)
    assert text.endswith(ending)
    assert text.count("Agora estamos") == 1


def test_open_text_has_no_next_opening(store):
    assert "Próxima abertura" not in get_policy(store, "hours", at(25, 10))


def test_closes_at():
    assert closes_at(at(25, 10)) == time(18)
    assert closes_at(at(28, 12, 59)) == time(13)
    assert closes_at(at(28, 13)) is None
    assert closes_at(at(25, 8, 59)) is None
    assert closes_at(at(29, 11)) is None
