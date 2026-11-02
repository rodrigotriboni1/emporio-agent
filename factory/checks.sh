#!/usr/bin/env bash
# The repo's checks. Exit 0 only when the branch is fit to review.
#
# The gate runs this script from the main checkout with the job's worktree as
# the working directory. Keep it fast, deterministic and non-interactive: no
# watch modes, no prompts, nothing that rewrites files.
set -euo pipefail

uv sync --frozen --quiet
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
