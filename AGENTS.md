# AGENTS.md

Python CLI customer-service LLM agent ("Mel") for Empório da Música, a fictional
musical-instrument store. Built for the Artefact AI Engineer take-home. Design
notes live in `docs/`.

## Setup (fresh checkout)

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (`.python-version`).

```bash
uv sync
cp .env.example .env   # holds OPENROUTER_API_KEY, MODEL and EMPORIO_NOW
```

`EMPORIO_NOW` sets the store clock: ISO 8601 with offset (default
`2026-03-25T10:00-04:00`) or `now` for the real clock at `-04:00`.

Two interfaces, run from the repo root (both read `.env` there):

- Web chat UI (PydanticAI `to_web`):
  `uv run uvicorn emporio.web:app --host 127.0.0.1 --port 7932`
- CLI: `uv run python -m emporio.cli`

Model spike: `uv run python scripts/spike.py` compares the candidate models live on
OpenRouter, so it spends credits and never runs in CI. Source the key from the main
checkout's `.env` first (`set -a; source <main checkout>/.env; set +a`). It writes
`docs/spike-results.md`, which is generated and never edited by hand.

Scenarios: `uv run python scripts/scenarios.py` runs Mel's six scripted conversations live
on the default model and checks them, so it spends credits and never runs in CI. Source the
key from the main checkout's `.env` the same way. It writes `examples/01-…` to `05-…` for
the scenarios that pass; they are generated and never edited by hand. The same run as a
test: `uv run pytest -m live` (deselected by default, skipped without the key).

WhatsApp dry run: `uv run python scripts/whatsapp_dryrun.py "Oi, vocês têm violão?"` feeds one
message through the WhatsApp core and prints Mel's reply; it needs no Twilio account but calls
the real model, so it spends credits. Source the key the same way.

## Validation

Same commands as CI:

```bash
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
```

Unit tests never call an LLM. Never commit `.env` or any API key.

## Conventions

- Code, identifiers, comments, commits and docs in English. Mel's replies to
  customers are PT-BR (English if the customer writes in English);
  `data/politicas.md` stays in PT.
- `src/emporio/domain.py` is the pure core: no I/O, no imports from other
  `emporio` modules, and time is always passed in as `now`.
- `src/emporio/store.py` loads `data/` into domain objects and checks the
  load-time invariants; it imports only `domain`.
- `src/emporio/search.py` is the deterministic product search over the `Store`;
  it imports only `domain` and `store`.
- `src/emporio/services.py` holds the use cases behind Mel's tools: it returns
  PT-BR text, enforces order authorization and PII masking, and imports only
  `domain`, `store` and `search`.
- `src/emporio/agent.py` is the only module that imports PydanticAI. Its four tools are
  thin wrappers over `services`; `deps` holds only the clock; one `Hooks` capability holds
  the input, conversation and request limits and the stderr logging.
- `src/emporio/prompt.py` holds Mel's instructions, written in English and telling Mel to
  reply in PT-BR, in sections F1 to F4. It does not import PydanticAI.
- `src/emporio/config.py` is stdlib only: it loads `.env` (real env vars win) and turns
  `EMPORIO_NOW` into the clock in `Deps`.
- `src/emporio/web.py` and `src/emporio/cli.py` are thin entry points over `agent` and `Deps`;
  they do not import PydanticAI. `web.py` adds the `POST /whatsapp/twilio` route only when all
  four `TWILIO_*` env vars are set.
- `src/emporio/whatsapp.py` is the shared WhatsApp channel core and holds the `Channel` port
  (the one `Protocol` in the code): in-memory history, dedupe, per-user locks, formatting and
  one agent turn per message. It does not import PydanticAI, and every log line that can hold a
  phone goes through `services.mask_text`.
- `src/emporio/whatsapp_twilio.py` is the Twilio adapter: it imports only the stdlib, Starlette
  and `whatsapp`, and checks the signature against `TWILIO_WEBHOOK_URL`, never `request.url`.
- Conventional Commits. Never push to `main`; work on a branch and open a PR.
  PRs merge with a merge commit, never squash.

## Software factory

The code was built with a local software factory (`factory/`, `.claude/agents/`,
`.claude/skills/factory/`). That tooling is gitignored and not part of this repository;
where it exists, `/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → gate → review → approve, one PR per issue.

Each factory job works in its own git worktree, a full checkout of the repo at
`.worktrees/<job-id>` (gitignored). A tool run from the repo root that doesn't
read `.gitignore` sees those copies too; exclude `.worktrees/` in its config.
