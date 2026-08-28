"""Unit B — position lifecycle campaigns via core.retrieval only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from core.retrieval.api import RetrievalSet, TemplateCall, retrieve
from utils.price_history import get_bars
from utils.thesis_reader import get_style, thesis_path_for_ticker

BENCHMARKS = ("VTI", "SPY")
STYLES_PATH = Path("data") / "styles.json"
_DWR_BASE_FLOOR_PCT = 0.02
_DWR_BASE_FLOOR_DOLLARS = 100.0
_DWR_ABS_CAP = 10.0  # backstop: |return| > 1000% is almost always a ratio artifact

_LIFECYCLE_DENOMINATOR_NOTE = (
    "> **Denominator note:** Single-entry and TWR are holding-period returns — timing is the "
    "variable Unit B tests. Campaign economic return divides total P&L by *gross capital deployed* "
    "(every buy dollar, including capital recycled via trims). The **pp delta** mixes those bases; "
    "treat **Δ dollars** as the authoritative comparison."
)


@dataclass
class Leg:
    trade_date: date
    action: str
    shares: float
    price: float
    net_amount: float


@dataclass
class Campaign:
    ticker: str
    legs: list[Leg]
    is_open: bool
    shares_held: float
    first_buy_date: Optional[date]
    first_buy_price: Optional[float]
    dollar_weighted_cost: float
    current_price: Optional[float]
    actual_return_pct: Optional[float]
    single_entry_return_pct: Optional[float]
    benchmark_vti_return_pct: Optional[float]
    benchmark_spy_return_pct: Optional[float]
    time_weighted_return_pct: Optional[float]
    dollar_weighted_return_pct: Optional[float]
    adds_into_strength: int = 0
    adds_into_weakness: int = 0
    total_invested: float = 0.0
    total_realized: float = 0.0
    current_value: float = 0.0
    net_invested_base: float = 0.0
    dwr_degenerate: bool = False
    campaign_economic_return_pct: Optional[float] = None
    scaling_delta_pct: Optional[float] = None
    scaling_delta_dollars: Optional[float] = None
    style_key: Optional[str] = None
    unrealized_pct: Optional[float] = None
    realized_pct: Optional[float] = None


def _parse_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _f(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _price_on(ticker: str, d: date) -> Optional[float]:
    df = get_bars(ticker, period_days=max(400, (date.today() - d).days + 60), interval="daily", adjusted=True)
    if df is None or df.empty:
        return None
    for idx in df.index:
        dt = idx.date() if hasattr(idx, "date") else idx
        if dt >= d:
            return float(df.loc[idx, "close"])
    return float(df.iloc[-1]["close"])


def _holding_return(ticker: str, buy_date: date, buy_price: float, as_of: date) -> Optional[float]:
    end_px = _price_on(ticker, as_of)
    if end_px is None or buy_price == 0:
        return None
    return (end_px / buy_price) - 1.0


def _leg_dollars(legs: list[Leg]) -> tuple[float, float]:
    invested = realized = 0.0
    for leg in legs:
        amt = abs(leg.net_amount) if leg.net_amount else leg.shares * leg.price
        if leg.action.upper().startswith("B"):
            invested += amt
        elif leg.action.upper().startswith("S"):
            realized += amt
    return invested, realized


def _net_invested_base(legs: list[Leg]) -> float:
    base = 0.0
    for leg in legs:
        amt = abs(leg.net_amount) if leg.net_amount else leg.shares * leg.price
        if leg.action.upper().startswith("B"):
            base += amt
        elif leg.action.upper().startswith("S"):
            base -= amt
    return base


def _is_dwr_degenerate(net_base: float, total_invested: float, dwr: Optional[float]) -> bool:
    if total_invested <= 0:
        return True
    if net_base <= 0:
        return True
    if net_base < max(_DWR_BASE_FLOOR_DOLLARS, _DWR_BASE_FLOOR_PCT * total_invested):
        return True
    if dwr is not None and abs(dwr) > _DWR_ABS_CAP:
        return True
    return False


def _dollar_weighted_return(legs: list[Leg], current_price: Optional[float], shares_held: float) -> Optional[float]:
    if current_price is None or shares_held <= 0:
        return None
    cost = 0.0
    for leg in legs:
        if leg.action.upper().startswith("B"):
            cost += abs(leg.net_amount) if leg.net_amount else leg.shares * leg.price
        elif leg.action.upper().startswith("S"):
            cost -= abs(leg.net_amount) if leg.net_amount else leg.shares * leg.price
    if cost <= 0:
        return None
    return (shares_held * current_price - cost) / cost


def _campaign_economics(
    *,
    total_invested: float,
    total_realized: float,
    current_value: float,
    shares_held: float,
    first_buy_price: Optional[float],
    single_entry_return_pct: Optional[float],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Economic return on gross deployed capital and delta vs single-entry counterfactual."""
    if total_invested <= 0:
        return None, None, None
    economic_pnl = current_value + total_realized - total_invested
    campaign_return = economic_pnl / total_invested
    if first_buy_price and first_buy_price > 0 and shares_held > 0:
        cf_pnl = current_value - (shares_held * first_buy_price)
        delta_dollars = economic_pnl - cf_pnl
        delta_pct = (
            (campaign_return - single_entry_return_pct)
            if single_entry_return_pct is not None
            else None
        )
        return campaign_return, delta_pct, delta_dollars
    return campaign_return, None, None


