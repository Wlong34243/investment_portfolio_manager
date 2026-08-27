"""
Open-lot inventory from Transactions buys minus Realized_GL closed lots.

Does NOT use FIFO sell consumption. Each Realized_GL row carries Opened Date —
remove that quantity from the matching buy lot. Remaining buys are open inventory
for the LT ladder. Labelled is_estimate=True because buy-side aggregation can
still disagree with Schwab's internal lot ids.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def _to_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    if not s or s.lower() in ("nan", "none", ""):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _qty(v: Any) -> float:
    try:
        return abs(float(v or 0))
    except (TypeError, ValueError):
        return 0.0


def reconstruct_open_lots_from_realized(
    transactions: list[dict[str, Any]],
    realized: list[dict[str, Any]],
    *,
    ticker: str,
    account: str | None = None,
) -> list[dict[str, Any]]:
    """
    Open lots for `ticker`: buys minus realized closes matched on Opened Date.

    Returns list of dicts: ticker, open_date, shares, cost_basis_per_share,
    account, is_estimate=True, source='txn_minus_realized'.
    """
    t = ticker.strip().upper()
    # open_date -> [remaining_qty, weighted_cost_sum]
    lots: dict[date, list[float]] = {}

    for row in transactions:
        rt = str(row.get("Ticker") or row.get("ticker") or "").upper()
        if rt != t:
            continue
        action = str(row.get("Action") or row.get("action") or "").strip().lower()
        if action not in ("buy", "buy to cover"):
            continue
        od = _to_date(row.get("Trade Date") or row.get("trade_date"))
        if od is None:
            continue
        q = _qty(row.get("Quantity") or row.get("shares"))
        px = abs(float(row.get("Price") or row.get("price") or 0))
        if q <= 0:
            continue
        if od not in lots:
            lots[od] = [0.0, 0.0]
        lots[od][0] += q
        lots[od][1] += q * px

    for row in realized:
        rt = str(row.get("Ticker") or row.get("ticker") or "").upper()
        if rt != t:
            continue
        od = _to_date(
            row.get("Opened Date")
            or row.get("Open Date")
            or row.get("opened_date")
            or row.get("open_date")
        )
        if od is None or od not in lots:
            continue
        q = _qty(row.get("Quantity") or row.get("shares"))
        if q <= 0:
            continue
        take = min(lots[od][0], q)
        if lots[od][0] <= 1e-9:
            continue
        # reduce cost pro-rata
        avg = lots[od][1] / lots[od][0] if lots[od][0] else 0.0
        lots[od][0] -= take
        lots[od][1] -= take * avg

    out: list[dict[str, Any]] = []
    for od, (q, cost_sum) in sorted(lots.items()):
        if q <= 1e-6:
            continue
        cps = (cost_sum / q) if q else 0.0
        out.append(
            {
                "ticker": t,
                "open_date": od,
                "shares": round(q, 6),
                "cost_basis_per_share": round(cps, 4),
                "account": account,
                "is_estimate": True,
                "source": "txn_minus_realized",
            }
        )
    return out
