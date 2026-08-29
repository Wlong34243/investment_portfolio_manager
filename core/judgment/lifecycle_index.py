"""Lifecycle artifact disk index — glob, dedupe, sidecar presence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.judgment import artifacts

_LIFECYCLE_TICKER_RE = re.compile(r"lifecycle_([A-Za-z0-9]+)\.md$", re.IGNORECASE)


def parse_lifecycle_ticker(path: Path) -> str:
    m = _LIFECYCLE_TICKER_RE.search(path.name)
    return m.group(1).upper() if m else ""


def _load_json_sidecar(md_path: Path) -> dict[str, Any] | None:
    json_path = md_path.with_suffix(".json")
    if not json_path.is_file():
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_lifecycle_artifacts() -> list[dict[str, Any]]:
    if not artifacts.OUTPUT_DIR.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in artifacts.OUTPUT_DIR.glob("*lifecycle_*.md"):
        if "lifecycle_all" in path.name.lower():
            continue
        ticker = parse_lifecycle_ticker(path)
        if not ticker:
            continue
        sidecar = _load_json_sidecar(path)
        legs = int(sidecar.get("legs", 0)) if sidecar else 0
        if not legs:
            text = path.read_text(encoding="utf-8", errors="replace")[:3000]
            m = re.search(r"legs\D*(\d+)", text, re.I)
            if m:
                legs = int(m.group(1))
        items.append(
            {
                "ticker": ticker,
                "path": str(path).replace("\\", "/"),
                "json_path": str(path.with_suffix(".json")).replace("\\", "/"),
                "mtime": path.stat().st_mtime,
                "legs": legs,
                "sidecar": sidecar or {},
            }
        )
    by_ticker: dict[str, dict[str, Any]] = {}
    for item in items:
        t = item["ticker"]
        prev = by_ticker.get(t)
        if prev is None or item["mtime"] > prev["mtime"] or (
            item["mtime"] == prev["mtime"] and item["path"] > prev["path"]
        ):
            by_ticker[t] = item
    items = list(by_ticker.values())
    items.sort(key=lambda x: (-x.get("legs", 0), -x["mtime"]))
    return items


def list_lifecycle_missing_json() -> list[dict[str, Any]]:
    """Newest .md per ticker where .json sibling is absent."""
    out: list[dict[str, Any]] = []
    for item in list_lifecycle_artifacts():
        md = Path(item["path"])
        if md.with_suffix(".json").is_file():
            out.append({"ticker": item["ticker"], "action": "skip", "path": item["path"]})
        else:
            out.append({"ticker": item["ticker"], "action": "run", "path": item["path"], "md_path": md})
    return out
