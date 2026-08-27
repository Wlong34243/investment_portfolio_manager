"""
3a — Open wash-sale window detection.

Pure date arithmetic over Realized_GL loss sales. No Tax Lot Optimizer model.
IRS wash-sale window: 30 calendar days before and after a loss sale. For the
pre-trade surface we report the *forward* half that still constrains a repurchase:
from the loss close date through close_date + 30 days (disallow-through).

A window is OPEN when as_of is on or before the disallow-through date and the
sale was a loss (gain_loss < 0, or ST/LT gain loss sum < 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

WASH_LOOKAHEAD_DAYS = 30


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


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("$", "").strip()
    if not s or s.lower() in ("nan", "none", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_loss_row(row: dict[str, Any]) -> bool:
    """Loss sale: negative G/L, or Schwab wash-sale with positive disallowed loss."""
    gl = _to_float(
        row.get("gain_loss")
        if "gain_loss" in row
        else row.get("Gain Loss $") or row.get("Gain Loss") or row.get("Gain/Loss")
    )
    if gl is not None and gl < -1e-9:
        return True
    st = _to_float(row.get("ST Gain Loss") or row.get("st_gain_loss")) or 0.0
    lt = _to_float(row.get("LT Gain Loss") or row.get("lt_gain_loss")) or 0.0
    if (st + lt) < -1e-9:
        return True
    flagged_raw = str(row.get("Wash Sale") or row.get("wash_sale") or "").strip().upper()
    dis = _to_float(row.get("Disallowed Loss") or row.get("disallowed_loss")) or 0.0
    if flagged_raw in ("TRUE", "YES", "1", "T") and dis > 1e-9:
        return True
    return False


@dataclass(frozen=True)
class WashWindow:
    ticker: str
    loss_close_date: date
    shares: float
    gain_loss: float
    disallow_through: date
    days_open_remaining: int
    wash_sale_flagged: bool  # Schwab already marked Wash Sale on the row
    is_estimate: bool = True  # labelling requirement — not a filing determination

    @property
    def is_open(self) -> bool:
        return self.days_open_remaining >= 0


def open_wash_windows(
    rows: list[dict[str, Any]],
    *,
    ticker: str | None = None,
    as_of: date | None = None,
    only_open: bool = True,
) -> list[WashWindow]:
    """
    Detect wash-sale windows from realized-loss rows.

    Args:
        rows: Realized_GL-shaped dicts (close_date / Closed Date, gain_loss, …).
        ticker: optional filter (upper).
        as_of: reference day (default today).
        only_open: if True, drop windows whose disallow-through is before as_of.
    """
    ref = as_of or date.today()
    want = (ticker or "").strip().upper() or None
    out: list[WashWindow] = []
    for row in rows:
        t = str(row.get("ticker") or row.get("Ticker") or row.get("Symbol") or "").upper()
        if want and t != want:
            continue
        if not t:
            continue
        if not _is_loss_row(row):
            continue
        close = _to_date(
            row.get("close_date")
            or row.get("Closed Date")
            or row.get("Close Date")
            or row.get("Date Sold")
        )
        if close is None:
            continue
        through = close + timedelta(days=WASH_LOOKAHEAD_DAYS)
        remaining = (through - ref).days
        if only_open and remaining < 0:
            continue
        gl = _to_float(
            row.get("gain_loss")
            or row.get("Gain Loss $")
            or row.get("Gain Loss")
            or row.get("Gain/Loss")
        )
        dis = _to_float(row.get("Disallowed Loss") or row.get("disallowed_loss")) or 0.0
        if gl is None or abs(gl) < 1e-12:
            st = _to_float(row.get("ST Gain Loss")) or 0.0
            lt = _to_float(row.get("LT Gain Loss")) or 0.0
            gl = st + lt
        if abs(gl) < 1e-12 and dis > 0:
            gl = -dis  # wash-disallowed loss often zeros Gain Loss $
        shares = abs(_to_float(row.get("shares") or row.get("Quantity")) or 0.0)
        flagged_raw = str(row.get("Wash Sale") or row.get("wash_sale") or "").strip().upper()
        flagged = flagged_raw in ("TRUE", "YES", "1", "T") or dis > 1e-9
        out.append(
            WashWindow(
                ticker=t,
                loss_close_date=close,
                shares=shares,
                gain_loss=float(gl),
                disallow_through=through,
                days_open_remaining=remaining,
                wash_sale_flagged=flagged,
            )
        )
    out.sort(key=lambda w: (w.disallow_through, w.ticker))
    return out
