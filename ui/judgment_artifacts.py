"""
Read judgment artifacts from disk — UI assembly over core lifecycle index.

Never call retrieve_campaign / build_campaign here or in other ui/ modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.judgment.artifacts import OUTPUT_DIR
from core.judgment.lifecycle_index import (
    list_lifecycle_artifacts,
    list_lifecycle_missing_json,
    parse_lifecycle_ticker,
)
from core.judgment.lifecycle_index import _load_json_sidecar

__all__ = [
    "OUTPUT_DIR",
    "parse_lifecycle_ticker",
    "list_lifecycle_artifacts",
    "list_lifecycle_missing_json",
    "newest_artifact",
    "load_artifact_bundle",
    "load_lifecycle_for_ticker",
]


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
