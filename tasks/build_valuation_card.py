"""
tasks/build_valuation_card.py — Builds the Valuation_Card tab.

Data flow (Phase 1.2+):
  1. Load the latest market bundle.
  2. For each position, read `fmp_fundamentals` (baked at snapshot time).
  3. Supplement with yfinance for price/52-week data that isn't in the bundle.
  4. No live FMP calls.  If `fmp_fundamentals` is missing or contains "error",
     the row is marked MONITOR and greyed out per Valuation_Card rules.
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf
import typer

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)
app = typer.Typer()

EXCLUDE_TICKERS = set(config.VALUATION_SKIP)


# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------

def _load_latest_composite_bundle():
    """Return latest CompositeBundle object, or None if not found."""
    from core.composite_bundle import resolve_latest_bundles, load_composite_bundle, CompositeBundle
    from dataclasses import fields
    try:
        market_path, vault_path = resolve_latest_bundles()
        # We need a way to get the CompositeBundle object. 
        # build_composite_bundle returns the object. 
        # load_composite_bundle returns a dict.
        from core.composite_bundle import build_composite_bundle
        return build_composite_bundle(market_path, vault_path)
    except Exception as e:
        logger.warning("Could not load composite bundle: %s", e)
        return None


def _load_latest_bundle() -> dict | None:
    """Return latest market bundle dict, or None if not found."""
    candidates = sorted(
        Path("bundles").glob("context_bundle_*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    try:
        with open(candidates[-1], "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        logger.warning("Could not load bundle %s: %s", candidates[-1], e)
        return None


def _build_fmp_map(bundle: dict) -> dict:
    """
    Returns ticker → fmp_fundamentals dict from bundle positions.
    Tickers without fmp_fundamentals get an empty dict.
    """
    result = {}
    for pos in bundle.get("positions", []):
        ticker = pos.get("ticker") or pos.get("Ticker") or ""
        if ticker:
            result[ticker] = pos.get("fmp_fundamentals") or {}
    return result


def _build_fundamentals_map(bundle: dict) -> dict:
    """Returns ticker → fundamentals dict (yfinance-sourced, already in bundle)."""
    result = {}
    for pos in bundle.get("positions", []):
        ticker = pos.get("ticker") or pos.get("Ticker") or ""
        if ticker:
            result[ticker] = pos.get("fundamentals") or {}
    return result


# ---------------------------------------------------------------------------
# Per-ticker valuation fetch
# ---------------------------------------------------------------------------

def fetch_ticker_valuation(
    ticker_symbol: str,
    fmp_data: dict | None = None,
    fundamentals: dict | None = None,
    composite_bundle = None,
):
    """
    Build a valuation row for one ticker.

    fmp_data       — from bundle's fmp_fundamentals (may be empty dict or error dict)
    fundamentals   — from bundle's fundamentals (yfinance-sourced, already baked in)
    composite_bundle — CompositeBundle object for trigger lookups

    No live FMP calls are made here.  yfinance is used only for price and
    52-week data that may not be in the bundle.
    """
    fmp_data = fmp_data or {}
    fundamentals = fundamentals or {}

    # MONITOR if fmp_fundamentals missing or error
    fmp_missing = not fmp_data or "error" in fmp_data

    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info

        high = info.get("fiftyTwoWeekHigh")
        low  = info.get("fiftyTwoWeekLow")
        price = info.get("currentPrice") or info.get("regularMarketPrice")

        # Get triggers from composite bundle
        triggers = {"price_trim_above": None, "price_add_below": None}
        if composite_bundle:
            triggers = composite_bundle.get_ticker_triggers(ticker_symbol)

        pos_52w = None
        if high and low and price and (high - low) != 0:
            pos_52w = (price - low) / (high - low)

        disc_52w_high = None
        if high and price:
            disc_52w_high = (high - price) / high

        # --- Valuation fields: FMP from bundle where available; yfinance otherwise ---
        trailing_pe = (
            fmp_data.get("pe_ratio")
            or fundamentals.get("trailing_pe")
            or info.get("trailingPE")
        )
        forward_pe = (
            fmp_data.get("forward_pe")
            or fundamentals.get("forward_pe")
            or info.get("forwardPE")
        )
        peg = (
            fmp_data.get("peg_ratio")
            or fundamentals.get("peg_ratio")
            or info.get("pegRatio")
        )
        if peg is None or str(peg).lower() in ("nan", "none", ""):
            peg = "N/A"

        gross_margin  = fmp_data.get("gross_margin")  or info.get("grossMargins")
        roic          = fmp_data.get("roic")           or fundamentals.get("roic")
        rev_growth    = fmp_data.get("revenue_growth_yoy") or fundamentals.get("revenue_growth")
        debt_to_equity = fmp_data.get("debt_to_equity")   or fundamentals.get("debt_to_equity")

        # Valuation_Signal determination (CHEAP / FAIR / RICH / MONITOR)
        # A ticker is marked MONITOR if we have NO P/E data from any source
        pe_val = trailing_pe if trailing_pe and trailing_pe != "N/A" else None
        try:
            pe_float = float(pe_val) if pe_val is not None else None
        except (TypeError, ValueError):
            pe_float = None

        if pe_float is None:
            valuation_signal = "MONITOR"
        elif pe_float < 15:
            valuation_signal = "CHEAP"
        elif pe_float > 30:
            valuation_signal = "RICH"
        else:
            valuation_signal = "FAIR"

        # Ensure Div Yield is raw decimal
        raw_div_yield = fmp_data.get("dividend_yield") or info.get("dividendYield")
        if raw_div_yield is not None:
             try:
                 raw_div_yield = float(raw_div_yield)
                 # If value is > 0.5, it's likely a percentage (e.g. 2.5 for 2.5%), so divide by 100
                 if raw_div_yield > 0.5:
                      raw_div_yield = raw_div_yield / 100.0
             except (TypeError, ValueError):
                 raw_div_yield = None

        return {
            "Ticker":               ticker_symbol,
            "Name":                 info.get("shortName", ""),
            "Sector":               info.get("sector", ""),
            "Market Cap":           fmp_data.get("market_cap") or info.get("marketCap"),
            "Price":                price,
            "Trim Target":          triggers.get("price_trim_above"),
            "Add Target":           triggers.get("price_add_below"),
            "Trailing P/E":         trailing_pe,
            "Forward P/E (FMP)":    fmp_data.get("forward_pe"),
            "Forward P/E (yf)":     info.get("forwardPE"),
            "P/B":                  info.get("priceToBook"),
            "PEG":                  peg,
            "Gross Margin":         gross_margin,
            "ROIC":                 roic,
            "D/E":                  debt_to_equity,
            "Rev Growth YoY":       rev_growth,
            "Div Yield %":          raw_div_yield,
            "Payout Ratio":         fmp_data.get("payout_ratio")   or info.get("payoutRatio"),
            "52w Low":              low,
            "52w High":             high,
            "52w Position %":       pos_52w,
            "Discount from 52w High %": disc_52w_high,
            "Valuation_Signal":     valuation_signal,
            "FMP_Data_Available":   not fmp_missing,
            "Last Updated":         time.strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        logger.warning("fetch_ticker_valuation: failed for %s: %s", ticker_symbol, e)
        return None


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

@app.command()
def main(
    live: bool = typer.Option(False, "--live", help="Write to Google Sheets"),
    include_all: bool = typer.Option(True, "--all", help="Include all tickers, ignoring VALUATION_SKIP"),
):
    print(f"Building Valuation Card (Live={live}, All={include_all})...")

    # --- Load bundles for FMP + fundamentals + triggers data ---
    composite_bundle = _load_latest_composite_bundle()
    
    # Still load market bundle dict for fmp_map/fund_map logic as written
    bundle = _load_latest_bundle()
    if bundle is None:
        print("Warning: No market bundle found — FMP data will be unavailable. "
              "Run 'python manager.py snapshot' first.")
    fmp_map = _build_fmp_map(bundle) if bundle else {}
    fund_map = _build_fundamentals_map(bundle) if bundle else {}

    # --- Get tickers from sheet ---
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws_holdings = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)

    all_values = ws_holdings.get_all_values()
    if len(all_values) < 2:
        print("Error: Holdings_Current is empty.")
        return

    header_row_idx = -1
    for i, row in enumerate(all_values[:5]):
        if "Ticker" in row or "ticker" in [str(h).strip().lower() for h in row]:
            header_row_idx = i
            break

    if header_row_idx == -1:
        print("Error: Could not find 'Ticker' column in Holdings_Current.")
        return

    headers = all_values[header_row_idx]
    data = all_values[header_row_idx + 1:]
    df_holdings = pd.DataFrame(data, columns=headers)

    from utils.column_guard import ensure_display_columns
    df_holdings = ensure_display_columns(df_holdings)

    tickers = df_holdings["Ticker"].unique()
    if not include_all:
        tickers = [t for t in tickers if t and t not in EXCLUDE_TICKERS]
    else:
        tickers = [t for t in tickers if t]

    print(f"Fetching valuation data for {len(tickers)} tickers "
          f"({len([t for t in tickers if fmp_map.get(t)])} have FMP data in bundle)...")

    results = []
    for t in tickers:
        print(f"  Processing {t}...", end="\r")
        val = fetch_ticker_valuation(
            t,
            fmp_data=fmp_map.get(t),
            fundamentals=fund_map.get(t),
            composite_bundle=composite_bundle,
        )
        if val:
            results.append(val)
        time.sleep(0.1)

    if not results:
        print("No valuation data found.")
        return

    df_val = pd.DataFrame(results)
    # Sort by market cap descending, MONITOR rows last
    monitor_mask = df_val["Valuation_Signal"] == "MONITOR"
    df_val = pd.concat([
        df_val[~monitor_mask].sort_values(by="Market Cap", ascending=False, na_position="last"),
        df_val[monitor_mask],
    ], ignore_index=True)
    df_val = df_val.fillna("")

    if not live:
        print("\nDRY RUN: Valuation Data Preview")
        print(df_val[["Ticker", "Trailing P/E", "Forward P/E (FMP)", "PEG",
                       "Valuation_Signal", "FMP_Data_Available"]].to_string(index=False))
        return

    tab_name = "Valuation_Card"
    try:
        ws_val = spreadsheet.worksheet(tab_name)
        ws_val.clear()
    except Exception:
        ws_val = spreadsheet.add_worksheet(title=tab_name, rows=100, cols=30)

    data_to_write = [df_val.columns.tolist()] + df_val.values.tolist()
    ws_val.update(range_name="A1", values=data_to_write)
    print(f"\n✅ Successfully wrote {len(df_val)} rows to {tab_name}")


if __name__ == "__main__":
    app()
