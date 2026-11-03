"""Deterministic product search over the Store, and same-category alternatives.

Structured results only; formatting for customers belongs to the services layer.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from difflib import get_close_matches

from emporio.domain import (
    Availability,
    PriceQuote,
    Product,
    _fold,
    availability,
    effective_price,
)
from emporio.store import Store

_CAP = 8

# Normalized token -> category name; singular and plural forms are listed explicitly.
SYNONYMS: dict[str, str] = {
    "violao": "Violões",
    "violoes": "Violões",
    "guitarra": "Guitarras",
    "guitarras": "Guitarras",
    "baixo": "Baixos",
    "baixos": "Baixos",
    "contrabaixo": "Baixos",
    "contrabaixos": "Baixos",
    "bateria": "Baterias e Percussão",
    "baterias": "Baterias e Percussão",
    "percussao": "Baterias e Percussão",
    "teclado": "Teclados e Pianos",
    "teclados": "Teclados e Pianos",
    "piano": "Teclados e Pianos",
    "pianos": "Teclados e Pianos",
    "sintetizador": "Teclados e Pianos",
    "sintetizadores": "Teclados e Pianos",
    "ukulele": "Ukuleles",
    "ukuleles": "Ukuleles",
    "uke": "Ukuleles",
    "ukes": "Ukuleles",
    "sax": "Instrumentos de Sopro (Madeiras)",
    "flauta": "Instrumentos de Sopro (Madeiras)",
    "flautas": "Instrumentos de Sopro (Madeiras)",
    "clarinete": "Instrumentos de Sopro (Madeiras)",
    "clarinetes": "Instrumentos de Sopro (Madeiras)",
    "trompete": "Instrumentos de Sopro (Metais)",
    "trompetes": "Instrumentos de Sopro (Metais)",
    "trombone": "Instrumentos de Sopro (Metais)",
    "trombones": "Instrumentos de Sopro (Metais)",
    "violino": "Cordas Orquestrais",
    "violinos": "Cordas Orquestrais",
    "viola": "Cordas Orquestrais",
    "violas": "Cordas Orquestrais",
    "violoncelo": "Cordas Orquestrais",
    "violoncelos": "Cordas Orquestrais",
}


@dataclass(frozen=True)
class SearchHit:
    id: int
    name: str
    category: str
    specs: Mapping[str, str]
    quote: PriceQuote
    availability: Availability


@dataclass(frozen=True)
class SearchResult:
    items: tuple[SearchHit, ...]
    total: int


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _fold(text)).strip()


def parse_price(text: str) -> Decimal | None:
    value = text.strip().removeprefix("R$").strip()
    if not value:
        return None
    if "," in value:
        if not re.fullmatch(r"(\d{1,3}(\.\d{3})+|\d+),\d{1,2}", value):
            raise ValueError(f"invalid price: {text!r}")
        return Decimal(value.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", value):
        return Decimal(value.replace(".", ""))
    if not re.fullmatch(r"\d+(\.\d{1,2})?", value):
        raise ValueError(f"invalid price: {text!r}")
    return Decimal(value)


def _hit(store: Store, product: Product) -> SearchHit:
    return SearchHit(
        id=product.id,
        name=product.name,
        category=store.categories[product.category_id].name,
        specs=product.specs,
        quote=effective_price(product.list_price, store.active_promotion(product.id)),
        availability=availability(product.status, product.stock),
    )


def _lowest(hit: SearchHit) -> Decimal:
    return (hit.quote.pix_price or hit.quote.price).amount


def _category_id(store: Store, name: str) -> int:
    return next(c.id for c in store.categories.values() if c.name == name)


def _category_filter(store: Store, category: str) -> set[int]:
    tokens = normalize(category).split()
    if tokens and all(t in SYNONYMS for t in tokens):
        return {_category_id(store, SYNONYMS[t]) for t in tokens}
    for c in store.categories.values():
        if normalize(c.name) == normalize(category):
            return {c.id}
    raise ValueError(f"unknown category: {category!r}")


def search(store: Store, query: str = "", category: str = "", max_price: str = "") -> SearchResult:
    limit = parse_price(max_price)
    categories = _category_filter(store, category) if category.strip() else set()
    texts = {
        p.id: normalize(" ".join([p.name, *p.specs.values()])) for p in store.products.values()
    }
    haystacks = {i: text.replace(" ", "") for i, text in texts.items()}
    vocabulary = {word for text in texts.values() for word in text.split()} | SYNONYMS.keys()

    words = []
    for token in normalize(query).split():
        if token not in SYNONYMS and not any(token in h for h in haystacks.values()):
            close = get_close_matches(token, vocabulary, n=1)
            if not close:
                return SearchResult((), 0)
            token = close[0]
        if token in SYNONYMS:
            categories.add(_category_id(store, SYNONYMS[token]))
        else:
            words.append(token)

    hits = [
        hit
        for p in store.products.values()
        if (not categories or p.category_id in categories)
        and all(w in haystacks[p.id] for w in words)
        for hit in [_hit(store, p)]
        if (limit is None or _lowest(hit) <= limit)
        and (words or hit.availability == Availability.AVAILABLE)
    ]
    hits.sort(key=lambda h: (h.availability != Availability.AVAILABLE, _lowest(h), h.id))
    return SearchResult(tuple(hits[:_CAP]), len(hits))


def alternatives(store: Store, product_id: int) -> tuple[SearchHit, ...]:
    target = _hit(store, store.products[product_id])
    hits = [
        hit
        for p in store.products.values()
        if p.category_id == store.products[product_id].category_id and p.id != product_id
        for hit in [_hit(store, p)]
        if hit.availability == Availability.AVAILABLE
    ]
    return tuple(sorted(hits, key=lambda h: (abs(_lowest(h) - _lowest(target)), h.id)))