def _style_description(style_key: str) -> str:
    try:
        data = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
        return str(data.get(style_key, {}).get("description", style_key))
    except (OSError, ValueError, TypeError):
        return style_key


def _scaling_adds_note(ticker: str, adds_strength: int, adds_weakness: int) -> str:
    style = get_style(path=thesis_path_for_ticker(ticker))
    thesis_path = thesis_path_for_ticker(ticker).as_posix()
    if not style:
        return (
            f"**Adds into strength / weakness:** {adds_strength} / {adds_weakness} "
            f"(style unknown — check `{thesis_path}`)"
        )
    desc = _style_description(style)
    base = f"**Adds into strength / weakness:** {adds_strength} / {adds_weakness} — **{style}** ({desc})"
    if style == "FUND" and adds_strength > 0 and adds_strength >= adds_weakness:
        return (
            f"{base}. Adding into strength diverges from the dip-buying sleeve; "
            f"if intentional, document in `{thesis_path}`."
        )
    if style == "GARP" and adds_strength > 0:
        return f"{base}. Adding into strength is consistent with GARP; nothing to reconcile."
    return base


def _time_weighted_return(legs: list[Leg], ticker: str, as_of: date) -> Optional[float]:
    """Simple linked-period TWR between cash flows (measurement, not advice)."""
    buys = [l for l in legs if l.action.upper().startswith("B")]
    if not buys:
        return None
    product = 1.0
    for i, leg in enumerate(buys):
        start = leg.trade_date
        end = buys[i + 1].trade_date if i + 1 < len(buys) else as_of
        r = _holding_return(ticker, start, leg.price, end)
        if r is None:
            continue
        product *= 1.0 + r
    return product - 1.0


def _benchmark_blended_return(legs: list[Leg], bench: str, as_of: date) -> Optional[float]:
    buys = [l for l in legs if l.action.upper().startswith("B")]
    if not buys:
        return None
    total = 0.0
    weighted = 0.0
    for leg in buys:
        dollars = abs(leg.net_amount) if leg.net_amount else leg.shares * leg.price
        r = _holding_return(bench, leg.trade_date, _price_on(bench, leg.trade_date) or 1.0, as_of)
        if r is None:
            continue
        total += dollars
        weighted += dollars * r
    if total == 0:
        return None
    return weighted / total


