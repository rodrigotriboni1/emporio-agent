"""Twilio adapter for the WhatsApp channel. Stdlib plus Starlette only: no Twilio SDK."""

import asyncio
import base64
import hashlib
import hmac
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from starlette.requests import Request
from starlette.responses import Response

from emporio.whatsapp import Inbound

MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{}/Messages.json"
SEND_TIMEOUT_S = 10
ENV_KEYS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "TWILIO_WEBHOOK_URL")


def twilio_signature(url: str, params: list[tuple[str, str]], token: str) -> str:
    data = url + "".join(k + v for k, v in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


async def _params(request: Request) -> list[tuple[str, str]]:
    # request.form() needs python-multipart, which is not installed; parse the raw body instead.
    return urllib.parse.parse_qsl((await request.body()).decode(), keep_blank_values=True)


def _post(request: urllib.request.Request) -> None:
    with urllib.request.urlopen(request, timeout=SEND_TIMEOUT_S):
        pass


@dataclass(frozen=True)
class Twilio:
    account_sid: str
    auth_token: str = field(repr=False)
    from_number: str  # e.g. whatsapp:+14155238886
    webhook_url: str  # the exact URL set in the Twilio Console

    async def verify(self, request: Request) -> bool:
        header = request.headers.get("X-Twilio-Signature")
        if header is None:
            return False
        try:
            params = await _params(request)
        except UnicodeDecodeError:
            return False
        # Sign the configured URL, never request.url: behind a tunnel the server sees another one.
        expected = twilio_signature(self.webhook_url, params, self.auth_token)
        return hmac.compare_digest(expected.encode(), header.encode())

    async def parse(self, request: Request) -> list[Inbound]:
        fields = dict(await _params(request))
        user_id, message_id = fields.get("From"), fields.get("MessageSid")
        if not user_id or not message_id:
            return []
        body = fields.get("Body", "")
        try:
            is_text = int(fields.get("NumMedia", "0")) <= 0 and body.strip() != ""
        except ValueError:
            is_text = False
        return [Inbound(user_id, message_id, body if is_text else None)]

    async def send(self, user_id: str, text: str) -> None:
        data = urllib.parse.urlencode({"From": self.from_number, "To": user_id, "Body": text})
        request = urllib.request.Request(MESSAGES_URL.format(self.account_sid), data=data.encode())
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        request.add_header("Authorization", f"Basic {auth}")
        await asyncio.to_thread(_post, request)

    def ack(self) -> Response:
        return Response("<Response/>", media_type="text/xml")


def from_env() -> Twilio | None:
    values = [os.environ.get(key, "").strip() for key in ENV_KEYS]
    return Twilio(*values) if all(values) else None
