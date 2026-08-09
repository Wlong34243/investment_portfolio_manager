"""
tasks/compute_rotation_attribution.py
──────────────────────────────────────
Basket-aware post-hoc P&L attribution for rotations in Trade_Log.

The basket (multi-ticker sell → multi-ticker buy) is the unit of analysis.
Headline number is Residual_Pair_Nd = Pair_Return − beta-explained portion,
because Bill systematically sells low-beta and buys high-beta — a raw pair
return in a rising market is mostly the risk step-up, not selection.

Architecture:
  1. Read Trade_Log (optionally Trade_Log_Staging for read-only backfill).
  2. Detect nested/superseded rows; attribute only the widest per group.
  3. Reconstruct per-ticker dollar weights from Transactions; reconcile.
  4. Net tickers that appear on both sides; record Both_Sides_Tickers.
  5. Weighted returns at 30/90/180 trading days via compute_return().
  6. Benchmarks SPY / VTI / QQQ; Vs_Index vs VTI; beta decomposition vs SPY.
  7. Dry-run prints full table; --live archives then rebuilds Rotation_Review.
  8. Always writes a local markdown summary under agent_outputs/rotation_attribution/.
"""

from __future__ import annotations

import logging
import math
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.table import Table

# Project root on path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from tasks.derive_rotations import (
    BUY_ACTIONS,
    CLUSTER_WINDOW_DAYS_DEFAULT,
    SELL_ACTIONS,
    _read_transactions,
)
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)
console = Console()

HORIZONS = (30, 90, 180)
WEIGHT_RECONCILE_TOL = 0.02
COVERAGE_FLAG_PCT = 0.90
BETA_REFERENCE = "SPY"
BENCH_QQQ_NOTE = "Held equivalent is QQQM (same index, lower fee); QQQ used for longer price history."
OUTPUT_DIR = _ROOT / "agent_outputs" / "rotation_attribution"
JEPI_INCOME_TICKERS = {"JEPI", "JPIE"}

# --historical-ledger (2026-08-09): the 2026-08-03 account-scope fix means the
# live Transactions tab only ever held the 3-account-scoped view, even for
# dates before the fix landed. Transactions_Historical_AllAccounts is a
# parallel, all-6-account fetch for 2025-01-01 -> 2026-08-03 written by
# scripts/fetch_transactions_historical_all_accounts_2026-08-09.py. Reading it
# is opt-in and never touches the Transactions tab or its live-scoped rows.
HISTORICAL_LEDGER_TAB = "Transactions_Historical_AllAccounts"
SCOPE_FIX_DATE = date(2026, 8, 3)

# Cache for yfinance downloads to avoid redundant hits in one run
_YF_CACHE: Dict[str, pd.DataFrame] = {}
_BETA_CACHE: Dict[str, Optional[float]] = {}


# ---------------------------------------------------------------------------
# Price / return primitives (preserved API)
# ---------------------------------------------------------------------------

