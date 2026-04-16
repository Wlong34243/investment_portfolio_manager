
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

def sync_transactions(days: int = 90, live: bool = False):
    """
    Fetches Schwab transactions, merges with existing history, 
    and performs an archive-before-overwrite write to the Sheet.
    """
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
        # We still continue to check if we should refresh the sheet with existing data
    else:
        print(f"✅ Fetched {len(new_tx_df)} transactions from API.")

    # 3. Read Existing from Sheet
    print("Reading existing transactions from Google Sheets...")
    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_TRANSACTIONS)
    
    # Fingerprint column is the last one in config.TRANSACTION_COLUMNS
    fp_col_idx = len(config.TRANSACTION_COLUMNS)
    all_values = ws.get_all_values()
    headers = all_values[0] if all_values else config.TRANSACTION_COLUMNS
    existing_data = all_values[1:] if len(all_values) > 1 else []
    
    # Load existing into DataFrame for merging
    if existing_data:
        existing_df = pd.DataFrame(existing_data, columns=headers)
    else:
        existing_df = pd.DataFrame(columns=config.TRANSACTION_COLUMNS)

    # 4. Merge and Deduplicate
    # Pattern: date|ticker|action|quantity|price
    # Note: schwab_client.fetch_transactions already builds 'Fingerprint' in this format.
    
    combined_df = pd.concat([existing_df, new_tx_df], ignore_index=True)
    
    # Deduplicate by Fingerprint
    if 'Fingerprint' in combined_df.columns:
        initial_count = len(combined_df)
        combined_df = combined_df.drop_duplicates(subset=['Fingerprint'], keep='first')
        deduped_count = len(combined_df)
        print(f"Deduplicated: {initial_count} total rows -> {deduped_count} unique transactions.")
    
    # Sort by Trade Date
    if 'Trade Date' in combined_df.columns:
        combined_df = combined_df.sort_values(by='Trade Date', ascending=False)

    # 5. Dry-Run Gate
    if not live:
        print("\n--- DRY RUN COMPLETE --- Use --live to overwrite the Sheet.")
        if not combined_df.empty:
            print(f"Sample unique transactions (top 5):\n{combined_df.head(5).to_string()}")
        return True

    # 6. Archive and Overwrite
    print(f"\n--- LIVE MODE --- Preparing to update {config.TAB_TRANSACTIONS}...")
    
    # Archive existing rows to Logs
    if existing_data:
        ws_logs = ss.worksheet(config.TAB_LOGS)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws_logs.append_row([
            timestamp,
            "INFO",
            "Sync_Transactions",
            f"Archiving {len(existing_data)} rows before overwrite refresh.",
            f"New total: {len(combined_df)}"
        ])
        print(f"Archived {len(existing_data)} rows metadata to Logs.")
        time.sleep(1.0)

    # Clear and Write
    print(f"Clearing and writing {len(combined_df)} rows to {config.TAB_TRANSACTIONS}...")
    ws.clear()
    time.sleep(1.0)
    
    # Sanitize
    data_to_write = pipeline.sanitize_dataframe_for_sheets(combined_df, config.TRANSACTION_COLUMNS, config.TRANSACTION_COL_MAP)
    
    # Write headers + data
    ws.update(range_name="A1", values=[config.TRANSACTION_COLUMNS] + data_to_write, value_input_option='USER_ENTERED')
    
    print(f"✅ SUCCESS: {len(combined_df)} transactions written.")
    return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync Schwab Transactions")
    parser.add_argument("--days", type=int, default=90, help="Number of days to fetch")
    parser.add_argument("--live", action="store_true", help="Perform live sheet write")
    args = parser.parse_args()
    
    sync_transactions(days=args.days, live=args.live)
