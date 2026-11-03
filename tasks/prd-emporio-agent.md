# PRD: Mel, the Empório da Música customer-service agent

> Note: the software factory tooling (`/factory run`) and `factory/checks.sh` are not in this
> repository. The equivalent validation commands are the ones in README's Quickstart.

- Source of truth for behaviour: `docs/superpowers/specs/2026-11-02-emporio-agent-design.md`
  (cited below as "spec §N"). This PRD slices it into stories; where the two
  differ, the spec wins. One ordering change was folded back into the spec:
  the model spike runs on the real agent (US-007) instead of before any agent
  code, so its numbers reflect the actual tools and prompt.
- Deadline: Wednesday 2026-11-04 23:59 BRT. No push or PR after it.
- Execution: the software factory (`/factory run`), one GitHub issue per story,
  `concurrency: 1`, stories in order.

## 1. Introduction

Empório da Música's staff answers every customer message by hand. Mel is a
Python text agent that answers catalog, price, policy and order questions from
the store's CSVs and manual, routes between data and policy correctly, and
declines what is out of scope. It is a take-home for the Artefact AI Engineer
role, judged on logic, clarity, initiative and justified decisions, "in the
simplest way possible".

## 2. Goals

- Every price, stock, deadline and order fact Mel states comes from a tool,
  never from the model (spec §16 definition of done).
- The six scenarios pass on the default model and `factory/checks.sh` is green
  on `main`.
- Order data is only revealed with valid credentials in the same call, with no
  customer state kept anywhere.
- A grader can run Mel in the browser or terminal from the README in under
  5 minutes.
- Everything is merged before the deadline, with one PR per story.

## 3. User stories

Each story is one factory issue and one PR. "Sensitive" stories touch rules the
approver must escalate (spec §15, `.claude/agents/approver.md`), so the user
merges them; the approver may merge the others.

### US-001: Domain core
**Status:** built in PR #9 (issue #7), paused at round 2 with the `Phone` repr
masking already pushed. **Sensitive.**

**Description:** As a developer, I need pure, tested business rules so every
number Mel gives is computed in code.

**Acceptance criteria:**
- [ ] `src/emporio/domain.py` per spec §6–7, no I/O, no project imports
- [ ] Spec §16 C1, C2, C3, C5 and the masking part of S4 proven by pytest
- [ ] `Phone` prints masked (`Phone('***3456')`), with a test
- [ ] `factory/checks.sh` passes

### US-002: Data store
**Description:** As a developer, I need the CSVs and the policy manual loaded
into domain objects with their invariants checked, so the rest of the system
reads trusted data.

**Acceptance criteria:**
- [ ] `src/emporio/store.py` loads `data/*.csv` into domain objects and
  translates CSV status values once
- [ ] Loads `data/politicas.md` into sections keyed by the `## [topic]` headings
  (9 topics)
- [ ] Load fails fast on a broken foreign key or on two active promotions for
  one product (tests with small fixture data)
- [ ] Counts 65 products, 50 customers, 20 orders, 25 promotions (C6)
- [ ] The known inconsistencies in spec §13 are asserted by a test (C6)
- [ ] `factory/checks.sh` passes

### US-003: Product search
**Description:** As a customer, I want to find instruments by name, category or
budget, even with typos and no accents, so I get the right products.

**Acceptance criteria:**
- [ ] Search rules of spec §8 implemented on top of the store: normalization
  and compact form, category synonyms with plurals, `difflib` fallback,
  `max_price` parsing against the lowest payable price, no-query means only
  available products, at most 8 results plus the total, descriptions never
  returned
- [ ] Same-category alternatives ordered by price closeness (spec §7)
- [ ] C4 cases pass: "violões até R$ 1000" → 13 ids incl. 101; "takamine gd-20"
  → 95; "martin d28" → 93 and 108; "VIOLAO", "violoes", "violão" → Violões;
  "1.000" and "R$ 1.000,00" parse as 1000
- [ ] Status handling for 96, 113, 130, 136 in search results (C5)
- [ ] `factory/checks.sh` passes

### US-004: Services (use cases behind the tools)
**Sensitive** (identity and PII).

