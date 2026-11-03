import asyncio
import importlib

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from emporio import web, whatsapp_twilio
from emporio.whatsapp_twilio import ENV_KEYS, Twilio, from_env, twilio_signature


def test_signature_matches_twilio_sdk_vector():
    # The vector from twilio-python's own tests/unit/test_request_validator.py
    # (ValidationTest.test_compute_signature), not computed by this implementation.
    url = "https://mycompany.com/myapp.php?foo=1&bar=2"
    params = [
        ("CallSid", "CA1234567890ABCDE"),
        ("Digits", "1234"),
        ("From", "+14158675309"),
        ("To", "+18005551212"),
        ("Caller", "+14158675309"),
    ]
    assert twilio_signature(url, params, "12345") == "RSOYDt4T1cUTdK1PDd93/VVr8B8="


def _request(body: bytes, headers: dict[str, str]) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "POST", "headers": raw}, receive)


TWILIO = Twilio("AC123", "token", "whatsapp:+14155238886", "https://example.org/whatsapp/twilio")


def test_blank_params_are_signed_and_undecodable_body_is_rejected():
    params = [("Body", ""), ("From", "whatsapp:+5511")]
    signature = twilio_signature(TWILIO.webhook_url, params, "token")
    request = _request(b"Body=&From=whatsapp%3A%2B5511", {"X-Twilio-Signature": signature})
    assert asyncio.run(TWILIO.verify(request))
    request = _request(b"\xff\xfe", {"X-Twilio-Signature": signature})
    assert not asyncio.run(TWILIO.verify(request))


def test_parse_needs_from_and_message_sid():
    request = _request(b"From=whatsapp%3A%2B5511&Body=oi", {})
    assert asyncio.run(TWILIO.parse(request)) == []


def test_auth_token_is_not_in_repr():
    assert "token" not in repr(TWILIO).replace("auth_token", "")


def _set_env(monkeypatch, **overrides):
    values = {
        "TWILIO_ACCOUNT_SID": "AC123",
        "TWILIO_AUTH_TOKEN": "token",
        "TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886",
        "TWILIO_WEBHOOK_URL": "https://example.org/whatsapp/twilio",
    }
    for key, value in {**values, **overrides}.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("key", ENV_KEYS)
def test_from_env_needs_all_four(monkeypatch, key):
    _set_env(monkeypatch, **{key: "  "})
    assert from_env() is None
    monkeypatch.delenv(key)
    assert from_env() is None


def test_from_env_builds_the_channel(monkeypatch):
    _set_env(monkeypatch)
    assert from_env() == TWILIO


def test_route_exists_only_when_configured(monkeypatch):
    try:
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        importlib.reload(web)
        assert TestClient(web.app).post("/whatsapp/twilio").status_code == 404

        _set_env(monkeypatch)
        importlib.reload(web)
        assert isinstance(web.twilio, whatsapp_twilio.Twilio)
        # The route exists: an unsigned POST is refused by the signature check, not unrouted.
        assert TestClient(web.app).post("/whatsapp/twilio").status_code == 403
    finally:
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        importlib.reload(web)
