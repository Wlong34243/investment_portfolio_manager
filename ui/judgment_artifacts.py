"""
Read judgment artifacts from disk — the only UI module allowed to glob agent_outputs/judgment.

Never call retrieve_campaign / build_campaign here or in other ui/ modules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

OUTPUT_DIR = Path("agent_outputs/judgment")
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
    if not OUTPUT_DIR.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in OUTPUT_DIR.glob("*lifecycle_*.md"):
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
    # Newest artifact per ticker (dedupe duplicate runs).
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


def newest_artifact(glob_pattern: str) -> Path | None:
    if not OUTPUT_DIR.is_dir():
        return None
    files = sorted(OUTPUT_DIR.glob(glob_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_artifact_bundle(md_path: Path | None) -> dict[str, Any] | None:
    if md_path is None or not md_path.is_file():
        return None
    sidecar = _load_json_sidecar(md_path)
    return {
        "path": str(md_path).replace("\\", "/"),
        "name": md_path.name,
        "sidecar": sidecar or {},
        "has_sidecar": sidecar is not None,
    }


def load_lifecycle_for_ticker(ticker: str) -> dict[str, Any] | None:
    """Newest *lifecycle_<ticker>.md + JSON sidecar for Position Story."""
    t = ticker.upper()
    pattern = f"*lifecycle_{t.lower()}.md"
    md = newest_artifact(pattern)
    if md is None:
        return None
    bundle = load_artifact_bundle(md)
    if bundle is None:
        return None
    sc = bundle.get("sidecar") or {}
    bundle["ticker"] = t
    bundle["computed_at"] = sc.get("computed_at")
    bundle["summary"] = {
        "is_open": sc.get("is_open"),
        "legs": sc.get("legs") or len(sc.get("leg_rows") or []),
        "dwr_degenerate": sc.get("dwr_degenerate", False),
        "dwr": sc.get("dollar_weighted_return_pct"),
        "twr": sc.get("time_weighted_return_pct"),
        "single_entry_cf": sc.get("single_entry_return_pct"),
        "campaign_economic_return": sc.get("campaign_economic_return_pct"),
        "scaling_delta_pct": sc.get("scaling_delta_pct"),
        "scaling_delta_dollars": sc.get("scaling_delta_dollars"),
        "benchmark_vti_cf": sc.get("benchmark_vti_return_pct"),
        "adds_strength": sc.get("adds_into_strength", 0),
        "adds_weakness": sc.get("adds_into_weakness", 0),
        "style_key": sc.get("style_key"),
    }
    return bundle
