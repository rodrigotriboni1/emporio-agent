# Empório da Música customer-service agent — design spec

- Date: 2026-11-02
- Status: approved in brainstorming + two grilling rounds; implementation not started
- Deadline: Wednesday 2026-11-04 23:59 BRT (hard cut: no push or PR after it)
- Sources: challenge brief (`desafio_tecnico_ai_eng_artefact.pdf`), store manual
  (`data/politicas_da_loja.pdf`), six CSVs in `data/`, framework research in
  `docs/research/2026-11-02-python-agent-framework.md`

## 1. Goal

A Python text-message agent, "Mel", that serves customers of Empório da Música
(fictional instrument store, Campo Grande/MS). Mel must:

1. keep a persona aligned with the store's identity and tone;
2. answer from the provided data and manual only;
3. know when to query data (catalog, price, stock, order status) and when to
   consult the policy manual (returns, hours, payment, shipping);
4. handle out-of-scope requests politely.

Graders (Artefact) judge logic, clarity, initiative and justified decisions,
and the recruiter asks for "the simplest way possible". Every design choice
below favours the smallest thing that is correct and explainable.

## 2. Non-goals

Router or multi-agent setups, RAG or embeddings, text-to-SQL, persistent
sessions, custom web API, Docker, custom UI, write operations (cart, order changes,
returns), a purchase simulator, a guardrail classifier model, holiday calendar,
local models. Each is named in the README as considered and why it was cut.

## 3. Stack

| Concern | Choice |
|---|---|
| Language / tooling | Python 3.12, `uv`, `pytest`, `ruff`, `pyproject.toml`, `uv.lock` |
| Agent framework | PydanticAI, `pydantic-ai-slim[openrouter,web]` pinned to an exact version |
| LLM provider | OpenRouter only; model from env `MODEL` (e.g. `openrouter:google/gemini-3.8-flash`) |
| Fallback framework | plain `openai` SDK with a hand-written loop, only if the spike fails |
| Interface | PydanticAI's built-in web chat UI (`agent.to_web()`, run with `uv run uvicorn emporio.web:app`) and a CLI (`python -m emporio.cli`) |
| CI | GitHub Actions: `uv sync --frozen`, `ruff check`, `ruff format --check`, `pytest` (no secrets) |

Why PydanticAI (details and sources in the research note): native OpenRouter
provider with no base-URL or API-mode workarounds; a built-in web chat UI for
local use; `UsageLimits` caps LLM calls per turn; typed `ToolCallPart`s make
trajectory assertions short; `TestModel` / `FunctionModel` allow agent tests
without credits; v2 is stable; the slim install pulls no LiteLLM.

Web UI caveat (checked in `pydantic_ai/ui/_web/app.py`, v2.64.0): `to_web()`
takes one `deps` object "for all requests", and the browser sends the message
history with each request. Any per-customer state kept in `deps` would leak
across conversations, so the design keeps no customer state at all (section 9).
The UI front end loads from a CDN by default and is meant for local
development, which matches a prototype. `to_web()` also takes no
`usage_limits` (so a run falls back to the default `request_limit=50`) and
shows `str(error)` to the user; limits and user-facing error texts therefore
live in a `Hooks` capability on the `Agent` itself (section 11), so they hold
in both the CLI and the web UI. The agent is built with
`defer_model_check=True` so it imports without `OPENROUTER_API_KEY` (CI).

Rejected: Google ADK (needs LiteLLM for OpenRouter, 81
packages), OpenAI Agents SDK (Responses API default, tracing to OpenAI,
pre-1.0), Vercel `ai` for Python (beta, no OpenRouter path, no local context),
LangChain/LangGraph (more concepts, OpenRouter package in beta).

### Default model

Chosen by a ~1 hour spike run on the real agent once it exists (PRD US-007),
so the measurements reflect the actual tools and prompt: ~8 scripted prompts (price,
catalog with ceiling, hours, return, accessory, off-topic, injection, order
without verification) against Gemini Flash, Claude Sonnet and DeepSeek on
OpenRouter. Record per model: right tool called, valid args, LLM calls per
turn, latency, cost. The winner is the default in `.env.example`; the table
goes in the README. The spike also confirms that multi-turn history stays
valid for all three, that the model re-sends the customer's credentials on a
follow-up order question, and that the web UI opens and chats via OpenRouter.

