# AGENTS.md

Python CLI customer-service LLM agent ("Mel") for Empório da Música, a fictional
musical-instrument store. Built for the Artefact AI Engineer take-home. Design
notes live in `docs/`.

## Setup (fresh checkout)

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (`.python-version`).

```bash
uv sync
cp .env.example .env   # once it exists; holds OPENROUTER_API_KEY and MODEL
```

Two interfaces, once the agent exists:

- Web chat UI (PydanticAI `to_web`):
  `uv run uvicorn emporio.web:app --host 127.0.0.1 --port <port>`
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
