"""
Server-rendered inline SVG charts for Position Story.

ChartSpec is the only public construction surface; SVG rendering lives in one
Jinja partial so publish_static and pm ui serve share identical output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PARTIAL = Path(__file__).resolve().parent / "templates" / "partials" / "chart.svg.j2"


@dataclass(frozen=True)
class ChartMarker:
    x_index: int
    y: float
    side: str  # buy | sell
    size: float
    txn_index: int
    is_rotation: bool = False
    count: int = 1


@dataclass(frozen=True)
class ChartSignalMarker:
    x_index: int
    signal_type: str
    downgraded: bool


@dataclass(frozen=True)
class LotBand:
    start_index: int
    end_index: int
    label: str


@dataclass(frozen=True)
class ChartSpec:
    width: int
    height: int
    dates: tuple[str, ...]
    closes: tuple[float, ...]
    cost_basis: tuple[Optional[float], ...]
    markers: tuple[ChartMarker, ...]
    signals: tuple[ChartSignalMarker, ...]
    lot_bands: tuple[LotBand, ...]
    today_index: Optional[int]
    padding: int = 48

    def to_render_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["y_min"], d["y_max"] = _y_range(self.closes, self.cost_basis, self.markers)
        return d


def _parse_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _aggregate_markers_by_week(
    markers: Sequence[ChartMarker],
    dates: Sequence[str],
) -> tuple[ChartMarker, ...]:
    """Same-calendar-week fills collapse to one mark with a count badge."""
    from collections import defaultdict

    buckets: dict[tuple[int, int, str], list[ChartMarker]] = defaultdict(list)
    for m in markers:
        if m.x_index >= len(dates):
            continue
        dt = _parse_date(dates[m.x_index])
        if dt is None:
            continue
        iso = dt.isocalendar()
        buckets[(iso[0], iso[1], m.side)].append(m)
    out: list[ChartMarker] = []
    for group in sorted(buckets.values(), key=lambda g: min(x.x_index for x in g)):
        xi = min(g.x_index for g in group)
        y = sum(g.y for g in group) / len(group)
        size = max(g.size for g in group)
        is_rot = any(g.is_rotation for g in group)
        txn_idx = group[0].txn_index
        out.append(
            ChartMarker(
                x_index=xi,
                y=y,
                side=group[0].side,
                size=size,
                txn_index=txn_idx,
                is_rotation=is_rot,
                count=len(group),
            )
        )
    return tuple(out)


def _date_index(dates: Sequence[str], target: date) -> Optional[int]:
    iso = target.isoformat()
    for i, d in enumerate(dates):
        if d[:10] == iso:
            return i
    # nearest prior bar
    best = None
    for i, d in enumerate(dates):
        if d[:10] <= iso:
            best = i
        else:
            break
    return best


def _y_range(
    closes: Sequence[float],
    cost_basis: Sequence[Optional[float]],
    markers: Sequence[ChartMarker],
) -> tuple[float, float]:
    vals: list[float] = [c for c in closes if c is not None]
    vals.extend(c for c in cost_basis if c is not None)
    vals.extend(m.y for m in markers)
    if not vals:
        return 0.0, 1.0
    lo, hi = min(vals), max(vals)
    if lo == hi:
        pad = lo * 0.05 or 1.0
        return lo - pad, hi + pad
    span = hi - lo
    return lo - span * 0.05, hi + span * 0.05


def build_cost_basis_series(
    bars: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[float, ...], tuple[Optional[float], ...]]:
    """Daily close series plus average-cost curve from transaction history."""
    bar_rows = sorted(
        (
            {
                "d": _parse_date(r.get("bar_date")),
                "close": float(r["close"]) if r.get("close") is not None else None,
            }
            for r in bars
            if _parse_date(r.get("bar_date")) is not None and r.get("close") is not None
        ),
        key=lambda x: x["d"],
    )
    if not bar_rows:
        return (), (), ()

    dates = tuple(row["d"].isoformat() for row in bar_rows)
    closes = tuple(float(row["close"]) for row in bar_rows)

    txns = []
    for i, t in enumerate(transactions):
        d = _parse_date(t.get("trade_date"))
        if d is None:
            continue
        action = str(t.get("action") or "").upper()
        shares = t.get("shares")
        price = t.get("price")
        try:
            sh = float(shares) if shares is not None else 0.0
        except (TypeError, ValueError):
            sh = 0.0
        try:
            px = float(price) if price is not None else 0.0
        except (TypeError, ValueError):
            px = 0.0
        if sh == 0:
            continue
        side = "buy" if "BUY" in action else "sell" if "SELL" in action else ""
        if not side:
            continue
        txns.append({"date": d, "side": side, "shares": abs(sh), "price": px, "index": i})
    txns.sort(key=lambda x: x["date"])

    shares_held = 0.0
    total_basis = 0.0
    txn_ptr = 0
    avg_costs: list[Optional[float]] = []
    for row in bar_rows:
        d = row["d"]
        while txn_ptr < len(txns) and txns[txn_ptr]["date"] <= d:
            t = txns[txn_ptr]
            if t["side"] == "buy":
                total_basis += t["shares"] * t["price"]
                shares_held += t["shares"]
            elif t["side"] == "sell" and shares_held > 0:
                sell_sh = min(t["shares"], shares_held)
                avg = total_basis / shares_held if shares_held else 0.0
                total_basis -= avg * sell_sh
                shares_held -= sell_sh
            txn_ptr += 1
        avg_costs.append(total_basis / shares_held if shares_held > 0 else None)

    return dates, closes, tuple(avg_costs)


def build_chart_spec(
    *,
    bars: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    open_lots: list[dict[str, Any]],
    rotation_txn_dates: set[str],
    as_of: Optional[date] = None,
    width: int = 900,
    height: int = 320,
) -> ChartSpec:
    """Assemble ChartSpec from retrieval rows (no store access)."""
    as_of = as_of or date.today()
    dates, closes, cost_basis = build_cost_basis_series(bars, transactions)
    if not dates:
        return ChartSpec(
            width=width,
            height=height,
            dates=(),
            closes=(),
            cost_basis=(),
            markers=(),
            signals=(),
            lot_bands=(),
            today_index=None,
        )

    markers: list[ChartMarker] = []
    for i, t in enumerate(transactions):
        d = _parse_date(t.get("trade_date"))
        if d is None:
            continue
        xi = _date_index(dates, d)
        if xi is None:
            continue
        action = str(t.get("action") or "").upper()
        side = "buy" if "BUY" in action else "sell" if "SELL" in action else ""
        if not side:
            continue
        try:
            amt = abs(float(t.get("net_amount") or 0))
        except (TypeError, ValueError):
            amt = 0.0
        try:
            px = float(t.get("price") or closes[xi])
        except (TypeError, ValueError):
            px = closes[xi]
        size = max(4.0, min(18.0, (amt / 5000.0) ** 0.5 * 6.0)) if amt else 6.0
        is_rot = d.isoformat() in rotation_txn_dates
        markers.append(
            ChartMarker(
                x_index=xi,
                y=px,
                side=side,
                size=size,
                txn_index=i,
                is_rotation=is_rot,
            )
        )

    sig_markers: list[ChartSignalMarker] = []
    for s in signals:
        d = _parse_date(s.get("event_date"))
        if d is None:
            continue
        xi = _date_index(dates, d)
        if xi is None:
            continue
        sig_markers.append(
            ChartSignalMarker(
                x_index=xi,
                signal_type=str(s.get("signal_type") or ""),
                downgraded=bool(s.get("doctrine_downgraded")),
            )
        )

    lot_bands: list[LotBand] = []
    for lot in open_lots:
        open_d = _parse_date(lot.get("lot_open_date"))
        if open_d is None:
            continue
        start = _date_index(dates, open_d)
        if start is None:
            continue
        hd = lot.get("holding_days")
        try:
            holding = int(hd) if hd is not None else (as_of - open_d).days
        except (TypeError, ValueError):
            holding = (as_of - open_d).days
        days_to_lt = max(0, 365 - holding)
        lt_date = open_d.fromordinal(open_d.toordinal() + 365)
        end = _date_index(dates, lt_date) or (len(dates) - 1)
        label = str(lot.get("shares") or "")
        lot_bands.append(LotBand(start_index=start, end_index=end, label=label))

    today_index = _date_index(dates, as_of)
    agg_markers = _aggregate_markers_by_week(markers, dates)

    return ChartSpec(
        width=width,
        height=height,
        dates=dates,
        closes=closes,
        cost_basis=cost_basis,
        markers=agg_markers,
        signals=tuple(sig_markers),
        lot_bands=tuple(lot_bands),
        today_index=today_index,
    )


def render_chart_svg(spec: ChartSpec) -> str:
    """Render ChartSpec to inline SVG via the shared Jinja partial."""
    env = Environment(
        loader=FileSystemLoader(str(_PARTIAL.parent.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template("partials/chart.svg.j2")
    return tpl.render(spec=spec.to_render_dict())