## 4. Architecture

Hexagonal in spirit, without the ceremony: a pure functional core and a thin
imperative shell. No `Protocol` ports, no DTOs, no composition root.

```
src/emporio/
├── domain.py    # frozen dataclasses, enums, value objects, pure rules. No I/O.
├── store.py     # loads data/*.csv and data/politicas.md into domain objects;
│                #   queries; load-time invariants
├── search.py    # deterministic product search and same-category alternatives
├── services.py  # use cases: search, policy, order lookup, handoff.
│                #   Authorization is enforced here.
├── agent.py     # PydanticAI Agent, tool wrappers, Deps (clock only)
├── prompt.py    # Mel's instructions
├── web.py       # app = agent.to_web(...)
└── cli.py       # REPL over agent.run_sync with message_history
data/            # products.csv, categories.csv, customers.csv, orders.csv,
                 #   order_items.csv, promotions.csv, politicas_da_loja.pdf, politicas.md
scripts/scenarios.py
tests/
examples/        # generated transcripts (delivered)
```

Dependencies point inward only: `domain` imports nothing from the project;
`store` imports `domain`; `services` imports both; only `agent.py` imports
PydanticAI. The clock is a plain `now: datetime` parameter.

## 5. Clock

One configurable instant, `EMPORIO_NOW`, ISO 8601 with offset. Default
`2026-03-25T10:00-04:00` (a Wednesday, three days after the last order).
`EMPORIO_NOW=now` uses the real clock at `-04:00` (Campo Grande has no DST).
It drives every date computation: return windows, order delay, "are we open
now", next opening time. It is also stated in Mel's instructions ("today is
…") so the model never guesses the date. Holidays are not modelled.

## 6. Domain model

Entities (frozen dataclasses): `Category`, `Product` (id, name, category,
list_price, stock, status, specs), `Promotion` (product, percent, description,
active), `Customer` (id, name, phone, email, city — PII, never leaves the
service layer), `Order` (id, customer, date, status, total, payment, tracking
code, estimated delivery, notes, items), `OrderItem`.

Value objects: `Money` (`Decimal`, half-up, BRL formatting `R$ 1.049,00`),
`Phone` (digits only), `Payment` (parses `credit_6x` → credit, 6 installments),
`ProductStatus` and `OrderStatus` enums (CSV values translated once, in `store`).

Derived, never stored: effective price, PIX price, max installments,
availability, return/warranty windows.

Load-time invariants (fail fast): every foreign key resolves; at most one
active promotion per product. The row counts (65 products, 50 customers, 20
orders, 25 promotions) are asserted by a test on the real data, not at load.
Known data inconsistencies (section 13) are asserted by a test
so the README table stays true to the data.

The README gets a Mermaid ER diagram:
`Category 1–N Product 1–N Promotion (≤1 active)`, `Customer 1–N Order 1–N
OrderItem N–1 Product`.

## 7. Business rules (`domain.py`, all unit-tested)

- **Effective price:** active promotion → promo price, always shown with the
  list price and the % off; no PIX discount on top (manual 6.2). No active
  promotion → list price plus PIX price (−5%, manual 3).
- **Installments (manual 3.1 wins over the summary table in 3):** up to 3x with
  no minimum installment; purchases below R$ 50,00 are not split (reading of
  "exceto abaixo de R$ 50,00"); 4x–6x need installments ≥ R$ 80,00; 7x–12x need
  ≥ R$ 100,00. Max 12x. Cases: 1.199,00 → 11x; 1.200,00 → 12x; 429,90 → 5x;
  349,90 → 4x.
- **Combined payment:** allowed only above R$ 2.000,00.
- **Shipping:** Campo Grande is the only metro city. Metro: free from
  R$ 500,00 (exactly 500 counts as free, documented), else R$ 35,00, 1–3
  business days. Other cities: quoted by CEP via PAC/SEDEX/Jadlog; Mel never
  invents a value. Large instruments may need a special quote.
