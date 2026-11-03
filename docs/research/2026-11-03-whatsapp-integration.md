# Connecting Mel to WhatsApp

Research date: 2026-11-03. Deadline: Wed 2026-11-04 23:59 BRT.
Context: `pydantic-ai-slim[openrouter,web]==2.64.0`, Starlette 1.10.0 and uvicorn 0.54.0 (installed versions in `.venv`). `src/emporio/web.py` mounts `agent.to_web()` at `/`. `get_order(order_id, phone_or_email)` checks credentials on every call, and `Deps` holds only a clock. History lives in the CLI process or the browser tab. The graders have no WhatsApp Business account.

Method: every claim links to the source that owns it: Twilio docs, Meta for Developers, PydanticAI docs and the installed 2.64.0 source, the Starlette docs and source, the LGPD text on planalto.gov.br, and ANPD pages. Anything I could not confirm is marked **UNVERIFIED**. Statements about this repo come from reading `src/emporio/*.py`.

---

## 1. TL;DR

**Recommendation: use the Twilio WhatsApp Sandbox with a fast acknowledgement and an async reply (option 2).** The webhook validates `X-Twilio-Signature`, deduplicates on `MessageSid`, and returns an empty TwiML `<Response/>` at once. A Starlette background task then runs the agent and sends the reply through the Twilio Messages REST API.

