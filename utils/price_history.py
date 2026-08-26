"""
Canonical OHLCV accessor — the only module that chooses Schwab vs yfinance.

Phase 1 (2026-08-25) verdict: Schwab daily bars are split-adjusted but NOT
dividend-adjusted (match yfinance auto_adjust=False; JEPI/XOM/VTI evidence in
agent_outputs/schwab_probe/price_history_reconciliation_2026-08-25.md).

Therefore:
  adjusted=True  → yfinance auto_adjust=True; Schwab cannot honor dividend
                   adjustment — Schwab leg returns split-only bars and
                   attrs["adjusted"] is False with a WARNING.
  adjusted=False → both legs return unadjusted (Schwab native; yf auto_adjust=False).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd

import config

logger = logging.getLogger(__name__)

_FALLBACK_COUNT = 0
_FALLBACK_EVENTS: list[dict] = []

_EMPTY_COLS = ["open", "high", "low", "close", "volume"]


def fallback_stats() -> dict:
    return {
        "fallback_count": _FALLBACK_COUNT,
        "events": list(_FALLBACK_EVENTS),
    }


def reset_fallback_stats() -> None:
    global _FALLBACK_COUNT, _FALLBACK_EVENTS
    _FALLBACK_COUNT = 0
    _FALLBACK_EVENTS = []


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=_EMPTY_COLS)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty()
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    # Map common aliases
    rename = {}
    for c in list(out.columns):
        if c in ("adj close", "adjclose"):
            rename[c] = "close"
    if rename:
        out = out.rename(columns=rename)
    keep = [c for c in _EMPTY_COLS if c in out.columns]
    if "close" not in keep:
        return _empty()
    out = out[keep]
    for c in keep:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["close"])
    if out.empty:
        return _empty()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    out.index = idx
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def _from_yfinance(
    ticker: str, period_days: int, interval: str, adjusted: bool
) -> pd.DataFrame:
    import yfinance as yf

    interval_map = {
        "daily": "1d",
        "weekly": "1wk",
        "1min": "1m",
        "5min": "5m",
        "15min": "15m",
        "30min": "30m",
    }
    yf_interval = interval_map.get(interval, "1d")
    try:
        df = yf.download(
            ticker,
            period=f"{max(period_days, 1)}d",
            interval=yf_interval,
            auto_adjust=bool(adjusted),
            progress=False,
            threads=False,
        )
    except Exception as e:
        logger.warning("price_history yfinance failed for %s: %s", ticker, e)
        return _empty()
    if df is None or df.empty:
        return _empty()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return _normalize(df)


def _from_schwab(
    ticker: str, period_days: int, interval: str, adjusted: bool
) -> pd.DataFrame:
    from utils.schwab_client import get_market_client, fetch_price_history

    client = get_market_client()
    if client is None:
        logger.warning("price_history: market client unavailable for %s", ticker)
        return _empty()
    df = fetch_price_history(
        client, ticker, period_days=period_days, interval=interval, use_cache=True
    )
    out = _normalize(df)
    if adjusted and not out.empty:
        logger.warning(
            "price_history: Schwab cannot dividend-adjust %s — returning "
            "split-adjusted-only bars (Phase 1 verdict)",
            ticker,
        )
    return out


def get_bars(
    ticker: str,
    period_days: int = 365,
    interval: str = "daily",
    source: Optional[str] = None,
    adjusted: bool = True,
) -> pd.DataFrame:
    """
    Canonical OHLCV accessor. Columns: open, high, low, close, volume.
    tz-aware UTC DatetimeIndex, ascending. Empty DataFrame on total failure.

    source semantics:
      "yfinance" — yfinance only (current behaviour)
      "schwab"   — Schwab only; empty on failure, NO silent fallback
      "auto"     — Schwab first, yfinance on empty/exception, with a WARNING
                   naming the ticker and the reason

    Phase 1 verdict (cite): Schwab bars are NOT dividend-adjusted. See module docstring.
    """
    global _FALLBACK_COUNT, _FALLBACK_EVENTS

    src = (source or getattr(config, "PRICE_HISTORY_SOURCE", "yfinance") or "yfinance").lower()
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return _empty()

    def _stamp(df: pd.DataFrame, used: str, adj_flag: bool) -> pd.DataFrame:
        df = df.copy() if not df.empty else _empty()
        df.attrs["source"] = used
        df.attrs["adjusted"] = bool(adj_flag)
        return df

    if src == "yfinance":
        df = _from_yfinance(ticker, period_days, interval, adjusted)
        return _stamp(df, "yfinance", adjusted if not df.empty else adjusted)

    if src == "schwab":
        df = _from_schwab(ticker, period_days, interval, adjusted)
        # Schwab never dividend-adjusts
        return _stamp(df, "schwab", False if not df.empty else False)

    if src == "auto":
        try:
            df = _from_schwab(ticker, period_days, interval, adjusted)
            if not df.empty:
                return _stamp(df, "schwab", False)
            reason = "empty schwab frame"
        except Exception as e:
            df = _empty()
            reason = f"schwab exception: {e}"
        logger.warning(
            "price_history AUTO fallback → yfinance for %s (%s)", ticker, reason
        )
        _FALLBACK_COUNT += 1
        _FALLBACK_EVENTS.append(
            {"ticker": ticker, "reason": reason, "ts": time.time()}
        )
        ydf = _from_yfinance(ticker, period_days, interval, adjusted)
        return _stamp(ydf, "yfinance", adjusted)

    logger.error("price_history: unknown source %r — returning empty", src)
    return _empty()
