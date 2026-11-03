"""Runtime config from the environment: `.env` loading and the `EMPORIO_NOW` clock. Stdlib only."""

import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=-4))
DEFAULT_NOW = datetime(2026, 3, 25, 10, 0, tzinfo=TZ)


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (s.strip() for s in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def clock() -> Callable[[], datetime]:
    value = os.environ.get("EMPORIO_NOW", "").strip()
    if not value:
        return lambda: DEFAULT_NOW
    if value == "now":
        return lambda: datetime.now(TZ)
    try:
        fixed = datetime.fromisoformat(value)
    except ValueError:
        fixed = None
    if fixed is None or fixed.tzinfo is None:
        raise ValueError(
            f"Invalid EMPORIO_NOW={value!r}: expected an ISO 8601 datetime with offset "
            "(e.g. 2026-03-25T10:00-04:00) or 'now'"
        )
    return lambda: fixed