def get_ohlcv(ticker: str, start_date: date, end_date: Optional[date] = None) -> Optional[pd.DataFrame]:
    """Fetch and cache OHLCV for ticker. auto_adjust=True → total-return (div-adjusted) closes."""
    requested_end = end_date if end_date is not None else start_date + timedelta(days=380)

    cached = _YF_CACHE.get(ticker)
    if cached is not None and not cached.empty:
        c0 = cached.index[0].date() if hasattr(cached.index[0], "date") else cached.index[0]
        c1 = cached.index[-1].date() if hasattr(cached.index[-1], "date") else cached.index[-1]
        if c0 <= start_date and c1 >= min(requested_end, date.today()):
            return cached

    try:
        df = yf.download(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=(requested_end + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
        # Prefer wider series in cache
        if cached is None or len(df) >= len(cached):
            _YF_CACHE[ticker] = df
        return df
    except Exception as e:
        logger.warning(f"Failed to download {ticker}: {e}")
        return None


def compute_return(
    ticker: str,
    anchor_date: date,
    trading_days: int,
    cash_yield: float,
) -> Optional[float]:
    """Compute cumulative total return for ticker over N trading days from anchor_date."""
    if not ticker or ticker == "" or ticker.upper() == "CASH":
        cal_days = trading_days * (365.0 / 252.0)
        return round((cash_yield / 100.0) * (cal_days / 365.0), 4)

    df = get_ohlcv(ticker, anchor_date)
    if df is None or df.empty:
        return None

    available_dates = df.index
    start_date_actual = available_dates[available_dates.date >= anchor_date]
    if len(start_date_actual) == 0:
        return None

    idx0 = df.index.get_loc(start_date_actual[0])
    if isinstance(idx0, slice):
        idx0 = idx0.start
    elif isinstance(idx0, np.ndarray):
        idx0 = int(idx0[0])

    target_idx = idx0 + trading_days
    if target_idx >= len(df):
        return None

    price0 = float(df.iloc[idx0]["Close"])
    price_n = float(df.iloc[target_idx]["Close"])
    if price0 == 0:
        return None
    return round((price_n / price0) - 1.0, 4)


# ---------------------------------------------------------------------------
# Beta
# ---------------------------------------------------------------------------

def _weekly_beta_vs_spy(ticker: str, as_of: date) -> Optional[float]:
    """Trailing ~1y weekly beta vs SPY from adjusted closes already fetched via get_ohlcv."""
    if ticker.upper() in getattr(config, "BETA_EXCLUDE_TICKERS", set()) | {"CASH", "CASH_MANUAL"}:
        return 0.0
    start = as_of - timedelta(days=400)
    t_df = get_ohlcv(ticker, start, as_of)
    s_df = get_ohlcv(BETA_REFERENCE, start, as_of)
    if t_df is None or s_df is None or t_df.empty or s_df.empty:
        return None
    try:
        t_close = t_df["Close"].astype(float)
        s_close = s_df["Close"].astype(float)
        # Align to weekly (Friday) closes
        t_w = t_close.resample("W-FRI").last().dropna()
        s_w = s_close.resample("W-FRI").last().dropna()
        joined = pd.concat([t_w.rename("t"), s_w.rename("s")], axis=1).dropna()
        if len(joined) < getattr(config, "MIN_BETA_DATA_POINTS", 30):
            return None
        t_ret = joined["t"].pct_change().dropna()
        s_ret = joined["s"].pct_change().dropna()
        common = t_ret.index.intersection(s_ret.index)
        if len(common) < getattr(config, "MIN_BETA_DATA_POINTS", 30):
            return None
        var_s = float(s_ret.loc[common].var())
        if var_s == 0:
            return None
        beta = float(t_ret.loc[common].cov(s_ret.loc[common]) / var_s)
        return float(np.clip(beta, -0.5, 3.5))
    except Exception as e:
        logger.warning(f"Weekly beta failed for {ticker}: {e}")
        return None


def get_ticker_beta(ticker: str, as_of: date) -> float:
    """Prefer existing yfinance info beta; else trailing weekly beta vs SPY. Default 1.0."""
    key = ticker.upper()
    if key in _BETA_CACHE:
        cached = _BETA_CACHE[key]
        return 1.0 if cached is None else cached

    if key in {"CASH", "CASH_MANUAL"} or key in getattr(config, "BETA_EXCLUDE_TICKERS", set()):
        _BETA_CACHE[key] = 0.0
        return 0.0

    beta: Optional[float] = None
    try:
        from utils.risk import get_ticker_beta_fast
        beta = get_ticker_beta_fast(key)
    except Exception:
        beta = None

    if beta is None:
        beta = _weekly_beta_vs_spy(key, as_of)

    if beta is None:
        beta = 1.0
    else:
        beta = float(np.clip(float(beta), -0.5, 3.5))

    _BETA_CACHE[key] = beta
    return beta


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_money(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("$", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


def _split_tickers(raw: str) -> List[str]:
    if not raw:
        return []
    parts = []
    for chunk in str(raw).replace("|", ",").split(","):
        t = chunk.strip().upper()
        if t:
            parts.append(t)
    # Preserve order, drop dupes
    seen = set()
    out = []
    for t in parts:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _parse_pipe_dates(raw: str) -> List[date]:
    if not raw:
        return []
    out = []
    for chunk in str(raw).replace(",", "|").split("|"):
        d = _parse_date(chunk.strip())
        if d:
            out.append(d)
    return out


def _row_get(row: Dict[str, Any], *names: str, default: str = "") -> Any:
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return default


def _classify_side(action_lc: str) -> str:
    for kw in SELL_ACTIONS:
        if kw in action_lc:
            return "sell"
    for kw in BUY_ACTIONS:
        if kw in action_lc:
            return "buy"
    return "other"


# ---------------------------------------------------------------------------
# Window + dollar weights (Steps 1–2)
# ---------------------------------------------------------------------------

def _cluster_dates(dates: List[date], gap_days: int) -> List[List[date]]:
    """Group dates into clusters where consecutive gaps are <= gap_days."""
    if not dates:
        return []
    ordered = sorted(set(dates))
    clusters: List[List[date]] = [[ordered[0]]]
    for d in ordered[1:]:
        if (d - clusters[-1][-1]).days <= gap_days:
            clusters[-1].append(d)
        else:
            clusters.append([d])
    return clusters


def _side_sum_in_window(
    txns: pd.DataFrame,
    tickers: Sequence[str],
    side: str,
    w0: date,
    w1: date,
) -> float:
    dollars = reconstruct_side_dollars(txns, tickers, side, w0, w1)
    return sum(dollars.values())


def fit_window_to_stated(
    txns: pd.DataFrame,
    sell_tickers: Sequence[str],
    buy_tickers: Sequence[str],
    anchor: date,
    stated_sell: float,
    stated_buy: float,
    seed_start: date,
    seed_end: date,
) -> Tuple[date, date, bool]:
    """
    Search contiguous windows around the seed that reconcile to stated proceeds.
    Returns (start, end, reconciled). Prefer exact ≤2% match; else keep seed.
    """
    if txns is None or txns.empty:
        return seed_start, seed_end, False

    # Candidate boundaries from actual trade dates near the seed
    pad = 21
    lo, hi = anchor - timedelta(days=pad), anchor + timedelta(days=pad)
    dates = sorted({
        d for d in txns[
            (txns["trade_date"] >= lo) & (txns["trade_date"] <= hi)
        ]["trade_date"].tolist()
    })
    if not dates:
        return seed_start, seed_end, False

    best = None  # (score, start, end)
    for i, d0 in enumerate(dates):
        for d1 in dates[i:]:
            if d0 > anchor or d1 < anchor:
                # Allow windows that don't contain anchor if seed didn't either,
                # but prefer those that include anchor.
                pass
            if (d1 - d0).days > pad:
                continue
            s = _side_sum_in_window(txns, sell_tickers, "sell", d0, d1)
            b = _side_sum_in_window(txns, buy_tickers, "buy", d0, d1)
            sell_ok = reconcile_weights(s, stated_sell) if stated_sell else s > 0
            buy_ok = reconcile_weights(b, stated_buy) if stated_buy else b > 0
            sell_err = abs(s - stated_sell) / stated_sell if stated_sell else 0.0
            buy_err = abs(b - stated_buy) / stated_buy if stated_buy else 0.0
            contains = 0 if d0 <= anchor <= d1 else 1
            score = (0 if (sell_ok and buy_ok) else 1, contains, sell_err + buy_err, (d1 - d0).days)
            if best is None or score < best[0]:
                best = (score, d0, d1, sell_ok and buy_ok)

    if best is None:
        return seed_start, seed_end, False
    _, d0, d1, ok = best
    if ok:
        return d0, d1, True
    return seed_start, seed_end, False


def resolve_window(
    row: Dict[str, Any],
    anchor: date,
    sell_tickers: Sequence[str],
    buy_tickers: Sequence[str],
    txns: Optional[pd.DataFrame] = None,
    stated_sell: float = 0.0,
    stated_buy: float = 0.0,
) -> Tuple[date, date, int]:
    """
    Return (window_start, window_end, window_days) for transaction lookup.

    Prefer Sell_Dates / Buy_Dates when present. Otherwise discover a date
    cluster near the anchor, then (when stated proceeds exist) fit a contiguous
    sub-window that reconciles within 2%.
    """
    sell_dates = _parse_pipe_dates(str(_row_get(row, "Sell_Dates", default="")))
    buy_dates = _parse_pipe_dates(str(_row_get(row, "Buy_Dates", default="")))
    all_dates = sell_dates + buy_dates

    raw_win = _row_get(row, "Cluster_Window_Days", default="")
    try:
        window_days = int(float(raw_win)) if raw_win not in ("", None) else CLUSTER_WINDOW_DAYS_DEFAULT
    except (TypeError, ValueError):
        window_days = CLUSTER_WINDOW_DAYS_DEFAULT

    if all_dates:
        pad = max(window_days, 0)
        return (
            min(all_dates) - timedelta(days=pad),
            max(all_dates) + timedelta(days=pad),
            max(window_days, (max(all_dates) - min(all_dates)).days),
        )

    discovery_pad = max(14, window_days * 7)
    gap = max(window_days + 1, 2)
    seed_start = anchor - timedelta(days=window_days)
    seed_end = anchor + timedelta(days=window_days)

    if txns is not None and not txns.empty and (sell_tickers or buy_tickers):
        d0, d1 = anchor - timedelta(days=discovery_pad), anchor + timedelta(days=discovery_pad)
        slice_df = txns[(txns["trade_date"] >= d0) & (txns["trade_date"] <= d1)].copy()
        if not slice_df.empty:
            slice_df["side"] = slice_df["action_lc"].apply(_classify_side)
            sell_set = {t.upper() for t in sell_tickers}
            buy_set = {t.upper() for t in buy_tickers}
            sell_hits = slice_df[(slice_df["side"] == "sell") & (slice_df["ticker"].isin(sell_set))]
            buy_hits = slice_df[(slice_df["side"] == "buy") & (slice_df["ticker"].isin(buy_set))]
            hit_dates: List[date] = []
            if not sell_hits.empty:
                hit_dates.extend(sell_hits["trade_date"].tolist())
            if not buy_hits.empty:
                hit_dates.extend(buy_hits["trade_date"].tolist())
            clusters = _cluster_dates(hit_dates, gap)
            chosen: Optional[List[date]] = None
            for cl in clusters:
                if any(abs((d - anchor).days) <= gap for d in cl) or (min(cl) <= anchor <= max(cl)):
                    chosen = cl
                    break
            if chosen is None and clusters:
                chosen = min(clusters, key=lambda cl: min(abs((d - anchor).days) for d in cl))
            if chosen:
                pad = max(window_days, 0)
                seed_start = min(chosen) - timedelta(days=pad)
                seed_end = max(chosen) + timedelta(days=pad)
                window_days = max(window_days, (max(chosen) - min(chosen)).days)

    if stated_sell or stated_buy:
        fitted0, fitted1, ok = fit_window_to_stated(
            txns if txns is not None else pd.DataFrame(),
            sell_tickers,
            buy_tickers,
            anchor,
            stated_sell,
            stated_buy,
            seed_start,
            seed_end,
        )
        if ok:
            return fitted0, fitted1, max(window_days, (fitted1 - fitted0).days)

    return seed_start, seed_end, window_days


def reconstruct_side_dollars(
    txns: pd.DataFrame,
    tickers: Sequence[str],
    side: str,
    window_start: date,
    window_end: date,
    target_amount: Optional[float] = None,
    anchor: Optional[date] = None,
) -> Dict[str, float]:
    """
    Sum abs(net_amount) per ticker for sell or buy actions in the window.
    If target_amount is set and the full-window sum overshoots by >2%, greedily
    select transactions nearest the anchor until the total reconciles — mirrors
    derive_rotations assigning buys without reuse across clusters.
    """
    empty = {t: 0.0 for t in tickers}
    if txns is None or txns.empty or not tickers:
        return empty

    df = txns[
        (txns["trade_date"] >= window_start)
        & (txns["trade_date"] <= window_end)
        & (txns["ticker"].isin([t.upper() for t in tickers]))
    ].copy()
    if df.empty:
        return empty

    df["side"] = df["action_lc"].apply(_classify_side)
    df = df[df["side"] == side].copy()
    if df.empty:
        return empty

    df["_abs"] = df["net_amount"].apply(lambda x: abs(float(x)))
    full_total = float(df["_abs"].sum())
    use_df = df

    if (
        target_amount
        and target_amount > 0
        and full_total > 0
        and not reconcile_weights(full_total, target_amount)
        and full_total > target_amount
    ):
        ref = anchor or window_start
        ranked = df.assign(
            _dist=df["trade_date"].apply(lambda d: abs((d - ref).days))
        ).sort_values(["_dist", "trade_date", "_abs"])
        chosen_idx: List[Any] = []
        running = 0.0
        for idx, r in ranked.iterrows():
            amt = float(r["_abs"])
            if running + amt > target_amount * (1.0 + WEIGHT_RECONCILE_TOL) and running > 0:
                if reconcile_weights(running, target_amount):
                    break
                continue
            chosen_idx.append(idx)
            running += amt
            if reconcile_weights(running, target_amount):
                break
        if chosen_idx and reconcile_weights(running, target_amount):
            use_df = df.loc[chosen_idx]

    dollars: Dict[str, float] = {t: 0.0 for t in tickers}
    for _, r in use_df.iterrows():
        t = str(r["ticker"]).upper()
        if t in dollars:
            dollars[t] += float(r["_abs"]) if "_abs" in r.index else abs(float(r["net_amount"]))
    return dollars


def net_both_sides(
    sell_dollars: Dict[str, float],
    buy_dollars: Dict[str, float],
) -> Tuple[Dict[str, float], Dict[str, float], List[str], Dict[str, Dict[str, float]]]:
    """
    Net tickers that appear on both sides into the side they dominate.
    Returns (sell_net, buy_net, both_sides_list, gross_detail).
    """
    both = sorted(set(sell_dollars) & set(buy_dollars))
    both = [t for t in both if sell_dollars.get(t, 0) > 0 and buy_dollars.get(t, 0) > 0]
    sell_net = dict(sell_dollars)
    buy_net = dict(buy_dollars)
    gross: Dict[str, Dict[str, float]] = {}

    for t in both:
        s_amt = sell_net.get(t, 0.0)
        b_amt = buy_net.get(t, 0.0)
        gross[t] = {"sell_gross": round(s_amt, 2), "buy_gross": round(b_amt, 2)}
        if s_amt >= b_amt:
            net = s_amt - b_amt
            if net > 0:
                sell_net[t] = net
            else:
                sell_net.pop(t, None)
            buy_net.pop(t, None)
            gross[t]["net_side"] = "sell"
            gross[t]["net_dollars"] = round(net, 2)
        else:
            net = b_amt - s_amt
            if net > 0:
                buy_net[t] = net
            else:
                buy_net.pop(t, None)
            sell_net.pop(t, None)
            gross[t]["net_side"] = "buy"
            gross[t]["net_dollars"] = round(net, 2)

    # Drop zero leftovers
    sell_net = {k: v for k, v in sell_net.items() if v > 0}
    buy_net = {k: v for k, v in buy_net.items() if v > 0}
    return sell_net, buy_net, both, gross


def reconcile_weights(
    reconstructed_total: float,
    stated_total: float,
) -> bool:
    """True if within 2% tolerance (or both near-zero)."""
    if stated_total == 0 and reconstructed_total == 0:
        return True
    if stated_total == 0:
        return False
    return abs(reconstructed_total - stated_total) / abs(stated_total) <= WEIGHT_RECONCILE_TOL


# ---------------------------------------------------------------------------
# Nested / superseded (Step 5)
# ---------------------------------------------------------------------------

def _ticker_set(raw: str) -> frozenset:
    return frozenset(_split_tickers(raw))


def find_superseded_groups(
    rows: List[Dict[str, Any]],
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """
    Among rows sharing an anchor Date, mark narrower ticker-set rows as
    SUPERSEDED_BY the widest. Returns (id -> superseding_id, group reports).
    """
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        d = str(_row_get(r, "Date", default="")).strip()
        by_date.setdefault(d, []).append(r)

    superseded: Dict[str, str] = {}
    groups_report: List[Dict[str, Any]] = []

    for d, group in by_date.items():
        if len(group) < 2:
            continue
        enriched = []
        for r in group:
            rid = str(_row_get(r, "Trade_Log_ID", "Stage_ID", default=""))
            sells = _ticker_set(str(_row_get(r, "Sell_Ticker", "Sell_Tickers", default="")))
            buys = _ticker_set(str(_row_get(r, "Buy_Ticker", "Buy_Tickers", default="")))
            enriched.append({"id": rid, "sells": sells, "buys": buys, "row": r})

        nested_pairs = []
        for i, a in enumerate(enriched):
            for j, b in enumerate(enriched):
                if i == j:
                    continue
                if a["sells"] <= b["sells"] and a["buys"] <= b["buys"]:
                    if a["sells"] < b["sells"] or a["buys"] < b["buys"]:
                        nested_pairs.append((a["id"], b["id"]))
                        # Prefer the widest known superseder
                        current = superseded.get(a["id"])
                        if current is None:
                            superseded[a["id"]] = b["id"]
                        else:
                            # Keep the one with larger combined set
                            cur_e = next(e for e in enriched if e["id"] == current)
                            if len(b["sells"]) + len(b["buys"]) >= len(cur_e["sells"]) + len(cur_e["buys"]):
                                superseded[a["id"]] = b["id"]

        if nested_pairs:
            widest_ids = [
                e["id"] for e in enriched
                if e["id"] not in superseded
            ]
            groups_report.append({
                "Date": d,
                "member_ids": [e["id"] for e in enriched],
                "widest_ids": widest_ids,
                "superseded": {k: v for k, v in superseded.items() if k in {e["id"] for e in enriched}},
                "pairs": nested_pairs,
            })

    return superseded, groups_report


# ---------------------------------------------------------------------------
# Weighted returns + benchmarks (Steps 3–4)
# ---------------------------------------------------------------------------

def side_price_coverage(
    dollars: Dict[str, float],
    anchor: date,
) -> float:
    """Share of side dollars with a usable close on/after the anchor (horizon-independent)."""
    total = sum(dollars.values())
    if total <= 0:
        return 0.0
    priced = 0.0
    for t, amt in dollars.items():
        if t.upper() == "CASH":
            priced += amt
            continue
        df = get_ohlcv(t, anchor)
        if df is None or df.empty:
            continue
        hits = df.index[df.index.date >= anchor] if hasattr(df.index, "date") else df.index[df.index >= pd.Timestamp(anchor)]
        if len(hits) > 0:
            priced += amt
    return round(priced / total, 4)


def weighted_side_return(
    dollars: Dict[str, float],
    anchor: date,
    trading_days: int,
    cash_yield: float,
) -> Tuple[Optional[float], float, Dict[str, Any]]:
    """
    Dollar-weighted return. Excludes unpriced tickers and renormalizes.
    Returns (weighted_return, coverage_pct_of_priced_for_horizon, detail).
    Coverage here is horizon-specific (None return = excluded); use
    side_price_coverage() for the row-level Coverage_Pct field.
    """
    total = sum(dollars.values())
    if total <= 0:
        return None, 0.0, {"priced": {}, "excluded": list(dollars)}

    priced: Dict[str, Dict[str, float]] = {}
    excluded: List[str] = []
    priced_dollars = 0.0

    for t, amt in dollars.items():
        ret = compute_return(t, anchor, trading_days, cash_yield)
        if ret is None:
            excluded.append(t)
            continue
        priced[t] = {"dollars": amt, "weight_gross": amt / total, "return": ret}
        priced_dollars += amt

    coverage = priced_dollars / total if total else 0.0
    if priced_dollars <= 0:
        return None, coverage, {"priced": priced, "excluded": excluded}

    w_ret = 0.0
    for t, info in priced.items():
        w = info["dollars"] / priced_dollars
        info["weight_renorm"] = w
        w_ret += w * info["return"]

    return round(w_ret, 4), round(coverage, 4), {"priced": priced, "excluded": excluded}


def weighted_side_beta(dollars: Dict[str, float], as_of: date) -> Optional[float]:
    total = sum(dollars.values())
    if total <= 0:
        return None
    acc = 0.0
    for t, amt in dollars.items():
        acc += (amt / total) * get_ticker_beta(t, as_of)
    return round(acc, 4)


def _fmt_pct(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return f"{v:.4f}"


def _fmt_display(v: Optional[float]) -> str:
    if v is None or v == "":
        return "—"
    try:
        return f"{float(v) * 100:+.2f}%"
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# Sheet row loading
# ---------------------------------------------------------------------------

def _sheet_rows_as_dicts(ws) -> List[Dict[str, Any]]:
    data = ws.get_all_values()
    if len(data) < 2:
        return []
    headers = data[0]
    out = []
    for r in data[1:]:
        padded = list(r) + [""] * (len(headers) - len(r))
        out.append(dict(zip(headers, padded[: len(headers)])))
    return out


def load_trade_log(ss) -> List[Dict[str, Any]]:
    try:
        ws = ss.worksheet(config.TAB_TRADE_LOG)
    except Exception:
        logger.error(f"Tab '{config.TAB_TRADE_LOG}' not found.")
        return []
    return _sheet_rows_as_dicts(ws)


def load_staging(ss) -> List[Dict[str, Any]]:
    try:
        ws = ss.worksheet(config.TAB_TRADE_LOG_STAGING)
    except Exception:
        logger.error(f"Tab '{config.TAB_TRADE_LOG_STAGING}' not found.")
        return []
    rows = _sheet_rows_as_dicts(ws)
    # Normalize staging plural / spaced headers → keys used elsewhere
    normalized = []
    for r in rows:
        n = dict(r)
        if "Sell_Tickers" in n and not n.get("Sell_Ticker"):
            n["Sell_Ticker"] = n["Sell_Tickers"]
        if "Buy_Tickers" in n and not n.get("Buy_Ticker"):
            n["Buy_Ticker"] = n["Buy_Tickers"]
        if "Stage_ID" in n and not n.get("Trade_Log_ID"):
            n["Trade_Log_ID"] = n["Stage_ID"]
        # Live staging headers are spaced: "Sell Dates", "Buy Dates", "Window"
        if n.get("Sell Dates") and not n.get("Sell_Dates"):
            n["Sell_Dates"] = n["Sell Dates"]
        if n.get("Buy Dates") and not n.get("Buy_Dates"):
            n["Buy_Dates"] = n["Buy Dates"]
        if n.get("Window") not in ("", None) and not n.get("Cluster_Window_Days"):
            n["Cluster_Window_Days"] = n["Window"]
        normalized.append(n)
    return normalized


def load_existing_review(ss) -> Dict[str, Dict[str, Any]]:
    existing: Dict[str, Dict[str, Any]] = {}
    try:
        ws = ss.worksheet(config.TAB_ROTATION_REVIEW)
        for r in _sheet_rows_as_dicts(ws):
            rid = r.get("Trade_Log_ID", "")
            if rid:
                existing[rid] = r
    except Exception:
        pass
    return existing


def get_cash_yield(ss) -> float:
    cash_yield = getattr(config, "DEFAULT_CASH_YIELD_PCT", 4.5)
    try:
        config_ws = ss.worksheet(config.TAB_CONFIG)
        for row in config_ws.get_all_values():
            if row and row[0] == "cash_yield_pct":
                cash_yield = float(row[1])
                break
    except Exception:
        pass
    return cash_yield


def cache_is_fresh(cached: Dict[str, Any], today: date) -> bool:
    """
    Preserve existing behaviour: skip recompute when as_of <= 7 days OR all
    Pair horizons filled. (Prompt Step 0 claimed AND; code historically used OR —
    Step 6 says preserve existing.)
    Also require Residual_Pair_30d so schema upgrades force one recompute.
    """
    try:
        as_of_str = cached.get("Attribution_As_Of", "")
        as_of_dt = datetime.strptime(as_of_str, "%Y-%m-%d").date()
        age_days = (today - as_of_dt).days
        horizons_filled = all(
            cached.get(f"Pair_Return_{h}d") not in ("", None) for h in HORIZONS
        )
        has_new_schema = cached.get("Residual_Pair_30d") not in ("", None) or cached.get("Status", "").startswith("SUPERSEDED")
        if not has_new_schema and cached.get("Status") != "WEIGHTS_UNRECONCILED":
            # Force recompute once after basket-aware upgrade
            if cached.get("Coverage_Pct") in ("", None) and not str(cached.get("Status", "")).startswith("SUPERSEDED"):
                return False
        if age_days <= 7 or horizons_filled:
            # Still recompute if new columns are blank (schema migration)
            if cached.get("Residual_Pair_30d") in ("", None) and not str(cached.get("Status", "")).startswith(
                ("SUPERSEDED", "WEIGHTS")
            ):
                if cached.get("Status") in ("", None) and cached.get("Coverage_Pct") in ("", None):
                    return False
            return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# Per-row attribution
# ---------------------------------------------------------------------------

def attribute_row(
    row: Dict[str, Any],
    txns: pd.DataFrame,
    cash_yield: float,
    today_str: str,
    weight_details_out: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    rid = str(_row_get(row, "Trade_Log_ID", "Stage_ID", default=""))
    dt_str = str(_row_get(row, "Date", default=""))
    anchor = _parse_date(dt_str)
    if anchor is None:
        return {
            "Trade_Log_ID": rid,
            "Date": dt_str,
            "Status": "BAD_DATE",
            "Attribution_As_Of": today_str,
            "Fingerprint": f"{rid}|{today_str}",
        }

    sell_tickers = _split_tickers(str(_row_get(row, "Sell_Ticker", "Sell_Tickers", default="")))
    buy_tickers = _split_tickers(str(_row_get(row, "Buy_Ticker", "Buy_Tickers", default="")))
    stated_sell = _parse_money(_row_get(row, "Sell_Proceeds", default=0))
    stated_buy = _parse_money(_row_get(row, "Buy_Amount", default=0))

    # Prefer a fitted window when possible; then reconstruct with target-aware
    # greedy selection so buy-side reuse across clusters does not overshoot.
    w_start, w_end, _win_days = resolve_window(
        row, anchor, sell_tickers, buy_tickers, txns, stated_sell, stated_buy
    )
    # Widen slightly so greedy has candidates; targets enforce the stated totals.
    w_start_ex = w_start - timedelta(days=2)
    w_end_ex = w_end + timedelta(days=2)
    sell_gross = reconstruct_side_dollars(
        txns, sell_tickers, "sell", w_start_ex, w_end_ex,
        target_amount=stated_sell, anchor=anchor,
    )
    buy_gross = reconstruct_side_dollars(
        txns, buy_tickers, "buy", w_start_ex, w_end_ex,
        target_amount=stated_buy, anchor=anchor,
    )

    recon_sell = sum(sell_gross.values())
    recon_buy = sum(buy_gross.values())
    sell_ok = reconcile_weights(recon_sell, stated_sell) if stated_sell else recon_sell > 0
    buy_ok = reconcile_weights(recon_buy, stated_buy) if stated_buy else recon_buy > 0

    # Both-sides from the row's ticker lists (gross), then net dollars for returns
    both_listed = sorted(set(sell_tickers) & set(buy_tickers))
    sell_net, buy_net, both_with_dollars, both_gross = net_both_sides(sell_gross, buy_gross)

    detail = {
        "Trade_Log_ID": rid,
        "Date": dt_str,
        "window": (str(w_start_ex), str(w_end_ex)),
        "stated_sell": stated_sell,
        "stated_buy": stated_buy,
        "recon_sell": round(recon_sell, 2),
        "recon_buy": round(recon_buy, 2),
        "sell_gross": {k: round(v, 2) for k, v in sell_gross.items()},
        "buy_gross": {k: round(v, 2) for k, v in buy_gross.items()},
        "sell_net": {k: round(v, 2) for k, v in sell_net.items()},
        "buy_net": {k: round(v, 2) for k, v in buy_net.items()},
        "both_sides": both_listed,
        "both_with_dollars": both_with_dollars,
        "both_gross": both_gross,
        "sell_ok": sell_ok,
        "buy_ok": buy_ok,
    }
    if weight_details_out is not None:
        weight_details_out.append(detail)

    base = {
        "Trade_Log_ID": rid,
        "Date": dt_str,
        "Sell_Ticker": _row_get(row, "Sell_Ticker", "Sell_Tickers", default=""),
        "Buy_Ticker": _row_get(row, "Buy_Ticker", "Buy_Tickers", default=""),
        "Rotation_Type": _row_get(row, "Rotation_Type", default=""),
        "Implicit_Bet": _row_get(row, "Implicit_Bet", default=""),
        "Sell_RSI_At_Decision": _row_get(row, "Sell_RSI_At_Decision", default=""),
        "Buy_RSI_At_Decision": _row_get(row, "Buy_RSI_At_Decision", default=""),
        "Sell_Trend_At_Decision": _row_get(row, "Sell_Trend_At_Decision", default=""),
        "Buy_Trend_At_Decision": _row_get(row, "Buy_Trend_At_Decision", default=""),
        "Both_Sides_Tickers": ", ".join(both_listed),
        "Beta_Reference": BETA_REFERENCE,
        "Bench_QQQ_Note": BENCH_QQQ_NOTE,
        "Attribution_As_Of": today_str,
        "Fingerprint": f"{rid}|{today_str}",
        "Status": "",
    }

    if not sell_ok or not buy_ok or not sell_net or not buy_net:
        base["Status"] = "WEIGHTS_UNRECONCILED"
        base["Coverage_Pct"] = ""
        logger.warning(
            f"{rid}: WEIGHTS_UNRECONCILED sell {recon_sell:.2f}/{stated_sell:.2f} "
            f"buy {recon_buy:.2f}/{stated_buy:.2f}"
        )
        return base

    sell_beta = weighted_side_beta(sell_net, anchor)
    buy_beta = weighted_side_beta(buy_net, anchor)
    base["Sell_Beta_Weighted"] = "" if sell_beta is None else sell_beta
    base["Buy_Beta_Weighted"] = "" if buy_beta is None else buy_beta

    coverage = min(side_price_coverage(sell_net, anchor), side_price_coverage(buy_net, anchor))
    base["Coverage_Pct"] = coverage

    matured_any = False
    for h in HORIZONS:
        s_ret, _, _ = weighted_side_return(sell_net, anchor, h, cash_yield)
        b_ret, _, _ = weighted_side_return(buy_net, anchor, h, cash_yield)

        spy = compute_return("SPY", anchor, h, cash_yield)
        vti = compute_return("VTI", anchor, h, cash_yield)
        qqq = compute_return("QQQ", anchor, h, cash_yield)

        pair = round(b_ret - s_ret, 4) if b_ret is not None and s_ret is not None else None
        vs_index = round(b_ret - vti, 4) if b_ret is not None and vti is not None else None
        sell_vs = round(s_ret - vti, 4) if s_ret is not None and vti is not None else None

        beta_explained = None
        residual = None
        if (
            pair is not None
            and spy is not None
            and sell_beta is not None
            and buy_beta is not None
        ):
            beta_explained = round((buy_beta - sell_beta) * spy, 4)
            residual = round(pair - beta_explained, 4)

        spread = None
        benches = [x for x in (spy, vti, qqq) if x is not None]
        if len(benches) >= 2:
            spread = round(max(benches) - min(benches), 4)

        if pair is not None:
            matured_any = True

        base[f"Sell_Return_{h}d"] = _fmt_pct(s_ret)
        base[f"Buy_Return_{h}d"] = _fmt_pct(b_ret)
        base[f"Pair_Return_{h}d"] = _fmt_pct(pair)
        base[f"Residual_Pair_{h}d"] = _fmt_pct(residual)
        base[f"Beta_Explained_Pair_{h}d"] = _fmt_pct(beta_explained)
        base[f"Vs_Index_{h}d"] = _fmt_pct(vs_index)
        base[f"Sell_Vs_Index_{h}d"] = _fmt_pct(sell_vs)
        base[f"Bench_SPY_{h}d"] = _fmt_pct(spy)
        base[f"Bench_VTI_{h}d"] = _fmt_pct(vti)
        base[f"Bench_QQQ_{h}d"] = _fmt_pct(qqq)
        base[f"Bench_Spread_{h}d"] = _fmt_pct(spread)

    if coverage < COVERAGE_FLAG_PCT:
        base["Status"] = f"LOW_COVERAGE:{coverage:.0%}"
    elif not matured_any:
        base["Status"] = "OK_HORIZONS_PENDING"
    else:
        base["Status"] = "OK"

    # Flag JEPI/JPIE-funded baskets — beta understates income/overlay risk given up
    funding_income = JEPI_INCOME_TICKERS & set(sell_net)
    if funding_income:
        note = (
            f"CAVEAT: funding side includes {', '.join(sorted(funding_income))} — "
            "realized equity beta understates risk-managed income given up; "
            "residual may misstate selection on this basket."
        )
        base["_jepi_caveat"] = note
        if base["Status"] == "OK":
            base["Status"] = "OK_JEPI_BETA_CAVEAT"

    return base


# ---------------------------------------------------------------------------
# Output: table, markdown, sheet write
# ---------------------------------------------------------------------------

def _dict_to_row(d: Dict[str, Any]) -> List[Any]:
    return [d.get(col, "") for col in config.ROTATION_REVIEW_COLUMNS]


def print_review_table(rows: List[Dict[str, Any]], title: str = "Rotation Attribution") -> None:
    table = Table(title=title, show_lines=False)
    cols = [
        "Trade_Log_ID", "Date", "Status", "Both_Sides_Tickers", "Coverage_Pct",
        "Sell_Beta_Weighted", "Buy_Beta_Weighted",
        "Residual_Pair_30d", "Pair_Return_30d", "Vs_Index_30d", "Sell_Vs_Index_30d",
        "Bench_VTI_30d", "Bench_SPY_30d", "Bench_QQQ_30d", "Bench_Spread_30d",
    ]
    for c in cols:
        table.add_column(c, overflow="fold")
    for r in rows:
        table.add_row(*[str(r.get(c, "")) for c in cols])
    console.print(table)


def _as_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def partition_rotation_rows(
    rows: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Split Rotation_Review rows into (included, excluded) for aggregate medians.
    Excludes SUPERSEDED_BY*/WEIGHTS_UNRECONCILED, Coverage_Pct < COVERAGE_FLAG_PCT,
    and any Status not starting with OK. Shared by build_track_record_summary()
    and any other surface (e.g. 0_DASHBOARD) reporting the same aggregate so the
    classification can't drift between call sites.
    """
    excluded = []
    included = []
    for r in rows:
        status = str(r.get("Status") or "")
        cov = _as_float(r.get("Coverage_Pct"))
        if status.startswith("SUPERSEDED") or status == "WEIGHTS_UNRECONCILED":
            excluded.append(r)
            continue
        if cov is not None and cov < COVERAGE_FLAG_PCT:
            excluded.append(r)
            continue
        if not status.startswith("OK"):
            excluded.append(r)
            continue
        included.append(r)
    return included, excluded


def compute_vti_qqq_signflips(included: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
    """
    Count included rows where the buy's return vs VTI and vs QQQ disagree in
    sign on at least one horizon (counted once per row, first horizon found).
    Shared by build_track_record_summary() and 0_DASHBOARD's rotation block.
    """
    flip_count = 0
    flip_rows: List[str] = []
    for r in included:
        for h in HORIZONS:
            vti_vs = _as_float(r.get(f"Vs_Index_{h}d"))
            vti_bn = _as_float(r.get(f"Bench_VTI_{h}d"))
            qqq_bn = _as_float(r.get(f"Bench_QQQ_{h}d"))
            if vti_vs is None or vti_bn is None or qqq_bn is None:
                continue
            # Buy - QQQ = (Buy - VTI) + VTI - QQQ
            vs_qqq = vti_vs + vti_bn - qqq_bn
            if (vti_vs > 0 and vs_qqq < 0) or (vti_vs < 0 and vs_qqq > 0):
                flip_count += 1
                flip_rows.append(
                    f"`{r.get('Trade_Log_ID', '')}` {h}d: "
                    f"Vs_VTI={vti_vs:+.2%} Vs_QQQ={vs_qqq:+.2%}"
                )
                break
    return flip_count, flip_rows


def build_track_record_summary(rows: List[Dict[str, Any]]) -> List[str]:
    """
    Aggregate medians/means for the question this build exists for.
    Excludes Coverage_Pct < 0.90 and Status not starting with OK.
    """
    lines = [
        "## Track-record summary (evidence, not a scorecard)",
        "",
        "One market regime; benchmark choice can flip the sign on tech-heavy buys. "
        "Read medians as a range, not a verdict.",
        "",
    ]

    included, excluded = partition_rotation_rows(rows)

    lines.append(f"Included in medians: **{len(included)}** rows. Excluded: **{len(excluded)}**.")
    if excluded:
        lines.append("")
        lines.append("Excluded (Coverage < 90% or Status not OK*):")
        for r in excluded:
            lines.append(
                f"- `{r.get('Trade_Log_ID', '')}` {r.get('Date', '')} "
                f"status=`{r.get('Status', '')}` coverage=`{r.get('Coverage_Pct', '')}`"
            )
    lines.append("")

    flip_count, flip_rows = compute_vti_qqq_signflips(included)

    lines.append(f"**VTI-vs-QQQ sign-flip rows:** {flip_count} of {len(included)}")
    for fr in flip_rows:
        lines.append(f"- {fr}")
    lines.append("")

    lines.append(
        "| Horizon | N matured | Residual median | Residual mean | "
        "Residual +/- | Vs_Index (VTI) median | Sell_Vs_Index median |"
    )
    lines.append("|---|---|---|---|---|---|---|")

    for h in HORIZONS:
        residuals: List[float] = []
        vs_idx: List[float] = []
        sell_vs: List[float] = []
        for r in included:
            res = _as_float(r.get(f"Residual_Pair_{h}d"))
            if res is None:
                continue
            residuals.append(res)
            v = _as_float(r.get(f"Vs_Index_{h}d"))
            s = _as_float(r.get(f"Sell_Vs_Index_{h}d"))
            if v is not None:
                vs_idx.append(v)
            if s is not None:
                sell_vs.append(s)
        n = len(residuals)
        if n == 0:
            lines.append(f"| {h}d | 0 | — | — | — | — | — |")
            continue
        med = float(np.median(residuals))
        mean = float(np.mean(residuals))
        pos = sum(1 for x in residuals if x > 0)
        neg = sum(1 for x in residuals if x < 0)
        vmed = f"{float(np.median(vs_idx)):+.2%}" if vs_idx else "—"
        smed = f"{float(np.median(sell_vs)):+.2%}" if sell_vs else "—"
        lines.append(
            f"| {h}d | {n} | {med:+.2%} | {mean:+.2%} | +{pos}/-{neg} | {vmed} | {smed} |"
        )

    lines.append("")
    lines.append(
        "Open caution: sample is one regime; on row 63.5 Bench_Spread_30d was 8.46% "
        "and Vs_Index flipped sign between VTI and QQQ."
    )
    lines.append("")
    return lines


def write_markdown_summary(
    rows: List[Dict[str, Any]],
    groups: List[Dict[str, Any]],
    weight_details: List[Dict[str, Any]],
    source: str,
    live: bool,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    path = OUTPUT_DIR / f"rotation_attribution_{today}.md"
    lines = [
        f"# Rotation Attribution — {today}",
        "",
        f"Source: `{source}` | Live write: `{live}` | Beta reference: `{BETA_REFERENCE}`",
        "",
        "## Headline",
        "",
        "`Residual_Pair_Nd` = selection net of the risk step-up "
        "(Pair_Return − (Buy_Beta − Sell_Beta) × Bench_SPY).",
        "Primary index counterfactual is **VTI** (`Vs_Index_Nd`). SPY and QQQ are context.",
        "",
        "### Open caveat (JEPI/JPIE)",
        "",
        "Beta is weakest where Bill funds from risk-managed income (JEPI/JPIE): "
        "realized equity beta understates what he is giving up. If residuals look wrong "
        "on those baskets, the fix is a different normalizer — not a patch to the beta math.",
        "",
    ]
    lines += build_track_record_summary(rows)

    if groups:
        lines += ["## Nested / superseded groups (read-only; Trade_Log untouched)", ""]
        for g in groups:
            lines.append(
                f"- **{g['Date']}**: members `{g['member_ids']}` → "
                f"widest `{g['widest_ids']}`; superseded `{g['superseded']}`"
            )
        lines.append("")

    lines += ["## Results", ""]
    for r in rows:
        rid = r.get("Trade_Log_ID", "")
        lines.append(f"### {rid} — {r.get('Date', '')} [{r.get('Status', '')}]")
        lines.append("")
        lines.append(f"- Sell: `{r.get('Sell_Ticker', '')}`")
        lines.append(f"- Buy: `{r.get('Buy_Ticker', '')}`")
        if r.get("Both_Sides_Tickers"):
            lines.append(f"- Both sides: `{r.get('Both_Sides_Tickers')}`")
        lines.append(f"- Coverage: `{r.get('Coverage_Pct', '')}`")
        lines.append(
            f"- Betas (vs {BETA_REFERENCE}): sell `{r.get('Sell_Beta_Weighted')}` / "
            f"buy `{r.get('Buy_Beta_Weighted')}`"
        )
        if r.get("_jepi_caveat"):
            lines.append(f"- **{r['_jepi_caveat']}**")
        lines.append("")
        lines.append("| Horizon | Residual (headline) | Pair | Vs_Index (VTI) | Sell_Vs_Index | SPY | VTI | QQQ | Spread |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for h in HORIZONS:
            lines.append(
                f"| {h}d | {_fmt_display(r.get(f'Residual_Pair_{h}d') or None)} | "
                f"{_fmt_display(r.get(f'Pair_Return_{h}d') or None)} | "
                f"{_fmt_display(r.get(f'Vs_Index_{h}d') or None)} | "
                f"{_fmt_display(r.get(f'Sell_Vs_Index_{h}d') or None)} | "
                f"{_fmt_display(r.get(f'Bench_SPY_{h}d') or None)} | "
                f"{_fmt_display(r.get(f'Bench_VTI_{h}d') or None)} | "
                f"{_fmt_display(r.get(f'Bench_QQQ_{h}d') or None)} | "
                f"{_fmt_display(r.get(f'Bench_Spread_{h}d') or None)} |"
            )
        lines.append("")
        # Worked beta example for 30d when numbers exist
        try:
            pair = float(r["Pair_Return_30d"]) if r.get("Pair_Return_30d") not in ("", None) else None
            spy = float(r["Bench_SPY_30d"]) if r.get("Bench_SPY_30d") not in ("", None) else None
            sb = float(r["Sell_Beta_Weighted"]) if r.get("Sell_Beta_Weighted") not in ("", None) else None
            bb = float(r["Buy_Beta_Weighted"]) if r.get("Buy_Beta_Weighted") not in ("", None) else None
            be = float(r["Beta_Explained_Pair_30d"]) if r.get("Beta_Explained_Pair_30d") not in ("", None) else None
            res = float(r["Residual_Pair_30d"]) if r.get("Residual_Pair_30d") not in ("", None) else None
            if all(x is not None for x in (pair, spy, sb, bb, be, res)):
                lines.append("**30d beta decomposition (check by hand):**")
                lines.append("")
                lines.append(
                    f"`Beta_Explained = ({bb:.4f} − {sb:.4f}) × {spy:.4f} = {be:.4f}`"
                )
                lines.append(
                    f"`Residual = {pair:.4f} − {be:.4f} = {res:.4f}`"
                )
                lines.append("")
        except (TypeError, ValueError):
            pass

    if weight_details:
        lines += ["## Weight reconciliation detail", ""]
        for d in weight_details:
            lines.append(f"### {d['Trade_Log_ID']} ({d['Date']})")
            lines.append(
                f"Window `{d['window'][0]}` → `{d['window'][1]}`. "
                f"Sell reconstructed `${d['recon_sell']:,.2f}` vs stated `${d['stated_sell']:,.2f}` "
                f"({'OK' if d['sell_ok'] else 'FAIL'}). "
                f"Buy reconstructed `${d['recon_buy']:,.2f}` vs stated `${d['stated_buy']:,.2f}` "
                f"({'OK' if d['buy_ok'] else 'FAIL'})."
            )
            lines.append("")
            lines.append("Sell gross:")
            for t, v in sorted(d["sell_gross"].items(), key=lambda x: -x[1]):
                lines.append(f"- {t}: ${v:,.2f}")
            lines.append("")
            lines.append("Buy gross:")
            for t, v in sorted(d["buy_gross"].items(), key=lambda x: -x[1]):
                lines.append(f"- {t}: ${v:,.2f}")
            if d["both_sides"]:
                lines.append("")
                lines.append(f"Both-sides netting: {d['both_sides']}")
                for t, g in d["both_gross"].items():
                    lines.append(
                        f"- {t}: sell ${g['sell_gross']:,.2f} / buy ${g['buy_gross']:,.2f} "
                        f"→ net {g['net_side']} ${g['net_dollars']:,.2f}"
                    )
            lines.append("")

    lines += [
        "## Data notes",
        "",
        "- Returns use yfinance `auto_adjust=True` closes (dividend-adjusted total return), "
        "not price-only.",
        f"- {BENCH_QQQ_NOTE}",
        "- Nothing in Trade_Log / Trade_Log_Staging was modified by this run.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Wrote markdown summary → {path}")
    return path


def _read_historical_transactions(ss, since: date, until: date) -> pd.DataFrame:
    """
    Read Transactions_Historical_AllAccounts (all 6 accounts, 2025-01-01 ->
    2026-08-03) in the same shape _read_transactions() returns. Rows on/after
    SCOPE_FIX_DATE are dropped -- the live Transactions tab is already
    correctly 3-account-scoped from that date forward, so only the pre-fix
    window is this tab's reason to exist. Never touches the Transactions tab.
    """
    try:
        existing_tabs = {ws.title for ws in ss.worksheets()}
        if HISTORICAL_LEDGER_TAB not in existing_tabs:
            logger.warning("Historical ledger tab '%s' not found.", HISTORICAL_LEDGER_TAB)
            return pd.DataFrame()
        ws = ss.worksheet(HISTORICAL_LEDGER_TAB)
        rows = ws.get_all_values()
    except Exception as e:
        logger.warning("Could not read %s: %s", HISTORICAL_LEDGER_TAB, e)
        return pd.DataFrame()

    if len(rows) < 2:
        return pd.DataFrame()

    headers = [h.strip() for h in rows[0]]
    df = pd.DataFrame(rows[1:], columns=headers)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    date_col = next((c for c in df.columns if c in ("trade_date", "date")), None)
    ticker_col = next((c for c in df.columns if c in ("ticker", "symbol")), None)
    action_col = next((c for c in df.columns if c in ("action",)), None)
    amount_col = next((c for c in ("net_amount", "amount") if c in df.columns), None)
    if not all([date_col, ticker_col, action_col]):
        return pd.DataFrame()

    def _pdate(val: str) -> Optional[date]:
        val = str(val).strip()
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                return datetime.strptime(val, fmt).date()
            except Exception:
                continue
        return None

    def _pamount(v) -> float:
        if not v:
            return 0.0
        s = str(v).strip().replace("$", "").replace(",", "")
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        try:
            return float(s)
        except Exception:
            return 0.0

    df["trade_date"] = df[date_col].apply(_pdate)
    df = df[df["trade_date"].notna()].copy()
    df = df[
        (df["trade_date"] >= since)
        & (df["trade_date"] <= until)
        & (df["trade_date"] < SCOPE_FIX_DATE)
    ]
    df["net_amount"] = df[amount_col].apply(_pamount) if amount_col else 0.0
    df["ticker"] = df[ticker_col].str.strip().str.upper()
    df["action_lc"] = df[action_col].str.strip().str.lower()

    return df[["trade_date", "ticker", "action_lc", "net_amount"]].reset_index(drop=True)


def _read_transactions_combined(
    ss, since: date, until: date, use_historical_ledger: bool
) -> pd.DataFrame:
    """
    Default (flag absent): identical to _read_transactions(since, until) --
    current-scope behavior unchanged. With --historical-ledger: unions in
    Transactions_Historical_AllAccounts's pre-2026-08-03 rows (all 6 accounts)
    for that window, de-duped against the primary tab's already-scoped rows on
    (trade_date, ticker, action_lc, net_amount) so the 3 in-scope accounts
    aren't double-counted.
    """
    primary = _read_transactions(since, until)
    if not use_historical_ledger:
        return primary

    hist = _read_historical_transactions(ss, since, until)
    if hist.empty:
        return primary

    combined = pd.concat([primary, hist], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(
        subset=["trade_date", "ticker", "action_lc", "net_amount"], keep="first"
    )
    logger.info(
        "historical-ledger: primary=%d + historical=%d -> %d combined "
        "(%d exact duplicates dropped)",
        len(primary), len(hist), len(combined), before - len(combined),
    )
    return combined


def archive_rotation_review(ss, run_ts: str) -> None:
    """Archive prior Rotation_Review rows locally before clear-and-rebuild."""
    try:
        ws = ss.worksheet(config.TAB_ROTATION_REVIEW)
        data = ws.get_all_values()
    except Exception:
        return
    if len(data) <= 1:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = run_ts.replace(":", "").replace(" ", "_")
    path = OUTPUT_DIR / f"archive_rotation_review_{safe_ts}.csv"
    # Simple CSV write
    import csv
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(data)
    logger.info(f"Archived {len(data) - 1} prior Rotation_Review row(s) → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_attribution(
    live: bool = False,
    from_staging: bool = False,
    staging_dates: Optional[Sequence[str]] = None,
    use_historical_ledger: bool = False,
) -> List[Dict[str, Any]]:
    """
    Main execution. Default dry-run prints table and writes local markdown only.
    --live archives then rebuilds Rotation_Review.
    --from-staging is read-only backfill against Trade_Log_Staging (never writes Sheets).
    --historical-ledger (default off): for rotations dated before 2026-08-03,
    reconstruct weights from the union of Transactions and
    Transactions_Historical_AllAccounts (all 6 accounts) instead of the
    3-account-scoped Transactions tab alone. Default-off behavior is
    unchanged from before this flag existed.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    cash_yield = get_cash_yield(ss)
    today_dt = date.today()
    today_str = today_dt.strftime("%Y-%m-%d")

    if from_staging:
        source_rows = load_staging(ss)
        source_name = config.TAB_TRADE_LOG_STAGING
        if staging_dates:
            want = set(staging_dates)
            source_rows = [
                r for r in source_rows
                if str(_row_get(r, "Date", default="")) in want
            ]
        live = False  # hard gate: staging path never writes Sheets
    else:
        source_rows = load_trade_log(ss)
        source_name = config.TAB_TRADE_LOG

    if not source_rows:
        logger.info(f"{source_name} is empty.")
        return []

    superseded_map, groups = find_superseded_groups(source_rows)
    if groups:
        console.print("[yellow]Nested/superseded groups found (Trade_Log untouched):[/yellow]")
        for g in groups:
            console.print(
                f"  Date {g['Date']}: widest={g['widest_ids']} "
                f"superseded={g['superseded']}"
            )

    # Transaction window spanning all candidate anchors
    anchors = [_parse_date(_row_get(r, "Date", default="")) for r in source_rows]
    anchors = [a for a in anchors if a]
    if anchors:
        since = min(anchors) - timedelta(days=14)
        until = max(anchors) + timedelta(days=14)
    else:
        since, until = today_dt - timedelta(days=180), today_dt

    txns = _read_transactions_combined(ss, since, until, use_historical_ledger)
    logger.info(f"Loaded {len(txns)} transactions from {since} → {until}")

    existing_review = {} if from_staging else load_existing_review(ss)
    review_dicts: List[Dict[str, Any]] = []
    weight_details: List[Dict[str, Any]] = []

    for row in source_rows:
        rid = str(_row_get(row, "Trade_Log_ID", "Stage_ID", default=""))

        if rid in superseded_map:
            parent = superseded_map[rid]
            review_dicts.append({
                "Trade_Log_ID": rid,
                "Date": _row_get(row, "Date", default=""),
                "Sell_Ticker": _row_get(row, "Sell_Ticker", "Sell_Tickers", default=""),
                "Buy_Ticker": _row_get(row, "Buy_Ticker", "Buy_Tickers", default=""),
                "Rotation_Type": _row_get(row, "Rotation_Type", default=""),
                "Implicit_Bet": _row_get(row, "Implicit_Bet", default=""),
                "Status": f"SUPERSEDED_BY: {parent}",
                "Attribution_As_Of": today_str,
                "Fingerprint": f"{rid}|{today_str}",
                "Beta_Reference": BETA_REFERENCE,
                "Bench_QQQ_Note": BENCH_QQQ_NOTE,
            })
            continue

        cached = existing_review.get(rid)
        if cached and cache_is_fresh(cached, today_dt) and not from_staging:
            # Pad missing new cols
            padded = {col: cached.get(col, "") for col in config.ROTATION_REVIEW_COLUMNS}
            review_dicts.append(padded)
            continue

        attributed = attribute_row(row, txns, cash_yield, today_str, weight_details)
        review_dicts.append(attributed)

    print_review_table(review_dicts, title=f"Rotation Attribution ({source_name})")
    md_path = write_markdown_summary(
        review_dicts, groups, weight_details, source_name, live=live and not from_staging
    )
    console.print(f"[cyan]Markdown summary:[/cyan] {md_path}")

    if from_staging:
        logger.info("FROM-STAGING: read-only — no Sheet writes.")
        return review_dicts

    if not live:
        logger.info(
            f"DRY RUN: Would write {len(review_dicts)} rows to {config.TAB_ROTATION_REVIEW}. "
            "No Sheet writes performed."
        )
        return review_dicts

    # Live write
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    archive_rotation_review(ss, run_ts)

    try:
        review_ws = ss.worksheet(config.TAB_ROTATION_REVIEW)
    except Exception:
        review_ws = ss.add_worksheet(
            title=config.TAB_ROTATION_REVIEW,
            rows=1000,
            cols=len(config.ROTATION_REVIEW_COLUMNS),
        )
        time.sleep(1)

    review_rows = [_dict_to_row(d) for d in review_dicts]
    review_ws.clear()
    time.sleep(1)
    review_ws.update(
        range_name="A1",
        values=[config.ROTATION_REVIEW_COLUMNS],
        value_input_option="USER_ENTERED",
    )
    time.sleep(1)
    if review_rows:
        review_ws.update(
            range_name="A2",
            values=review_rows,
            value_input_option="USER_ENTERED",
        )
        logger.info(f"SUCCESS: Wrote {len(review_rows)} rows to {config.TAB_ROTATION_REVIEW}")

    try:
        from tasks.format_sheets_dashboard_v2 import format_rotation_review
        format_rotation_review(ss)
    except Exception as e:
        logger.warning(f"Formatting failed: {e}")

    return review_dicts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Basket-aware rotation attribution")
    parser.add_argument("--live", action="store_true", help="Write to Rotation_Review")
    parser.add_argument(
        "--from-staging",
        action="store_true",
        help="Read-only attribution against Trade_Log_Staging (never writes Sheets)",
    )
    parser.add_argument(
        "--staging-dates",
        type=str,
        default="",
        help="Comma-separated YYYY-MM-DD filter when using --from-staging",
    )
    parser.add_argument(
        "--historical-ledger",
        action="store_true",
        help=(
            "For rotations before 2026-08-03, reconstruct weights from the union of "
            "Transactions and Transactions_Historical_AllAccounts (all 6 Schwab "
            "accounts) instead of the 3-account-scoped Transactions tab alone. "
            "Default off; behavior with the flag absent is unchanged."
        ),
    )
    args = parser.parse_args()
    dates = [d.strip() for d in args.staging_dates.split(",") if d.strip()] or None
    run_attribution(
        live=args.live,
        from_staging=args.from_staging,
        staging_dates=dates,
        use_historical_ledger=args.historical_ledger,
    )
