"""Positions list page — held tickers with style/ceiling/signals."""

from __future__ import annotations

from datetime import date
from typing import Any

from core.retrieval.api import TemplateCall, retrieve
from ui.format import weight_to_pct_points
from ui.position_story import BALLAST_TICKERS

OPEN_SIGNAL_TYPES = frozenset(
    {"NEAR_TRIM", "NEAR_ADD", "DISLOCATION", "MISSING_LEVEL", "HOLD_TAX", "ADD_SUSPENDED"}
)


def _safe_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def assemble_positions() -> dict[str, Any]:
    rs = retrieve(
        label="positions",
        caller="ui",
        queries=[
            TemplateCall("holdings_current", {}),
            TemplateCall("decision_view", {}),
        ],
    )
    holdings = rs.tables.get("holdings_current", [])
    decision = rs.tables.get("decision_view", [])

    signals: dict[str, str] = {}
    days_lt: dict[str, Any] = {}
    for row in decision:
        t = str(row.get("Ticker") or row.get("ticker") or "").upper()
        if t and t not in signals:
            signals[t] = str(row.get("Reason") or row.get("reason") or "")
            dlt = row.get("Days_To_LT") or row.get("days_to_lt")
            if dlt not in (None, ""):
                days_lt[t] = dlt

    rows: list[dict[str, Any]] = []
    for h in holdings:
        ticker = str(h.get("ticker") or h.get("Ticker") or "").upper()
        if not ticker or ticker == "CASH_MANUAL":
            continue
        wt = weight_to_pct_points(_safe_float(h.get("weight") or h.get("Weight") or h.get("Weight %")))
        day_raw = h.get("Day Change %") or h.get("day_change_pct") or ""
        unreal_raw = h.get("Unrealized G/L") or h.get("unrealized") or ""
        day_f = _safe_float(str(day_raw).replace("%", "").replace(",", "").strip())
        if day_f is not None and abs(day_f) <= 1.0:
            day_f = day_f * 100
        unreal_f = _safe_float(str(unreal_raw).replace("$", "").replace(",", "").strip())
        cb = _safe_float(h.get("cost_basis") or h.get("Cost Basis"))
        unrealized_pct = None
        if unreal_f is not None and cb and cb != 0:
            unrealized_pct = (unreal_f / cb) * 100.0
        headroom_bar_pct = None
        weight_bar_pct = None
        style = h.get("style") or h.get("Asset Strategy") or ""
        is_ballast = ticker in BALLAST_TICKERS
        ceiling = None
        headroom = None
        if not is_ballast:
            try:
                from utils.thesis_reader import read_thesis_text, thesis_path_for_ticker, get_triggers
                import json
                from pathlib import Path

                text = read_thesis_text(thesis_path_for_ticker(ticker))
                triggers = get_triggers(text=text) if text else {}
                ceiling = _safe_float(triggers.get("style_size_ceiling_pct"))
                if ceiling is None and style:
                    data = json.loads(Path("data/styles.json").read_text(encoding="utf-8"))
                    ceiling = _safe_float(data.get(style, {}).get("size_ceiling_pct"))
                if ceiling is not None and wt is not None:
                    headroom = ceiling - wt
                    weight_bar_pct = min(100.0, max(0.0, (wt / ceiling) * 100.0))
                    headroom_bar_pct = min(100.0, max(0.0, (headroom / ceiling) * 100.0))
            except Exception:
                pass
        rows.append(
            {
                "ticker": ticker,
                "weight": wt,
                "weight_bar_pct": weight_bar_pct,
                "headroom_bar_pct": headroom_bar_pct,
                "style": style,
                "ceiling": ceiling if not is_ballast else None,
                "headroom": headroom if not is_ballast else None,
                "is_ballast": is_ballast,
                "market_value": _safe_float(h.get("market_value") or h.get("Market Value")),
                "day_pct": day_f,
                "day_pct_raw": day_raw,
                "unrealized": unreal_f,
                "unrealized_pct": unrealized_pct,
                "unrealized_raw": unreal_raw,
                "days_to_lt": days_lt.get(ticker, ""),
                "signal": signals.get(ticker, ""),
            }
        )
    rows.sort(key=lambda r: r.get("market_value") or 0, reverse=True)
    return {"positions": rows, "retrieval_hash": rs.retrieval_hash}
