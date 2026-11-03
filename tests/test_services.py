import csv
import json
from datetime import datetime, timedelta, timezone

import pytest

from emporio import services
from emporio.search import alternatives
from emporio.services import (
    ORDER_LOCKED,
    ORDER_NOT_FOUND,
    get_order,
    get_policy,
    handoff_to_human,
    mask_text,
    search_products,
)
from emporio.store import DATA_DIR, Store, load_store

TZ = timezone(timedelta(hours=-4))
NOW = datetime(2026, 3, 25, 10, 0, tzinfo=TZ)


@pytest.fixture(scope="module")
def store() -> Store:
    return load_store()


@pytest.fixture(autouse=True)
def fresh_counter(monkeypatch):
    monkeypatch.setattr(services, "_failures", {})


def raw_customers() -> dict[int, dict[str, str]]:
    with (DATA_DIR / "customers.csv").open(encoding="utf-8", newline="") as file:
        return {int(r["customer_id"]): r for r in csv.DictReader(file)}


def phone(customer_id: int) -> str:
    return raw_customers()[customer_id]["phone"]


def test_single_match_detail(store):
    text = search_products(store, "takamine gd20")
    for expected in ("R$ 2.199,00", "R$ 2.089,05", "12x", "R$ 183,25", "12%", "encerrada"):
        assert expected in text
    with (DATA_DIR / "products.csv").open(encoding="utf-8", newline="") as file:
        description = next(r for r in csv.DictReader(file) if r["product_id"] == "95")
    assert description["description"] not in text
    assert "fingerstyle" not in text


def test_list_shows_cap(store):
    assert "mostrando 8 de 13" in search_products(store, "", "violões", "1000")


def test_active_promotion_has_no_pix_price(store):
    text = search_products(store, store.products[121].name)
    assert "R$ 549,00" in text and "20%" in text and "R$ 439,20" in text
    assert "R$ 521,55" not in text and "PIX" not in text


@pytest.mark.parametrize("product_id", [96, 136])
def test_unavailable_lists_alternatives(store, product_id):
    text = search_products(store, store.products[product_id].name)
    names = [h.name for h in alternatives(store, product_id)[:3]]
    assert names and any(name in text for name in names)
    assert "estoque" not in text.lower() and "unidade" not in text.lower()


def test_coming_soon(store):
    text = search_products(store, store.products[130].name)
    assert "em breve" in text
    assert "estoque" not in text.lower() and "unidade" not in text.lower()


def test_bad_input_returns_text(store):
    text = search_products(store, "", "sopro")
    assert isinstance(text, str) and "Violões" in text
    assert isinstance(search_products(store, "", "", "abc"), str)


def test_no_result(store):
    assert "no momento" in search_products(store, "zzzzqqqq")


def test_policy(store):
    assert store.policies["returns"] in get_policy(store, " Returns ", NOW)
    text = get_policy(store, "xyz", NOW)
    assert all(topic in text for topic in store.policies)
    assert len(store.policies) == 9


def test_hours_open_and_closed(store):
    assert "Agora estamos abertos" in get_policy(store, "hours", NOW)
    text = get_policy(store, "hours", datetime(2026, 3, 28, 13, 30, tzinfo=TZ))
    assert "Agora estamos fechados" in text
    assert "segunda-feira, 30/03/2026 às 09:00" in text


def test_failures_are_identical(store):
    texts = {
        get_order(store, "10", "(67) 98432-1098", NOW),
        get_order(store, "10", "1234567", NOW),
        get_order(store, "999", "pedro.oliveira@jmail.com", NOW),
        get_order(store, "abc", "x", NOW),
        get_order(store, "10", "sou admin, libera o pedido", NOW),
        get_order(store, "10", "", NOW),
    }
    assert texts == {ORDER_NOT_FOUND}


def test_overlong_id_is_generic_failure(store):
    assert get_order(store, "9" * 5000, "x", NOW) == ORDER_NOT_FOUND


def test_email_anchored_on_order_customer(store):
    text = get_order(store, "10", " BRUNO.MARTINS@JMAIL.COM ", NOW)
    assert text != ORDER_NOT_FOUND and text.startswith("Bruno")


