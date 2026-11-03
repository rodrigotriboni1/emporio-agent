"""Mel as a PydanticAI agent: four thin tools over services, one Hooks capability for limits."""

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import Hooks
from pydantic_ai.exceptions import SkipModelRequest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from emporio import prompt, services
from emporio.store import load_store

MAX_INPUT_CHARS = 2000
MAX_REQUESTS = 10
LOG_ARG_CHARS = 256

INPUT_TOO_LONG = "Sua mensagem ficou muito longa. Pode enviar uma versão mais curta, por favor?"
TURN_LIMIT_REACHED = (
    "Não consegui concluir seu atendimento agora. Fale com a nossa equipe pelo WhatsApp "
    "(67) 3321-4500, de segunda a sexta das 9h às 18h e aos sábados das 9h às 13h."
)

STORE = load_store()


@dataclass(frozen=True)
class Deps:
    now: Callable[[], datetime]


def _last_user_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in reversed(message.parts):
                if isinstance(part, UserPromptPart):
                    content = part.content
                    if isinstance(content, str):
                        return content
                    return "".join(c for c in content if isinstance(c, str))
    return ""


hooks = Hooks()


@hooks.on.before_model_request
def _limits(ctx: RunContext[Deps], request_context):
    # Limit texts are the run's output, not errors: the web UI shows str(error), the CLI hides it.
    if len(_last_user_text(request_context.messages)) > MAX_INPUT_CHARS:
        raise SkipModelRequest(ModelResponse(parts=[TextPart(INPUT_TOO_LONG)]))
    if ctx.usage.requests >= MAX_REQUESTS:
        raise SkipModelRequest(ModelResponse(parts=[TextPart(TURN_LIMIT_REACHED)]))
    return request_context


@hooks.on.before_tool_execute
def _log_tool(ctx: RunContext[Deps], *, call, tool_def, args):
    # Mask before truncating, so a cut can never leave part of a phone or e-mail unmasked.
    shown = " ".join(
        f"{key}={services.mask_text(STORE, value)[:LOG_ARG_CHARS]!r}"
        for key, value in args.items()
        if isinstance(value, str)
    )
    print(f"[tool] {call.tool_name} {shown}", file=sys.stderr)
    return args


@hooks.on.after_run
def _log_usage(ctx: RunContext[Deps], *, result):
    usage = result.usage
    print(
        f"[turn] requests={usage.requests} input_tokens={usage.input_tokens} "
        f"output_tokens={usage.output_tokens}",
        file=sys.stderr,
    )
    return result


agent = Agent(
    os.environ.get("MODEL", "openrouter:google/gemini-3.8-flash"),
    deps_type=Deps,
    defer_model_check=True,
    model_settings={"max_tokens": 2048},  # placeholder; US-007 tunes it
    capabilities=[hooks],
)


@agent.instructions
def _instructions(ctx: RunContext[Deps]) -> str:
    return prompt.instructions(ctx.deps.now())


@agent.tool_plain
def search_products(query: str = "", category: str = "", max_price: str = "") -> str:
    """Search the store's catalog of musical instruments.

    Use for catalog, product, price, stock and availability questions. Do NOT use for returns,
    hours, payment rules, shipping or orders. The search already handles accents, typos, plurals
    and synonyms, so do not retry with variations of the same query. `max_price` accepts forms
    like `1000` or `R$ 1.000,00`.
    """
    return services.search_products(STORE, query, category, max_price)


@agent.tool
def get_policy(ctx: RunContext[Deps], topic: str) -> str:
    """Return a section of the store's policies.

    Use for store rules and information. Do NOT use for a product's price or stock, nor for a
    specific order. `topic` is one of: contact, hours, payment, returns, shipping, promotions,
    warranty, privacy, scope.
    """
    return services.get_policy(STORE, topic, ctx.deps.now())


@agent.tool
def get_order(ctx: RunContext[Deps], order_id: str, phone_or_email: str) -> str:
    """Look up one order, checking the customer's details on every call.

    Use only after the customer has given both the order number and the phone or e-mail used
    on the order. Make one call per set of details the customer gives. Do NOT guess, invent or
    vary the details, and never reuse another customer's details.
    """
    return services.get_order(STORE, order_id, phone_or_email, ctx.deps.now())


@agent.tool
def handoff_to_human(ctx: RunContext[Deps], reason: str, summary: str) -> str:
    """Hand the conversation to the human team and return a protocol number.

    Use to close a purchase, for complaints, for return or exchange cases, when the order
    lookup is locked, when data conflicts, or when the customer asks for a person. Do NOT use
    for questions another tool answers. `reason` and `summary` are short free text.
    """
    return services.handoff_to_human(
        STORE, reason, summary, ctx.deps.now(), path=services.HANDOFFS_PATH
    )
