"""
scripts/re-enrich_all.py — Live fetch from Schwab and full Gemini enrichment.
Updates data/ticker_mapping.json for all tickers in the portfolio.
"""

import os
import sys
import pandas as pd
import json

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils import schwab_client
from utils.agents.portfolio_enricher import enrich_holdings_from_df

def run_full_enrichment():
    print("--- Portfolio Wide Enrichment Strategy ---")
    
    # 1. Fetch live tickers from Schwab API
    client = schwab_client.get_accounts_client()
    if not client:
        print("❌ Schwab client not available.")
        return

    print("Fetching live holdings from Schwab...")
    df = schwab_client.fetch_positions(client)
    if df.empty:
        print("❌ No positions found.")
        return
    
    print(f"✅ Found {len(df)} tickers. Sending to Gemini for categorization...")
    
    # 2. Call Gemini agent to categorize
    # Note: enrich_holdings_from_df expects 'ticker' and 'description' columns
    # fetch_positions already returns these in snake_case.
    ok, msg = enrich_holdings_from_df(df)
    
    if ok:
        print(f"✅ SUCCESS: {msg}")
        
        # 3. Print a sample of the new mapping
        with open("data/ticker_mapping.json", "r") as f:
            mapping = json.load(f)
        
        print("\nSample Mappings (First 5):")
        for i, (ticker, data) in enumerate(mapping.items()):
            if i >= 5: break
            print(f"  - {ticker}: {data['asset_class']} | {data['sector_strategy']}")
    else:
        print(f"❌ FAILED: {msg}")

if __name__ == "__main__":
    run_full_enrichment()
