import dataclasses
from decimal import Decimal

import pytest

from emporio.domain import Availability
from emporio.search import SearchHit, alternatives, normalize, parse_price, search
from emporio.store import Store, load_store


@pytest.fixture(scope="module")
def store() -> Store:
    return load_store()


def ids(result):
    return {h.id for h in result.items}


def test_violoes_under_1000(store):
    result = search(store, query="violões", max_price="R$ 1000")
    assert result.total == 13
    assert len(result.items) == 8
    assert search(store, category="violão", max_price="1000") == result
    assert ids(search(store, query="gnf-3", max_price="1000")) == {101}
    assert search(store, query="gnf-3", max_price="990").total == 0


def test_violoes_under_1000_full_set(store, monkeypatch):
    # Lift the cap of 8 so every matching id is visible.
    monkeypatch.setattr("emporio.search._CAP", 100)
    result = search(store, query="violões", max_price="R$ 1000")
    assert ids(result) == {81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 101, 107, 112}


@pytest.mark.parametrize("query", ["takamine gd-20", "GD 20", "gd20"])
def test_model_number_spacing(store, query):
    assert ids(search(store, query=query)) == {95}


def test_martin_d28(store):
    assert ids(search(store, query="martin d28")) == {93, 108}


def test_category_spellings(store):
    results = [
        search(store, query="VIOLAO"),
        search(store, query="violoes"),
        search(store, query="violão"),
        search(store, category="Violões"),
    ]
    assert len({r.total for r in results}) == 1
    assert all(h.category == "Violões" for r in results for h in r.items)


@pytest.mark.parametrize("text", ["1000", "1.000", "R$ 1.000,00", "R$1000"])
def test_parse_price_thousand(text):
    assert parse_price(text) == Decimal("1000")


def test_parse_price_other_values(store):
    assert parse_price("999,90") == Decimal("999.90")
    assert parse_price("") is None
    for text in ["abc", "-5"]:
        with pytest.raises(ValueError, match=text):
            parse_price(text)
    with pytest.raises(ValueError):
        search(store, max_price="abc")


def test_typo_fallback(store):
    assert ids(search(store, query="taylr")) == {94, 106}
    assert ids(search(store, query="martn d28")) == {93, 108}


@pytest.mark.parametrize(
    ("query", "product_id", "status"),
    [
        ("giannini gf-3d", 96, Availability.OUT_OF_STOCK),
        ("shelby sn-7c", 113, Availability.DISCONTINUED),
        ("kala ka-abp-ctg", 130, Availability.COMING_SOON),
        ("ibanez bass 2x", 136, Availability.DISCONTINUED),
    ],
)
def test_query_returns_any_status(store, query, product_id, status):
    hits = {h.id: h for h in search(store, query=query).items}
    assert hits[product_id].availability == status


def test_unavailable_sorts_last(store):
    result = search(store, query="giannini")
    assert {84, 88, 96, 101, 110} <= ids(result)
    assert result.items[-1].id == 96


def test_no_query_is_available_only(store, monkeypatch):
    monkeypatch.setattr("emporio.search._CAP", 100)
    violoes = search(store, category="violão")
    assert {96, 113}.isdisjoint(ids(violoes))
    assert all(h.availability == Availability.AVAILABLE for h in violoes.items)
    assert ids(search(store, category="baixo")) == {135, 137, 138}
    assert 130 not in ids(search(store, category="ukulele"))


def test_cap_and_order(store):
    result = search(store, category="violões")
    assert len(result.items) == 8
    assert result.total == 33
    assert result.items[0].id == 83
    lowest = [h.quote.pix_price or h.quote.price for h in result.items]
    assert lowest == sorted(lowest)


def test_hits_carry_no_description_or_stock():
    names = {f.name for f in dataclasses.fields(SearchHit)}
    assert "description" not in names
    assert "stock" not in names


def test_empty_and_unknown_categories(store):
    assert search(store, query="sax").total == 0
    assert search(store, category="violino").total == 0
    with pytest.raises(ValueError):
        search(store, category="acessórios")


def test_alternatives(store):
    assert [h.id for h in alternatives(store, 136)] == [138, 135, 137]
    assert [h.id for h in alternatives(store, 96)][:3] == [107, 82, 86]
    for product_id in (96, 136):
        for hit in alternatives(store, product_id):
            assert hit.id != product_id
            assert hit.availability == Availability.AVAILABLE
    with pytest.raises(KeyError):
        alternatives(store, 9999)


def test_normalize():
    assert normalize("Violão GD-20!") == "violao gd 20"
