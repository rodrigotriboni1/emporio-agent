"""WhatsApp dry run: one message through the channel core, with replies printed instead of sent.

Needs no Twilio account. It calls the real model, so it spends OpenRouter credits. Run from the
worktree with the key sourced (`set -a; source <main checkout>/.env; set +a`):
`uv run python scripts/whatsapp_dryrun.py "Oi, vocês têm violão?"`
"""

import asyncio
import sys

from starlette.requests import Request
from starlette.responses import Response

from emporio import config, whatsapp
from emporio.agent import Deps


class PrintChannel:
    async def verify(self, request: Request) -> bool:
        return False

    async def parse(self, request: Request) -> list[whatsapp.Inbound]:
        return []

    async def send(self, user_id: str, text: str) -> None:
        print(f"Mel: {text}")

    def ack(self) -> Response:
        return Response()


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit('usage: uv run python scripts/whatsapp_dryrun.py "Oi, vocês têm violão?"')
    middleware = whatsapp.Middleware(PrintChannel(), Deps(now=config.clock()))
    inbound = whatsapp.Inbound(user_id="dryrun", message_id="dryrun-1", text=" ".join(argv))
    asyncio.run(middleware.handle(inbound))


if __name__ == "__main__":
    main(sys.argv[1:])