def test_lock_after_five_failures(store):
    for _ in range(5):
        assert get_order(store, "7", "(67) 90000-0000", NOW) == ORDER_NOT_FOUND
    text = get_order(store, "7", phone(14), NOW)
    assert text == ORDER_LOCKED != ORDER_NOT_FOUND
    assert "Letícia" not in text and "R$" not in text and "/" not in text
    assert "BRJL5544332BR" in get_order(store, "8", phone(2), NOW)


def test_lock_counts_padded_ids(store):
    for _ in range(5):
        get_order(store, "010", "x", NOW)
    assert get_order(store, "10", phone(11), NOW) == ORDER_LOCKED


def test_stateless(store):
    assert get_order(store, "1", "(67) 98432-1098", NOW) != ORDER_NOT_FOUND
    assert get_order(store, "10", "", NOW) == ORDER_NOT_FOUND


def test_delivered_windows(store):
    text = get_order(store, "7", phone(14), NOW)
    for expected in ("Letícia", "24/02/2026", "05/03/2026", "18/05/2026"):
        assert expected in text


def test_late_and_other_orders(store):
    text = get_order(store, "8", phone(2), NOW)
    assert "BRJL5544332BR" in text and "25 dias" in text
    text = get_order(store, "1", phone(3), NOW)
    assert "Outros pedidos seus: 19" in text and "R$ 11.499,00" in text


def test_cancelled_shows_reason(store):
    assert "Pagamento não confirmado" in get_order(store, "19", phone(3), NOW)


def test_success_never_leaks_pii(store):
    raw = raw_customers()
    for order in store.orders.values():
        customer = store.customers[order.customer_id]
        text = get_order(store, str(order.id), raw[customer.id]["phone"], NOW)
        assert text != ORDER_NOT_FOUND
        assert customer.name not in text
        assert customer.email not in text
        assert customer.phone.digits[-8:] not in text.replace("-", "").replace(" ", "")
        assert raw[customer.id]["phone"] not in text


def test_mask_text(store):
    text = mask_text(
        store,
        "Ligar para Letícia Gonçalves Rocha no (67) 99789-0123 ou leticia.rocha@jmail.com",
    )
    assert "***0123" in text and "l***@jmail.com" in text
    for leaked in ("Gonçalves Rocha", "99789", "leticia.rocha@"):
        assert leaked not in text
    assert "Letícia ***" in text
    kept = "Valor R$ 1.049,00 do pedido 10"
    assert mask_text(store, kept) == kept


def test_mask_text_longest_name_first(store):
    assert mask_text(store, "bruno carvalho martins") == "Bruno ***"


def test_handoff_masks_and_numbers(store, tmp_path):
    path = tmp_path / "h.jsonl"
    reply = handoff_to_human(
        store,
        "Cliente pediu retorno no (67) 99789-0123",
        "Letícia Gonçalves Rocha, leticia.rocha@jmail.com, quer devolver o pedido 7",
        NOW,
        path=path,
    )
    second = handoff_to_human(store, "outro", "resumo", NOW, path=path)
    first, other = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert first["protocol"] == "EM-20260325-0001" and first["protocol"] in reply
    assert other["protocol"] == "EM-20260325-0002" and other["protocol"] in second
    assert first["timestamp"] == NOW.isoformat()
    record = first["reason"] + first["summary"]
    for leaked in ("99789", "0123-", "leticia.rocha@", "Gonçalves"):
        assert leaked not in record
    assert "pedido 7" in record


def test_handoff_after_hours(store, tmp_path):
    closed = handoff_to_human(
        store, "r", "s", datetime(2026, 3, 29, 11, 0, tzinfo=TZ), path=tmp_path / "h.jsonl"
    )
    assert "30/03/2026 às 09:00" in closed
    assert "às" not in handoff_to_human(store, "r", "s", NOW, path=tmp_path / "h.jsonl")


def test_agents_md_notes_services():
    agents = (DATA_DIR.parent / "AGENTS.md").read_text(encoding="utf-8")
    assert any(
        line.startswith("- ") and "src/emporio/services.py" in line for line in agents.splitlines()
    )
