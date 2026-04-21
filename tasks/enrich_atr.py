"""
ATR Enrichment Task — computes 14-day Average True Range for all non-cash
positions and writes `calculated_technical_stops` into the composite bundle JSON.

This is the pre-computation step that replaces the live yfinance ATR call that
was previously inside macro_cycle_agent.py (the Phase 5-D violation).

Architecture:
  - `load_composite_bundle()` verifies composite_hash == SHA256(market_hash + vault_hash).
  - Extra fields added to the composite JSON are not part of that hash, so writing
    `calculated_technical_stops` back to the composite JSON is safe.
  - The macro_cycle_agent reads `composite["calculated_technical_stops"]` from the bundle.

Usage:
    python tasks/enrich_atr.py                            # enriches latest composite bundle
    python tasks/enrich_atr.py --bundle path/to/composite.json
    python -m tasks.enrich_atr                            # module form
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

# Project root on path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from core.bundle import load_bundle, _sha256_canonical, _hashable_payload

logger = logging.getLogger(__name__)

ATR_MULTIPLIER = 2.5   # stop_loss = current_price - (ATR_MULTIPLIER × ATR_14)
ATR_PERIOD = 14        # standard ATR period


def calculate_atr(ticker: str, period: int = ATR_PERIOD) -> float:
    """
    Calculate the n-day Average True Range using yfinance.

    Downloads 1 month of daily OHLC data and computes:
        TR  = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        ATR = rolling mean(TR, period)

    Returns 0.0 if data is unavailable or ticker is a cash instrument.
    """
    try:
        df = yf.download(ticker, period="1mo", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < period:
            logger.warning("Insufficient data for ATR on %s (%d rows, need %d)", ticker, len(df), period)
            return 0.0

        # Handle MultiIndex columns from yfinance
        if hasattr(df.columns, "levels"):
            df = df.droplevel(1, axis=1)

        high_low     = df["High"] - df["Low"]
        high_close   = (df["High"] - df["Close"].shift(1)).abs()
        low_close    = (df["Low"]  - df["Close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = float(tr.rolling(window=period).mean().iloc[-1])
        return round(atr, 4) if not pd.isna(atr) else 0.0
    except Exception as e:
        logger.warning("ATR calculation failed for %s: %s", ticker, e)
        return 0.0


def compute_technical_stops(positions: list[dict]) -> list[dict]:
    """
    For each non-cash position, compute ATR-based stop loss.

    Returns list of dicts matching the ATRStopLoss Pydantic schema:
        ticker, atr_14, stop_loss_level, current_price, pct_from_stop
    """
    stops = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_TICKERS:
            continue

        current_price = float(pos.get("price", 0.0) or 0.0)
        if current_price <= 0:
            logger.warning("Zero price for %s — skipping ATR.", ticker)
            continue

        atr = calculate_atr(ticker)
        stop_loss = round(current_price - (ATR_MULTIPLIER * atr), 4)
        pct_from_stop = round(
            (current_price - stop_loss) / current_price
            if current_price > 0 else 0.0,
            4,
        )

        stops.append({
            "ticker": ticker,
            "atr_14": atr,
            "stop_loss_level": stop_loss,
            "current_price": round(current_price, 4),
            "pct_from_stop": pct_from_stop,
        })

    return stops


def enrich_composite_bundle(bundle_path: Path) -> dict:
    """
    Load the bundle (context or composite), compute ATR stops for all positions, 
    inject `calculated_technical_stops` into the JSON, and write it back.

    If it's a context bundle (has positions at root), it re-hashes the bundle.
    If it's a composite bundle, it just appends the metadata.
    """
    with open(bundle_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Resolve positions
    if "positions" in data:
        # Context/Market bundle
        positions = data["positions"]
        is_context = True
    elif "market_bundle_path" in data:
        # Composite bundle
        market_path = Path(data["market_bundle_path"])
        if not market_path.is_absolute():
             market_path = bundle_path.parent / market_path
        market = load_bundle(market_path)
        positions = market.get("positions", [])
        is_context = False
    else:
        raise ValueError(f"File at {bundle_path} does not appear to be a context or composite bundle.")

    # 2. Compute ATR stops
    stops = compute_technical_stops(positions)

    # 3. Inject into dict
    data["calculated_technical_stops"] = stops
    data["atr_enriched_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    data["atr_multiplier"] = ATR_MULTIPLIER

    # 4. Re-hash if context bundle
    if is_context:
        payload = _hashable_payload(data)
        data["bundle_hash"] = _sha256_canonical(payload)

    # 5. Write back
    with open(bundle_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return data


def main(bundle_path: Optional[str] = None) -> None:
    """Entry point for standalone use."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if bundle_path:
        path = Path(bundle_path)
    else:
        candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            print("ERROR: No context bundles found in bundles/.")
            sys.exit(1)
        path = candidates[-1]

    print(f"Enriching bundle: {path.name}")
    bundle = enrich_composite_bundle(path)
    stops = bundle.get("calculated_technical_stops", [])
    print(f"ATR stops computed for {len(stops)} position(s).")
    for s in stops[:5]:
        triggered = "TRIGGERED" if s["current_price"] < s["stop_loss_level"] else "ok"
        print(
            f"  {s['ticker']:8s}  price={s['current_price']:.2f}  "
            f"stop={s['stop_loss_level']:.2f}  ATR={s['atr_14']:.2f}  [{triggered}]"
        )
    if len(stops) > 5:
        print(f"  ... and {len(stops)-5} more.")
    print(f"Written back to: {path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich composite bundle with ATR technical stops.")
    parser.add_argument("--bundle", default=None, help="Path to composite bundle JSON.")
    args = parser.parse_args()
    main(args.bundle)