def build_campaign_from_transactions(ticker: str, txns: list[dict]) -> Optional[Campaign]:
    legs: list[Leg] = []
    for row in sorted(txns, key=lambda r: str(r.get("trade_date", ""))):
        d = _parse_date(row.get("trade_date"))
        if d is None:
            continue
        action = str(row.get("action", "")).strip()
        sh = _f(row.get("shares")) or 0.0
        px = _f(row.get("price")) or 0.0
        net = _f(row.get("net_amount")) or 0.0
        legs.append(Leg(d, action, sh, px, net))

    if not legs:
        return None

    shares = 0.0
    first_buy_date = None
    first_buy_price = None
    running_cost = 0.0
    adds_strength = adds_weakness = 0

    for leg in legs:
        if leg.action.upper().startswith("B"):
            if first_buy_date is None:
                first_buy_date = leg.trade_date
                first_buy_price = leg.price
            elif shares > 0:
                avg = running_cost / shares if shares else leg.price
                if leg.price >= avg:
                    adds_strength += 1
                else:
                    adds_weakness += 1
            shares += leg.shares
            running_cost += abs(leg.net_amount) if leg.net_amount else leg.shares * leg.price
        elif leg.action.upper().startswith("S"):
            shares -= leg.shares
            running_cost -= abs(leg.net_amount) if leg.net_amount else leg.shares * leg.price

    is_open = shares > 0.01
    as_of = date.today()
    current_price = _price_on(ticker, as_of) if is_open else _price_on(ticker, legs[-1].trade_date)

    dwr = _dollar_weighted_return(legs, current_price, shares) if is_open else None
    twr = _time_weighted_return(legs, ticker, as_of)

    single_entry = None
    if is_open and first_buy_price and first_buy_price > 0 and current_price:
        single_entry = (current_price / first_buy_price) - 1.0

    bench_vti = _benchmark_blended_return(legs, "VTI", as_of)
    bench_spy = _benchmark_blended_return(legs, "SPY", as_of)

    total_invested, total_realized = _leg_dollars(legs)
    net_base = _net_invested_base(legs)
    current_value = (shares * current_price) if current_price is not None and is_open else 0.0
    dwr_degenerate = _is_dwr_degenerate(net_base, total_invested, dwr) if is_open else False
    if dwr_degenerate:
        dwr = None

    camp_return, scaling_delta_pct, scaling_delta_dollars = _campaign_economics(
        total_invested=total_invested,
        total_realized=total_realized,
        current_value=current_value,
        shares_held=shares,
        first_buy_price=first_buy_price,
        single_entry_return_pct=single_entry,
    )
    style_key = get_style(path=thesis_path_for_ticker(ticker))

    return Campaign(
        ticker=ticker,
        legs=legs,
        is_open=is_open,
        shares_held=shares,
        first_buy_date=first_buy_date,
        first_buy_price=first_buy_price,
        dollar_weighted_cost=running_cost,
        current_price=current_price,
        actual_return_pct=camp_return,
        single_entry_return_pct=single_entry,
        benchmark_vti_return_pct=bench_vti,
        benchmark_spy_return_pct=bench_spy,
        time_weighted_return_pct=twr,
        dollar_weighted_return_pct=dwr,
        adds_into_strength=adds_strength,
        adds_into_weakness=adds_weakness,
        total_invested=total_invested,
        total_realized=total_realized,
        current_value=current_value,
        net_invested_base=net_base,
        dwr_degenerate=dwr_degenerate,
        campaign_economic_return_pct=camp_return,
        scaling_delta_pct=scaling_delta_pct,
        scaling_delta_dollars=scaling_delta_dollars,
        style_key=style_key,
        unrealized_pct=dwr if is_open and not dwr_degenerate else None,
    )


def retrieve_campaign(ticker: str) -> tuple[Campaign | None, RetrievalSet]:
    t = ticker.upper()
    since = date(2020, 1, 1)
    until = date.today()
    rs = retrieve(
        queries=[
            TemplateCall("position_transactions", {"ticker": t, "since": since, "until": until}),
            TemplateCall("holdings_current", {}),
        ],
        label=f"judgment:lifecycle:{t}",
        caller="judgment",
    )
    txns = rs.tables.get("position_transactions", [])
    camp = build_campaign_from_transactions(t, txns)
    return camp, rs


def list_held_tickers() -> list[str]:
    rs = retrieve(
        queries=[TemplateCall("holdings_current", {})],
        label="judgment:lifecycle:tickers",
        caller="judgment",
    )
    out: list[str] = []
    for row in rs.tables.get("holdings_current", []):
        tick = str(row.get("ticker", "")).strip().upper()
        if tick and tick not in getattr(__import__("config"), "CASH_TICKERS", set()):
            out.append(tick)
    return sorted(set(out))


