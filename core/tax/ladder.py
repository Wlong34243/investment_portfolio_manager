"""
3b — Days-to-long-term ladder.

Every open lot's crossing date, sorted by days remaining — not by open date.
No import of lot_relief / Tax Lot Optimizer hierarchy. Structural tests enforce that.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from utils.tax import days_until_long_term


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


@dataclass(frozen=True)
class LotLadderRow:
    ticker: str
    open_date: date
    shares: float
    days_to_lt: int
    crosses_on: date
    already_long_term: bool
    cost_basis_per_share: float | None = None
    account: str | None = None
    is_estimate: bool = True  # open inventory may be reconstructed


def days_to_lt_ladder(
    lots: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    ticker: str | None = None,
) -> list[LotLadderRow]:
    """
    Build the holding-period ladder.

    Each lot dict needs: open_date / acquisition_date / Opened Date, shares / quantity,
    optional ticker, cost_basis_per_share, account.
    Sorted by days_to_lt ascending (already-LT first at 0), then open_date.
    """
    ref = as_of or date.today()
    want = (ticker or "").strip().upper() or None
    rows: list[LotLadderRow] = []
    for lot in lots:
        t = str(lot.get("ticker") or lot.get("Ticker") or "").upper()
        if want and t != want:
            continue
        if not t:
            continue
        open_d = _to_date(
            lot.get("open_date")
            or lot.get("acquisition_date")
            or lot.get("Opened Date")
            or lot.get("Open Date")
            or lot.get("lot_open_date")
        )
        if open_d is None:
            continue
        shares = float(
            lot.get("shares")
            or lot.get("quantity")
            or lot.get("Quantity")
            or 0.0
        )
        if shares <= 1e-9:
            continue
        dlt = days_until_long_term(open_d, ref)
        if dlt is None:
            continue
        crosses = open_d + timedelta(days=366)
        cps = lot.get("cost_basis_per_share") or lot.get("Cost Per Share")
        try:
            cps_f = float(cps) if cps is not None and str(cps).strip() != "" else None
        except (TypeError, ValueError):
            cps_f = None
        rows.append(
            LotLadderRow(
                ticker=t,
                open_date=open_d,
                shares=shares,
                days_to_lt=int(dlt),
                crosses_on=crosses,
                already_long_term=(dlt == 0),
                cost_basis_per_share=cps_f,
                account=str(lot.get("account") or lot.get("Account") or "") or None,
                is_estimate=bool(lot.get("is_estimate", True)),
            )
        )
    rows.sort(key=lambda r: (r.days_to_lt, r.open_date, r.ticker))
    return rows


def nearest_days_to_lt(ladder: list[LotLadderRow]) -> int | None:
    """Smallest days_to_lt among still-short lots; 0 if any already LT; None if empty."""
    if not ladder:
        return None
    short = [r.days_to_lt for r in ladder if not r.already_long_term]
    if short:
        return min(short)
    return 0
