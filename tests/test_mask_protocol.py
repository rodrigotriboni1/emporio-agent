import json
from datetime import datetime, timedelta, timezone

import pytest

from emporio.services import handoff_to_human, mask_text
from emporio.store import Store, load_store

NOW = datetime(2026, 3, 25, 10, 0, tzinfo=timezone(timedelta(hours=-4)))


@pytest.fixture(scope="module")
def store() -> Store:
    return load_store()


@pytest.mark.parametrize("text", ["(protocolo EM-20260325-0002)", "Protocolo: EM-20260325-0001."])
def test_protocol_is_left_as_is(store, text):
    assert mask_text(store, text) == text


def test_phone_next_to_protocol_is_masked(store):
    masked = mask_text(store, "EM-20260325-0001 (67) 99789-0123")
    assert masked == "EM-20260325-0001 ***0123"
    assert "99789" not in masked


def test_email_next_to_protocol_is_masked(store):
    masked = mask_text(store, "Protocolo EM-20260325-0001, e-mail leticia.rocha@jmail.com")
    assert masked == "Protocolo EM-20260325-0001, e-mail l***@jmail.com"


def test_handoff_summary_keeps_protocol_and_masks_phone(store, tmp_path):
    path = tmp_path / "h.jsonl"
    summary = "Retomar EM-20260324-0003 e ligar no (67) 99789-0123"
    handoff_to_human(store, "retorno", summary, NOW, path=path)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["summary"] == "Retomar EM-20260324-0003 e ligar no ***0123"