**Description:** As Mel, I need four use cases that return ready-to-say text,
so the model never computes or authorizes anything.

**Acceptance criteria:**
- [ ] `src/emporio/services.py` with `search_products`, `get_policy(topic)`,
  `get_order(order_id, phone_or_email)` and `handoff_to_human(reason, summary)`
  per spec §8, each returning formatted PT-BR text with BRL amounts
- [ ] `get_policy("hours")` includes open-now and next opening for a given `now`
- [ ] `get_order` is stateless: wrong credentials, another customer's order and
  a missing order give the same generic failure; phone under 8 digits never
  matches; a process-wide counter locks an order after 5 failures (S1–S3)
- [ ] Success output: first name, status explained, tracking code, delay,
  return/warranty windows, other order ids; never phone, e-mail or full name
- [ ] `handoff_to_human` appends a masked record to `handoffs.jsonl` and returns
  a protocol number; outside hours it says when the team is back
- [ ] Regex masking of every string argument, including free-text handoff
  fields (S4)
- [ ] `factory/checks.sh` passes

### US-005: Agent, prompt and hooks
**Sensitive** (persona prompt).

**Description:** As a customer, I want to chat with Mel and get grounded,
in-persona answers, so I can solve my question without waiting for staff.

**Acceptance criteria:**
- [ ] `src/emporio/agent.py`: PydanticAI `Agent` with model from `MODEL`,
  `defer_model_check=True`, `deps` holding only the clock, the four tools
  wrapping `services.py`
- [ ] Tool docstrings say when to use and when NOT to use each tool (spec §8)
- [ ] `src/emporio/prompt.py`: numbered sections mapped to F1–F4 with every
  rule in spec §10, written from scratch
- [ ] One `Hooks` capability (spec §11): 2000-character cap before any model
  call; stop after 10 model requests per turn with the fixed PT-BR message
  (WhatsApp + hours); masked, truncated tool-call log to stderr; requests and
  tokens per turn logged
- [ ] `model_settings` sets `max_tokens`
- [ ] Tests with `TestModel` / `FunctionModel`: tools registered; both limits
  fire through the hooks; tool log line is masked; `agent.py` imports without
  `OPENROUTER_API_KEY` (S6)
- [ ] `factory/checks.sh` passes

### US-006: Web UI and CLI
**Description:** As a grader, I want to talk to Mel in the browser or the
terminal with one command each.

**Acceptance criteria:**
- [ ] `src/emporio/web.py`: `app = agent.to_web(...)` bound for local use;
  `uv run uvicorn emporio.web:app --host 127.0.0.1 --port 7932` serves the chat
- [ ] `src/emporio/cli.py`: REPL over `run_sync` keeping `message_history`;
  any exception becomes a generic PT-BR message with details in the log
- [ ] `.env.example` with `OPENROUTER_API_KEY=`, `MODEL`, `EMPORIO_NOW`; config
  read from env (and `.env` if present)
- [ ] Test: the web app object builds without a key
- [ ] Manual check recorded in `build.md`: one message answered in the web UI
  and one in the CLI against OpenRouter
- [ ] `factory/checks.sh` passes

### US-007: Model spike
**Sensitive** (sets the default model).

**Description:** As the author, I need measured evidence to pick the default
model, so the README justifies the choice with numbers.

**Acceptance criteria:**
- [ ] `scripts/spike.py` runs ~8 scripted prompts (price, catalog with ceiling,
  hours, return, accessory, off-topic, injection, order follow-up with
  credentials re-sent) against Gemini Flash, Claude Sonnet and DeepSeek on
  OpenRouter
- [ ] Records per model: right tool called, valid args, requests per turn,
  tokens, latency, cost; writes `docs/spike-results.md`
- [ ] Confirms multi-turn history stays valid and that a stopped turn behaves
  as spec §11 says
- [ ] Sets the chosen default in `.env.example` and the request/`max_tokens`
  values if the spike changes them
- [ ] `factory/checks.sh` passes (the script itself is not run in CI)

### US-008: Scenarios and example transcripts
**Sensitive** (examples are a deliverable).

