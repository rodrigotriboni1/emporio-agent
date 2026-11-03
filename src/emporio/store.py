"""Load data/ into domain objects and check the load-time invariants.

CSV values are translated once, here; everything downstream sees domain types.
"""

import csv
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio.domain import (
    Category,
    Customer,
    Money,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    Phone,
    Product,
    ProductStatus,
    Promotion,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True)
class Store:
    categories: dict[int, Category]
    products: dict[int, Product]
    customers: dict[int, Customer]
    orders: dict[int, Order]
    promotions: dict[int, Promotion]
    policies: dict[str, str]

    def active_promotion(self, product_id: int) -> Promotion | None:
        return next(
            (p for p in self.promotions.values() if p.active and p.product_id == product_id),
            None,
        )


def _read[T](data_dir: Path, name: str, key: str, build: Callable[[dict[str, str]], T]) -> list[T]:
    with (data_dir / name).open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    built = []
    for row in rows:
        try:
            built.append(build(row))
        except ValueError as error:
            raise ValueError(f"{name} {key}={row[key]}: {error}") from error
    return built


def _ref(table: Mapping[int, object], column: str, text: str) -> int:
    value = int(text)
    if value not in table:
        raise ValueError(f"unknown {column} {value}")
    return value


def _flag(text: str) -> bool:
    if text not in ("0", "1"):
        raise ValueError(f"unknown is_active value {text!r}")
    return text == "1"


def _optional_date(text: str) -> date | None:
    return date.fromisoformat(text) if text else None


def _policies(text: str) -> dict[str, str]:
    # The split alternates [preamble, topic, body, topic, body, ...]; the preamble is dropped.
    parts = re.split(r"^## \[([^\]]+)\][^\n]*$", text, flags=re.MULTILINE)
    return {topic: body.strip() for topic, body in zip(parts[1::2], parts[2::2], strict=True)}


def load_store(data_dir: Path = DATA_DIR) -> Store:
    categories = {
        c.id: c
        for c in _read(
            data_dir,
            "categories.csv",
            "category_id",
            lambda r: Category(int(r["category_id"]), r["name"], r["description"]),
        )
    }

    def product(r: dict[str, str]) -> Product:
        return Product(
            id=int(r["product_id"]),
            name=r["name"],
            category_id=_ref(categories, "category_id", r["category_id"]),
            list_price=Money(Decimal(r["price_brl"])),
            stock=int(r["stock_quantity"]),
            status=ProductStatus(r["status"]),
            specs=json.loads(r["specs"]),
        )

    products = {p.id: p for p in _read(data_dir, "products.csv", "product_id", product)}

    active: dict[int, int] = {}

    def promotion(r: dict[str, str]) -> Promotion:
        p = Promotion(
            id=int(r["promotion_id"]),
            product_id=_ref(products, "product_id", r["product_id"]),
            percent=int(r["discount_percent"]),
            description=r["description"],
            active=_flag(r["is_active"]),
        )
        if p.active:
            if p.product_id in active:
                raise ValueError(
                    f"product_id {p.product_id} already has active promotion {active[p.product_id]}"
                )
            active[p.product_id] = p.id
        return p

    promotions = {p.id: p for p in _read(data_dir, "promotions.csv", "promotion_id", promotion)}

    customers = {
        c.id: c
        for c in _read(
            data_dir,
            "customers.csv",
            "customer_id",
            lambda r: Customer(
                int(r["customer_id"]), r["name"], Phone.parse(r["phone"]), r["email"], r["city"]
            ),
        )
    }

    def order(r: dict[str, str]) -> Order:
        return Order(
            id=int(r["order_id"]),
            customer_id=_ref(customers, "customer_id", r["customer_id"]),
            date=date.fromisoformat(r["order_date"]),
            status=OrderStatus(r["status"]),
            total=Money(Decimal(r["total_brl"])),
            payment=Payment.parse(r["payment_method"]),
            tracking_code=r["tracking_code"] or None,
            estimated_delivery=_optional_date(r["estimated_delivery"]),
            notes=r["notes"] or None,
            items=(),
        )

    orders = {o.id: o for o in _read(data_dir, "orders.csv", "order_id", order)}

    items: dict[int, list[OrderItem]] = {}
    for order_id, item in _read(
        data_dir,
        "order_items.csv",
        "order_id",
        lambda r: (
            _ref(orders, "order_id", r["order_id"]),
            OrderItem(_ref(products, "product_id", r["product_id"]), int(r["quantity"])),
        ),
    ):
        items.setdefault(order_id, []).append(item)
    orders = {i: replace(o, items=tuple(items.get(i, ()))) for i, o in orders.items()}

    policies = _policies((data_dir / "politicas.md").read_text(encoding="utf-8"))
    return Store(categories, products, customers, orders, promotions, policies)
