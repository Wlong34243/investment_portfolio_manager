"""
utils/tax.py — Pure tax-lot math functions.

All functions are I/O-free and unit-testable.  No wash-sale or estimated-tax
math lives here (those are Phase 3).  This module scaffolds the data structures
and holding-period logic needed for Phase 1.3 lot ingestion.

IRS long-term rule: held MORE THAN one year means (as_of - acquisition_date).days > 365.
  - Bought Jan 1, sold Jan 1 next year  → 365 days → short_term
  - Bought Jan 1, sold Jan 2 next year  → 366 days → long_term
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

# ---------------------------------------------------------------------------
# Lot dataclass
# ---------------------------------------------------------------------------

@dataclass
class Lot:
    ticker:               str
    account_hash:         str
    account_type:         str                                    # taxable / ira / roth / unknown
    lot_id:               str | None
    acquisition_date:     date | None
    quantity:             float
    cost_basis_per_share: float
    cost_basis_total:     float
    holding_period:       Literal["short_term", "long_term", "unknown"]
    days_until_long_term: int | None                            # 0 if already long_term; None if unknown
    source:               Literal["schwab", "derived"]

    def to_dict(self) -> dict:
        return {
            "ticker":               self.ticker,
            "account_hash":         self.account_hash,
            "account_type":         self.account_type,
            "lot_id":               self.lot_id,
            "acquisition_date":     self.acquisition_date.isoformat() if self.acquisition_date else None,
            "quantity":             self.quantity,
            "cost_basis_per_share": self.cost_basis_per_share,
            "cost_basis_total":     self.cost_basis_total,
            "holding_period":       self.holding_period,
            "days_until_long_term": self.days_until_long_term,
            "source":               self.source,
        }


# ---------------------------------------------------------------------------
# Holding-period helpers
# ---------------------------------------------------------------------------

def _to_date(d: date | datetime | str | None) -> date | None:
    """Coerce date/datetime/ISO-string to date, or None."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    # Try ISO string
    s = str(d).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def classify_holding_period(
    acquisition_date: date | datetime | str | None,
    as_of: date | datetime | str | None = None,
) -> Literal["short_term", "long_term", "unknown"]:
    """
    Classify the holding period of a lot.

    Returns "long_term" when the lot has been held MORE THAN 365 days
    (i.e., (as_of - acquisition_date).days > 365), "short_term" otherwise.
    Returns "unknown" when either date is unavailable.

    Args:
        acquisition_date: date the position was opened (any date-like type)
        as_of: reference date (defaults to today)
    """
    acq = _to_date(acquisition_date)
    ref = _to_date(as_of) if as_of is not None else date.today()

    if acq is None or ref is None:
        return "unknown"

    days_held = (ref - acq).days
    return "long_term" if days_held > 365 else "short_term"


def days_until_long_term(
    acquisition_date: date | datetime | str | None,
    as_of: date | datetime | str | None = None,
) -> int | None:
    """
    Number of calendar days until this lot becomes long-term.

    Returns 0  if already long-term (held > 365 days).
    Returns None if acquisition_date is unavailable.

    Args:
        acquisition_date: date the position was opened
        as_of: reference date (defaults to today)
    """
    acq = _to_date(acquisition_date)
    ref = _to_date(as_of) if as_of is not None else date.today()

    if acq is None or ref is None:
        return None

    days_held = (ref - acq).days
    return max(0, 366 - days_held)


# ---------------------------------------------------------------------------
# FIFO lot reconstruction
# ---------------------------------------------------------------------------

def reconstruct_lots_fifo(
    transactions: list[dict],
    ticker: str,
    account_hash: str = "",
    account_type: str = "taxable",
    as_of: date | None = None,
) -> list[Lot]:
    """
    Reconstruct open tax lots for `ticker` from transaction history using FIFO.

    Args:
        transactions: list of transaction dicts in the Transactions tab schema.
            Required keys per row: 'Trade Date', 'Action', 'Ticker', 'Quantity',
            'Price', 'Account'.  Missing keys are treated as zero/empty.
        ticker:       ticker symbol to reconstruct (case-sensitive match).
        account_hash: account identifier to stamp on each derived lot.
        account_type: tax treatment tag ('taxable' | 'ira' | 'roth' | 'unknown').
        as_of:        reference date for holding-period classification (default: today).

    Returns:
        List of open Lot objects, oldest first.  Sells reduce the oldest lots first
        (FIFO).  Partial lot closure splits the lot.  All returned lots are marked
        source='derived'.

    Raises:
        Nothing — bad rows are skipped with a zero-quantity guard.
    """
    if as_of is None:
        as_of = date.today()

    # Filter and sort buys + sells for this ticker, oldest first
    relevant: list[tuple[date, str, float, float]] = []   # (trade_date, action, qty, price)
    for row in transactions:
        if str(row.get("Ticker", "")).strip().upper() != ticker.upper():
            continue
        action = str(row.get("Action", "")).strip().lower()
        if action not in ("buy", "sell"):
            continue
        acq = _to_date(row.get("Trade Date"))
        if acq is None:
            continue
        qty = abs(float(row.get("Quantity") or 0))
        price = abs(float(row.get("Price") or 0))
        if qty <= 0:
            continue
        relevant.append((acq, action, qty, price))

    # Sort by trade date ascending (FIFO = oldest first)
    relevant.sort(key=lambda r: r[0])

    # Maintain open lot queue as list of [acq_date, qty, price]
    open_lots: list[list] = []

    for acq, action, qty, price in relevant:
        if action == "buy":
            open_lots.append([acq, qty, price])
        elif action == "sell":
            remaining_sell = qty
            while remaining_sell > 1e-6 and open_lots:
                oldest = open_lots[0]
                lot_qty = oldest[1]
                if lot_qty <= remaining_sell + 1e-6:
                    # Consume this lot entirely
                    remaining_sell -= lot_qty
                    open_lots.pop(0)
                else:
                    # Partial consumption — split the lot
                    oldest[1] -= remaining_sell
                    remaining_sell = 0.0

    # Build Lot objects from the remaining open lots
    result: list[Lot] = []
    for (acq_date, qty, price) in open_lots:
        if qty < 1e-6:
            continue
        hp = classify_holding_period(acq_date, as_of)
        dlt = days_until_long_term(acq_date, as_of)
        cost_total = round(price * qty, 2)
        result.append(Lot(
            ticker=ticker,
            account_hash=account_hash,
            account_type=account_type,
            lot_id=None,
            acquisition_date=acq_date,
            quantity=round(qty, 6),
            cost_basis_per_share=price,
            cost_basis_total=cost_total,
            holding_period=hp,
            days_until_long_term=dlt,
            source="derived",
        ))

    return result