def format_campaign_markdown(camp: Campaign, *, retrieval_hash: str = "") -> str:
    status = "OPEN" if camp.is_open else "CLOSED"
    lines = [
        f"# Judgment — Lifecycle: {camp.ticker} ({status})",
        "",
        "> **Measurement only.** Counterfactuals report what the same dollars would have returned — "
        "not what you should have done. One regime; N=1 campaign.",
        "",
    ]
    if retrieval_hash:
        lines.append(f"**retrieval_hash:** `{retrieval_hash}`")
        lines.append("")

    lines.extend([
        f"**First buy:** {camp.first_buy_date} @ ${camp.first_buy_price:,.2f}" if camp.first_buy_price else "**First buy:** —",
        f"**Legs:** {len(camp.legs)} · **Shares held:** {camp.shares_held:,.2f}",
        _scaling_adds_note(camp.ticker, camp.adds_into_strength, camp.adds_into_weakness),
        "",
        "## Scaling — legs vs buy-once (headline)",
        "",
        _LIFECYCLE_DENOMINATOR_NOTE,
        "",
    ])

    def _pct(v: Optional[float], label: str) -> str:
        if v is None:
            return f"- **{label}:** —"
        return f"- **{label}:** {v:+.2%}"

    lines.append(_pct(camp.single_entry_return_pct, "Single-entry counterfactual (full position at first-buy price)"))
    lines.append(_pct(camp.campaign_economic_return_pct, "Campaign economic return (gross deployed capital)"))
    if camp.scaling_delta_pct is not None:
        delta_line = f"- **Delta (legs minus buy-once):** {camp.scaling_delta_pct:+.2%}"
        if camp.scaling_delta_dollars is not None:
            delta_line += f" (${camp.scaling_delta_dollars:+,.0f})"
        lines.append(delta_line)
    else:
        lines.append("- **Delta (legs minus buy-once):** —")

    lines.extend([
        "",
        "## Supporting measures",
        "",
    ])
    lines.append(_pct(camp.time_weighted_return_pct, "Time-weighted return (TWR) — timing stripped"))
    if camp.dwr_degenerate:
        lines.append(
            "- **Dollar-weighted return (DWR):** n/a — invested base degenerate "
            f"(invested ${camp.total_invested:,.0f}, realized ${camp.total_realized:,.0f}, "
            f"current ${camp.current_value:,.0f})"
        )
    else:
        lines.append(_pct(camp.dollar_weighted_return_pct, "Dollar-weighted return (DWR)"))
    lines.append(_pct(camp.benchmark_vti_return_pct, "Benchmark counterfactual (same dollars → VTI on same dates)"))
    lines.append(_pct(camp.benchmark_spy_return_pct, "Benchmark counterfactual (same dollars → SPY on same dates)"))

    if camp.is_open:
        lines.extend([
            "",
            f"*Campaign still open. Current price: ${camp.current_price:,.2f}*",
        ])
    else:
        lines.extend(["", "*Campaign closed — comparison uses final leg date.*"])

    lines.extend(["", "## Legs", "", "| Date | Action | Shares | Price | Net |", "|---|---|---:|---:|---:|"])
    for leg in camp.legs:
        lines.append(
            f"| {leg.trade_date} | {leg.action} | {leg.shares:,.2f} | ${leg.price:,.2f} | ${leg.net_amount:,.2f} |"
        )
    return "\n".join(lines)


def _format_dwr_cell(c: Campaign) -> str:
    if c.dwr_degenerate:
        return "n/a (base degenerate)"
    if c.dollar_weighted_return_pct is None:
        return "—"
    return f"{c.dollar_weighted_return_pct:+.1%}"


def format_lifecycle_summary(campaigns: list[Campaign]) -> str:
    lines = [
        "# Judgment — Lifecycle summary (Unit B)",
        "",
        "> **Analysis Rule 9:** Each row is one ticker campaign in the scoped book — not a recommendation.",
        "",
        _LIFECYCLE_DENOMINATOR_NOTE,
        "",
        "| Ticker | Status | Legs | Δ legs−buy-once | Single-entry | Campaign econ | TWR | DWR | Adds +/− |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for c in campaigns:
        def p(v: Optional[float]) -> str:
            return f"{v:+.1%}" if v is not None else "—"

        delta = p(c.scaling_delta_pct)
        lines.append(
            f"| {c.ticker} | {'OPEN' if c.is_open else 'CLOSED'} | {len(c.legs)} | "
            f"{delta} | {p(c.single_entry_return_pct)} | {p(c.campaign_economic_return_pct)} | "
            f"{p(c.time_weighted_return_pct)} | {_format_dwr_cell(c)} | "
            f"{c.adds_into_strength}/{c.adds_into_weakness} |"
        )
    lines.append("")
    lines.append("*No moralizing — underperformance vs single-entry is a measurement, not a verdict.*")
    return "\n".join(lines)
