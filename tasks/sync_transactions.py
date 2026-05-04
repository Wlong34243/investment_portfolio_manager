"""
tasks/sync_transactions.py — Sync Schwab transaction history to Google Sheets.
Default: last 90 days.
Pattern: archive-before-overwrite (refreshes the full tab with merged history).
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from utils import schwab_client
from utils.sheet_readers import get_gspread_client
import pipeline

logger = logging.getLogger(__name__)


def _canonical_key(trade_date: str, ticker: str, action: str, net_amount) -> str:
    """Stable comparison key independent of fingerprint format."""
    return f"{trade_date}|{ticker}|{action}|{round(float(net_amount or 0), 2)}"


def _read_sheet_transactions(ws) -> pd.DataFrame:
    """Read all rows from the Transactions worksheet into a DataFrame."""
    all_values = ws.get_all_values()
    if not all_values or len(all_values) < 2:
        return pd.DataFrame(columns=config.TRANSACTION_COLUMNS)
    headers = all_values[0]
    data = all_values[1:]
    return pd.DataFrame(data, columns=headers)


def reconcile_transactions(days: int = 90) -> bool:
    """
    Fetch `days` days of transactions from Schwab and diff against what's in
    the Google Sheet.  Prints three tables:
      - Rows in Schwab but missing from the Sheet
      - Rows in Sheet but missing from Schwab
      - Rows present in both but with a changed Net Amount

    No writes are performed.  Returns True on success, False on API failure.
    """
    print(f"--- Transaction Reconcile ({days} days, read-only) ---")

    client = schwab_client.get_accounts_client()
    if not client:
        print("❌ Could not initialize Schwab client.")
        return False

    start_date = datetime.now() - timedelta(days=days)
    print(f"Fetching Schwab transactions since {start_date.strftime('%Y-%m-%d')}...")
    api_df = schwab_client.fetch_transactions(client, start_date=start_date)

    print("Reading existing transactions from Google Sheets...")
    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_TRANSACTIONS)
    sheet_df = _read_sheet_transactions(ws)

    # Build canonical-key → row maps for comparison
    def _to_keyed(df: pd.DataFrame) -> dict:
        result = {}
        for _, row in df.iterrows():
            key = _canonical_key(
                str(row.get('Trade Date', '')),
                str(row.get('Ticker', '')),
                str(row.get('Action', '')),
                row.get('Net Amount', 0),
            )
            result[key] = row
        return result

    api_keyed = _to_keyed(api_df)
    sheet_keyed = _to_keyed(sheet_df)

    api_keys = set(api_keyed)
    sheet_keys = set(sheet_keyed)

    only_in_api = sorted(api_keys - sheet_keys)
    only_in_sheet = sorted(sheet_keys - api_keys)
    # Value diffs: same key, compare Net Amount as a sanity check
    changed = []
    for key in api_keys & sheet_keys:
        api_net = round(float(api_keyed[key].get('Net Amount', 0) or 0), 2)
        sheet_net = round(float(sheet_keyed[key].get('Net Amount', 0) or 0), 2)
        if api_net != sheet_net:
            changed.append((key, api_net, sheet_net))

    # --- Print results ---
    print(f"\n{'='*60}")
    print(f"RECONCILE SUMMARY  ({days}-day window)")
    print(f"  Schwab API:   {len(api_df):>5} transactions")
    print(f"  Sheet:        {len(sheet_df):>5} transactions")
    print(f"  Only in API:  {len(only_in_api):>5} (missing from sheet)")
    print(f"  Only in sheet:{len(only_in_sheet):>5} (not in API window)")
    print(f"  Value diffs:  {len(changed):>5}")
    print(f"{'='*60}")

    if only_in_api:
        print(f"\n[MISSING FROM SHEET — {len(only_in_api)} rows]")
        print(f"{'Trade Date':<12} {'Ticker':<8} {'Action':<12} {'Net Amount':>12}")
        print("-" * 50)
        for key in only_in_api[:50]:  # cap display at 50
            row = api_keyed[key]
            print(f"{str(row.get('Trade Date','')):<12} "
                  f"{str(row.get('Ticker','')):<8} "
                  f"{str(row.get('Action','')):<12} "
                  f"{float(row.get('Net Amount', 0) or 0):>12.2f}")
        if len(only_in_api) > 50:
            print(f"  ... and {len(only_in_api) - 50} more")

    if only_in_sheet:
        print(f"\n[ONLY IN SHEET (outside {days}-day window or orphaned) — {len(only_in_sheet)} rows]")
        print(f"{'Trade Date':<12} {'Ticker':<8} {'Action':<12} {'Net Amount':>12}")
        print("-" * 50)
        for key in only_in_sheet[:20]:
            row = sheet_keyed[key]
            print(f"{str(row.get('Trade Date','')):<12} "
                  f"{str(row.get('Ticker','')):<8} "
                  f"{str(row.get('Action','')):<12} "
                  f"{float(row.get('Net Amount', 0) or 0):>12.2f}")
        if len(only_in_sheet) > 20:
            print(f"  ... and {len(only_in_sheet) - 20} more")

    if changed:
        print(f"\n[VALUE DIFFS — {len(changed)} rows]")
        print(f"{'Key':<50} {'API Net':>10} {'Sheet Net':>10}")
        print("-" * 74)
        for key, api_net, sheet_net in changed[:20]:
            print(f"{key:<50} {api_net:>10.2f} {sheet_net:>10.2f}")

    if not only_in_api and not changed:
        print("\n✅ CLEAN: Schwab API matches Sheet (within the reconcile window).")
    else:
        print(f"\n⚠️  Run 'sync transactions --live' to refresh the sheet.")

    return True


def sync_transactions(days: int = 90, live: bool = False, reconcile: bool = False):
    """
    Fetches Schwab transactions, merges with existing history,
    and performs an archive-before-overwrite write to the Sheet.

    With reconcile=True: read-only diff mode — no writes.
    """
    if reconcile:
        return reconcile_transactions(days=days)

    print(f"--- Transaction Sync ({days} days, live={live}) ---")

    # 1. Initialize Schwab Client
    client = schwab_client.get_accounts_client()
    if not client:
        print("❌ Could not initialize Schwab client.")
        return False

    # 2. Fetch from API
    start_date = datetime.now() - timedelta(days=days)
    print(f"Fetching Schwab transactions since {start_date.strftime('%Y-%m-%d')}...")
    new_tx_df = schwab_client.fetch_transactions(client, start_date=start_date)

    if new_tx_df.empty:
        print("ℹ️ No transactions found in API for the specified range.")
    else:
        print(f"✅ Fetched {len(new_tx_df)} transactions from API.")

    # 3. Read Existing from Sheet
    print("Reading existing transactions from Google Sheets...")
    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_TRANSACTIONS)
    sheet_df = _read_sheet_transactions(ws)
    existing_data = sheet_df.values.tolist() if not sheet_df.empty else []

    # 4. Merge and Deduplicate
    combined_df = pd.concat([sheet_df, new_tx_df], ignore_index=True)

    if 'Fingerprint' in combined_df.columns:
        initial_count = len(combined_df)
        # keep='last' so fresh API data overwrites stale sheet rows with the same key
        combined_df = combined_df.drop_duplicates(subset=['Fingerprint'], keep='last')
        deduped_count = len(combined_df)
        print(f"Deduplicated: {initial_count} total rows -> {deduped_count} unique transactions.")

    if 'Trade Date' in combined_df.columns:
        combined_df = combined_df.sort_values(by='Trade Date', ascending=False)

    # 5. Dry-Run Gate
    if not live:
        print("\n--- DRY RUN COMPLETE --- Use --live to append new transactions to the Sheet.")
        if not new_rows_df.empty:
            print(f"New transactions found (top 5):\n{new_rows_df.head(5).to_string()}")
        else:
            print("No new transactions found in the specified range.")
        return True

    # 6. Live Mode: Append Only
    print(f"\n--- LIVE MODE --- Preparing to append new transactions to {config.TAB_TRANSACTIONS}...")

    # Identify which rows are actually new
    existing_fps = set(sheet_df['Fingerprint'].astype(str).tolist()) if 'Fingerprint' in sheet_df.columns else set()
    new_rows_df = new_tx_df[~new_tx_df['Fingerprint'].astype(str).isin(existing_fps)].copy()
    
    if new_rows_df.empty:
        print("✅ No new unique transactions to append.")
        return True

    print(f"Found {len(new_rows_df)} new transactions to append.")

    data_to_append = pipeline.sanitize_dataframe_for_sheets(
        new_rows_df, config.TRANSACTION_COLUMNS, config.TRANSACTION_COL_MAP
    )

    ws.append_rows(
        values=data_to_append,
        value_input_option='USER_ENTERED',
    )

    # Optional: Log the append
    ws_logs = ss.worksheet(config.TAB_LOGS)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws_logs.append_row([
        timestamp,
        "INFO",
        "Sync_Transactions",
        f"Appended {len(data_to_append)} new transactions.",
        f"Total unique now approx: {len(sheet_df) + len(data_to_append)}",
    ])

    print(f"✅ SUCCESS: {len(data_to_append)} transactions appended.")
    return True


def clean_junk_tickers(live: bool = False) -> bool:
    """
    Remove rows from the Transactions sheet where Ticker is CURRENCY_USD, USD,
    or other known non-ticker placeholders written by older code versions.

    Reads all rows, filters junk, rewrites in a single batch (archive-before-overwrite).
    With live=False: prints a dry-run summary only.
    """
    JUNK_TICKERS = {"CURRENCY_USD", "USD", ""}

    print("--- Clean Junk Tickers (Transactions tab) ---")
    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_TRANSACTIONS)

    all_values = ws.get_all_values()
    if not all_values or len(all_values) < 2:
        print("Sheet is empty — nothing to clean.")
        return True

    headers = all_values[0]
    rows = all_values[1:]

    try:
        ticker_col = headers.index("Ticker")
    except ValueError:
        print("ERROR: 'Ticker' column not found in sheet headers.")
        return False

    clean_rows = [r for r in rows if r[ticker_col] not in JUNK_TICKERS]
    junk_rows  = [r for r in rows if r[ticker_col] in JUNK_TICKERS]

    print(f"  Total rows:   {len(rows)}")
    print(f"  Junk rows:    {len(junk_rows)}  (ticker in {JUNK_TICKERS})")
    print(f"  Clean rows:   {len(clean_rows)}")

    if not junk_rows:
        print("✅ No junk ticker rows found.")
        return True

    if not live:
        print("\n--- DRY RUN --- Pass --clean --live to apply.")
        print("Sample junk rows (first 10):")
        for r in junk_rows[:10]:
            print("  ", r[:5])
        return True

    # Archive existing sheet to a backup tab before overwriting
    import time as _time
    from datetime import datetime as _dt
    archive_tab = f"Transactions_Archive_{_dt.now().strftime('%Y%m%d_%H%M%S')}"
    ws_arc = ss.add_worksheet(title=archive_tab, rows=len(rows) + 10, cols=len(headers))
    _time.sleep(1)
    ws_arc.update(range_name="A1", values=[headers] + rows, value_input_option="USER_ENTERED")
    print(f"  Archived {len(rows)} rows → '{archive_tab}'")
    _time.sleep(1)

    ws.clear()
    _time.sleep(1)
    ws.update(range_name="A1", values=[headers] + clean_rows, value_input_option="USER_ENTERED")
    print(f"✅ Rewrote {len(clean_rows)} clean rows. Removed {len(junk_rows)} junk rows.")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync Schwab Transactions")
    parser.add_argument("--days", type=int, default=90, help="Number of days to fetch")
    parser.add_argument("--live", action="store_true", help="Perform live sheet write")
    parser.add_argument("--reconcile", action="store_true", help="Diff-only mode, no writes")
    parser.add_argument("--clean", action="store_true", help="Remove CURRENCY_USD junk rows from the sheet")
    args = parser.parse_args()

    if args.clean:
        clean_junk_tickers(live=args.live)
    else:
        sync_transactions(days=args.days, live=args.live, reconcile=args.reconcile)
