
import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils import schwab_client, schwab_token_store
from utils.enrichment import enrich_positions, apply_smart_categorization
import pipeline

def update_portfolio():
    print(f"--- Portfolio Live Update (DRY_RUN={config.DRY_RUN}) ---")
    
    # 1. Initialize Client
    client = schwab_client.get_accounts_client()
    if not client:
        print("❌ Could not initialize Schwab Accounts client. Check your tokens in GCS.")
        return False
    
    # 2. Fetch & Update Positions
    print("\n[1/2] Updating Holdings...")
    print("Fetching positions from Schwab API...")
    raw_positions = schwab_client.fetch_positions(client)
    if raw_positions.empty:
        print("❌ Schwab API returned no positions.")
    else:
        print(f"✅ Fetched {len(raw_positions)} positions.")
        
        print("Enriching positions (metadata & smart mapping)...")
        raw_positions = enrich_positions(raw_positions)
        raw_positions = apply_smart_categorization(raw_positions)
        
        print("Normalizing positions for sheet schema...")
        today_iso = datetime.now().strftime("%Y-%m-%d")
        positions_df = pipeline.normalize_positions(raw_positions, import_date=today_iso, source="schwab_api")
        
        print("Writing to Google Sheets...")
        h_results = pipeline.write_to_sheets(positions_df, cash_amount=0.0, dry_run=config.DRY_RUN)
        
        print(f"  - Holdings Written: {h_results['holdings_written']}")
        print(f"  - History Appended: {h_results['history_appended']}")
        print(f"  - Daily Snapshot:   {h_results['snapshot']}")

    # 3. Fetch & Update Transactions
    print("\n[2/2] Updating Transactions...")
    # Default to last 30 days
    start_date = datetime.now() - timedelta(days=30)
    print(f"Fetching transactions since {start_date.strftime('%Y-%m-%d')}...")
    
    # Use fetch_transactions from schwab_client
    tx_df = schwab_client.fetch_transactions(client, start_date=start_date)
    
    if tx_df.empty:
        print("ℹ️ No new transactions found in the last 30 days.")
    else:
        print(f"✅ Fetched {len(tx_df)} transactions.")
        print("Deduplicating and appending to Transactions tab...")
        t_results = pipeline.ingest_schwab_transactions(tx_df, dry_run=config.DRY_RUN)
        
        print(f"  - Total Fetched: {t_results['parsed']}")
        print(f"  - New Appended:  {t_results['new']}")
        print(f"  - Duplicates:    {t_results['skipped']}")

    print("\n--- Update Complete ---")
    return True

if __name__ == "__main__":
    update_portfolio()
