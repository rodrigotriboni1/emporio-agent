"""Use cases behind Mel's tools: each returns ready-to-say PT-BR text.

Formatting and authorization only; the rules live in domain, store and search.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

from emporio import search
from emporio.domain import (
    Availability,
    OrderStatus,
    PriceQuote,
    is_open,
    mask_pii,
    max_installments,
    next_opening,
    return_windows,
)
from emporio.store import Store

HANDOFFS_PATH = Path(__file__).resolve().parents[2] / "handoffs.jsonl"

ORDER_NOT_FOUND = (
    "Não encontrei um pedido com esses dados. Confira o número do pedido e o telefone "
    "ou e-mail usado na compra."
)
ORDER_LOCKED = (
    "Por segurança, a consulta deste pedido está bloqueada depois de várias tentativas sem "
    "sucesso. Posso encaminhar você para um atendente humano."
)
_MAX_FAILURES = 5

# Failed lookups per numeric order id; lives until the process restarts (S3).
# shortcut: no thread lock, so a concurrent race allows a few extra tries; add one if served
# by a multi-threaded server.
_failures: dict[int, int] = {}

_LABELS = {
    Availability.AVAILABLE: "disponível",
    Availability.OUT_OF_STOCK: "esgotado",
    Availability.DISCONTINUED: "fora de linha",
    Availability.COMING_SOON: "em breve",
}
_STATUS = {
    OrderStatus.PENDING: "aguardando confirmação do pagamento",
    OrderStatus.CONFIRMED: "pagamento confirmado, em preparação para envio",
    OrderStatus.SHIPPED: "enviado, a caminho",
    OrderStatus.DELIVERED: "entregue",
    OrderStatus.CANCELLED: "cancelado",
}
_WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_DIGIT_RUN = re.compile(r"[+(]*\d[\d\s().+-]*\d\)?")


def _date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _when(moment: datetime) -> str:
    return f"{_WEEKDAYS[moment.weekday()]}, {_date(moment)} às {moment:%H:%M}"


def _price(quote: PriceQuote) -> str:
    if quote.percent_off is not None:
        return f"{quote.price} (de {quote.list_price}, {quote.percent_off}% off)"
    return f"{quote.price} ou {quote.pix_price} no PIX"


def _detail(store: Store, hit: search.SearchHit) -> str:
    quote = hit.quote
    lines = [f"{hit.name} ({hit.category}) — {_LABELS[hit.availability]}"]
    lines.append("Especificações: " + "; ".join(f"{k}: {v}" for k, v in hit.specs.items()))
    if quote.percent_off is not None:
        lines.append(
            f"Promoção ativa: de {quote.list_price} por {quote.price} ({quote.percent_off}% off)"
        )
    else:
        lines.append(f"Preço: {quote.price} ou {quote.pix_price} no PIX (5% de desconto)")
    for promo in store.promotions.values():
        if promo.product_id == hit.id and not promo.active:
            lines.append(f"Promoção encerrada: {promo.description} ({promo.percent}%)")
    installments = max_installments(quote.price)
    lines.append(f"Parcelamento: até {installments.count}x de {installments.value} sem juros")
    if hit.availability in (Availability.OUT_OF_STOCK, Availability.DISCONTINUED):
        alternatives = search.alternatives(store, hit.id)[:3]
        if alternatives:
            lines.append("Alternativas disponíveis:")
            lines.extend(f"- {a.name}: {_price(a.quote)}" for a in alternatives)
    return "\n".join(lines)


def search_products(store: Store, query: str = "", category: str = "", max_price: str = "") -> str:
    try:
        result = search.search(store, query, category, max_price)
    except ValueError as error:
        if str(error).startswith("unknown category"):
            names = ", ".join(c.name for c in store.categories.values())
            return f"Não conheço essa categoria. Categorias da loja: {names}."
        return "Não entendi o preço máximo. Informe um valor como 1000 ou R$ 1.000,00."
    if not result.items:
        return "Não encontrei nenhum produto com esses critérios no sistema no momento."
    if len(result.items) == 1:
        return _detail(store, result.items[0])
    lines = [f"- {h.name}: {_price(h.quote)} — {_LABELS[h.availability]}" for h in result.items]
    if result.total > len(result.items):
        lines.append(f"mostrando {len(result.items)} de {result.total}")
    return "\n".join(lines)


def get_policy(store: Store, topic: str, now: datetime) -> str:
    topic = topic.strip().lower()
    if topic not in store.policies:
        return f"Tópico desconhecido. Tópicos válidos: {', '.join(store.policies)}."
    text = store.policies[topic]
    if topic == "hours":
        state = "abertos" if is_open(now) else "fechados"
        text += f"\n\nAgora estamos {state}. Próxima abertura: {_when(next_opening(now))}."
    return text


def _authorized(store: Store, customer_id: int, credential: str) -> bool:
    customer = store.customers[customer_id]
    if "@" in credential:
        return credential.strip().casefold() == customer.email.strip().casefold()
    return customer.phone.matches(credential)


def get_order(store: Store, order_id: str, phone_or_email: str, now: datetime) -> str:
    order_id = order_id.strip()
    # Capped at 9 digits: no order id is that long, and int() rejects strings over 4300 digits.
    if not re.fullmatch(r"[0-9]{1,9}", order_id):
        return ORDER_NOT_FOUND
    number = int(order_id)
    if _failures.get(number, 0) >= _MAX_FAILURES:
        return ORDER_LOCKED
    order = store.orders.get(number)
    if order is None or not _authorized(store, order.customer_id, phone_or_email):
        _failures[number] = _failures.get(number, 0) + 1
        return ORDER_NOT_FOUND

    first_name = store.customers[order.customer_id].name.split()[0]
    status = _STATUS[order.status]
    if order.notes:
        status += f" ({order.notes})"
    lines = [f"{first_name}, encontrei o pedido {order.id}.", f"Status: {status}."]
    if order.tracking_code:
        lines.append(f"Código de rastreamento: {order.tracking_code}.")
    expected = order.estimated_delivery
    final = (OrderStatus.DELIVERED, OrderStatus.CANCELLED)
    if expected is not None and order.status not in final and expected < now.date():
        days = (now.date() - expected).days
        lines.append(f"Entrega: atrasado {days} dias (previsão {_date(expected)}).")
    elif expected is not None:
        lines.append(f"Previsão de entrega: {_date(expected)}.")
    else:
        lines.append("Previsão de entrega: ainda não definida.")
    lines.append(f"Valor do pedido: {order.total}.")
    if order.status == OrderStatus.DELIVERED:
        windows = return_windows(order.date, expected, now)
        for label, window in (
            ("Arrependimento", windows.regret),
            ("Troca por preferência", windows.preference),
            ("Defeito", windows.defect),
            ("Garantia legal", windows.legal_warranty),
        ):
            if window is not None:
                state = "aberto" if window.open else "encerrado"
                lines.append(f"{label}: até {_date(window.ends)} ({state}).")
    else:
        lines.append("Os prazos de troca e devolução contam a partir da entrega.")
    others = [
        str(o.id)
        for o in store.orders.values()
        if o.customer_id == order.customer_id and o.id != order.id
    ]
    if others:
        lines.append(f"Outros pedidos seus: {', '.join(others)}.")
    return "\n".join(lines)


def mask_text(store: Store, text: str) -> str:
    text = _EMAIL.sub(lambda m: mask_pii(m.group()), text)
    text = _DIGIT_RUN.sub(
        lambda m: mask_pii(m.group()) if sum(c.isdigit() for c in m.group()) >= 8 else m.group(),
        text,
    )
    # shortcut: case-insensitive only, not accent-insensitive; fold accents if the model rewrites
    # names.
    for name in sorted({c.name for c in store.customers.values()}, key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        text = pattern.sub(f"{name.split()[0]} ***", text)
    return text


def handoff_to_human(
    store: Store, reason: str, summary: str, now: datetime, path: Path = HANDOFFS_PATH
) -> str:
    count = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
    protocol = f"EM-{now:%Y%m%d}-{count + 1:04d}"
    record = {
        "protocol": protocol,
        "timestamp": now.isoformat(),
        "reason": mask_text(store, reason),
        "summary": mask_text(store, summary),
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    text = f"Encaminhei seu atendimento para a equipe humana. Protocolo: {protocol}."
    if not is_open(now):
        text += f" A equipe volta {_when(next_opening(now))}."
    return text