- **Return and warranty windows** (from `EMPORIO_NOW`; delivery date ≈
  `estimated_delivery`, since there is no delivered-at column):
  - regret (online purchase): 7 days from delivery;
  - exchange by preference: 7 days from delivery (start date assumed);
  - defect exchange: 30 days from order date;
  - legal warranty: 90 days from delivery; after that, manufacturer warranty.
  Mel explains eligibility and hands off; she never approves a return. Manual
  4.4 exclusions (custom setups, "venda final", mouthpieces) have no data flag,
  so they are stated as conditions.
- **Opening hours:** Mon–Fri 09:00–18:00, Sat 09:00–13:00, Sun closed
  (intervals are `[open, close)`). `next_opening(now)` is computed, e.g.
  Saturday 13:30 → Monday 09:00.
- **Product status beats stock:** `discontinued` → "no longer in the catalog"
  plus alternatives (applies to 136 despite stock 13); `coming_soon` →
  "coming soon", not sold, stock not quoted (130); stock 0 → unavailable plus
  alternatives (96). Never promise a reservation (no rain check, manual 6.2).
- **Alternatives:** same category, available, ordered by closeness to the
  product's price; Mel states the gap honestly ("the cheapest bass available
  today is R$ 7.157,00").
- **Promotions:** only active ones affect prices. When asked about an ended one,
  Mel says it ended and gives the current price (manual 7.3).
- **Order total:** `total_brl` is reported as "order value" and never
  recomputed.

## 8. Tools

Four tools with English names and docstrings, scalar parameters, and outputs
that are already computed and formatted. The LLM never does arithmetic. Each
docstring says when to use the tool and when NOT to (e.g. `get_policy` is not
for prices or stock; `search_products` is not for returns or hours), because
data-vs-policy routing (F3) rides on these descriptions. `search_products`
says it already handles accents, typos, plurals and synonyms, so the model
does not retry with variations.

| Tool | Parameters | Returns |
|---|---|---|
| `search_products` | `query=""`, `category=""`, `max_price=""` | up to 8 items, available first, plus "showing 8 of 13"; a single match returns full detail (specs, promotion or ended promotions, PIX price, max installments, availability label) |
| `get_policy` | `topic`: `contact`, `hours`, `payment`, `returns`, `warranty`, `shipping`, `promotions`, `privacy`, `scope` | that section of `data/politicas.md`; `hours` also says whether the store is open now and when it next opens |
| `get_order` | `order_id`, `phone_or_email` | credentials checked on every call; on success: the customer's first name, the order's status explained, tracking code, delay, return and warranty windows, plus the ids of the customer's other orders; on failure: a generic "couldn't find an order with these details" |
| `handoff_to_human` | `reason`, `summary` | protocol number; appends to `handoffs.jsonl` (gitignored); outside hours, says when the team is back |

Search rules (deterministic):

- Normalization: NFKD, strip accents, lowercase, non-alphanumerics to spaces;
  a compact form joins tokens so `gd-20`, `GD 20` and `gd20` match.
- Category synonyms with plurals: violão/violões → Violões; guitarra →
  Guitarras; baixo/contrabaixo → Baixos; bateria/percussão → Baterias e
  Percussão; teclado/piano/sintetizador → Teclados e Pianos; ukulele/uke →
  Ukuleles; sax/flauta/clarinete → Sopro (Madeiras); trompete/trombone →
  Sopro (Metais); violino/viola/violoncelo → Cordas Orquestrais.
- Typos fall back to `difflib.get_close_matches`. An ambiguous query returns
  every match ("martin d28" → 93 and 108).
- `max_price` accepts `1000`, `1.000`, `R$ 1.000,00`; it compares against the
  lowest payable price (promo or PIX). "Violões até R$ 1000" → 13 products,
  including the Giannini GNF-3 CEQ (R$ 1.049,00, R$ 996,55 via PIX).
- No `query` → only active products with stock. With `query` → any status,
  labelled, available first.
- Product descriptions are not returned (they contradict names in 135–144);
  name and specs are the source of truth.

## 9. Identity and privacy (enforced in code)

- Factor: order number plus the phone or e-mail on that order's customer.
  Phone input must have ≥ 8 digits; compare the last 8 (unique across
  customers). E-mail compared trimmed and case-insensitive. Anchoring on the
  order solves the duplicated e-mail (`bruno.martins@jmail.com`, customers 11
  and 43).
