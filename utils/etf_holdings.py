"""
ETF top-holdings lookup for look-through concentration math.

Purpose:
    Answer "what is my true exposure to NVDA once I count what's inside QQQM
    and VTI?" The positions table shows direct weights only, so single-name
    concentration is systematically understated for a book that is ~50% ETFs.

Inputs:
    - ETF ticker symbols (str)
    - Disk cache under data/etf_holdings_cache/{TICKER}.json (TTL 30 days)

Outputs:
    - get_top_holdings(ticker)  -> list[{"symbol", "name", "weight_pct"}] | None
    - compute_lookthrough(...)  -> combined direct + indirect weight per symbol

Dependencies:
    - yfinance (already in requirements.txt; no new vendor)
    - No API key required. Network optional: every function degrades to None or
      an empty result rather than raising, so callers can run offline.

Notes:
    FMP's ETF holdings endpoint (/stable/etf/holdings) is Ultimate-tier only
    ($149/mo as of 2026-07). yfinance's funds_data.top_holdings covers the
    top ~10 for free, which is enough for concentration work. Top-10 does NOT
    sum to 100% of a fund, so all look-through numbers here are FLOORS, not
    exact exposures. Callers must label them as such.
"""

from __future__ import annotations

import json
import logging
import os
import time

CACHE_DIR = os.path.join("data", "etf_holdings_cache")
CACHE_TTL_SECONDS = 30 * 24 * 3600  # holdings drift slowly; monthly is plenty

logger = logging.getLogger(__name__)


def _cache_path(ticker: str) -> str:
    return os.path.join(CACHE_DIR, "%s.json" % ticker.upper())


def _read_cache(ticker: str):
    path = _cache_path(ticker)
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > CACHE_TTL_SECONDS:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_cache(ticker: str, holdings) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(ticker), "w", encoding="utf-8", newline="\n") as f:
            json.dump(holdings, f, indent=2)
    except OSError as e:
        logger.warning("etf_holdings: cache write failed for %s: %s", ticker, e)


def get_top_holdings(ticker: str, use_network: bool = True):
    """Top ~10 holdings for an ETF, or None if unavailable.

    Returns [{"symbol": "NVDA", "name": "NVIDIA Corp", "weight_pct": 8.9}, ...]
    Weights are percent of fund (0-100), not fractions.
    """
    cached = _read_cache(ticker)
    if cached is not None:
        return cached
    if not use_network:
        return None

    try:
        import yfinance as yf
    except ImportError:
        logger.warning("etf_holdings: yfinance not installed; look-through skipped")
        return None

    try:
        funds = yf.Ticker(ticker).funds_data
        top = funds.top_holdings
    except Exception as e:  # noqa: BLE001 - yfinance raises many shapes
        logger.info("etf_holdings: no holdings for %s (%s)", ticker, e)
        return None

    if top is None or getattr(top, "empty", True):
        return None

    holdings = []
    try:
        for symbol, row in top.iterrows():
            weight = row.get("Holding Percent")
            if weight is None:
                continue
            weight = float(weight)
            # yfinance returns fractions (0.089); normalize to percent.
            if weight <= 1.0:
                weight *= 100.0
            holdings.append(
                {
                    "symbol": str(symbol).upper(),
                    "name": str(row.get("Name", "")),
                    "weight_pct": round(weight, 2),
                }
            )
    except Exception as e:  # noqa: BLE001
        logger.info("etf_holdings: parse failed for %s (%s)", ticker, e)
        return None

    if not holdings:
        return None
    _write_cache(ticker, holdings)
    return holdings


def compute_lookthrough(positions, etf_tickers, use_network: bool = True):
    """Combined direct + indirect single-name exposure.

    positions:   iterable of dicts with "ticker" and "weight_pct"
    etf_tickers: which of those positions to look inside

    Returns (rows, resolved, unresolved) where rows is a list of
    {"symbol", "direct_pct", "indirect_pct", "total_pct", "via"} sorted by
    total_pct descending, and resolved/unresolved are ticker lists describing
    which ETFs actually returned holdings data.

    Every number is a FLOOR: only the top ~10 holdings of each fund are known,
    so true indirect exposure is at least this much and probably more.
    """
    direct = {}
    for p in positions:
        t = (p.get("ticker") or "").upper()
        if t:
            direct[t] = direct.get(t, 0.0) + float(p.get("weight_pct") or 0.0)

    indirect = {}
    via = {}
    resolved, unresolved = [], []

    for etf in etf_tickers:
        etf = etf.upper()
        etf_weight = direct.get(etf, 0.0)
        if not etf_weight:
            continue
        holdings = get_top_holdings(etf, use_network=use_network)
        if not holdings:
            unresolved.append(etf)
            continue
        resolved.append(etf)
        for h in holdings:
            sym = h["symbol"]
            contribution = etf_weight * (h["weight_pct"] / 100.0)
            if contribution <= 0:
                continue
            indirect[sym] = indirect.get(sym, 0.0) + contribution
            via.setdefault(sym, []).append("%s %.2f%%" % (etf, contribution))

    rows = []
    for sym in set(list(direct) + list(indirect)):
        if sym in etf_tickers:
            continue  # don't double-count the funds themselves
        d = direct.get(sym, 0.0)
        i = indirect.get(sym, 0.0)
        if i <= 0:
            continue  # only interesting where a fund adds hidden exposure
        rows.append(
            {
                "symbol": sym,
                "direct_pct": round(d, 2),
                "indirect_pct": round(i, 2),
                "total_pct": round(d + i, 2),
                "via": ", ".join(via.get(sym, [])),
            }
        )

    rows.sort(key=lambda r: -r["total_pct"])
    return rows, sorted(resolved), sorted(unresolved)
