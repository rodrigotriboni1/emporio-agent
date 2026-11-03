"""Pure domain core: entities, value objects and store rules.

No I/O and no imports from other emporio modules. Time is always passed in as `now`.
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

_CENT = Decimal("0.01")


class ProductStatus(StrEnum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    PIX = "pix"
    DEBIT = "debit"
    BOLETO = "boleto"
    CREDIT = "credit"


class Availability(StrEnum):
    AVAILABLE = "available"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


@dataclass(frozen=True, order=True)
class Money:
    amount: Decimal

    def __post_init__(self) -> None:
        amount = Decimal(self.amount).quantize(_CENT, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", amount)

    def __str__(self) -> str:
        # Swap the en-US separators for BRL ones: 1,049.00 -> 1.049,00.
        text = f"{self.amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return f"R$ {text}"


@dataclass(frozen=True)
class Phone:
    digits: str

    @classmethod
    def parse(cls, raw: str) -> "Phone":
        return cls("".join(c for c in raw if c.isdigit()))

    def matches(self, raw: str) -> bool:
        digits = Phone.parse(raw).digits
        return len(digits) >= 8 and digits[-8:] == self.digits[-8:]

    def __repr__(self) -> str:
        # Masked so a logged Phone never leaks the full number (S4); str() uses this too.
        return f"Phone({mask_pii(self.digits)!r})"


@dataclass(frozen=True)
class Payment:
    method: PaymentMethod
    installments: int

    @classmethod
    def parse(cls, value: str) -> "Payment":
        if value in (PaymentMethod.PIX, PaymentMethod.DEBIT, PaymentMethod.BOLETO):
            return cls(PaymentMethod(value), 1)
        match = re.fullmatch(r"credit_([1-9]|1[0-2])x", value)
        if not match:
            raise ValueError(f"unknown payment method: {value!r}")
        return cls(PaymentMethod.CREDIT, int(match.group(1)))


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    description: str


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category_id: int
    list_price: Money
    stock: int
    status: ProductStatus
    specs: Mapping[str, str]


@dataclass(frozen=True)
class Promotion:
    id: int
    product_id: int
    percent: int
    description: str
    active: bool


@dataclass(frozen=True)
class Customer:
    id: int
    name: str = field(repr=False)
    phone: Phone = field(repr=False)
    email: str = field(repr=False)
    city: str


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    date: date
    status: OrderStatus
    total: Money
    payment: Payment
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: tuple[OrderItem, ...]


@dataclass(frozen=True)
class PriceQuote:
    list_price: Money
    price: Money
    percent_off: int | None
    pix_price: Money | None


def effective_price(list_price: Money, promotion: Promotion | None) -> PriceQuote:
    if promotion is not None and promotion.active:
        price = Money(list_price.amount * (100 - promotion.percent) / 100)
        # The PIX discount doesn't stack on a promotion.
        return PriceQuote(list_price, price, promotion.percent, None)
    return PriceQuote(list_price, list_price, None, Money(list_price.amount * Decimal("0.95")))


@dataclass(frozen=True)
class Installments:
    count: int
    value: Money


def _installments_allowed(amount: Decimal, count: int) -> bool:
    if count <= 3:
        return True
    if count <= 6:
        return amount >= count * 80
    return amount >= count * 100


def max_installments(amount: Money) -> Installments:
    count = 1
    if amount.amount >= 50:
        count = next(n for n in range(12, 0, -1) if _installments_allowed(amount.amount, n))
    return Installments(count, Money(amount.amount / count))


def combined_payment_allowed(amount: Money) -> bool:
    return amount.amount > 2000


@dataclass(frozen=True)
class Shipping:
    fee: Money | None
    business_days: tuple[int, int] | None


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip().casefold()


def shipping(city: str, subtotal: Money) -> Shipping:
    if _fold(city) != "campo grande":
        # Other cities are quoted by CEP; never estimate a fee here.
        return Shipping(None, None)
    fee = Money(0) if subtotal.amount >= 500 else Money(35)
    return Shipping(fee, (1, 3))


@dataclass(frozen=True)
class Window:
    ends: date
    open: bool


@dataclass(frozen=True)
class ReturnWindows:
    regret: Window | None
    preference: Window | None
    defect: Window | None
    legal_warranty: Window | None


def return_windows(order_date: date, delivery_date: date | None, now: datetime) -> ReturnWindows:
    def window(start: date | None, days: int) -> Window | None:
        if start is None:
            return None
        ends = start + timedelta(days=days)
        return Window(ends, now.date() <= ends)

    return ReturnWindows(
        regret=window(delivery_date, 7),
        preference=window(delivery_date, 7),
        defect=window(order_date, 30),
        legal_warranty=window(delivery_date, 90),
    )


# Opening hours by weekday (Monday is 0), as [open, close); Sunday is closed.
_HOURS: dict[int, tuple[time, time]] = {
    **{day: (time(9), time(18)) for day in range(5)},
    5: (time(9), time(13)),
}


def is_open(now: datetime) -> bool:
    hours = _HOURS.get(now.weekday())
    return hours is not None and hours[0] <= now.time() < hours[1]


def next_opening(now: datetime) -> datetime:
    # Strictly after `now`, so a call while open gives the next day's opening.
    for offset in range(8):
        day = now.date() + timedelta(days=offset)
        hours = _HOURS.get(day.weekday())
        if hours is None:
            continue
        opening = datetime.combine(day, hours[0], tzinfo=now.tzinfo)
        if opening > now:
            return opening
    raise AssertionError("unreachable: the store opens every week")


def availability(status: ProductStatus, stock: int) -> Availability:
    if status == ProductStatus.DISCONTINUED:
        return Availability.DISCONTINUED
    if status == ProductStatus.COMING_SOON:
        return Availability.COMING_SOON
    return Availability.AVAILABLE if stock > 0 else Availability.OUT_OF_STOCK


def mask_pii(value: str) -> str:
    if "@" in value:
        local, _, domain = value.rpartition("@")
        return f"{local[:1]}***@{domain}"
    digits = Phone.parse(value).digits
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"
