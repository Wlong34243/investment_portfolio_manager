"""
scripts/schwab_test_fetch_write.py — Test Schwab API fetch and Google Sheet write.
Disabling DRY_RUN (if not already) and confirming data flow.
Now includes full enrichment and smart categorization.
"""

import os
import sys
from datetime import date

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils import schwab_client, schwab_token_store
from utils.enrichment import enrich_positions, apply_smart_categorization
import pipeline

def test_fetch_and_write():
    print("--- Schwab API Live Fetch & Sheet Write Test ---")
    
    # 1. Initialize Client
    client = schwab_client.get_accounts_client()
    if not client:
        print("❌ Could not initialize Schwab Accounts client. Check your tokens in GCS.")
        return False
    
    # 2. Fetch Live Positions
    print("Fetching positions from Schwab API...")
    raw_positions = schwab_client.fetch_positions(client)
    if raw_positions.empty:
        print("❌ Schwab API returned no positions. Check your SCHWAB_ACCOUNT_HASH.")
        return False
    
    print(f"✅ Fetched {len(raw_positions)} positions.")
    
    # 3. Enrich & Categorize
    print("Enriching positions (metadata & smart mapping)...")
    # Note: fetch_positions returns snake_case internally
    raw_positions = enrich_positions(raw_positions)
    raw_positions = apply_smart_categorization(raw_positions)
    
    # 4. Normalize (snake_case internally)
    print("Normalizing positions for sheet schema...")
    today_iso = date.today().isoformat()
    positions_df = pipeline.normalize_positions(raw_positions, import_date=today_iso, source="schwab_api")
    
    # 5. Write to Sheets (DRY_RUN is False now in config.py)
    print(f"Writing to Google Sheets (DRY_RUN={config.DRY_RUN})...")
    results = pipeline.write_to_sheets(positions_df, cash_amount=0.0, dry_run=config.DRY_RUN)
    
    print("\n--- Summary ---")
    print(f"Holdings Written (Current): {results['holdings_written']}")
    print(f"History Appended: {results['history_appended']}")
    print(f"Daily Snapshot Added: {results['snapshot']}")
    print(f"Income Tracking Snapshot Added: {results['income_snapshot']}")
    
    if results['holdings_written'] > 0:
        print("\n✅ SUCCESS: Schwab API data with full enrichment has been sent to your Google Sheet.")
        return True
    else:
        print("\n❌ FAILED: No data was written to the sheet.")
        return False

if __name__ == "__main__":
    test_fetch_and_write()
