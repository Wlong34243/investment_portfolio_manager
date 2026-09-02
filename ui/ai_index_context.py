"""Cached read of data/ai_thematic_index.json for cockpit."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

INDEX_PATH = Path("data/ai_thematic_index.json")
_CACHE: dict[str, Any] = {"data": None, "expires": 0.0, "mtime": None}
_TTL_SEC = 60


def load_ai_index() -> dict[str, Any] | None:
    now = time.time()
    try:
        mtime = INDEX_PATH.stat().st_mtime if INDEX_PATH.exists() else None
    except OSError:
        mtime = None

    if (
        _CACHE["data"] is not None
        and now < _CACHE["expires"]
        and _CACHE["mtime"] == mtime
    ):
        return _CACHE["data"]

    if not INDEX_PATH.exists():
        _CACHE.update({"data": None, "expires": now + _TTL_SEC, "mtime": None})
        return None

    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _CACHE.update({"data": None, "expires": now + _TTL_SEC, "mtime": mtime})
        return None

    _CACHE.update({"data": data, "expires": now + _TTL_SEC, "mtime": mtime})
    return data


def cockpit_ai_panel() -> dict[str, Any]:
    idx = load_ai_index()
    if not idx:
        return {
            "available": False,
            "state": "not_built",
            "message": "AI index not yet built — run `pm ai index --live`",
        }

    rollup = idx.get("rollup") or {}
    entries = idx.get("entries") or []

    # Three distinct states, never merged. An index over zero briefs used to render
    # as "0 new results" with every channel listed quiet, which is indistinguishable
    # from a genuinely quiet week -- it is what the cockpit showed on 2026-08-31
    # while AI ingestion was in fact dead. A file written before ingestion_state
    # existed is treated as stale, not as evidence of a quiet week.
    if not entries or idx.get("ingestion_state") != "ok":
        return {
            "available": False,
            "state": "no_briefs",
            "message": (
                "No AI briefs ingested — the index is empty or stale. "
                "Check `pm podcast batch --track ai` before trusting this panel."
            ),
        }
    catalyst = entries[0] if entries else None

    novelty = rollup.get("novelty") or {}
    new_n = novelty.get("new_result", 0)
    unverified = rollup.get("named_figure_claims_total", 0)

    mentions_exposed = []
    mentions_unheld = []
    mentions_unlisted = []
    for e in entries:
        for x in e.get("exposed") or []:
            mentions_exposed.append(x.get("ticker"))
        for x in e.get("listed_unheld") or []:
            mentions_unheld.append(x.get("ticker"))
        for x in e.get("unlisted") or []:
            mentions_unlisted.append(x)

    from collections import Counter

    exp_c = Counter(mentions_exposed)
    unheld_c = Counter(mentions_unheld)
    unlist_c = Counter(mentions_unlisted)

    def _fmt(counter: Counter) -> str:
        if not counter:
            return "—"
        return " · ".join(f"{t} ({n})" for t, n in counter.most_common(5))

    return {
        "available": True,
        "provenance": "model output",
        "catalyst": catalyst,
        "evidence": f"{new_n} new results · {unverified} unverified figures",
        "mentions_exposed": _fmt(exp_c),
        "mentions_listed_unheld": _fmt(unheld_c),
        "mentions_unlisted": _fmt(unlist_c),
        "quiet": ", ".join(rollup.get("quiet_channels") or []) or "—",
    }
