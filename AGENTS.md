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

## Validation

Must match `factory/checks.sh`:

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
  they do not import PydanticAI.
- Conventional Commits. Never push to `main`; work on a branch and open a PR.
  PRs merge with a merge commit, never squash.

## Software factory

`/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → gate → review → approve, one PR per issue. State is in
`factory/jobs/` (gitignored); `factory/bin/job` is its only writer. Checks:
`factory/checks.sh`. Dashboard: `cd factory && python3 -m http.server`, then
open http://localhost:8000/dashboard.html.

Each job works in its own git worktree, a full checkout of the repo at
`.worktrees/<job-id>` (gitignored). A tool run from the repo root that doesn't
read `.gitignore` sees those copies too; exclude `.worktrees/` in its config.
