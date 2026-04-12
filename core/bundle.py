"""
Immutable context bundle — freezes market state to disk with a SHA256
content hash. Every AI agent downstream receives a bundle path and stamps
the hash into its output metadata, creating an auditable chain from
input snapshot to agent conclusion.

V1 scope: CSV holdings + yfinance enrichment + manual cash. Vault
documents are NOT included in V1 — see cli_migration_02 for vault
bundling.
"""

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance

# Import existing project parser
from utils.csv_parser import parse_schwab_csv, clean_numeric

BUNDLE_DIR = Path("bundles")
BUNDLE_SCHEMA_VERSION = "1.0.0"

@dataclass
class ContextBundle:
    schema_version: str
    timestamp_utc: str          # ISO-8601 with 'Z' suffix
    bundle_hash: str            # SHA256 hex, 64 chars — computed last
    source_csv_path: str
    source_csv_sha256: str      # SHA256 of raw CSV bytes
    positions: list[dict]       # enriched holdings: ticker, qty, price,
                                # value, cost_basis, sector, weight_pct
    cash_manual: float
    total_value: float
    position_count: int
    environment: dict           # python, pandas, yfinance versions, os
    enrichment_errors: list[str]

def _sha256_file(path: Path) -> str:
    """Stream-read the file in 64KB chunks and return hex digest."""
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def _sha256_canonical(payload: dict) -> str:
    """Compute SHA256 hash of canonical JSON serialization."""
    canonical_json = json.dumps(
        payload, 
        sort_keys=True, 
        separators=(",", ":"),
        ensure_ascii=True, 
        default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()

def _capture_environment() -> dict:
    """Returns dict with library and environment versions."""
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "yfinance": yfinance.__version__,
        "schema_version": BUNDLE_SCHEMA_VERSION
    }

def _hashable_payload(data: dict) -> dict:
    """
    Canonical pre-hash view of a bundle payload.

    Single source of truth for what gets hashed. Both build_bundle() and
    load_bundle() route through this so a future field addition cannot
    cause the hash shape to drift between write and read paths.
    """
    return {k: v for k, v in data.items() if k != "bundle_hash"}


def _normalize_positions(records: list[dict]) -> list[dict]:
    """
    Coerce numpy/pandas scalars to JSON-native types.

    df.to_dict(orient='records') returns dicts whose values are numpy
    scalars, pandas Timestamps, and NaN floats. These do not serialize
    deterministically across library versions and NaN is lossy under
    json.dumps. This normalizer produces values that json.dumps can
    round-trip without information loss.

    Rules:
      - NaN / NaT  -> None
      - bool       -> bool (must be checked before int; numpy bool is int)
      - int/float/str/None -> passthrough
      - numpy scalar -> .item() to native Python
      - anything else (Timestamp, etc.) -> str()
    """
    out = []
    for r in records:
        clean = {}
        for k, v in r.items():
            if v is None:
                clean[k] = None
            elif isinstance(v, bool):
                clean[k] = v
            elif isinstance(v, (int, float, str)):
                # pd.isna on a plain float handles NaN; guard on type first
                if isinstance(v, float) and pd.isna(v):
                    clean[k] = None
                else:
                    clean[k] = v
            elif pd.isna(v):
                clean[k] = None
            elif hasattr(v, "item"):
                # numpy scalar — unwrap to Python native
                try:
                    clean[k] = v.item()
                except (ValueError, AttributeError):
                    clean[k] = str(v)
            else:
                clean[k] = str(v)
        out.append(clean)
    return out


