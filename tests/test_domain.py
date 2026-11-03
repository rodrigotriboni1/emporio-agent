from datetime import date, datetime
from decimal import Decimal

import pytest

from emporio.domain import (
    Availability,
    Customer,
    Money,
    Payment,
    PaymentMethod,
    Phone,
    ProductStatus,
    Promotion,
    availability,
    combined_payment_allowed,
    effective_price,
    is_open,
    mask_pii,
    max_installments,
    next_opening,
    return_windows,
    shipping,
)

NOW = datetime.fromisoformat("2026-03-25T10:00-04:00")


def test_money_formats_brl_and_rounds_half_up():
    assert str(Money("1049")) == "R$ 1.049,00"
    assert str(Money(35)) == "R$ 35,00"
    assert str(Money(0)) == "R$ 0,00"
    assert str(Money("11499")) == "R$ 11.499,00"
    assert Money("87.475").amount == Decimal("87.48")
    assert Money("500") >= Money("500.00")
    assert Money("500") == Money("500.00")
    assert Money("499.99") < Money("500")


def test_phone_matches_last_eight_digits():
    phone = Phone.parse("(67) 99812-3456")
    assert phone.digits == "67998123456"
    for raw in ["99812-3456", "9812-3456", "+55 67 99812 3456"]:
        assert phone.matches(raw)
    for raw in ["2-3456", "123456", "99812-3457"]:
        assert not phone.matches(raw)


def test_payment_parse():
    assert Payment.parse("credit_6x") == Payment(PaymentMethod.CREDIT, 6)
    assert Payment.parse("credit_12x").installments == 12
    for method in ["pix", "debit", "boleto"]:
        assert Payment.parse(method) == Payment(PaymentMethod(method), 1)


@pytest.mark.parametrize("value", ["credit_13x", "credit_0x", "cash", ""])
def test_payment_parse_rejects_unknown(value):
    with pytest.raises(ValueError):
        Payment.parse(value)


@pytest.mark.parametrize(
    ("amount", "count", "value"),
    [
        ("1199", 11, None),
        ("1200", 12, "100"),
        ("429.90", 5, None),
        ("349.90", 4, "87.48"),
        ("49.99", 1, None),
        ("50", 3, None),
        ("2199", 12, "183.25"),
    ],
)
def test_max_installments(amount, count, value):
    result = max_installments(Money(amount))
    assert result.count == count
    if value is not None:
        assert result.value == Money(value)


def test_effective_price_without_promotion_has_pix_discount():
    quote = effective_price(Money("2199"), None)
    assert quote.price == Money("2199")
    assert str(quote.pix_price) == "R$ 2.089,05"
    assert quote.percent_off is None
    inactive = Promotion(4, 95, 12, "Inactive promo", active=False)
    assert effective_price(Money("2199"), inactive) == quote


def test_effective_price_with_active_promotion_skips_pix():
    quote = effective_price(Money("549"), Promotion(14, 121, 20, "Ohana promo", active=True))
    assert str(quote.price) == "R$ 439,20"
    assert str(quote.list_price) == "R$ 549,00"
    assert quote.percent_off == 20
    assert quote.pix_price is None


def test_combined_payment_threshold():
    assert not combined_payment_allowed(Money("2000"))
    assert combined_payment_allowed(Money("2000.01"))


def test_shipping():
    local = shipping("Campo Grande", Money("439.20"))
    assert local.fee == Money(35)
    assert local.business_days == (1, 3)
    assert shipping("campo grande", Money("500")).fee == Money(0)
    assert shipping(" CAMPO GRANDE ", Money("499.99")).fee == Money(35)
    other = shipping("Dourados", Money("439.20"))
    assert other.fee is None
    assert other.business_days is None


def test_return_windows_order_7():
    windows = return_windows(date(2026, 2, 3), date(2026, 2, 17), NOW)
    assert (windows.regret.ends, windows.regret.open) == (date(2026, 2, 24), False)
    assert (windows.preference.ends, windows.preference.open) == (date(2026, 2, 24), False)
    assert (windows.defect.ends, windows.defect.open) == (date(2026, 3, 5), False)
    assert (windows.legal_warranty.ends, windows.legal_warranty.open) == (date(2026, 5, 18), True)


def test_return_windows_without_delivery():
    windows = return_windows(date(2026, 2, 3), None, NOW)
    assert windows.regret is None
    assert windows.preference is None
    assert windows.legal_warranty is None
    assert windows.defect.ends == date(2026, 3, 5)


def test_return_window_end_day_is_inside():
    windows = return_windows(date(2026, 2, 3), date(2026, 2, 17), datetime(2026, 2, 24, 23, 59))
    assert windows.regret.open


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def test_opening_hours():
    assert is_open(at("2026-03-25T10:00-04:00"))
    assert not is_open(at("2026-03-28T13:30-04:00"))
    assert next_opening(at("2026-03-28T13:30-04:00")) == at("2026-03-30T09:00-04:00")
    assert not is_open(at("2026-03-27T18:00-04:00"))
    assert next_opening(at("2026-03-27T18:00-04:00")) == at("2026-03-28T09:00-04:00")
    assert not is_open(at("2026-03-29T12:00-04:00"))
    assert next_opening(at("2026-03-29T12:00-04:00")) == at("2026-03-30T09:00-04:00")
    assert is_open(at("2026-03-28T12:59-04:00"))
    assert not is_open(at("2026-03-28T13:00-04:00"))
    assert next_opening(at("2026-03-30T08:00-04:00")) == at("2026-03-30T09:00-04:00")


def test_next_opening_while_open_is_next_day():
    assert next_opening(at("2026-03-25T10:00-04:00")) == at("2026-03-26T09:00-04:00")
    assert next_opening(at("2026-03-28T09:00-04:00")) == at("2026-03-30T09:00-04:00")


@pytest.mark.parametrize(
    ("status", "stock", "expected"),
    [
        (ProductStatus.ACTIVE, 0, Availability.OUT_OF_STOCK),
        (ProductStatus.DISCONTINUED, 0, Availability.DISCONTINUED),
        (ProductStatus.COMING_SOON, 2, Availability.COMING_SOON),
        (ProductStatus.DISCONTINUED, 13, Availability.DISCONTINUED),
        (ProductStatus.ACTIVE, 5, Availability.AVAILABLE),
    ],
)
def test_availability_status_beats_stock(status, stock, expected):
    assert availability(status, stock) == expected


def test_mask_pii():
    assert mask_pii("(67) 99812-3456") == "***3456"
    assert mask_pii("lucas.mendes@jmail.com") == "l***@jmail.com"
    assert mask_pii("12") == "***"


def test_phone_repr_and_str_are_masked():
    phone = Phone.parse("(67) 99812-3456")
    assert repr(phone) == "Phone('***3456')"
    assert str(phone) == "Phone('***3456')"
    assert f"{phone}" == "Phone('***3456')"


def test_customer_repr_hides_pii():
    customer = Customer(
        1, "Lucas Mendes", Phone.parse("(67) 99812-3456"), "lucas.mendes@jmail.com", "Campo Grande"
    )
    text = repr(customer)
    assert "99812" not in text
    assert "67998123456" not in text
    assert "lucas.mendes@jmail.com" not in text
    assert "Lucas Mendes" not in text
    assert "Campo Grande" in text
