"""
Assemble 3a/3b/3c/3d tax annotations for CLI + Crosshairs.

Every rendered figure is labelled ESTIMATE. Does not write Realized_GL.
3d is forward-looking — not gated on effective_date (Step 6 diagnostic is).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from core.tax.ladder import LotLadderRow, days_to_lt_ladder, nearest_days_to_lt
from core.tax.lot_relief import ReliefBound, bound_relief_cost, relief_lots_from_open_dicts
from core.tax.open_lots import reconstruct_open_lots_from_realized
from core.tax.wash import WashWindow, open_wash_windows
from utils.doctrine_reader import cost_basis_method, load_doctrine


@dataclass
class TaxAnnotation:
    ticker: str
    as_of: date
    wash_windows: list[WashWindow] = field(default_factory=list)
    ladder: list[LotLadderRow] = field(default_factory=list)
    days_to_lt: int | None = None
    wash_window_open: bool = False
    is_tax_hold_runner: bool = False
    doctrine_note: str = ""
    relief: ReliefBound | None = None
    is_estimate: bool = True
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Fields safe to merge into signal_events.payload_json."""
        return {
            "tax_estimate": True,
            "days_to_lt": self.days_to_lt,
            "wash_window_open": self.wash_window_open,
            "wash_disallow_through": (
                self.wash_windows[0].disallow_through.isoformat()
                if self.wash_windows
                else None
            ),
            "is_tax_hold_runner": self.is_tax_hold_runner,
            "est_tax_cost_low": (
                self.relief.best_case_tax if self.relief and self.relief.has_range else None
            ),
            "est_tax_cost_high": (
                self.relief.worst_case_tax if self.relief and self.relief.has_range else None
            ),
        }


def _tax_hold_runner_tickers() -> set[str]:
    try:
        doc = load_doctrine()
    except Exception:
        return set()
    out: set[str] = set()
    for c in getattr(doc, "constraints", None) or []:
        if getattr(c, "id", None) == "tax_hold_runners":
            for t in getattr(c, "tickers", None) or []:
                out.add(str(t).upper())
    return out


def _realized_records(ticker: str | None = None) -> list[dict]:
    from core.store import get_store

    df = get_store().get_realized_gl()
    if df is None or df.empty:
        return []
    if ticker:
        t = ticker.upper()
        df = df[df["Ticker"].astype(str).str.upper() == t]
    return df.to_dict(orient="records")


def _txn_records(ticker: str) -> list[dict]:
    from core.store import get_store

    tdf = get_store().get_transactions()
    if tdf is None or tdf.empty:
        return []
    t = ticker.upper()
    sub = tdf[tdf["Ticker"].astype(str).str.upper() == t]
    return sub.to_dict(orient="records")


def _holding_price_qty(ticker: str) -> tuple[float | None, float | None]:
    from core.store import get_store

    df = get_store().get_holdings_current()
    if df is None or df.empty:
        return None, None
    t = ticker.upper()
    col_t = "Ticker" if "Ticker" in df.columns else "ticker"
    sub = df[df[col_t].astype(str).str.upper() == t]
    if sub.empty:
        return None, None
    row = sub.iloc[0]
    price = row.get("Price") or row.get("Last Price") or row.get("price")
    qty = row.get("Quantity") or row.get("quantity")
    try:
        p = float(price) if price is not None else None
    except (TypeError, ValueError):
        p = None
    try:
        q = float(qty) if qty is not None else None
    except (TypeError, ValueError):
        q = None
    return p, q


def _tax_rates() -> tuple[float, float]:
    try:
        from tasks.build_tax_control import get_tax_rates

        st, lt, _, _ = get_tax_rates()
        return float(st), float(lt)
    except Exception:
        return 0.37, 0.20  # fallback for dry-run / tests only


def _method_basis_label() -> str:
    cb = cost_basis_method()
    method = cb.get("method") or "tax_lot_optimizer"
    eff = cb.get("effective_date") or "unknown"
    label = "Schwab Tax Lot Optimizer" if "optimizer" in str(method) else str(method)
    return f"{label} (effective_date={eff}, per doctrine.md)"


