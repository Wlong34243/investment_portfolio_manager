"""
tasks/create_dashboard.py — Idempotent 0_DASHBOARD tab builder.

Reads Holdings_Current and Daily_Snapshots via existing sheet readers,
computes all metrics in Python (guardrail #1 — no LLM math, no Sheets formulas),
and writes hard values to the "0_DASHBOARD" tab at sheet index 0.

Idempotent: safe to re-run at any frequency.  Each run clears the tab and
rewrites from scratch — no row accumulation, no stale data.

Respects config.DRY_RUN (guardrail #3) — pass --live to write to Sheets.

Usage:
    python tasks/create_dashboard.py           # dry-run (default)
    python tasks/create_dashboard.py --live    # write to Sheet
"""

import sys
import os
import time
import argparse
from datetime import datetime

# Add project root to sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd
import config
from utils.sheet_readers import get_gspread_client, get_holdings_current, get_daily_snapshots

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TAB_DASHBOARD = config.TAB_DASHBOARD   # "0_DASHBOARD"

# Tickers that count as dry powder (cash + cash-equivalents)
# config.CASH_TICKERS already includes SGOV, CASH_MANUAL, QACDS, etc.
DRY_POWDER_TICKERS = config.CASH_TICKERS


# ---------------------------------------------------------------------------
# Metric computation — all Python math, no Sheets formulas
# ---------------------------------------------------------------------------

