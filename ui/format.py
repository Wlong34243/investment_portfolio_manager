"""Jinja formatting filters — no raw model values in templates."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def _f(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def fmt_pct(val: Any, *, fractional: bool = True) -> str:
    """Signed percent, 1 dp. Input fractional (0.066) or percent (6.6) when fractional=False."""
    v = _f(val)
    if v is None:
        return "—"
    if fractional:
        v *= 100.0
    sign = "+" if v > 0 else ""
    if v == 0:
        sign = ""
    return f"{sign}{v:.1f}%"


def fmt_money(val: Any) -> str:
    v = _f(val)
    if v is None:
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1_000_000:
        return f"{sign}${av / 1_000_000:.1f}M"
    if av >= 10_000:
        return f"{sign}${av:,.0f}"
    return f"{sign}${av:,.2f}"


def fmt_money_range(lo: Any, hi: Any, *, suffix: str = " est.") -> str:
    a, b = _f(lo), _f(hi)
    if a is None and b is None:
        return "—"
    if a is None:
        a = 0.0
    if b is None:
        b = a
    return f"{fmt_money(a).lstrip('-') if a >= 0 else fmt_money(a)}–{fmt_money(b).lstrip('-')}{suffix}"


def fmt_days(val: Any) -> str:
    if val is None or val == "":
        return "—"
    try:
        n = int(float(val))
    except (TypeError, ValueError):
        return "—"
    return f"{n}d"


def fmt_hash8(val: Any) -> str:
    s = str(val or "")
    if len(s) <= 8:
        return s or "n/a"
    return s[:8] + "…"


def fmt_dt(val: Any) -> str:
    if val is None or val == "":
        return "—"
    if isinstance(val, datetime):
        dt = val
    elif isinstance(val, date):
        return val.strftime("%b %d") if val.year == date.today().year else val.isoformat()
    else:
        s = str(val)
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return s[:16]
    today = date.today()
    if dt.date() == today:
        return dt.strftime("%H:%M")
    if dt.year == today.year:
        return dt.strftime("%b %d")
    return dt.date().isoformat()


def fmt_dist_pct(val: Any) -> str:
    """Distance to trim/add level — always fractional from Crosshairs."""
    return fmt_pct(val, fractional=True)


def fmt_polarity_class(val: Any) -> str:
    v = _f(val)
    if v is None or v == 0:
        return ""
    return "pos-gain" if v > 0 else "pos-loss"


def weight_to_pct_points(wt: Any) -> Optional[float]:
    """Store/retrieval weight → percentage points (3.6 not 0.036). Same heuristic as positions_page."""
    v = _f(wt)
    if v is None:
        return None
    if v < 1.5:
        return v * 100.0 if v <= 1.0 else v
    return v


def fmt_pct_points(val: Any) -> str:
    """Percent value already in points (6.5 means 6.5%)."""
    return fmt_pct(val, fractional=False)


DELTA_BAR_DOMAIN = 0.20


def delta_bar_width(val: Any) -> float:
    v = _f(val)
    if v is None:
        return 0.0
    return min(50.0, abs(v) / DELTA_BAR_DOMAIN * 50.0)
