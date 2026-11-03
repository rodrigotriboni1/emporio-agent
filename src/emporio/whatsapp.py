"""WhatsApp channel core: the `Channel` port, in-memory history and one agent turn per message."""

import asyncio
import re
import sys
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import Response

from emporio import services
from emporio.agent import HISTORY_TOO_LONG, STORE, Deps, agent
from emporio.cli import GENERIC_ERROR

IDLE_TTL_S = 24 * 3600  # the WhatsApp customer-service window
MAX_USERS = 500  # bounds memory and the PII held
MAX_SEEN_IDS = 1000
MAX_CHUNK = 1000  # under Twilio's 1,600 and the reported (unverified) 1,024 for WhatsApp

TEXT_ONLY = (
    "Por enquanto eu só consigo ler mensagens de texto. Pode escrever sua dúvida, por favor?"
)

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"^#{1,6} ", re.MULTILINE)


@dataclass(frozen=True)
class Inbound:
    user_id: str
    message_id: str
    text: str | None  # None for a non-text message (media, location)


class Channel(Protocol):
    """A messaging provider: checks and parses its webhook, acknowledges it, sends replies."""

    async def verify(self, request: Request) -> bool: ...

    async def parse(self, request: Request) -> list[Inbound]: ...

    async def send(self, user_id: str, text: str) -> None: ...

    def ack(self) -> Response: ...


class Conversations:
    """History per user, in memory only, expiring after 24 h idle and capped at 500 users (LRU)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._data: OrderedDict[str, tuple[float, list]] = OrderedDict()

    def get(self, user_id: str) -> list:
        seen, messages = self._data.get(user_id, (None, []))
        if seen is not None and self.clock() - seen >= IDLE_TTL_S:
            del self._data[user_id]
            return []
        return messages

    def put(self, user_id: str, messages: list) -> None:
        self._data[user_id] = (self.clock(), messages)
        self._data.move_to_end(user_id)
        while len(self._data) > MAX_USERS:
            self._data.popitem(last=False)

    def drop(self, user_id: str) -> None:
        self._data.pop(user_id, None)


def to_whatsapp(text: str) -> list[str]:
    text = _HEADING.sub("", _BOLD.sub(r"*\1*", text))
    pieces = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        pieces += [paragraph[i : i + MAX_CHUNK] for i in range(0, len(paragraph), MAX_CHUNK)]
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + 2 + len(piece) <= MAX_CHUNK:
            chunks[-1] += "\n\n" + piece
        else:
            chunks.append(piece)
    return chunks


def _log(line: str) -> None:
    print(f"[whatsapp] {services.mask_text(STORE, line)}", file=sys.stderr)


class Middleware:
    def __init__(
        self, channel: Channel, deps: Deps, conversations: Conversations | None = None
    ) -> None:
        self.channel = channel
        self.deps = deps
        self.conversations = conversations or Conversations()
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: dict[str, int] = {}  # turns running or waiting per user

    async def webhook(self, request: Request) -> Response:
        if not await self.channel.verify(request):
            _log("rejected a webhook with a bad or missing signature")
            return Response(status_code=403)
        tasks = BackgroundTasks()
        for inbound in await self.channel.parse(request):
            if inbound.message_id in self._seen:
                continue
            self._seen[inbound.message_id] = None
            if len(self._seen) > MAX_SEEN_IDS:
                self._seen.popitem(last=False)
            tasks.add_task(self.handle, inbound)
        response = self.channel.ack()
        response.background = tasks
        return response

    async def handle(self, inbound: Inbound) -> None:
        user_id = inbound.user_id
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        self._pending[user_id] = self._pending.get(user_id, 0) + 1
        try:
            async with lock:
                await self._turn(inbound)
        except Exception as error:
            _log(f"turn failed for {user_id}: {error!r}")
        finally:
            self._pending[user_id] -= 1
            if not self._pending[user_id]:
                del self._pending[user_id], self._locks[user_id]

    async def _turn(self, inbound: Inbound) -> None:
        user_id = inbound.user_id
        if inbound.text is None:
            await self.channel.send(user_id, TEXT_ONLY)
            return
        try:
            result = await agent.run(
                inbound.text, message_history=self.conversations.get(user_id), deps=self.deps
            )
        except Exception as error:
            _log(f"agent error for {user_id}: {error!r}")
            await self.channel.send(user_id, GENERIC_ERROR)
            return
        if result.output == HISTORY_TOO_LONG:
            self.conversations.drop(user_id)
        else:
            self.conversations.put(user_id, result.all_messages())
        for chunk in to_whatsapp(result.output):
            await self.channel.send(user_id, chunk)
