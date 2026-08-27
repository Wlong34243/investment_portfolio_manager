"""
Assemble 3a/3b (and later 3c/3d) tax annotations for CLI + Crosshairs.

Every rendered figure is labelled ESTIMATE. Does not write Realized_GL.
Does not call lot_relief (3d bound is a separate increment gated on doctrine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from core.tax.ladder import LotLadderRow, days_to_lt_ladder, nearest_days_to_lt
from core.tax.open_lots import reconstruct_open_lots_from_realized
from core.tax.wash import WashWindow, open_wash_windows
from utils.doctrine_reader import load_doctrine


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
            # 3d bound deliberately absent until doctrine method+effective date lands
            "est_tax_cost_low": None,
            "est_tax_cost_high": None,
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
    # dict-shaped fallback
    if not out and isinstance(doc, dict):
        for c in doc.get("constraints") or []:
            if c.get("id") == "tax_hold_runners":
                for t in c.get("tickers") or []:
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


def annotate_ticker(ticker: str, *, as_of: date | None = None) -> TaxAnnotation:
    ref = as_of or date.today()
    t = ticker.strip().upper()
    realized = _realized_records(t)
    windows = open_wash_windows(realized, ticker=t, as_of=ref, only_open=True)
    warnings: list[str] = []
    try:
        txns = _txn_records(t)
        open_lots = reconstruct_open_lots_from_realized(txns, realized, ticker=t)
    except Exception as e:
        open_lots = []
        warnings.append(f"open_lots unavailable: {e}")
    ladder = days_to_lt_ladder(open_lots, as_of=ref, ticker=t)
    runners = _tax_hold_runner_tickers()
    is_runner = t in runners
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
        warnings=warnings,
    )


def format_project_report(ann: TaxAnnotation, *, shares: float | None = None) -> str:
    lines = [
        f"{ann.ticker} — tax surface, {ann.as_of.isoformat()}"
        f"              *** ESTIMATE — not a tax determination ***",
        "Method: Schwab Tax Lot Optimizer (effective date: PENDING doctrine — "
        "Prompt 9 Step 2; 3d cost bound withheld until then)",
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
    lines.append("  COST OF TRIMMING NOW               [3d]")
    lines.append(
        "    WITHHELD — cost-basis method effective date not yet in doctrine.md "
        "(Prompt 9 Step 2). Bound will not be invented."
    )
    if shares is not None:
        lines.append(f"    (requested size: {shares:g} sh — unused until 3d ships)")
    for w in ann.warnings:
        lines.append(f"  WARNING: {w}")
    return "\n".join(lines)
