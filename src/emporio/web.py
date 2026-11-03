"""Web chat UI: `uv run uvicorn emporio.web:app --host 127.0.0.1 --port 7932`."""

from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Route

from emporio import config, whatsapp, whatsapp_twilio
from emporio.agent import Deps, agent

deps = Deps(now=config.clock())
twilio = whatsapp_twilio.from_env()  # None unless all four TWILIO_* vars are set
routes = (
    [Route("/whatsapp/twilio", whatsapp.Middleware(twilio, deps).webhook, methods=["POST"])]
    if twilio
    else []
)


@asynccontextmanager
async def _lifespan(app: Starlette):
    # to_web builds the model's provider, which needs OPENROUTER_API_KEY, so build at server start
    # rather than at import. The mounted app keeps its own Host check (localhost and IPs only).
    app.mount("/", agent.to_web(deps=deps))
    yield


app = Starlette(routes=routes, lifespan=_lifespan)
