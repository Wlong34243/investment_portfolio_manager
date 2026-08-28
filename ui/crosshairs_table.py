"""Crosshairs row shaping — shared by cockpit and /decision."""

from __future__ import annotations

from typing import Any

from core.retrieval.api import TemplateCall, retrieve
from tasks.build_crosshairs import REASON_NEAR_TRIM

TRIM_REASONS = frozenset({REASON_NEAR_TRIM, "HOLD_TAX", "NEAR_TRIM"})


def crosshair_row(rec: dict[str, Any], *, rank: int | None = None) -> dict[str, Any]:
    reason = str(rec.get("reason_code") or rec.get("Reason") or rec.get("reason") or "")
    ticker = str(rec.get("Ticker") or rec.get("ticker") or "").upper()
    trim_side = reason in TRIM_REASONS or "TRIM" in reason.upper()
    if not trim_side and reason:
        trim_side = "TRIM" in reason or reason in ("NEAR_TRIM", "HOLD_TAX")
    days_to_lt = rec.get("days_to_lt") if rec.get("days_to_lt") is not None else rec.get("Days_To_LT")
    wash = rec.get("wash_window") or rec.get("Wash_Window") or ""
    est_lo = rec.get("est_tax_cost_low") if rec.get("est_tax_cost_low") is not None else rec.get("Est_Tax_Low (ESTIMATE)")
    est_hi = rec.get("est_tax_cost_high") if rec.get("est_tax_cost_high") is not None else rec.get("Est_Tax_High (ESTIMATE)")
    dist_trim = rec.get("dist_trim") if rec.get("dist_trim") is not None else rec.get("->Trim %")
    dist_add = rec.get("dist_add") if rec.get("dist_add") is not None else rec.get("->Add %")
    from ui.format import fmt_dist_pct, fmt_money_range

    dist_val = dist_trim if trim_side else dist_add
    r = rec.get("rank") if rec.get("rank") is not None else rec.get("Rank")
    if rank is not None:
        r = rank
    return {
        "rank": r if r is not None else 0,
        "ticker": ticker,
        "reason": reason,
        "signal": reason or rec.get("override_tag") or "—",
        "dist_trim": dist_trim,
        "dist_add": dist_add,
        "dist_display": fmt_dist_pct(dist_val),
        "dist_val": dist_val,
        "price": rec.get("price") or rec.get("Price") or "",
        "trim_side": trim_side,
        "days_to_lt": days_to_lt if trim_side else None,
        "wash_window": wash if trim_side else "",
        "est_tax_low": est_lo if trim_side else None,
        "est_tax_high": est_hi if trim_side else None,
        "est_tax_display": fmt_money_range(est_lo, est_hi) if trim_side else "",
    }


def assemble_decision() -> dict[str, Any]:
    rs = retrieve(
        label="decision",
        caller="ui",
        queries=[TemplateCall("decision_view", {})],
    )
    decision = rs.tables.get("decision_view", [])
    rows = [crosshair_row(r, rank=i + 1) for i, r in enumerate(decision)]
    return {
        "rows": rows,
        "count": len(rows),
        "retrieval_hash": rs.retrieval_hash,
    }
