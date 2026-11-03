import asyncio
import contextlib
import importlib.util
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from emporio import cli, services, whatsapp
from emporio.agent import HISTORY_TOO_LONG, MAX_HISTORY_CHARS, Deps, agent
from emporio.whatsapp import MAX_CHUNK, MAX_USERS, TEXT_ONLY, Conversations, Inbound, to_whatsapp
from emporio.whatsapp_twilio import Twilio, twilio_signature

models.ALLOW_MODEL_REQUESTS = False

ROOT = Path(__file__).resolve().parents[1]
DEPS = Deps(now=lambda: datetime(2026, 3, 25, 10, 0, tzinfo=timezone(timedelta(hours=-4))))
SID, TOKEN = "AC0123456789abcdef", "test-token"
FROM = "whatsapp:+14155238886"
URL = "https://mel.example.org/whatsapp/twilio"
PHONE = "whatsapp:+5567999998888"
OTHER = "whatsapp:+5511988887777"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(services, "HANDOFFS_PATH", tmp_path / "handoffs.jsonl")
    monkeypatch.setattr(services, "_failures", {})


@pytest.fixture
def sent(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return contextlib.nullcontext()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return requests


def bodies(requests) -> list[str]:
    return [dict(urllib.parse.parse_qsl(r.data.decode()))["Body"] for r in requests]


class Model:
    """A FunctionModel that records what it saw and answers `resposta N`, or raises on demand."""

    def __init__(self, fail: bool = False):
        self.seen: list[list] = []
        self.fail = fail

    def __call__(self, messages, info) -> ModelResponse:
        self.seen.append(messages)
        if self.fail:
            raise RuntimeError(f"provider exploded for {PHONE}")
        return ModelResponse(parts=[TextPart(f"resposta {len(self.seen)}")])


def make_client(conversations: Conversations | None = None):
    middleware = whatsapp.Middleware(Twilio(SID, TOKEN, FROM, URL), DEPS, conversations)
    app = Starlette(routes=[Route("/whatsapp/twilio", middleware.webhook, methods=["POST"])])
    return TestClient(app), middleware


def post(client, sid="SM1", sender=PHONE, body="Oi", media="0", url=URL, signature=None):
    params = [("From", sender), ("To", FROM), ("MessageSid", sid), ("Body", body)]
    params.append(("NumMedia", media))
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if signature is not False:
        headers["X-Twilio-Signature"] = signature or twilio_signature(url, params, TOKEN)
    return client.post("/whatsapp/twilio", content=urllib.parse.urlencode(params), headers=headers)


def test_signed_message_is_acked_and_answered(sent):
    client, _ = make_client()
    model = Model()
    with agent.override(model=FunctionModel(model)):
        response = post(client, body="Vocês têm violão?")
    assert response.status_code == 200
    assert response.text == "<Response/>"
    assert response.headers["content-type"].startswith("text/xml")
    [request] = sent
    assert request.full_url == f"https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json"
    form = dict(urllib.parse.parse_qsl(request.data.decode()))
    assert form == {"From": FROM, "To": PHONE, "Body": "resposta 1"}
    assert request.get_header("Authorization").startswith("Basic ")
    assert "Vocês têm violão?" in str(model.seen[0])


@pytest.mark.parametrize("signature", ["d3Jvbmc=", False])
def test_bad_or_missing_signature_is_403(sent, capsys, signature):
    client, _ = make_client()
    model = Model()
    with agent.override(model=FunctionModel(model)):
        assert post(client, signature=signature).status_code == 403
    assert model.seen == [] and sent == []
    err = capsys.readouterr().err
    assert "[whatsapp]" in err and "5567999998888" not in err


def test_signature_must_use_the_configured_url(sent):
    client, _ = make_client()
    model = Model()
    with agent.override(model=FunctionModel(model)):
        # The URL the test client's request.url shows, not TWILIO_WEBHOOK_URL.
        response = post(client, url="http://testserver/whatsapp/twilio")
    assert response.status_code == 403
    assert model.seen == [] and sent == []


def test_repeated_message_sid_runs_once(sent):
    client, _ = make_client()
    model = Model()
    with agent.override(model=FunctionModel(model)):
        assert post(client, sid="SM9").status_code == 200
        assert post(client, sid="SM9").status_code == 200
    assert len(model.seen) == 1 and len(sent) == 1


def test_users_keep_separate_histories(sent):
    client, _ = make_client()
    model = Model()
    with agent.override(model=FunctionModel(model)):
        post(client, sid="A1", sender=PHONE, body="pergunta de A")
        post(client, sid="B1", sender=OTHER, body="pergunta de B")
        post(client, sid="A2", sender=PHONE, body="segunda de A")
        post(client, sid="B2", sender=OTHER, body="segunda de B")
    a2, b2 = str(model.seen[2]), str(model.seen[3])
    assert "pergunta de A" in a2 and "pergunta de B" not in a2
    assert "pergunta de B" in b2 and "pergunta de A" not in b2
    assert [r.full_url for r in sent] == [sent[0].full_url] * 4
    assert [dict(urllib.parse.parse_qsl(r.data.decode()))["To"] for r in sent] == [
        PHONE,
        OTHER,
        PHONE,
        OTHER,
    ]


def test_history_expires_after_24h_idle(sent):
    now = [0.0]
    client, _ = make_client(Conversations(clock=lambda: now[0]))
    model = Model()
    with agent.override(model=FunctionModel(model)):
        post(client, sid="SM1", body="primeira")
        now[0] += 24 * 3600 - 1
        post(client, sid="SM2", body="segunda")
        now[0] += 24 * 3600
        post(client, sid="SM3", body="terceira")
    assert "primeira" in str(model.seen[1])
    assert "segunda" not in str(model.seen[2]) and len(model.seen[2]) == 1


def test_user_cap_evicts_least_recently_used():
    conversations = Conversations(clock=lambda: 0.0)
    for i in range(MAX_USERS):
        conversations.put(f"u{i}", [i])
    conversations.put("u0", ["again"])
    conversations.put("new", ["n"])
    assert conversations.get("u1") == []
    assert conversations.get("u0") == ["again"] and conversations.get("new") == ["n"]
    assert conversations.get("u2") == [2]


def test_history_too_long_is_sent_and_then_reset(sent):
    big = []
    for _ in range(11):
        big += [ModelRequest(parts=[UserPromptPart("a" * 1999)])]
        big += [ModelResponse(parts=[TextPart("b" * 1999)])]
    assert 2 * 11 * 1999 > MAX_HISTORY_CHARS
    conversations = Conversations()
    conversations.put(PHONE, big)
    client, _ = make_client(conversations)
    model = Model()
    with agent.override(model=FunctionModel(model)):
        post(client, sid="SM1", body="mais uma")
        post(client, sid="SM2", body="recomeço")
    assert bodies(sent) == [HISTORY_TOO_LONG, "resposta 1"]
    assert len(model.seen) == 1 and len(model.seen[0]) == 1


def test_same_user_turns_run_one_after_the_other(sent):
    seen = []

    async def model(messages, info) -> ModelResponse:
        seen.append(messages)
        await asyncio.sleep(0.01)
        return ModelResponse(parts=[TextPart("ok")])

    _, middleware = make_client()

    async def both():
        await asyncio.gather(
            middleware.handle(Inbound(PHONE, "SM1", "primeira mensagem")),
            middleware.handle(Inbound(PHONE, "SM2", "segunda mensagem")),
        )

    with agent.override(model=FunctionModel(model)):
        asyncio.run(both())
    assert "primeira mensagem" in str(seen[1])
    assert middleware._locks == {} and middleware._pending == {}


def test_to_whatsapp_converts_bold_and_headings():
    assert to_whatsapp("# Título\n\n**Violão** Yamaha") == ["Título\n\n*Violão* Yamaha"]
    assert to_whatsapp("### Seção\nTexto") == ["Seção\nTexto"]


def test_to_whatsapp_packs_paragraphs_into_chunks():
    paragraphs = [f"{i} " + "x" * 300 for i in range(9)]
    text = "\n\n".join(paragraphs)
    assert len(text) >= 2500
    chunks = to_whatsapp(text)
    assert len(chunks) > 1
    assert all(0 < len(c) <= MAX_CHUNK for c in chunks)
    assert "\n\n".join(chunks).split("\n\n") == paragraphs


def test_to_whatsapp_hard_splits_a_long_paragraph():
    chunks = to_whatsapp("y" * 2500)
    assert [len(c) for c in chunks] == [1000, 1000, 500]
    assert to_whatsapp("") == [] and to_whatsapp("\n\n \n\n") == []


@pytest.mark.parametrize(("media", "body"), [("1", "olha"), ("0", ""), ("x", "oi")])
def test_non_text_gets_text_only_reply(sent, media, body):
    client, _ = make_client()
    model = Model()
    with agent.override(model=FunctionModel(model)):
        assert post(client, media=media, body=body).status_code == 200
    assert bodies(sent) == [TEXT_ONLY]
    assert model.seen == []


def test_agent_error_sends_generic_message_and_keeps_history(sent, capsys):
    client, _ = make_client()
    model = Model()
    with agent.override(model=FunctionModel(model)):
        post(client, sid="SM1", body="primeira")
        model.fail = True
        post(client, sid="SM2", body="falha")
        model.fail = False
        post(client, sid="SM3", body="terceira")
    assert bodies(sent) == ["resposta 1", cli.GENERIC_ERROR, "resposta 3"]
    assert "primeira" in str(model.seen[2]) and "falha" not in str(model.seen[2])
    err = capsys.readouterr().err
    assert "[whatsapp]" in err and "***8888" in err and "provider exploded" in err
    assert "5567999998888" not in err


def test_send_failure_is_logged_and_does_not_escape(monkeypatch, capsys):
    def broken(request, timeout):
        raise OSError(f"cannot reach Twilio for {PHONE}")

    monkeypatch.setattr(urllib.request, "urlopen", broken)
    _, middleware = make_client()
    with agent.override(model=FunctionModel(Model())):
        assert asyncio.run(middleware.handle(Inbound(PHONE, "SM1", "oi"))) is None
    err = capsys.readouterr().err
    assert "[whatsapp]" in err and "***8888" in err and "cannot reach" in err
    assert "5567999998888" not in err
    assert middleware._locks == {}


def test_dryrun_prints_the_reply(monkeypatch, capsys):
    def no_network(*args, **kwargs):
        raise AssertionError("network call")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    spec = importlib.util.spec_from_file_location("dryrun", ROOT / "scripts" / "whatsapp_dryrun.py")
    dryrun = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dryrun)
    with agent.override(
        model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("Temos!")]))
    ):
        dryrun.main(["Oi, vocês têm violão?"])
    assert capsys.readouterr().out == "Mel: Temos!\n"
