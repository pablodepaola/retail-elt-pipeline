"""Watermark state management for incremental, idempotent extraction.

The watermark is the high-water mark of the *business event date* we have landed.
Stored as JSON so it is trivially inspectable and diffable. Persisted between
scheduled runs via GitHub Releases / artifacts (see CD workflow).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from . import config


_DATE_FMT = "%Y-%m-%d"


@dataclass
class Watermark:
    last_loaded_date: str | None = None  # inclusive high-water mark (YYYY-MM-DD)
    last_run_at: str | None = None
    runs: int = 0

    @property
    def last_loaded(self) -> date | None:
        if not self.last_loaded_date:
            return None
        return datetime.strptime(self.last_loaded_date, _DATE_FMT).date()


def load_watermark(path: Path | None = None) -> Watermark:
    path = path or config.STATE_PATH
    if not path.exists():
        return Watermark()
    data = json.loads(path.read_text())
    return Watermark(**data)


def save_watermark(wm: Watermark, path: Path | None = None) -> None:
    path = path or config.STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    wm.last_run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(asdict(wm), indent=2, sort_keys=True) + "\n")


def advance(wm: Watermark, new_high: date) -> Watermark:
    """Move the watermark forward only (monotonic). Re-running an old date never
    moves it backward, which keeps backfills safe."""
    current = wm.last_loaded
    if current is None or new_high > current:
        wm.last_loaded_date = new_high.strftime(_DATE_FMT)
    wm.runs += 1
    return wm