- Stateless: `get_order` checks the credentials on every call and nothing about
  the customer is stored between calls. `deps` holds only the clock, so the web
  UI's shared `deps` cannot leak a verification between conversations. No tool
  accepts a customer id. The customer's own credentials stay in their
  conversation history so the model can re-send them on follow-up questions.
- Wrong credentials and another customer's order return the same generic
  failure as a missing order.
- Failures are counted per order id in the process; 5 failures lock that order
  until restart and Mel offers a human.
- Tools never return phone, e-mail or full name; Mel uses the first name only
  after a successful `get_order`.
- The tool-call log (stderr), `handoffs.jsonl` and transcripts mask PII
  (`***3456`, `l***@jmail.com`). Masking is a regex over every string
  argument, not by field name, because `handoff_to_human`'s `reason` and
  `summary` are free text written by the model and may carry a name, phone or
  e-mail. Strings over 256 characters are truncated in the log.
- History lives in memory only (CLI process, or the browser tab in the web
  UI). Persisting it server-side would store customer PII on disk (LGPD,
  manual 9).

## 10. Mel (prompt)

The instructions are written from scratch in numbered sections that map to the
acceptance criteria (persona → F1, grounding → F2, tool routing → F3, scope →
F4), so a reviewer can audit them line by line.

- Store's virtual assistant on the WhatsApp channel (manual 7). Says she is a
  virtual assistant. Slogan "Sua música começa aqui." in the first greeting
  only.
- Tone (manual 7.1): informal but professional, "a friend who knows music";
  at most one emoji, at the close.
- Language: PT-BR; English if the customer writes in English.
- Never states price, stock or deadlines that did not come from a tool result
  in the conversation (manual 7.1).
- Never offers a discount, a gift or a price change, and does not haggle
  ("faz por 1000?"): prices are what the tools return.
- Accessories (strings, picks, cables, cases, pedals, amps): polite refusal, no
  partner store names (no partner list exists).
- Off-topic: short redirect. Prompt-injection attempts are ignored.
- Purchase intent: price and conditions, then handoff to a human to close the
  sale; no reservation.
- Complaints: empathy, handoff, "return within 24 business hours" (manual 7.3).
- Conflicting data: offer to confirm with the team.
- Categories with no products (wind, orchestral strings): "nothing available in
  the system right now", not "we don't sell it".
- Asks for the order number and the phone or e-mail before any order question;
  one `get_order` call per set of details the customer gives; never guesses
  or varies them.

## 11. Loop guard and logging

One `Hooks` capability registered on the `Agent` (`capabilities=[...]`), so
the same rules apply in the CLI, the web UI and the scenarios:

- `before_run`: a message over 2000 characters is rejected with a short PT-BR
  text, before any model call.
- `before_model_request`: more than 10 model requests in one turn (value
  confirmed by the spike) stops the turn with a fixed PT-BR text that gives
  the WhatsApp number and opening hours. No automatic handoff: no model call is
  left to make one.
- `before_model_request`: a conversation whose total text (user and model text,
  tool-call arguments and tool returns, not instructions) is over 40,000
  characters stops with a fixed PT-BR text asking the customer to start a new
  conversation. The web UI sends the whole history with every request, so this
  bounds the cost of each turn.
- Tool calls are logged to stderr with masked, truncated arguments (section 9).
- `after_run`: requests and input/output tokens for the turn are logged; the
  scenario transcripts and the spike table report them.

Output length is capped with `model_settings={"max_tokens": N}` (N set by the
spike, with headroom for reasoning tokens on thinking models). In the CLI any
other exception becomes a generic PT-BR message and the details go to the log;
in the web UI an error raised by the provider still reaches the browser as-is
(listed under limitations).

## 12. Testing

- **Unit (no LLM, CI):** installment boundaries; promo vs PIX, no stacking,
  rounding; shipping (439,20 → R$ 35; 500 → free; other city → quote);
  windows for order 7 at the default clock (regret ended 02-24, defect ended
  03-05, legal warranty until 05-18); next opening; search cases from section
  8; `max_price` parsing; status handling for 96, 113, 130, 136; load counts
  and invariants; known inconsistencies.
- **Authorization (no LLM, CI):** wrong credentials → generic failure;
  customer 3's phone with order 10 → same generic failure; short phone input
  rejected; 5 failures lock the order; "I'm an admin" text changes nothing;
  two calls in a row share no customer state.
