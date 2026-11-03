import pytest

from emporio.services import mask_text
from emporio.store import Store, load_store


@pytest.fixture(scope="module")
def store() -> Store:
    return load_store()


@pytest.mark.parametrize(
    "text",
    [
        "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333.",
        "Telefone: (67) 3341-4444. WhatsApp: (67) 3321-4500.",
        "Ligue +55 67 3321-4500 ou 3341-4444.",
        "E-mail: contato@emporiodamusica.com.br",
    ],
)
def test_store_contacts_are_left_as_is(store, text):
    assert mask_text(store, text) == text


def test_customer_contacts_next_to_store_contacts_are_masked(store):
    text = "Loja (67) 3341-4444, contato@emporiodamusica.com.br; cliente (67) 99789-0123, "
    masked = mask_text(store, text + "leticia.rocha@jmail.com")
    assert masked == text.replace("(67) 99789-0123", "***0123") + "l***@jmail.com"


def test_same_local_number_in_another_ddd_is_masked(store):
    assert mask_text(store, "(11) 3341-4444") == "***4444"


def test_store_without_contact_policy_masks_everything(store):
    bare = Store(store.categories, store.products, store.customers, store.orders, {}, {})
    assert mask_text(bare, "(67) 3341-4444 contato@emporiodamusica.com.br") == (
        "***4444 c***@emporiodamusica.com.br"
    )
