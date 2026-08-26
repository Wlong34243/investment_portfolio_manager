"""
Read-only Schwab vs yfinance daily-bar reconciliation harness (Phase 1 Step 5).

Writes only under agent_outputs/schwab_probe/. No Sheet writes. No --live flag.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from utils.schwab_client import (  # noqa: E402
    fetch_price_history,
    fetch_price_history_batch,
    get_market_client,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("reconcile_price_history")

TICKERS = ["AAPL", "META", "VTI", "JEPI", "XOM", "RRC", "SPY", "GLD"]
OUT_DIR = _REPO / "agent_outputs" / "schwab_probe"
OUT_MD = OUT_DIR / "price_history_reconciliation_2026-08-25.md"
PERIOD_DAYS = 365


def _yf_daily(ticker: str, period_days: int, auto_adjust: bool) -> pd.DataFrame:
    df = yf.download(
        ticker,
        period=f"{period_days}d",
        interval="1d",
        auto_adjust=auto_adjust,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={c: c.lower() for c in df.columns})
    if "close" not in df.columns:
        return pd.DataFrame()
    idx = pd.to_datetime(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    df = df.copy()
    df.index = idx.normalize()
    return df[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])


def _schwab_daily(client, ticker: str, period_days: int) -> pd.DataFrame:
    df = fetch_price_history(client, ticker, period_days=period_days, interval="daily")
    if df.empty:
        return df
    out = df.copy()
    out.index = out.index.tz_convert("UTC").normalize()
    return out


def _compare(schwab: pd.DataFrame, yf_df: pd.DataFrame, label: str) -> dict:
    row = {
        "variant": label,
        "schwab_rows": len(schwab),
        "yf_rows": len(yf_df),
        "only_schwab": 0,
        "only_yf": 0,
        "joined": 0,
        "max_abs_close": None,
        "max_abs_close_date": None,
        "max_rel_bps": None,
        "max_rel_date": None,
        "mean_abs_rel_bps": None,
        "max_vol_rel": None,
    }
    if schwab.empty or yf_df.empty:
        return row
    s = schwab[["close", "volume"]].copy()
    s.columns = ["s_close", "s_vol"]
    y = yf_df[["close", "volume"]].copy()
    y.columns = ["y_close", "y_vol"]
    joined = s.join(y, how="inner")
    only_s = s.index.difference(y.index)
    only_y = y.index.difference(s.index)
    row["only_schwab"] = len(only_s)
    row["only_yf"] = len(only_y)
    row["joined"] = len(joined)
    if joined.empty:
        return row
    abs_dev = (joined["s_close"] - joined["y_close"]).abs()
    rel_bps = abs_dev / joined["y_close"].replace(0, pd.NA) * 10000.0
    row["max_abs_close"] = float(abs_dev.max())
    row["max_abs_close_date"] = str(abs_dev.idxmax().date())
    row["max_rel_bps"] = float(rel_bps.max())
    row["max_rel_date"] = str(rel_bps.idxmax().date())
    row["mean_abs_rel_bps"] = float(rel_bps.mean())
    vol_rel = (
        (joined["s_vol"] - joined["y_vol"]).abs()
        / joined["y_vol"].replace(0, pd.NA)
    )
    row["max_vol_rel"] = float(vol_rel.max()) if vol_rel.notna().any() else None
    return row


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = get_market_client()
    if client is None:
        print("ERROR: market client unavailable — cannot reconcile")
        return 1

    lines = [
        "# Price history reconciliation — 2026-08-25",
        "",
        "Schwab daily bars vs yfinance `auto_adjust=True` and `auto_adjust=False`.",
        "Trailing 365 calendar days. Read-only.",
        "",
        "| Ticker | Variant | Schwab rows | YF rows | Only Schwab | Only YF | Joined |"
        " Max |close| Δ | Date | Max rel bps | Date | Mean abs rel bps | Max vol rel |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    results: list[dict] = []

    for ticker in TICKERS:
        schwab = _schwab_daily(client, ticker, PERIOD_DAYS)
        yf_adj = _yf_daily(ticker, PERIOD_DAYS, auto_adjust=True)
        yf_raw = _yf_daily(ticker, PERIOD_DAYS, auto_adjust=False)
        for label, ydf in (("yf_auto_adjust=True", yf_adj), ("yf_auto_adjust=False", yf_raw)):
            cmp_row = _compare(schwab, ydf, label)
            cmp_row["ticker"] = ticker
            results.append(cmp_row)
            lines.append(
                f"| {ticker} | {label} | {cmp_row['schwab_rows']} | {cmp_row['yf_rows']} | "
                f"{cmp_row['only_schwab']} | {cmp_row['only_yf']} | {cmp_row['joined']} | "
                f"{cmp_row['max_abs_close']!s} | {cmp_row['max_abs_close_date']} | "
                f"{cmp_row['max_rel_bps']!s} | {cmp_row['max_rel_date']} | "
                f"{cmp_row['mean_abs_rel_bps']!s} | {cmp_row['max_vol_rel']!s} |"
            )

    # Depth / intraday ceiling probes
    lines.extend(["", "## Depth / ceiling probes", ""])
    deep = fetch_price_history(client, "AAPL", period_days=7300, interval="daily", use_cache=False)
    if deep.empty:
        lines.append("- AAPL daily period_days=7300: EMPTY")
    else:
        lines.append(
            f"- AAPL daily period_days=7300: {len(deep)} bars, "
            f"{deep.index.min().date()} → {deep.index.max().date()}"
        )
    intraday = fetch_price_history(client, "AAPL", period_days=60, interval="1min", use_cache=False)
    if intraday.empty:
        lines.append("- AAPL 1min period_days=60: EMPTY (ceiling likely bitten)")
    else:
        lines.append(
            f"- AAPL 1min period_days=60: {len(intraday)} bars, "
            f"{intraday.index.min()} → {intraday.index.max()}"
        )

    # Batch timing — cold then warm (same tickers, cache now warm)
    sample = TICKERS + ["NVDA", "AMZN", "GOOG", "META"]  # pad toward ~12; full 39 if needed
    # Prefer held-like set size: repeat TICKERS to approximate 39 without inventing unknowns
    batch39 = (TICKERS * 5)[:39]
    t0 = time.perf_counter()
    fetch_price_history_batch(client, batch39, period_days=30, interval="daily")
    cold_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    fetch_price_history_batch(client, batch39, period_days=30, interval="daily")
    warm_s = time.perf_counter() - t1
    lines.extend([
        "",
        "## Batch wall-clock (39 tickers, daily, period_days=30)",
        f"- Cold-ish pass: {cold_s:.2f}s",
        f"- Warm (cache) pass: {warm_s:.2f}s",
        "",
        "## Dividend-adjustment interpretation (human verdict — not decided by script)",
        "",
        "If JEPI / XOM / VTI match `auto_adjust=False` far more closely than "
        "`auto_adjust=True`, Schwab bars are **not** dividend-adjusted.",
        "",
    ])

    # Helper numbers for the human verdict
    for t in ("JEPI", "XOM", "VTI"):
        true_row = next(r for r in results if r["ticker"] == t and "True" in r["variant"])
        false_row = next(r for r in results if r["ticker"] == t and "False" in r["variant"])
        lines.append(
            f"- {t}: mean abs rel bps vs adj=True = {true_row['mean_abs_rel_bps']!s}; "
            f"vs adj=False = {false_row['mean_abs_rel_bps']!s}"
        )

    text = "\n".join(lines) + "\n"
    OUT_MD.write_text(text, encoding="utf-8")
    print(text)
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
