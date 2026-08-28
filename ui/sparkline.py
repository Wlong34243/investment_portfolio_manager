"""Sparkline data assembly — no retrieval imports."""

from __future__ import annotations

from typing import Any


def _safe_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def sparkline_from_values(values: list[float], *, tail: int = 30) -> dict[str, Any] | None:
    series = [v for v in values[-tail:] if v is not None]
    if len(series) < 2:
        return None
    return {"values": series, "lo": min(series), "hi": max(series)}


def sparkline_from_bars(bars: list[dict[str, Any]], *, tail: int = 30) -> dict[str, Any] | None:
    closes = [_safe_float(b.get("close")) for b in bars[-tail:]]
    closes = [c for c in closes if c is not None]
    if len(closes) < 2:
        return None
    return {"values": closes, "lo": min(closes), "hi": max(closes)}