- **Why not a synchronous TwiML reply (option 1):** Twilio stops waiting after **15 s in total**, and by default it retries **only on connect or TLS failure** ([connection overrides](https://www.twilio.com/docs/usage/webhooks/webhooks-connection-overrides)). A slow turn (up to 10 model requests in `agent.py`) loses the reply silently. Option 2 costs about 15 more lines.
- **Why not Meta Cloud API directly (option 3):** it is official and has no Twilio fee, but setup takes longer: a Meta app, a business portfolio, a short-lived token, Live mode for some webhooks, and a valid TLS endpoint. It is the better **production** target (§6), not the better prototype.
- **Reject the unofficial libraries** (Baileys, Evolution API in Baileys mode, whatsapp-web.js). WhatsApp's Terms forbid "auto-messaging" and access "through automated or other means", and WhatsApp may disable the account ([WhatsApp Terms](https://www.whatsapp.com/legal/terms-of-service)).
- **Graders cannot use any option without their own account.** The deliverable that graders can run is therefore **offline tests with signed fake payloads** plus a **dry-run local simulator**. The owner can record a live sandbox demo.
- **Biggest risk:** Twilio says the Sandbox number "might be temporarily restricted from sending to certain countries, such as **Brazil** or Indonesia" ([sandbox](https://www.twilio.com/docs/whatsapp/sandbox)). Test with a +55 number **today**. The fallback is the Meta test number (option 3), which reuses the same adapter core.

---

## 2. Ranked comparison

| # | Option | Setup / approval | Cost / limits | Webhook timeout & retries | Signature | Grader can try? |
|---|---|---|---|---|---|---|
| 1 | **Twilio Sandbox + async REST reply** | Twilio account; sandbox in the **legacy** Console; each tester sends `join <code>` to +1 415 523 8886; no WABA needed | Billed at standard WhatsApp API rates; trial includes 100 WhatsApp messages; 1 msg / 3 s; join expires after 3 days | 5 s connect, 15 s read and total; 1 retry on connect failure only | HMAC-SHA1, auth token, URL plus sorted params | Only with their own Twilio account. Offline tests otherwise |
| 2 | Twilio Sandbox + sync TwiML | Same | Same | Same. A reply that misses 15 s is lost (error 11200) | Same | Same |
| 3 | Meta Cloud API direct | Meta developer account, app, business portfolio; a test business number is generated automatically; temporary token "expires quickly" | Test numbers have "relaxed messaging limits" and need no payment method for templates; 1,000 free service messages per number per month | No documented timeout; any non-200 is retried "up to 7 days"; duplicates possible | HMAC-SHA256 of the payload with the App Secret, `sha256=` prefix | Only with their own Meta app |
| 4 | 360dialog sandbox (BSP) | Send `START` to their number and get an API key | **One fixed recipient** (your own number); max **25** messages, then HTTP 429; 3 fixed templates | Not researched | Not researched | No (one recipient) |
| 5 | Baileys / Evolution API (Baileys mode) / whatsapp-web.js | Scan a QR code with a personal phone | Free | n/a | n/a | **Do not use**: ToS violation and ban risk |

Sources for the table: [Twilio sandbox](https://www.twilio.com/docs/whatsapp/sandbox), [Twilio overrides](https://www.twilio.com/docs/usage/webhooks/webhooks-connection-overrides), [Twilio security](https://www.twilio.com/docs/usage/webhooks/webhooks-security), [Twilio 11200](https://www.twilio.com/docs/api/errors/11200), [Meta get started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started), [Meta phone numbers](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers), [Meta about the platform](https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform), [Meta pricing](https://developers.facebook.com/docs/whatsapp/pricing), [Meta webhooks overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview), [Graph webhooks](https://developers.facebook.com/docs/graph-api/webhooks/getting-started), [360dialog sandbox](https://docs.360dialog.com/docs/get-started/sandbox), [WhatsApp Terms](https://www.whatsapp.com/legal/terms-of-service).

---

## 3. Findings per option

### 3.1 Twilio (options 1 and 2)

**Setup and the sandbox**
- You activate the sandbox in the legacy Console; trial accounts in the new Console use "Try out WhatsApp" instead. No WhatsApp Business Account or registered sender is needed ([sandbox](https://www.twilio.com/docs/whatsapp/sandbox)).
- Messages reach only users who joined, and anyone else fails with error 63015. "The Sandbox session expires three days after joining." The number "can only send one message every three seconds" (same page).
- You set the webhook in the "When a Message Comes in" field of the Sandbox settings (same page).
- Only three pre-approved templates are available (Appointment Reminders, Order Notifications, Verification Codes). Custom templates need a registered sender (same page).

**Cost**
- Twilio charges $0.005 per message, inbound or outbound, plus Meta's fees. A $0.001 fee applies to messages that end as Failed ([Twilio WhatsApp pricing](https://www.twilio.com/en-us/whatsapp/pricing)).
- That page contradicts itself on whether service messages inside the window are free (see Meta's own rules in §3.2).

**Webhook timeouts and retries**
- The defaults are `ct` = 5000 ms, `rt` = 15000 ms and `tt` = 15000 ms. The retry count `rc` is 1, and the retry policy `rp` is `ct`, meaning connect or TLS failures only. You can override these with a URL fragment such as `#rc=2&rp=5xx`. "Twilio doesn't include the fragment in the signature computation" ([overrides](https://www.twilio.com/docs/usage/webhooks/webhooks-connection-overrides)).
- A timeout surfaces as error 11200, "unable to retrieve a successful response". The 11200 page does not say whether the message is redelivered ([11200](https://www.twilio.com/docs/api/errors/11200)).
- **Consequence for option 1:** a turn that runs past 15 s is simply lost.

**Idempotency**
- "To distinguish retry attempts, use the HTTP header `I-Twilio-Idempotency-Token`" ([overrides](https://www.twilio.com/docs/usage/webhooks/webhooks-connection-overrides)).
- The incoming payload carries `MessageSid`; `SmsSid` and `SmsMessageSid` are deprecated aliases ([webhook request](https://www.twilio.com/docs/messaging/guides/webhook-request)). Deduplicate on `MessageSid`.

**Payload**
- Fields: `From`/`To` as `whatsapp:+E164`, `Body` (up to 1600 characters), `NumMedia`, `MediaUrl{N}`, and the WhatsApp-specific `ProfileName` and `WaId`. "Twilio occasionally adds parameters without advance notice", so validate over **all** received params ([webhook request](https://www.twilio.com/docs/messaging/guides/webhook-request), [security](https://www.twilio.com/docs/usage/webhooks/webhooks-security)).

**Signature**
- Twilio computes HMAC-SHA1 with the auth token as the key, over the full URL followed by the form params sorted by name, with each name and value appended. Decoding or re-encoding the URL breaks it, and Twilio advises "Don't implement your own signature validation" ([security](https://www.twilio.com/docs/usage/webhooks/webhooks-security)).
- The SDK's `RequestValidator` base64-encodes the digest. It checks the URL both with and without the port, because "sig generation on back end is inconsistent" ([source](https://github.com/twilio/twilio-python/blob/main/twilio/request_validator.py)).
- The `twilio` SDK 9.12.0 pulls in `requests`, `aiohttp`, `aiohttp-retry` and `PyJWT` ([PyPI](https://pypi.org/pypi/twilio/json)).
- **Proxies and tunnels:** behind a tunnel, uvicorn sees `http://127.0.0.1:<port>/...` while Twilio signed the public `https://` URL. Validate against a configured `PUBLIC_URL` and never against `request.url`. This is my inference from the algorithm; the security page does not cover proxies.

**Replying**
- **Sync:** return `<Response><Message>…</Message></Response>`. Several `<Message>` verbs send several messages ([TwiML](https://www.twilio.com/docs/messaging/twiml)).
- **Async:** `POST https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json` with HTTP Basic auth and `From`, `To`, `Body` (≤ 1,600 characters) and an optional `StatusCallback` ([Message resource](https://www.twilio.com/docs/messaging/api/message-resource)).
- **Empty acknowledgement:** the TwiML docs document `204` or `200` with an empty `<Response/>` only **for status callbacks** ([TwiML](https://www.twilio.com/docs/messaging/twiml)). That an empty `<Response/>` on an *incoming* message sends nothing follows from it containing no verbs. **UNVERIFIED on a docs page.**

**24-hour window**
- "Customer service windows are valid for 24 hours after the most recently received message." Outside the window you need an approved template ([WhatsApp API](https://www.twilio.com/docs/whatsapp/api)).
- A free-form send after the window closes fails with **63016**. Since 2025-04-01, putting template text in `Body` also fails ([63016](https://www.twilio.com/docs/api/errors/63016)).
- Mel only ever replies to an incoming message, so it is always inside the window.

**Formatting and length**
- WhatsApp supports `*bold*`, `_italic_`, `~strike~` and triple-backtick code ([Twilio message features](https://www.twilio.com/docs/whatsapp/message-features)). Markdown `**bold**`, `#` headings and `[text](url)` links are not in that list, so convert or strip them.
- Twilio caps `Body` at 1,600 characters ([Message resource](https://www.twilio.com/docs/messaging/api/message-resource)). Twilio's help center reportedly gives 1,024 characters for non-template WhatsApp messages, but the page returned 403. **UNVERIFIED.** Split long replies on paragraph boundaries and keep them short.

### 3.2 Meta WhatsApp Cloud API (option 3)

**Setup**
- Create an app with the "Connect with customers through WhatsApp" use case and choose or create a business portfolio. Then generate a temporary token, which "expires quickly and is not suitable for development purposes". For anything lasting, create a system-user token with `whatsapp_business_messaging` ([get started](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)).
- "A test business phone number is generated and registered for you automatically" ([phone numbers](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers)).
- Test numbers "have relaxed messaging limits and don't require a payment method" for templates ([about the platform](https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform)).
- The often-quoted cap of 5 test recipients is **UNVERIFIED**; I found no Meta page that states it.

**Webhook verification and signature**
- Meta first sends a `GET` with `hub.mode=subscribe`, `hub.verify_token` and `hub.challenge`. Check the token and echo the challenge.
- Each `POST` carries `X-Hub-Signature-256: sha256=<hex>`, an HMAC-SHA256 of the payload keyed with the App Secret. Compute it over the **raw body bytes**; the page does not say which bytes are signed ([Graph webhooks](https://developers.facebook.com/docs/graph-api/webhooks/getting-started)).
- The endpoint needs "a valid TLS or SSL certificate"; "Self-signed certificates are not supported" (same page).

**Retries and duplicates**
- The general Graph doc says failed deliveries are retried immediately and then over 36 hours, and "Your server should handle deduplication" ([Graph webhooks](https://developers.facebook.com/docs/graph-api/webhooks/getting-started)).
- The WhatsApp doc says any non-200 response is retried "up to 7 days", and retries "can result in duplicate webhook notifications" ([WA webhooks overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview)). The two windows conflict; trust the WhatsApp page.
- No response timeout is documented. Payloads can be up to 3 MB. Some webhooks are not sent while the app is in Dev mode (same page).

**Payload and dedupe key**
- The path is `entry[].changes[].value.messages[]`, with `from`, `id` (a `wamid.…` value), `timestamp`, `type` and `text.body`. The sender's `wa_id` is in `contacts[]` ([set up webhooks](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks)).
- Meta prescribes no dedupe key; using `id` is my choice.

**Sending and limits**
- Send with `POST graph.facebook.com/<ver>/<PHONE_NUMBER_ID>/messages` and the body `{"messaging_product":"whatsapp","to":…,"type":"text","text":{"body":…}}`. The body is limited to **4096 characters** ([text messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/text-messages)).

**Pricing and the window**
- Pricing has been per message since 2025-07-01. The window is "a 24-hour timer" that resets on each user message.
- Each number gets 1,000 free service messages per month. Service messages have been charged since 2026-10-01, and utility templates sent inside the window have been charged since the same date ([Meta pricing](https://developers.facebook.com/docs/whatsapp/pricing)).

**AI policy**
- Section 4.7 of the Platform terms bars "AI Providers" when AI is "a funcionalidade principal (em vez de incidental ou auxiliar)", as decided by Meta at its sole discretion ([Meta Terms for WhatsApp Business Platform](https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform), last updated 2026-09-23).
- Since 2026-03-11, AI Providers sending to **Brazil** pay per message ([AI providers pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers)).
- A store's own support assistant reads as *incidental* to its business, but that is my reading; Meta has not ruled on it.

### 3.3 Other options (option 4)

- **360dialog sandbox:** you send `START` and receive a `D360-API-KEY`. Each key has "one fixed recipient", a maximum of 25 messages (then HTTP 429), and three fixed templates. The webhook is set with `POST /v1/configs/webhook` and must be HTTPS ([360dialog sandbox](https://docs.360dialog.com/docs/get-started/sandbox)). It is no better than Twilio for a demo, and graders still could not use it.
- **Baileys:** "not affiliated, associated, authorized, endorsed by, or in any way officially connected with WhatsApp" ([README](https://github.com/WhiskeySockets/Baileys)).
- **Evolution API:** offers a Baileys mode, "a free API based on WhatsApp Web", next to the official Cloud API ([README](https://github.com/EvolutionAPI/evolution-api)).
- **WhatsApp Terms:** they forbid "bulk messaging, auto-messaging", access "through automated or other means" in unauthorized ways, and allow "disabling or suspending your account" ([WhatsApp Terms](https://www.whatsapp.com/legal/terms-of-service)). A grader reading "Baileys" in a take-home would rightly mark it as a risk.

---

## 4. Server-side history with PydanticAI

- `result.all_messages()` returns the history including earlier runs, and `new_messages()` returns only the current run. Both have `_json()` variants ([message history](https://pydantic.dev/docs/ai/core-concepts/message-history/)). In 2.64.0, `all_messages_json()` is defined in `pydantic_ai/run.py` and `pydantic_ai/result.py`.
- **Serialization:** "The intended way to do this is using a `TypeAdapter`." Write with `to_json(messages)` (from `pydantic_core`) and read with `ModelMessagesTypeAdapter.validate_json(...)`. A JSON round-trip normalizes some values, such as a tuple reloading as a list ([message history](https://pydantic.dev/docs/ai/core-concepts/message-history/)). `ModelMessagesTypeAdapter` is exported from `pydantic_ai` (`__init__.py`) and defined in `pydantic_ai/messages.py` in 2.64.0.
- For long threads, "store the messages separately and append each run's `new_messages()`" (same page).
- **Trimming:** a `ProcessHistory` processor can keep the last N messages. However, "A slice that separates a tool call from its result no longer reaches the provider that way", so slice on message boundaries (same page).
- **This repo:** `agent.py` already caps history at `MAX_HISTORY_CHARS = 40_000` in a `before_model_request` hook and answers `HISTORY_TOO_LONG` ("Pode começar uma nova conversa"). WhatsApp has no "new conversation" button, so **the store must drop that sender's history when the cap fires**, and on idle TTL. Otherwise the customer is stuck.
- **WhatsApp does not resend history.** Twilio's payload carries a single `Body` ([webhook request](https://www.twilio.com/docs/messaging/guides/webhook-request)), and Meta's carries `messages[]` for the new event only ([set up webhooks](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks)). Server-side history keyed by sender is therefore required.

---

## 5. LGPD implications of history keyed by phone number

Primary source: [Lei 13.709/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm).

- **It is personal data.** "dado pessoal: informação relacionada a pessoa natural identificada ou identificável" (Art. 5 I). A `whatsapp:+55…` key, the `ProfileName`, and any order id, e-mail or address the customer types all qualify. Storing and transmitting them is "tratamento" (Art. 5 X).
- **Legal basis.** Answering the customer's own order or product request fits Art. 7 V, "execução de contrato ou de procedimentos preliminares relacionados a contrato". Anything beyond that, such as analytics or training, needs its own basis. The store's policy already limits use to orders and communication (`data/politicas.md` §privacy).
- **Purpose (Art. 6 I) and necessity (Art. 6 III).** "limitação do tratamento ao mínimo necessário" points to:
  - keeping history only to continue the current conversation;
  - in-memory storage for the prototype;
  - an idle TTL of about 24 h, which also matches the customer-service window, after which free-form replies are impossible anyway;
  - a cap on stored senders;
  - no message bodies or raw phone numbers in logs (`services.mask_text` already exists).
- **Retention and deletion.** Processing ends when "a finalidade foi alcançada" (Art. 15 I), and data "serão eliminados após o término de seu tratamento" (Art. 16). The data subject has rights of access and elimination (Art. 18 II, VI), and the store's policy promises deletion on request. Production therefore needs a delete-by-phone path.
- **Security.** Art. 6 VII and Art. 46 require "medidas de segurança, técnicas e administrativas". In production that means encryption at rest, access control and signature-checked webhooks.
- **Incidents.** These must be reported to the ANPD **and** the data subjects within **3 business days** ([ANPD CIS page](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis), Res. CD/ANPD nº 15/2024, Arts. 6 and 9).
- **Records of processing.** Art. 37 applies.
- **International transfer.** Twilio, Meta, OpenRouter and the LLM vendor all process outside Brazil. Art. 33 allows that only under listed mechanisms, for example "cláusulas contratuais". The ANPD's standard clauses are in [Res. CD/ANPD nº 19/2024](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-19-de-23-de-agosto-de-2024), with 12 months to adopt them. This is a **production contract item**, not code.
- **Transparency (Art. 6 VI).** Mel already says it is a virtual assistant (`prompt.py`), and `get_policy("privacy")` serves the policy.

---

## 6. Recommended minimal design for the prototype

**Module layout.** Add only `src/emporio/whatsapp.py`, plus one route in `web.py`, `tests/test_whatsapp.py` and new keys in `.env.example`. `domain.py`, `services.py` and the tools stay untouched.

- **`web.py`:** `Starlette(routes=[Route("/whatsapp/twilio", whatsapp.webhook, methods=["POST"])], lifespan=_lifespan)`. Routes declared in the constructor match before the `/` mount that the lifespan adds.
  - The mounted `to_web` app keeps its own localhost-only Host check (comment in `web.py`).
  - The WhatsApp route sits outside that mount, so a tunnel's Host header does not reach it.
- **Config (env):** `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` (e.g. `whatsapp:+14155238886`), `WHATSAPP_PUBLIC_URL` (the exact URL set in the Console) and `WHATSAPP_DRY_RUN=1`, which prints replies instead of sending them.
  - With no auth token set, the route answers 404, so there is never an unauthenticated endpoint.

**Endpoint flow (`whatsapp.webhook`)**
1. Read the **raw body** and parse it with `urllib.parse.parse_qsl`.
   - Starlette's `request.form()` needs `python-multipart`, which is not installed (assertion at `starlette/requests.py`, [source](https://github.com/encode/starlette/blob/master/starlette/requests.py)).
2. Validate `X-Twilio-Signature` against `WHATSAPP_PUBLIC_URL` and **all** params. On a mismatch return 403 and log only the reason.
3. Deduplicate on `MessageSid` with a bounded `OrderedDict` (e.g. the last 1,000 ids). On a repeat, acknowledge and do nothing.
4. Return `Response("<Response/>", media_type="text/xml", background=BackgroundTask(handle, sender, body))`. Starlette runs the task "only once the response has been sent" ([Starlette background](https://starlette.dev/background/)).
5. `handle`:
   - Take the sender's `asyncio.Lock`, so two quick messages do not race on the same history.
   - Load the history and run `await agent.run(body, message_history=history, deps=deps)`.
   - Store `result.all_messages()`, or **drop** the history if the output is `HISTORY_TOO_LONG`.
   - Format the reply and send it.
   - On an exception, send the CLI's `GENERIC_ERROR` and log `repr` with the sender masked.
6. Ignore media politely: if `NumMedia > 0`, reply that Mel only reads text. Mel takes no files (`agent.py`).

**History store (in memory, about 25 lines)**

```python
@dataclass
class Conversations:
    ttl_s: float = 24 * 3600            # idle TTL = the WhatsApp service window
    max_senders: int = 500              # LRU cap: bounds memory and stored PII
    clock: Callable[[], float] = time.monotonic   # wall clock, not EMPORIO_NOW; injectable in tests
    _data: OrderedDict[str, tuple[float, list]] = field(default_factory=OrderedDict)

    def get(self, sender: str) -> list:
        seen, msgs = self._data.get(sender, (0.0, []))
        return msgs if self.clock() - seen < self.ttl_s else []

    def put(self, sender: str, msgs: list) -> None:
        self._data[sender] = (self.clock(), msgs)
        self._data.move_to_end(sender)
        while len(self._data) > self.max_senders:
            self._data.popitem(last=False)

    def drop(self, sender: str) -> None:
        self._data.pop(sender, None)
```

Persisting the store later only swaps the dict for `to_json(msgs)` and `ModelMessagesTypeAdapter.validate_json(...)` (§4).

**Signature check (stdlib; mirrors twilio-python's algorithm)**

```python
def twilio_signature(url: str, params: list[tuple[str, str]], token: str) -> str:
    data = url + "".join(k + v for k, v in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()
# valid = hmac.compare_digest(twilio_signature(PUBLIC_URL, params, token), header)
```

This writes a few lines instead of adding the `twilio` SDK and its four extra dependencies. It goes against Twilio's advice not to implement your own check, so pin it with a test vector (see the open questions). The Meta equivalent is `hmac.compare_digest(hmac.new(secret, raw, hashlib.sha256).hexdigest(), header.removeprefix("sha256="))`.

**Outgoing formatting**
- `to_whatsapp(text)` converts `**x**` to `*x*`, strips `#` heading markers, and splits the text into chunks of ≤ 1,600 characters on blank lines.
- Add one line to the prompt asking for WhatsApp formatting and short replies. The sandbox's 1 msg / 3 s makes multi-part replies slow.

**Sending**
- POST to `Messages.json` with `urllib.request` inside `asyncio.to_thread`, so no new dependency is needed. `httpx2` is only a transitive dependency of pydantic-ai, so do not import it directly.
- In dry-run mode, print to stdout instead.

**Keeping the identity rules**
- `Deps` stays `Deps(now=...)`. The sender's phone number goes **neither into deps nor into the prompt**.
- `get_order` still needs the order number **and** the phone or e-mail that the customer types, checked in code on every call.
- The per-order failure lock in `services._failures` is unchanged.
- History is keyed by sender, so one customer's tool results can never appear in another customer's run.
- The README's idea of treating the channel-verified `From` as the credential is a later domain change. It would go through deps, never the model, and stays out of scope here.

**Offline tests (`tests/test_whatsapp.py`, no LLM, no network)**
- Use `models.ALLOW_MODEL_REQUESTS = False` and `agent.override(model=FunctionModel(...))` as in `tests/test_history_cap.py`.
- Use `starlette.testclient.TestClient`, which runs on `httpx2` in this Starlette version, and monkeypatch the sender to collect replies.
- Cases:
  1. A signed fake payload returns 200 and `<Response/>`, and the reply is sent to the right `whatsapp:` address.
  2. A bad or missing signature returns 403, and the model is never called.
  3. The same `MessageSid` twice is processed once.
  4. Two senders keep separate histories: the `FunctionModel` sees only that sender's earlier turns.
  5. After the TTL passes (fake clock), the history is empty.
  6. After `HISTORY_TOO_LONG`, the next message starts fresh.
  7. Formatting and chunking work.
  8. With no token configured, the route returns 404.
  9. The signature function matches a fixed vector.
- **UNVERIFIED:** the tests assume TestClient finishes background tasks before returning.

**How a grader or the owner can try it**
- **Grader, no accounts:** run `uv run pytest -q`. Then run the server with `WHATSAPP_DRY_RUN=1 TWILIO_AUTH_TOKEN=test`, and a small `scripts/whatsapp_simulate.py "Oi, cadê meu pedido?"` that signs a fake payload and POSTs it to localhost. The server prints Mel's reply. This needs only the OpenRouter key the project already uses.
- **Owner, live:**
  1. Twilio account, then the legacy Console and the WhatsApp Sandbox.
  2. Send `join <code>` from your phone.
  3. Expose the port through an HTTPS tunnel (tool choice not researched).
  4. Put `https://<tunnel>/whatsapp/twilio` in "When a message comes in" and set `WHATSAPP_PUBLIC_URL` to the same value.
  5. Record a short video for the README. Check the Brazil restriction first.

---

## 7. What a production version adds

- **A registered sender:** a Twilio WhatsApp sender, or a direct Cloud API number with business verification. Verification improves throughput ([about the platform](https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform)). Direct Cloud API removes the $0.005 per message Twilio fee.
- **A durable queue and workers** (Redis or SQS) with retries, instead of `BackgroundTask`. Starlette notes that a failing task stops the ones after it ([Starlette background](https://starlette.dev/background/)), and a process restart loses in-flight turns.
- **Shared state in Redis or Postgres**, so the app scales horizontally:
  - dedupe keys with a TTL longer than Meta's 7-day retry window;
  - per-sender locks;
  - history, encrypted at rest, with a TTL and a delete-by-phone endpoint (LGPD Art. 18).
- **Approved templates** for anything sent after 24 h, such as handoff follow-ups and order updates (63016). Status callbacks track delivery.
- **For Meta:** mTLS or an IP allowlist for webhooks, and secret rotation ([set up webhooks](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks)).
- **Product and compliance:**
  - per-sender rate limiting;
  - media handling;
  - handoff into a real agent inbox;
  - OpenTelemetry;
  - a DPA and SCCs with Twilio, Meta, OpenRouter and the model vendor (Art. 33, Res. 19/2024);
  - an incident runbook with the 3-business-day notice;
  - a record of processing (Art. 37).
- **Optional:** the sender's `From` as a verified order credential, enforced in `services` and passed through `deps`.

---

## 8. Open questions and unverified claims

1. **Brazil:** is the Twilio Sandbox currently restricted from sending to +55? The docs only say it "might be". Test it live first.
2. **Empty `<Response/>`:** does it on an *incoming* WhatsApp message send nothing and raise no Console warning? It is documented only for status callbacks.
3. **Non-template length:** is the WhatsApp non-template limit on Twilio 1,600 characters (API docs) or 1,024 (help-center article, HTTP 403)? Meta's own text limit is 4,096.
4. **Idempotency token:** is `I-Twilio-Idempotency-Token` stable across retries of the same event? Not stated. `MessageSid` is the safer key.
5. **Signature test vector:** I found no official one. Either add `twilio` as a **dev-only** dependency to cross-check, or compute one vector once with the SDK and freeze it.
6. **Meta test recipients:** the test-number recipient limit (often said to be 5) and token lifetime are not stated on current Meta pages.
7. **Meta retry window:** 36 h (Graph doc) or 7 days (WhatsApp doc). No response timeout is documented.
8. **WhatsApp's own formatting page:** faq.whatsapp.com returned only its title. The formatting list above comes from Twilio. Bulleted lists and quotes are **UNVERIFIED**.
9. **Sandbox bursts:** whether the sandbox queues or rejects bursts above 1 msg / 3 s.
10. **AI Provider status:** whether Meta would treat a store's assistant as an "AI Provider" (Meta's sole discretion).
11. **Twilio pricing page:** it is internally inconsistent on whether service messages are free. Meta's page is the authority.
12. **TestClient:** whether it waits for `BackgroundTask` to finish. Confirm in the first test run.

---

## 9. Sources

**Twilio:**
- https://www.twilio.com/docs/whatsapp/sandbox
- https://www.twilio.com/docs/whatsapp/api
- https://www.twilio.com/docs/whatsapp/message-features
- https://www.twilio.com/docs/usage/webhooks/webhooks-connection-overrides
- https://www.twilio.com/docs/usage/webhooks/webhooks-security
- https://www.twilio.com/docs/messaging/guides/webhook-request
- https://www.twilio.com/docs/messaging/twiml
- https://www.twilio.com/docs/messaging/api/message-resource
- https://www.twilio.com/docs/api/errors/63016
- https://www.twilio.com/docs/api/errors/11200
- https://www.twilio.com/en-us/whatsapp/pricing
- https://github.com/twilio/twilio-python/blob/main/twilio/request_validator.py
- https://pypi.org/pypi/twilio/json

**Meta / WhatsApp:**
- https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
- https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started
- https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers
- https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform
- https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks
- https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview
- https://developers.facebook.com/docs/graph-api/webhooks/getting-started
- https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/text-messages
- https://developers.facebook.com/docs/whatsapp/pricing
- https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers
- https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform
- https://www.whatsapp.com/legal/terms-of-service

**Others:**
- https://docs.360dialog.com/docs/get-started/sandbox
- https://github.com/WhiskeySockets/Baileys
- https://github.com/EvolutionAPI/evolution-api

**PydanticAI and Starlette:**
- https://pydantic.dev/docs/ai/core-concepts/message-history/
- Installed source checked in `.venv`: `pydantic_ai/{__init__,messages,run,result}.py` (2.64.0) and `starlette/{requests,testclient,background}.py` (1.10.0)
- https://starlette.dev/background/

**LGPD / ANPD:**
- https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis
- https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-19-de-23-de-agosto-de-2024
