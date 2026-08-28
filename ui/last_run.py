"""Read logs/last_run.json written by morning_auto.bat."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LAST_RUN_PATH = Path("logs") / "last_run.json"


def read_last_run() -> dict[str, Any] | None:
    if not LAST_RUN_PATH.is_file():
        return None
    try:
        data = json.loads(LAST_RUN_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
