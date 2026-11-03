import csv
import re
from decimal import Decimal
from pathlib import Path

import pytest

from emporio.domain import Money, Payment, PaymentMethod, ProductStatus, max_installments
from emporio.store import DATA_DIR, Store, load_store

MINIMAL = {
    "categories.csv": "category_id,name,description\n1,Guitarras,Guitarras elétricas\n",
    "products.csv": (
        "product_id,price_brl,name,category_id,description,stock_quantity,status,specs,created_at\n"
        '81,599.9,Yamaha C40,1,Violão,12,active,"{""top"":""Spruce""}",2021-03-15\n'
    ),
    "customers.csv": (
        "customer_id,name,phone,email,city\n"
        "1,Lucas Mendes,(67) 99812-3456,lucas@jmail.com,Campo Grande\n"
    ),
    "orders.csv": (
        "order_id,customer_id,order_date,status,total_brl,payment_method,"
        "tracking_code,estimated_delivery,notes\n"
        "1,1,2025-10-15,delivered,599.9,credit_3x,BRAB1234567BR,2025-10-25,\n"
    ),
    "order_items.csv": "order_id,quantity,product_id\n1,1,81\n",
    "promotions.csv": (
        "promotion_id,product_id,discount_percent,description,is_active\n1,81,10,Black Friday,1\n"
    ),
    "politicas.md": "# Políticas\n\nPreâmbulo.\n\n## [hours] Horário\n\nSegunda a sexta.\n",
}


def write_data(tmp_path: Path, extra: dict[str, str] | None = None) -> Path:
    """Write the minimal data set, appending `extra` rows to the named files."""
    for name, text in MINIMAL.items():
        (tmp_path / name).write_text(text + (extra or {}).get(name, ""), encoding="utf-8")
    return tmp_path


def test_minimal_data_loads(tmp_path):
    store = load_store(write_data(tmp_path))
    order = store.orders[1]
    assert order.payment == Payment(PaymentMethod.CREDIT, 3)
    assert order.notes is None
    assert [i.product_id for i in order.items] == [81]
    assert store.products[81].list_price == Money(Decimal("599.90"))
    assert store.products[81].specs == {"top": "Spruce"}
    assert store.active_promotion(81) == store.promotions[1]
    assert store.policies == {"hours": "Segunda a sexta."}


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            {"promotions.csv": "2,99,10,Oferta,0\n"},
            r"promotions\.csv promotion_id=2: unknown product_id 99",
        ),
        (
            {"order_items.csv": "99,1,81\n"},
            r"order_items\.csv order_id=99: unknown order_id 99",
        ),
        (
            {"promotions.csv": "2,81,20,Oferta,1\n"},
            r"promotions\.csv promotion_id=2: product_id 81 already has active promotion 1",
        ),
        (
            {"orders.csv": "2,1,2026-01-05,lost,100,pix,,,\n"},
            r"orders\.csv order_id=2: .*'lost'",
        ),
        (
            {"orders.csv": "2,1,2026-01-05,pending,100,bitcoin,,,\n"},
            r"orders\.csv order_id=2: unknown payment method: 'bitcoin'",
        ),
    ],
    ids=[
        "promotion-product-fk",
        "item-order-fk",
        "two-active",
        "order-status",
        "payment",
    ],
)
def test_invalid_data_fails_load(tmp_path, extra, message):
    with pytest.raises(ValueError, match=message):
        load_store(write_data(tmp_path, extra))


@pytest.fixture(scope="module")
def store() -> Store:
    return load_store()


def test_real_data_counts_and_translations(store):
    counts = [len(store.products), len(store.customers), len(store.orders), len(store.promotions)]
    assert counts == [65, 50, 20, 25]
    assert len(store.categories) == 9
    assert set(store.policies) == {
        "contact",
        "hours",
        "payment",
        "returns",
        "shipping",
        "promotions",
        "warranty",
        "privacy",
        "scope",
    }
    assert store.orders[9].payment == Payment(PaymentMethod.CREDIT, 6)
    assert store.orders[9].tracking_code is None
    assert store.products[130].status == ProductStatus.COMING_SOON
    assert store.orders[1].total == Money(Decimal("11499"))


def test_real_data_inconsistencies(store):
    products, orders = store.products, store.orders

    def item_sum(order):
        return sum(products[i.product_id].list_price.amount * i.quantity for i in order.items)

    assert (products[136].status, products[136].stock) == (ProductStatus.DISCONTINUED, 13)
    assert products[130].status == ProductStatus.COMING_SOON
    assert {o.id for o in orders.values() if any(i.product_id == 130 for i in o.items)} == {3, 14}
    assert (products[96].status, products[96].stock) == (ProductStatus.ACTIVE, 0)

    assert "Madeiras" in store.categories[6].name
    assert store.categories[8].name == "Cordas Orquestrais"
    assert not {p.category_id for p in products.values()} & {6, 8}

    too_many = {
        o.id for o in orders.values() if o.payment.installments > max_installments(o.total).count
    }
    assert too_many == {9, 16, 18}

    pix = [o for o in orders.values() if o.payment.method == PaymentMethod.PIX]
    assert {o.id for o in pix} == {1, 5, 10, 13, 17}
    assert all(o.total.amount == item_sum(o) for o in pix)

    assert orders[11].total == products[127].list_price
    assert store.active_promotion(127) is not None

    assert {o.id for o in orders.values() if o.total.amount != item_sum(o)} == {3, 20}

    campo_grande = [
        o.tracking_code
        for o in orders.values()
        if store.customers[o.customer_id].city == "Campo Grande" and o.tracking_code
    ]
    assert campo_grande
    assert all(re.fullmatch(r"BR[A-Z]{2}\d{7}BR", code) for code in campo_grande)

    assert store.customers[11].email == store.customers[43].email

    assert "(67) 3341-4444" in store.policies["contact"]
    assert "(67) 3321-4500" in store.policies["contact"]

    with (DATA_DIR / "orders.csv").open(encoding="utf-8", newline="") as file:
        header = next(csv.reader(file))
    # The exact header shows there is no delivered-at and no sales-channel column.
    assert header == [
        "order_id",
        "customer_id",
        "order_date",
        "status",
        "total_brl",
        "payment_method",
        "tracking_code",
        "estimated_delivery",
        "notes",
    ]