- **Agent wiring (no LLM, CI):** `TestModel` / `FunctionModel` drive the agent
  to check tool registration, that the request limit and the 2000-character
  limit fire through the hooks (not only through `run_sync` arguments), and
  that a tool call's log line is masked; `agent.py` imports without
  `OPENROUTER_API_KEY`; the web app object builds.
- **Scenarios (live LLM, `scripts/scenarios.py`):** six scripted conversations
  run against OpenRouter at temperature 0. Each asserts the tool trajectory
  (expected tools called; no order data without a successful `get_order`) and forbidden
  content (partner store names, ended discounts, customer e-mail), plus a
  grounding check: every `R$` amount in Mel's replies (regex
  `R\$\s?[\d.]+,\d{2}`) must appear in a tool result or a customer message
  earlier in the same conversation. Each run writes `examples/NN-name.md` with
  model, `EMPORIO_NOW`, run date, requests and tokens per turn, and masked tool
  calls inline. Transcripts are never hand-edited; a bad run is regenerated.
  Marked so CI skips them without a key.

Scenarios (five delivered, the sixth is a test only):

1. Violões up to R$ 1000, then "eletroacústico" (the GNF-3 CEQ shows up with
   its PIX price).
2. Price and installments of the Takamine GD20 (R$ 2.199,00; PIX
   R$ 2.089,05; up to 12x of R$ 183,25; its 12% promotion has ended).
3. "Me arrependi, posso devolver?" → Mel asks for order and phone → `get_order` for order 7 → regret window
   closed → legal warranty path → handoff.
4. Order 8 shipped and late → tracking code, apology, handoff offer.
5. Accessories, off-topic and injection in one conversation.
6. (test only) Hours, address and payment methods.

## 13. Data inconsistencies (README table, each with the adopted assumption)

Contact: phone (67) 3341-4444 vs WhatsApp (67) 3321-4500 (manual 1.2 vs 7) →
3341-4444 as phone, 3321-4500 as WhatsApp. E-mail with and without accent →
unaccented. Installments: table in 3 vs tiers in 3.1 → 3.1. "Exceto abaixo de
R$ 50" → no split below R$ 50. "300+ instruments" vs 65 products → never
quote 300. Wind and orchestral categories empty. No partner store list. Product
136 discontinued with stock 13 → status wins. Product 130 `coming_soon` but
sold in orders 3 and 14. Names vs descriptions contradict in 135–144 → name and
specs win. Product 96 active with stock 0. Orders 9, 16, 18 break installment
minimums. PIX orders (1, 5, 10, 13, 17) carry no 5% discount; order 11 ignores
an active promotion; orders 3 and 20 totals differ from items → totals reported
as-is. Metro deliveries carry Correios-style tracking codes → carrier never
stated. Duplicate customer e-mail (11, 43). No delivered-at column →
`estimated_delivery` used. No sales-channel column → all orders treated as
online. Start date of exchange by preference unstated → delivery.

## 14. README (English)

