"""
tasks/enrich_fmp.py — Bake FMP fundamentals into the market bundle at snapshot time.

Architecture
------------
Reads the market bundle JSON, fetches FMP fundamentals for each non-excluded
ticker (using a 14-day disk cache), writes a `fmp_fundamentals` dict into each
position, re-hashes, and saves the bundle back to disk.

Called automatically by `manager.py snapshot` (default-on).
Disable with `--no-enrich-fmp` for offline testing.

The `fmp_fundamentals` key contains:
    pe_ratio, forward_pe, peg_ratio, debt_to_equity, roic,
    revenue_growth_yoy, gross_margin, net_margin, dividend_yield,
    payout_ratio, market_cap, fetched_at

On per-ticker failure:
    {"error": "reason", "fetched_at": timestamp}  -- continues to next ticker

ETFs / fixed-income receive partial dicts with null fields (no error flag).
"""

import json
import logging
import sys
from pathlib import Path

# Project root on sys.path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from core.bundle import _sha256_canonical, _hashable_payload
from utils.fmp_client import get_fmp_fundamentals_bundle

logger = logging.getLogger(__name__)

SKIP_TICKERS = set(config.CASH_TICKERS)


def enrich_bundle_fmp(bundle_path: Path) -> dict:
    """
    Read market bundle at `bundle_path`, add `fmp_fundamentals` to every
    non-excluded position, re-hash, and write back.

    Returns the updated bundle dict so callers can inspect the new hash.
    Raises FileNotFoundError if the bundle path does not exist.
    """
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")

    with open(bundle_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    positions = data.get("positions", [])
    ok_count = 0
    err_count = 0
    skip_count = 0

    logger.info("enrich_fmp: %d positions in %s", len(positions), bundle_path.name)

    for pos in positions:
        ticker = pos.get("ticker") or pos.get("Ticker") or ""
        if not ticker or ticker in SKIP_TICKERS:
            skip_count += 1
            continue

        asset_class = pos.get("asset_class") or pos.get("Asset Class") or ""

        # Supply forward_pe from the already-enriched `fundamentals` dict so we
        # don't make an extra API call.  FMP free tier doesn't reliably carry it.
        forward_pe = None
        existing_funds = pos.get("fundamentals", {})
        if isinstance(existing_funds, dict):
            forward_pe = existing_funds.get("forward_pe")

        try:
            fmp_data = get_fmp_fundamentals_bundle(
                ticker, asset_class=asset_class, forward_pe_override=forward_pe
            )
            pos["fmp_fundamentals"] = fmp_data
            if "error" in fmp_data:
                err_count += 1
                logger.warning(
                    "enrich_fmp: %s — error: %s", ticker, fmp_data["error"]
                )
            else:
                ok_count += 1
        except Exception as exc:
            logger.warning("enrich_fmp: unexpected failure for %s: %s", ticker, exc)
            from datetime import datetime, timezone
            pos["fmp_fundamentals"] = {
                "error": str(exc),
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            err_count += 1

    logger.info(
        "enrich_fmp: complete — %d enriched, %d errors, %d skipped",
        ok_count, err_count, skip_count,
    )

    # Re-hash (bundles are immutable — mutation requires rehash)
    payload = _hashable_payload(data)
    data["bundle_hash"] = _sha256_canonical(payload)

    with open(bundle_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=True, default=str)

    return data


if __name__ == "__main__":
    import argparse
    from pathlib import Path as _Path

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Enrich latest bundle with FMP fundamentals")
    parser.add_argument("--bundle", type=str, default=None, help="Path to bundle JSON (default: latest)")
    args = parser.parse_args()

    if args.bundle:
        bundle_path = _Path(args.bundle)
    else:
        candidates = sorted(
            _Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            print("No market bundles found in bundles/")
            sys.exit(1)
        bundle_path = candidates[-1]

    print(f"Enriching {bundle_path.name} with FMP fundamentals...")
    result = enrich_bundle_fmp(bundle_path)
    print(f"Done. New hash: {result['bundle_hash']}")