def compute_metrics(holdings_df: pd.DataFrame, snapshots_df: pd.DataFrame) -> dict:
    """
    Compute dashboard KPIs entirely in Python.

    Guardrail #1 enforced:
      - Nuclear type casting via pd.to_numeric on every numeric column before use.
      - All division guarded against zero-total edge cases.
      - No values are passed to an LLM or Sheets formula engine.

    Returns a flat dict of scalar metrics plus a pd.Series for top-3 sectors.
    """
    if holdings_df.empty:
        return {}

    # --- Nuclear type enforcement (guardrail #2) ---
    for col in ['Market Value', 'Weight', 'Est Annual Income', 'Dividend Yield']:
        if col in holdings_df.columns:
            holdings_df[col] = pd.to_numeric(
                holdings_df[col].astype(str)
                    .str.replace('$', '', regex=False)
                    .str.replace(',', '', regex=False)
                    .str.replace('%', '', regex=False)
                    .str.strip(),
                errors='coerce',
            ).fillna(0.0)

    # --- 1. Total Portfolio Value ---
    total_value = float(holdings_df['Market Value'].sum())

    # --- 2. Dry Powder (Cash + SGOV, per config.CASH_TICKERS) ---
    dp_mask     = holdings_df['Ticker'].isin(DRY_POWDER_TICKERS)
    dry_powder  = float(holdings_df.loc[dp_mask, 'Market Value'].sum())
    dp_pct      = (dry_powder / total_value) if total_value > 0 else 0.0

    # --- 3. Invested capital (excluding dry powder) ---
    invested_df    = holdings_df[~dp_mask].copy()
    invested_value = float(invested_df['Market Value'].sum())
    position_count = int(len(invested_df))

    # --- 4. Top 3 Sector Weights (% of invested capital only) ---
    # Use Asset Class as sector proxy — excludes cash rows via invested_df filter.
    if invested_value > 0 and 'Asset Class' in invested_df.columns:
        sector_mv = (
            invested_df.groupby('Asset Class')['Market Value']
            .sum()
            .sort_values(ascending=False)
        )
        top3_sectors: pd.Series = (sector_mv / invested_value).round(4).head(3)
    else:
        top3_sectors = pd.Series(dtype=float)

    # --- 5. Latest Daily Snapshot date ---
    snapshot_date = ""
    if not snapshots_df.empty and 'Date' in snapshots_df.columns:
        non_empty = snapshots_df['Date'].replace('', pd.NA).dropna()
        if not non_empty.empty:
            snapshot_date = str(non_empty.iloc[-1])

    # --- 6. Blended yield (income / total_value) ---
    total_income   = float(holdings_df['Est Annual Income'].sum()) if 'Est Annual Income' in holdings_df.columns else 0.0
    blended_yield  = (total_income / total_value) if total_value > 0 else 0.0

    return {
        "total_value":     total_value,
        "invested_value":  invested_value,
        "dry_powder":      dry_powder,
        "dp_pct":          dp_pct,
        "position_count":  position_count,
        "blended_yield":   blended_yield,
        "top3_sectors":    top3_sectors,
        "snapshot_date":   snapshot_date,
        "last_updated":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Layout builder — returns list[list] of hard values (no formulas)
# ---------------------------------------------------------------------------

def build_rows(metrics: dict) -> list[list]:
    """
    Convert metrics dict into a 2-D list ready for ws.update().
    All values are native Python scalars — no numpy types, no Sheets formulas.
    """
    tv   = metrics["total_value"]
    inv  = metrics["invested_value"]
    dp   = metrics["dry_powder"]
    dppc = metrics["dp_pct"]
    pc   = metrics["position_count"]
    by   = metrics["blended_yield"]

    rows: list[list] = [
        # ── Title row ──────────────────────────────────────────────
        ["PORTFOLIO DASHBOARD", "", f"Updated: {metrics['last_updated']}"],
        ["", "", ""],

        # ── Summary block ──────────────────────────────────────────
        ["SUMMARY",               "Value",                    ""],
        ["Total Portfolio Value",  f"${tv:,.2f}",              ""],
        ["Total Invested",         f"${inv:,.2f}",             ""],
        ["Total Dry Powder",       f"${dp:,.2f}",              f"{dppc:.2%} of portfolio"],
        ["Position Count",         pc,                         ""],
        ["Blended Yield",          f"{by:.2%}",               "(est. annual income / total value)"],
        ["", "", ""],

        # ── Sector block ───────────────────────────────────────────
        ["TOP 3 SECTOR WEIGHTS",  "% of Invested Capital",    ""],
    ]

    if not metrics["top3_sectors"].empty:
        for sector, pct in metrics["top3_sectors"].items():
            rows.append([str(sector), f"{pct:.2%}", ""])
    else:
        rows.append(["No sector data available", "", ""])

    rows += [
        ["", "", ""],
        ["Source Snapshot Date", metrics["snapshot_date"], ""],
        ["Last Updated",         metrics["last_updated"],  ""],
    ]

    return rows


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def create_dashboard(live: bool = False) -> None:
    """
    Build or refresh 0_DASHBOARD.

    Idempotency contract:
      - Tab created if absent; existing tab reused if present.
      - Tab moved to index 0 if not already there.
      - Contents fully cleared before every write — no row accumulation.
      - Safe to run on a cron schedule.

    Dry-run gate (guardrail #3): pass live=True or --live flag to write.
    """
    dry_run = not live
    print(f"=== create_dashboard (dry_run={dry_run}) ===")

    # 1. Read source data via existing sheet readers
    print("Reading Holdings_Current...")
    holdings_df = get_holdings_current()
    if holdings_df.empty:
        print("⚠  Holdings_Current is empty — nothing to compute.")
        return

    print("Reading Daily_Snapshots...")
    snapshots_df = get_daily_snapshots()

    # 2. Compute all metrics in Python
    print("Computing metrics...")
    metrics = compute_metrics(holdings_df.copy(), snapshots_df.copy())
    if not metrics:
        print("⚠  Metric computation returned empty — aborting.")
        return

    print(f"  Total Value:   ${metrics['total_value']:,.2f}")
    print(f"  Invested:      ${metrics['invested_value']:,.2f}")
    print(f"  Dry Powder:    ${metrics['dry_powder']:,.2f}  ({metrics['dp_pct']:.2%})")
    print(f"  Blended Yield: {metrics['blended_yield']:.2%}")
    if not metrics['top3_sectors'].empty:
        for sector, pct in metrics['top3_sectors'].items():
            print(f"  {sector:<30} {pct:.2%}")


    # 3. Dry-run gate — print preview and exit
    if dry_run:
        print("\n--- DRY RUN: No Sheets writes executed. Pass --live to write. ---")
        return

    # 4. Connect to Sheets
    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)

    # 5. Ensure 0_DASHBOARD tab exists (idempotent — create only if absent)
    existing_tabs  = ss.worksheets()
    existing_titles = [ws.title for ws in existing_tabs]

    if TAB_DASHBOARD not in existing_titles:
        ws = ss.add_worksheet(title=TAB_DASHBOARD, rows=50, cols=10, index=0)
        print(f"Created tab: {TAB_DASHBOARD} at index 0")
    else:
        ws = ss.worksheet(TAB_DASHBOARD)
        # Move to index 0 if not already there (reorder is idempotent)
        if existing_tabs[0].title != TAB_DASHBOARD:
            ordered = [ws] + [w for w in existing_tabs if w.title != TAB_DASHBOARD]
            ss.reorder_worksheets(ordered)
            print(f"Moved {TAB_DASHBOARD} to index 0")
        else:
            print(f"Using existing tab: {TAB_DASHBOARD} (already at index 0)")

    time.sleep(0.5)   # brief pause after structural changes

    # 6. Clear ALL contents (idempotent — prevents stale data across runs)
    ws.clear()
    time.sleep(0.5)

    # 7. Write hard values — RAW mode ensures no Sheets formula interpretation
    rows = build_rows(metrics)
    ws.update(range_name="A1", values=rows, value_input_option="RAW")

    print(f"✅  {TAB_DASHBOARD} updated — {len(rows)} rows written as hard values.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build or refresh the 0_DASHBOARD tab in the Portfolio Sheet.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Write computed metrics to Sheets. Default: dry-run (print only).",
    )
    args = parser.parse_args()
    create_dashboard(live=args.live)
