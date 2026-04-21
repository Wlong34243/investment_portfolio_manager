
import os
import sys
from datetime import datetime, timedelta
import pandas as pd

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils import schwab_client, schwab_token_store
from utils.enrichment import enrich_positions, apply_smart_categorization
import pipeline

def update_portfolio(tx_days: int = 90):
    """
    Pull current positions and recent transactions from Schwab API → write to Sheets.

    Args:
        tx_days: How many calendar days of transaction history to fetch.
                 Default 90. Pass 365 for a historical backfill.
    """
    print(f"--- Portfolio Live Update (DRY_RUN={config.DRY_RUN}, tx_days={tx_days}) ---")

    # 1. Initialize Client
    client = schwab_client.get_accounts_client()
    if not client:
        print("❌ Could not initialize Schwab Accounts client. Check your tokens in GCS.")
        print("   → Run: python scripts/schwab_manual_reauth.py")
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

        # Fix 100x percentage bug (Google Sheets formatting)
        for col in ['Dividend Yield', 'Daily Change %', 'Unrealized G/L %', 'dividend_yield', 'daily_change_pct', 'unrealized_gl_pct']:
            if col in raw_positions.columns:
                raw_positions[col] = pd.to_numeric(raw_positions[col], errors='coerce').fillna(0)
                if raw_positions[col].abs().max() > 1.0:
                    raw_positions[col] = raw_positions[col] / 100.0

        print("Normalizing positions for sheet schema...")
        today_iso = datetime.now().strftime("%Y-%m-%d")
        positions_df = pipeline.normalize_positions(raw_positions, import_date=today_iso, source="schwab_api")

        print("Writing to Google Sheets...")
        h_results = pipeline.write_to_sheets(positions_df, cash_amount=0.0, dry_run=config.DRY_RUN)

        print(f"  - Holdings Written: {h_results['holdings_written']}")
        print(f"  - History Appended: {h_results['history_appended']}")
        print(f"  - Daily Snapshot:   {h_results['snapshot']}")

    # 3. Fetch & Update Transactions
    print(f"\n[2/2] Updating Transactions (last {tx_days} days)...")
    start_date = datetime.now() - timedelta(days=tx_days)
    print(f"Fetching transactions since {start_date.strftime('%Y-%m-%d')}...")

    tx_df = schwab_client.fetch_transactions(client, start_date=start_date)

    if tx_df.empty:
        print(f"ℹ️ No transactions returned from API for the last {tx_days} days.")
        print("   → Check token status: python scripts/schwab_test_fetch_write.py")
        print("   → If token expired: python scripts/schwab_manual_reauth.py")
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
    import argparse
    parser = argparse.ArgumentParser(description="Live portfolio update from Schwab API")
    parser.add_argument("--days", type=int, default=90,
                        help="Days of transaction history to fetch (default 90, use 365 for backfill)")
    args = parser.parse_args()
    update_portfolio(tx_days=args.days)