def build_bundle(csv_path: Path, cash_manual: float) -> ContextBundle:
    """
    Steps:
      a. Read and parse CSV using the existing project parser.
      b. Enrich with yfinance unique tickers.
      c. Compute value, then weight_pct.
      d. Inject the synthetic CASH_MANUAL row.
      e. Compute total_value and position_count.
      f. Build the payload and compute hash.
    """
    # a. Read and parse CSV
    with open(csv_path, "rb") as f:
        csv_bytes = f.read()
    
    df = parse_schwab_csv(csv_bytes)
    csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    
    enrichment_errors = []
    
    # b. Enrich with yfinance
    # CASH_TICKERS are handled separately or skip enrichment
    CASH_TICKERS = {'CASH_MANUAL', 'QACDS', 'CASH & CASH INVESTMENTS'}
    
    unique_tickers = [t for t in df['ticker'].unique() if t.upper() not in CASH_TICKERS]
    
    # Default every row to csv_fallback; flip to yfinance_live only on success.
    df['price_source'] = 'csv_fallback'

    live_prices: dict[str, float] = {}
    for ticker in unique_tickers:
        try:
            yt = yfinance.Ticker(ticker)
            try:
                price = yt.fast_info['lastPrice']
            except (AttributeError, KeyError, Exception):
                hist = yt.history(period="1d")
                if hist.empty:
                    raise ValueError(f"No price data found for {ticker}")
                price = hist['Close'].iloc[-1]
            live_prices[ticker] = float(price)
        except Exception as e:
            enrichment_errors.append(f"Failed to enrich {ticker}: {str(e)}")

    if live_prices:
        mask = df['ticker'].isin(live_prices.keys())
        df.loc[mask, 'price'] = df.loc[mask, 'ticker'].map(live_prices)
        df.loc[mask, 'price_source'] = 'yfinance_live'
    
    # c. Compute value
    df['market_value'] = df['quantity'] * df['price']
    
    # d. Always inject synthetic CASH_MANUAL row so bundle schema is
    # consistent across zero-cash and nonzero-cash snapshots.
    cash_row = {
        'ticker': 'CASH_MANUAL',
        'description': 'Manual Cash Entry',
        'quantity': float(cash_manual),
        'price': 1.0,
        'market_value': float(cash_manual),
        'cost_basis': float(cash_manual),
        'asset_class': 'Cash',
        'asset_strategy': 'Cash',
        'is_cash': True,
        'price_source': 'manual',
    }
    df = pd.concat([df, pd.DataFrame([cash_row])], ignore_index=True)

    # e. Compute totals
    total_value = df['market_value'].sum()
    position_count = len(df)
    
    # weight_pct
    if total_value > 0:
        df['weight_pct'] = (df['market_value'] / total_value) * 100
    else:
        df['weight_pct'] = 0.0

    # Convert positions to list of dicts
    positions = _normalize_positions(df.to_dict(orient="records"))
    
    # f. Build payload
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    payload = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "timestamp_utc": timestamp_utc,
        "source_csv_path": str(csv_path),
        "source_csv_sha256": csv_sha256,
        "positions": positions,
        "cash_manual": float(cash_manual),
        "total_value": float(total_value),
        "position_count": int(position_count),
        "environment": _capture_environment(),
        "enrichment_errors": enrichment_errors
    }
    
    # g. Compute hash via the single source of truth helper
    bundle_hash = _sha256_canonical(_hashable_payload(payload))
    
    return ContextBundle(
        bundle_hash=bundle_hash,
        **payload
    )

def write_bundle(bundle: ContextBundle) -> Path:
    """Writes the bundle to BUNDLE_DIR as a JSON file."""
    BUNDLE_DIR.mkdir(exist_ok=True)
    
    filename = (
        f"context_bundle_{bundle.timestamp_utc.replace(':', '')}"
        f"_{bundle.bundle_hash[:12]}.json"
    )
    path = BUNDLE_DIR / filename
    
    with open(path, "w") as f:
        json.dump(asdict(bundle), f, indent=2)
        
    return path

def load_bundle(path: Path) -> dict:
    """
    Read, parse, and verify the hash matches.

    Both the write path and this read path compute the hash via
    _hashable_payload() so the pre-hash view cannot drift.
    """
    with open(path, "r") as f:
        data = json.load(f)

    stored_hash = data.get("bundle_hash")
    if not stored_hash:
        raise ValueError(f"Bundle missing bundle_hash field: {path.name}")

    expected_hash = _sha256_canonical(_hashable_payload(data))

    if stored_hash != expected_hash:
        raise ValueError(
            f"Bundle hash mismatch! Filename: {path.name}\n"
            f"Stored:   {stored_hash}\n"
            f"Computed: {expected_hash}"
        )

    return data

__all__ = [
    "ContextBundle", "build_bundle", "write_bundle", "load_bundle",
    "BUNDLE_DIR", "BUNDLE_SCHEMA_VERSION"
]
