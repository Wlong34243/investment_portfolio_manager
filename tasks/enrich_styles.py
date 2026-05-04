"""
tasks/enrich_styles.py — Apply Bill's style classification (GARP/THEME/BORING/ETF/CASH)
to every position in the market bundle at snapshot time.

Source: data/ticker_strategies.json (maintained manually by Bill).
Positions not in the lookup receive "UNKNOWN" so gaps are visible in the sheet.
Re-hashes the bundle after mutation.
"""

import json
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.bundle import _sha256_canonical, _hashable_payload

logger = logging.getLogger(__name__)

STRATEGIES_PATH = _ROOT / "data" / "ticker_strategies.json"


def _load_strategies() -> dict:
    if not STRATEGIES_PATH.exists():
        raise FileNotFoundError(f"ticker_strategies.json not found at {STRATEGIES_PATH}")
    raw = json.loads(STRATEGIES_PATH.read_text(encoding="utf-8"))
    # Strip meta keys that start with underscore
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def enrich_bundle_styles(bundle_path: Path) -> dict:
    """
    Read market bundle at bundle_path, stamp asset_strategy on every position,
    re-hash, and write back.  Returns updated bundle dict.
    """
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")

    strategies = _load_strategies()

    with open(bundle_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    positions = data.get("positions", [])
    ok = unknown = 0

    for pos in positions:
        ticker = pos.get("ticker") or pos.get("Ticker") or ""
        strategy = strategies.get(ticker)
        if strategy:
            pos["asset_strategy"] = strategy
            ok += 1
        else:
            pos["asset_strategy"] = "UNKNOWN"
            unknown += 1
            logger.warning("enrich_styles: no strategy for %s — marked UNKNOWN", ticker)

    logger.info("enrich_styles: %d classified, %d unknown", ok, unknown)

    payload = _hashable_payload(data)
    data["bundle_hash"] = _sha256_canonical(payload)

    with open(bundle_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=True, default=str)

    return data
