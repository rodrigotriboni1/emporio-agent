import os
from datetime import UTC, datetime, timedelta, timezone

import pytest

from emporio import config

TZ = timezone(timedelta(hours=-4))


@pytest.mark.parametrize("value", [None, ""])
def test_clock_default(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("EMPORIO_NOW", raising=False)
    else:
        monkeypatch.setenv("EMPORIO_NOW", value)
    assert config.clock()().isoformat() == "2026-03-25T10:00:00-04:00"


def test_clock_now_is_real_time_at_minus_four(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "now")
    now = config.clock()()
    assert now.utcoffset() == timedelta(hours=-4)
    assert abs(now - datetime.now(UTC)) < timedelta(seconds=5)


def test_clock_explicit_value_round_trips(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-04-01T18:30-04:00")
    assert config.clock()() == datetime(2026, 4, 1, 18, 30, tzinfo=TZ)


@pytest.mark.parametrize("value", ["amanha", "2026-03-25T10:00"])
def test_clock_invalid_value_names_the_variable(monkeypatch, value):
    monkeypatch.setenv("EMPORIO_NOW", value)
    with pytest.raises(ValueError, match="EMPORIO_NOW") as error:
        config.clock()
    assert value in str(error.value)


def test_load_dotenv(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n\nNEW_KEY = value\nDOUBLE=\"quoted\"\nSINGLE='quoted'\nKEPT=from_file\n"
    )
    for key in ("NEW_KEY", "DOUBLE", "SINGLE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KEPT", "from_env")
    config.load_dotenv(path)
    assert os.environ["NEW_KEY"] == "value"
    assert os.environ["DOUBLE"] == "quoted"
    assert os.environ["SINGLE"] == "quoted"
    assert os.environ["KEPT"] == "from_env"
    assert not any(key.startswith("#") for key in os.environ)


def test_load_dotenv_missing_file_does_nothing(tmp_path):
    before = dict(os.environ)
    config.load_dotenv(tmp_path / "missing.env")
    assert dict(os.environ) == before
