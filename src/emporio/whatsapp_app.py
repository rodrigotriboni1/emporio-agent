"""WhatsApp webhook only, the app to expose through a tunnel:
`uv run uvicorn emporio.whatsapp_app:app --host 127.0.0.1 --port 7933`.

It serves `POST /whatsapp/twilio` and nothing else, so the chat UI (`emporio.web`) never shares
a public port with it.
"""

from starlette.applications import Starlette
from starlette.routing import Route

from emporio import config, whatsapp, whatsapp_twilio
from emporio.agent import Deps

deps = Deps(now=config.clock())
twilio = whatsapp_twilio.from_env()  # None unless all four TWILIO_* vars are set
routes = (
    [Route("/whatsapp/twilio", whatsapp.Middleware(twilio, deps).webhook, methods=["POST"])]
    if twilio
    else []
)
app = Starlette(routes=routes)