def annotate_ticker(
    ticker: str,
    *,
    as_of: date | None = None,
    shares: float | None = None,
) -> TaxAnnotation:
    ref = as_of or date.today()
    t = ticker.strip().upper()
    realized = _realized_records(t)
    windows = open_wash_windows(realized, ticker=t, as_of=ref, only_open=True)
    warnings: list[str] = []
    open_lots: list[dict] = []
    try:
        txns = _txn_records(t)
        open_lots = reconstruct_open_lots_from_realized(txns, realized, ticker=t)
    except Exception as e:
        warnings.append(f"open_lots unavailable: {e}")
    ladder = days_to_lt_ladder(open_lots, as_of=ref, ticker=t)
    runners = _tax_hold_runner_tickers()
    is_runner = t in runners

    relief: ReliefBound | None = None
    price, qty = _holding_price_qty(t)
    trim_sh = shares
    if trim_sh is None and qty is not None:
        trim_sh = max(1.0, round(qty * 0.10, 2))  # nominal 10% trim for Crosshairs
    if trim_sh is not None and price is not None and open_lots:
        rate_st, rate_lt = _tax_rates()
        relief = bound_relief_cost(
            relief_lots_from_open_dicts(open_lots),
            trim_sh,
            price=price,
            as_of=ref,
            rate_st=rate_st,
            rate_lt=rate_lt,
            basis=_method_basis_label(),
        )
        if relief.refused:
            warnings.append(relief.refuse_reason)
    elif trim_sh is not None and price is None:
        warnings.append("no live price — 3d bound skipped")
    elif trim_sh is not None and not open_lots:
        warnings.append("no open lots — 3d bound skipped")

    return TaxAnnotation(
        ticker=t,
        as_of=ref,
        wash_windows=windows,
        ladder=ladder,
        days_to_lt=nearest_days_to_lt(ladder),
        wash_window_open=bool(windows),
        is_tax_hold_runner=is_runner,
        doctrine_note=(
            f"{t} is a tax_hold_runner. Crosshairs may downgrade NEAR_TRIM to HOLD_TAX."
            if is_runner
            else ""
        ),
        relief=relief,
        warnings=warnings,
    )


def format_project_report(ann: TaxAnnotation, *, shares: float | None = None) -> str:
    cb = cost_basis_method()
    eff = cb.get("effective_date") or "unknown"
    lines = [
        f"{ann.ticker} — tax surface, {ann.as_of.isoformat()}"
        f"              *** ESTIMATE — not a tax determination ***",
        f"Method: Schwab Tax Lot Optimizer (effective_date={eff}, per doctrine.md). "
        "3d is forward-looking on open lots — election date does not block the bound.",
        "",
        "  HOLDING PERIOD                     [3b]   -- no optimizer model required",
    ]
    if not ann.ladder:
        lines.append("    (no open lots reconstructed — check Transactions / Realized_GL)")
    else:
        for row in ann.ladder:
            if row.already_long_term:
                lines.append(
                    f"    {row.open_date.isoformat()}  {row.shares:g} sh   already long-term"
                )
            else:
                lines.append(
                    f"    {row.open_date.isoformat()}  {row.shares:g} sh   "
                    f"crosses to long-term in {row.days_to_lt} days "
                    f"({row.crosses_on.isoformat()})"
                )
        near = [r for r in ann.ladder if 0 < r.days_to_lt <= 90]
        if near:
            lines.append(f"    {len(near)} lot(s) cross inside 90 days.")
    lines.append("")
    lines.append("  WASH SALE                          [3a]   -- no optimizer model required")
    if not ann.wash_windows:
        lines.append("    No open wash-sale window on this ticker as of as_of.")
    else:
        for w in ann.wash_windows:
            lines.append(
                f"    OPEN WINDOW — loss sale {w.loss_close_date.isoformat()} "
                f"({w.shares:g} sh, G/L {w.gain_loss:.2f}). "
                f"A repurchase before {w.disallow_through.isoformat()} disallows "
                f"({w.days_open_remaining} days remaining)."
            )
    lines.append("")
    lines.append("  DOCTRINE                           [3c]")
    if ann.is_tax_hold_runner:
        lines.append(f"    {ann.doctrine_note}")
    else:
        lines.append(
            "    Not a tax_hold_runner. Days-to-LT / wash state shown above; "
            "downgrade stays in doctrine.md (manual-only)."
        )
    lines.append("")
    lines.append("  COST OF TRIMMING NOW               [3d]   *** ESTIMATE bound ***")
    trim_sh = shares
    if ann.relief and ann.relief.has_range:
        r = ann.relief
        lines.append(
            f"    Best case  (relief from ST/LT losses):   $ {r.best_case_tax:,.2f}"
        )
        lines.append(
            f"    Worst case (relief hits ST/LT gains):    $ {r.worst_case_tax:,.2f}"
        )
        if r.is_tight:
            lines.append("    Range is tight — lot selection unlikely to move the outcome much.")
        else:
            lines.append(
                "    Range is wide — lot selection materially matters on this position."
            )
        if trim_sh is not None:
            lines.append(f"    (for {trim_sh:g} sh at current price)")
    elif ann.relief and ann.relief.refused:
        lines.append(f"    REFUSED — {ann.relief.refuse_reason}")
    else:
        lines.append("    (bound not computed — missing price, lots, or share count)")
    for w in ann.warnings:
        lines.append(f"  WARNING: {w}")
    return "\n".join(lines)
