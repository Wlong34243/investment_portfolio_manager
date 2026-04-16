"""
Enriches a context bundle with fundamental data.
Priority: Schwab (if available) -> yfinance -> FMP (cached).
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

import config
from utils.fmp_client import get_fundamentals
from core.bundle import _sha256_canonical, _hashable_payload

logger = logging.getLogger(__name__)

def enrich_bundle_fundamentals(bundle_path: Path) -> dict:
    """
    Reads a bundle, enriches each position with fundamentals,
    re-hashes, and saves back to disk.
    """
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")

    with open(bundle_path, "r") as f:
        data = json.load(f)

    positions = data.get("positions", [])
    enriched_count = 0
    empty_tickers = []

    # Filter out cash
    SKIP_TICKERS = config.CASH_TICKERS | {"QACDS"}

    print(f"Enriching fundamentals for {len(positions)} positions in {bundle_path.name}...")

    for i, pos in enumerate(positions):
        ticker = pos.get("ticker")
        if not ticker or ticker in SKIP_TICKERS:
            continue

        # Tier 0 source: bundle_quote (only present in Schwab API bundles)
        bundle_quote = pos.get("bundle_quote")
        asset_class = pos.get("asset_class", "")

        try:
            funds = get_fundamentals(ticker, bundle_quote=bundle_quote, asset_class=asset_class)
            pos["fundamentals"] = funds
            
            if not funds:
                empty_tickers.append(ticker)
            else:
                enriched_count += 1
        except Exception as e:
            logger.warning("Failed to enrich fundamentals for %s: %s", ticker, e)
            pos["fundamentals"] = {}
            empty_tickers.append(ticker)

        # Rate limit guard for yfinance scraping
        time.sleep(0.5)

    if empty_tickers:
        print(f"⚠ Fundamentals returned empty for {len(empty_tickers)} tickers: {empty_tickers}")

    # Re-hash the bundle
    # We must remove the old bundle_hash before re-hashing
    data["bundle_hash"] = _sha256_canonical(_hashable_payload(data))
    
    # Save back to disk
    with open(bundle_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Successfully enriched {enriched_count} positions. Bundle re-hashed and saved.")
    return data

if __name__ == "__main__":
    # For manual testing
    import sys
    if len(sys.argv) > 1:
        enrich_bundle_fundamentals(Path(sys.argv[1]))