Run instructions (`uv sync`, `.env` with `OPENROUTER_API_KEY` and `MODEL`,
`python -m emporio.cli`, `uv run pytest`, `scripts/scenarios.py`); swapping
models; architecture (two axes: code structure vs agent control flow) with the
module diagram and ER diagram; decisions with rejected alternatives; spike
results table; the inconsistency table; a "Considered and rejected: input
guardrail classifier" paragraph (what it would protect is already enforced in
code; an extra serial model call per turn; false positives on short PT-BR
messages like "violao?"; fail-closed vs fail-open dilemma; next step is a
structured-output classifier, fail-open with logging, behind a labelled eval);
limitations (provider errors reach the web UI unformatted; holidays not
modelled) and next steps (persistence with PII controls, RAG if the manual
grows, MCP if another channel needs the tools, real handoff system,
OpenTelemetry via PydanticAI's instrumentation); credit to AlvarDev/sre-genai
for ideas (no code copied);
AI-assistant workflow (brainstorming, grilling, Opus review agents, research
agent, software factory, what was verified by hand); data is fictional and
provided by the challenge; the `factory/` and `.claude/` files are GPLv3
(zazencodes).

## 15. Delivery

- Repo `rodrigotriboni1/emporio-agent`, private until delivery, then public.
- One PR per stage, merge commits only (no squash), Conventional Commits in
  English. Never push to `main` directly.
- Implementation slices run as `factory` issues where useful: domain + tests,
  store + data loading, agent + web UI + CLI, scenarios + README.
- A 1–2 page English PDF with the repo link, solution summary, key decisions
  and run steps, named `Rodrigo Triboni - AI Engineer – Full-Stack para
  Aplicações com IA Generativa.pdf`. The user submits the Google Form.
- Cut order if time runs short: CI, then scenario 6. Tests, the inconsistency
  table and the examples are never cut.

## 16. Acceptance criteria

The agent is done when every item below holds. Each names how it is proven.

**Definition of done, in one line:** the six scenarios pass on the default
model, `factory/checks.sh` is green, and every statement Mel makes about price,
stock, deadlines or orders comes from a tool, never from the model.

### Functional (challenge requirements)

| # | Criterion | Proof |
|---|---|---|
| F1 | Persona: PT-BR (English if the customer writes in English), informal but professional, introduces herself as the store's virtual assistant, slogan only in the first greeting, at most one emoji per message | Scenario transcripts in `examples/` |
| F2 | Grounded answers: no price, stock, deadline or order fact that did not come from a tool result earlier in the conversation; never names a partner store, quotes a shipping value outside Campo Grande, offers an ended promotion's discount, or offers any discount or gift | Scenario forbidden-content assertions + the `R$` grounding check |
| F3 | Data vs policy routing: catalog and price questions call `search_products`; returns, hours, payment, shipping, warranty and privacy questions call `get_policy` with the matching topic; order questions make Mel ask for the order number and phone or e-mail, then call `get_order` | Expected tool trajectory per scenario |
| F4 | Out of scope: accessory requests refused politely, off-topic questions redirected, prompt-injection attempts change nothing | Scenario 5 |

### Correctness

| # | Criterion | Proof |
|---|---|---|
| C1 | Prices: effective price, PIX price (no stacking with promotions), max installments and shipping match section 7, including the documented cases | Unit tests |
| C2 | Windows: regret, preference, defect and legal-warranty dates for order 7 at the default clock are 02-24, 02-24, 03-05 and 05-18 | Unit tests |
| C3 | Hours: open/closed and next opening are right for weekday, Saturday afternoon and Sunday instants | Unit tests |
| C4 | Search: the cases in section 8 return the expected product ids, including "violões até R$ 1000" → 13 ids and "martin d28" → 93 and 108 | Unit tests |
| C5 | Product status beats stock for 96, 113, 130 and 136 | Unit tests |
| C6 | Data loads with the expected counts and invariants, and the known inconsistencies in section 13 are present | Unit tests |

### Security and privacy

| # | Criterion | Proof |
|---|---|---|
| S1 | No order data without valid credentials in the same `get_order` call; no customer state kept between calls; no tool accepts a customer id | Authorization tests |
| S2 | Another customer's order reads exactly like a missing order | Authorization tests |
| S3 | Phone input under 8 digits never verifies; 5 failures lock the order | Authorization tests |
| S4 | No phone, e-mail or full name in tool outputs, stderr logs, `handoffs.jsonl` or `examples/`, including free-text handoff fields | Unit tests on regex masking of every string argument + grep of `examples/` |
| S5 | The web UI keeps no customer state server-side: one conversation's lookup grants nothing in another | Authorization tests + spike check in two browser tabs |
| S6 | A looping turn stops at 10 model requests with the fixed PT-BR message, in both the CLI and the web UI; messages over 2000 characters are rejected before any model call | Agent wiring tests (`FunctionModel`, hooks) |

### Delivery

| # | Criterion | Proof |
|---|---|---|
| D1 | `factory/checks.sh` exits 0 on `main` | CI / local run |
| D2 | Five unedited transcripts in `examples/`, at least one non-trivial (scenarios 3 and 4) | Files with generation header |
| D3 | README covers run steps, decisions with rejected alternatives, spike table, inconsistency table, limitations and the AI-assistant workflow | Review |
| D4 | Repo public with a real PR history and no secrets in any commit | `git log -p` grep for `sk-or` |
| D5 | Delivery PDF exists with the required file name | File |
| D6 | Everything above is pushed before 2026-11-04 23:59 BRT | Commit timestamps |