**Description:** As a grader, I want real, unedited conversations that show Mel
handling trivial and non-trivial cases.

**Acceptance criteria:**
- [ ] `scripts/scenarios.py` runs the six scenarios of spec §12 at temperature
  0 on the default model
- [ ] Asserts per scenario: expected tool trajectory, forbidden content, no
  order data without a successful `get_order`, and the `R$` grounding check
- [ ] Writes `examples/01-…md` to `05-…md` (scenario 6 is test only) with
  model, `EMPORIO_NOW`, run date, requests/tokens per turn and masked tool calls
- [ ] All six pass; transcripts are not hand-edited
- [ ] A pytest marker skips the live run in CI without a key

### US-009: README and CI
**Description:** As a grader, I want a README that explains how to run Mel and
why every decision was made.

**Acceptance criteria:**
- [ ] README covers everything in spec §14, including the spike table, the
  inconsistency table (spec §13), the guardrail "considered and rejected"
  paragraph, limitations, next steps and the AI-assistant workflow
- [ ] Mermaid module and ER diagrams
- [ ] `.github/workflows/ci.yml` runs `factory/checks.sh` steps on push and PR
  without secrets (first item cut if time runs short)
- [ ] `factory/checks.sh` passes

### US-010: Delivery (outside the factory)
Done by the user and Claude in the session, after US-009 merges.

- [ ] `git log -p | grep sk-or` finds nothing
- [ ] Repo made public
- [ ] English delivery PDF with the required file name (spec §15)
- [ ] User submits the Google Form

## 4. Functional requirements

- FR-1: All money and date rules are computed in `domain.py` and unit-tested
  (spec §7).
- FR-2: Data is loaded from `data/` with load-time invariants (spec §6).
- FR-3: Search is deterministic and follows spec §8.
- FR-4: The model sees exactly four tools: `search_products`, `get_policy`,
  `get_order`, `handoff_to_human`.
- FR-5: `get_order` checks credentials on every call; no customer state exists
  between calls; `deps` holds only the clock (spec §9).
- FR-6: No phone, e-mail or full name appears in tool outputs, logs,
  `handoffs.jsonl` or `examples/`.
- FR-7: A single `Hooks` capability enforces the input cap, the per-turn request
  limit and masked logging in both interfaces (spec §11).
- FR-8: Mel replies in PT-BR (English when the customer writes in English)
  following spec §10.
- FR-9: The web UI and the CLI run from one command each.
- FR-10: The clock is `EMPORIO_NOW` (default `2026-03-25T10:00-04:00`).

## 5. Non-goals

Everything in spec §2, plus: an LLM input guardrail classifier, a post-RAG
drift filter, MCP, OpenTelemetry, persistent sessions, a custom front end,
deployment.

## 6. Design considerations

- PydanticAI's built-in web chat UI is the interface; no custom UI.
- Mel's output style: short messages, BRL amounts like `R$ 1.049,00`, at most
  one emoji.

## 7. Technical considerations

- Stack and pins per spec §3: Python 3.12, `uv`,
  `pydantic-ai-slim[openrouter,web]` pinned exactly.
- Factory jobs run in `.worktrees/<job-id>`, where `.env` is absent. Live
  stories (US-006 manual check, US-007, US-008) load the key with
  `set -a; source <main checkout>/.env; set +a` and must never print it,
  write it to a file or commit it.
- Stories run in order; each starts from `main` after the previous one is
  merged. Sensitive stories wait for the user's merge.
- Unit tests never call an LLM; only US-007 and US-008 spend credits.

## 8. Success metrics

- `factory/checks.sh` green on `main`; all spec §16 criteria checked.
- Six scenarios pass on the default model; zero ungrounded `R$` amounts.
- Median turn under ~5 s on the default model (measured in the spike).
- Merged before 2026-11-04 23:59 BRT.

## 9. Open questions

- Issue #8 currently bundles US-002 to US-004. Proposal: close it and open one
  issue per story from this PRD.
- If the spike shows none of the three models handles the tools reliably, fall
  back to the plain `openai` loop (spec §3) — that would be a new story.
