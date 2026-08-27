"""
3d — Pre-trade relief cost as a bound (never a point estimate).

Best/worst endpoints are deterministic sorts on open lots — not a claim to
replicate Schwab's proprietary tier logic exactly. The true cost should land
inside the range if the hierarchy in doctrine.md is current.

Step 6 backward-looking diagnostics may refuse UNKNOWN_METHOD_PERIOD when
effective_date is unknown — that guard does NOT apply here (3d is forward-looking).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from utils.tax import classify_holding_period


@dataclass(frozen=True)
class ReliefLot:
    open_date: date
    shares: float
    cost_basis_per_share: float
    account: str | None = None


@dataclass
class ReliefBound:
    best_case_tax: float
    worst_case_tax: float
    best_case_lots: list[dict[str, Any]] = field(default_factory=list)
    worst_case_lots: list[dict[str, Any]] = field(default_factory=list)
    is_estimate: bool = True
    basis: str = ""
    is_tight: bool = False
    refused: bool = False
    refuse_reason: str = ""

    @property
    def has_range(self) -> bool:
        return not self.refused and self.best_case_tax <= self.worst_case_tax


def _term(lot: ReliefLot, as_of: date) -> str:
    return classify_holding_period(lot.open_date, as_of)


def _gain_per_share(lot: ReliefLot, price: float) -> float:
    return price - lot.cost_basis_per_share


def _tier_best(lot: ReliefLot, price: float, as_of: date) -> tuple[int, float]:
    """Optimizer-favourable consumption order (doctrine six-tier intent)."""
    g = _gain_per_share(lot, price)
    st = _term(lot, as_of) != "long_term"
    if g < -1e-9:
        return (0 if st else 1, g)  # ST loss before LT loss; larger loss first (more negative)
    if abs(g) <= 1e-9:
        return (2 if st else 3, 0.0)
    if not st:
        return (4, g)  # LT gains smallest first
    return (5, g)  # ST gains smallest first


def _tier_worst(lot: ReliefLot, price: float, as_of: date) -> tuple[int, float]:
    """Least-favourable: ST gains largest, then LT gains largest."""
    g = _gain_per_share(lot, price)
    st = _term(lot, as_of) != "long_term"
    if g > 1e-9:
        return (0 if st else 1, -g)  # negate for descending sort via ascending key
    if abs(g) <= 1e-9:
        return (2 if st else 3, 0.0)
    if st:
        return (4, -g)  # ST losses last among unfavourable — smallest magnitude
    return (5, -g)


def _consume(
    lots: list[ReliefLot],
    *,
    shares_to_sell: float,
    price: float,
    as_of: date,
    rate_st: float,
    rate_lt: float,
    sort_key: Callable[[ReliefLot, float, date], tuple],
) -> tuple[float, list[dict[str, Any]]]:
    ordered = sorted(lots, key=lambda lot: sort_key(lot, price, as_of))
    remaining = float(shares_to_sell)
    total_tax = 0.0
    consumed: list[dict[str, Any]] = []
    for lot in ordered:
        if remaining <= 1e-9:
            break
        avail = float(lot.shares)
        if avail <= 1e-9:
            continue
        take = min(avail, remaining)
        gain = _gain_per_share(lot, price) * take
        term = _term(lot, as_of)
        rate = rate_lt if term == "long_term" else rate_st
        tax = gain * rate
        total_tax += tax
        consumed.append(
            {
                "open_date": lot.open_date.isoformat(),
                "shares": round(take, 6),
                "cost_basis_per_share": lot.cost_basis_per_share,
                "gain": round(gain, 2),
                "term": term,
                "tax": round(tax, 2),
            }
        )
        remaining -= take
    return round(total_tax, 2), consumed


def bound_relief_cost(
    lots: list[ReliefLot],
    shares_to_sell: float,
    *,
    price: float,
    as_of: date | None = None,
    rate_st: float,
    rate_lt: float,
    basis: str = "Schwab Tax Lot Optimizer (doctrine.md)",
) -> ReliefBound:
    """
    ESTIMATE bound on federal capital-gains tax for selling `shares_to_sell` at `price`.
    Refuses cross-account lot sets only — not gated on effective_date (3d is forward-looking).
    """
    ref = as_of or date.today()
    if shares_to_sell <= 0:
        return ReliefBound(
            0.0,
            0.0,
            basis=basis,
            refused=True,
            refuse_reason="shares_to_sell must be positive",
        )
    if price <= 0:
        return ReliefBound(
            0.0,
            0.0,
            basis=basis,
            refused=True,
            refuse_reason="price required for gain estimate",
        )
    if not lots:
        return ReliefBound(
            0.0,
            0.0,
            basis=basis,
            refused=True,
            refuse_reason="no open lots",
        )
    accounts = {str(lot.account or "").strip() for lot in lots if lot.account}
    accounts.discard("")
    if len(accounts) > 1:
        return ReliefBound(
            0.0,
            0.0,
            basis=basis,
            refused=True,
            refuse_reason="CROSS_ACCOUNT — relief is per-account; mixed lot set refused",
        )
    total_sh = sum(l.shares for l in lots)
    if shares_to_sell > total_sh + 1e-6:
        return ReliefBound(
            0.0,
            0.0,
            basis=basis,
            refused=True,
            refuse_reason=f"requested {shares_to_sell:g} sh exceeds open inventory {total_sh:g}",
        )

    best_tax, best_lots = _consume(
        lots,
        shares_to_sell=shares_to_sell,
        price=price,
        as_of=ref,
        rate_st=rate_st,
        rate_lt=rate_lt,
        sort_key=_tier_best,
    )
    worst_tax, worst_lots = _consume(
        lots,
        shares_to_sell=shares_to_sell,
        price=price,
        as_of=ref,
        rate_st=rate_st,
        rate_lt=rate_lt,
        sort_key=_tier_worst,
    )
    if best_tax > worst_tax:
        best_tax, worst_tax = worst_tax, best_tax

    span = worst_tax - best_tax
    mid = (worst_tax + best_tax) / 2.0 if (worst_tax + best_tax) else 0.0
    is_tight = mid == 0.0 or (span / abs(mid)) <= 0.05 if mid else span <= 1.0

    return ReliefBound(
        best_case_tax=best_tax,
        worst_case_tax=worst_tax,
        best_case_lots=best_lots,
        worst_case_lots=worst_lots,
        is_estimate=True,
        basis=basis,
        is_tight=is_tight,
    )


def relief_lots_from_open_dicts(rows: list[dict[str, Any]]) -> list[ReliefLot]:
    out: list[ReliefLot] = []
    for r in rows:
        od = r.get("open_date")
        if isinstance(od, str):
            od = date.fromisoformat(od[:10])
        if not isinstance(od, date):
            continue
        sh = float(r.get("shares") or 0)
        cps = float(r.get("cost_basis_per_share") or 0)
        if sh <= 0 or cps <= 0:
            continue
        out.append(
            ReliefLot(
                open_date=od,
                shares=sh,
                cost_basis_per_share=cps,
                account=str(r.get("account") or "") or None,
            )
        )
    return out
