"""
Immutable context bundle — freezes market state to disk with a SHA256
content hash. Every AI agent downstream receives a bundle path and stamps
the hash into its output metadata, creating an auditable chain from
input snapshot to agent conclusion.

V1 scope: CSV holdings + yfinance enrichment + manual cash.
V2 scope: Schwab API + CSV fallback. Pluggable data sources.
"""

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

import pandas as pd
import yfinance
import config

# Import existing project parser
from utils.csv_parser import parse_schwab_csv, clean_numeric

BUNDLE_DIR = Path("bundles")
BUNDLE_SCHEMA_VERSION = "1.0.0"

# Data source modes for build_bundle()
SOURCE_SCHWAB = "schwab"
SOURCE_CSV = "csv"
SOURCE_AUTO = "auto"
VALID_SOURCES = {SOURCE_SCHWAB, SOURCE_CSV, SOURCE_AUTO}

@dataclass
class ContextBundle:
    schema_version: str
    timestamp_utc: str          # ISO-8601 with 'Z' suffix
    bundle_hash: str            # SHA256 hex, 64 chars — computed last
    source_csv_path: str        # Identifies the source (path or "schwab_api")
    source_csv_sha256: str      # Source fingerprint (file SHA or account hash)
    data_source: str            # "schwab" | "csv"
    data_source_fingerprint: str # stable identity of the source
    tax_treatment_available: bool # True only on Schwab path in v1
    positions: list[dict]       # enriched holdings: ticker, qty, price,
                                # value, cost_basis, sector, weight_pct
    cash_manual: float
    total_value: float
    position_count: int
    environment: dict           # python, pandas, yfinance versions, os
    enrichment_errors: list[str]
    tax_lots: list[dict] = field(default_factory=list)  # Phase 1.3: one synthetic lot per position per account

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

def _build_from_schwab(
    cash_manual: float,
) -> tuple[pd.DataFrame, str, list[str], list[dict]]:
    """
    Fetch positions from the live Schwab API.

    Returns:
        (positions_df, data_source_fingerprint, enrichment_errors, tax_lots)

    Raises:
        RuntimeError: if get_accounts_client() returns None (no token,
            auth failure, GCS unreachable) — the caller decides
            whether to fall back to CSV.
    """
    # Lazy import so core/bundle.py is importable even on machines
    # without schwab-py installed (unit tests, CI).
    try:
        from utils.schwab_client import (
            get_accounts_client, get_market_client,
            fetch_positions, fetch_quotes, fetch_tax_lots,
        )
    except ImportError as e:
        raise RuntimeError(
            f"Schwab client not available: {e}. "
            "Install schwab-py or use --source csv."
        )

    client = get_accounts_client()
    if client is None:
        raise RuntimeError(
            "Schwab accounts client returned None — token missing, "
            "expired, or GCS unreachable. Check "
            "`gsutil ls gs://portfolio-manager-tokens/` and "
            "the Cloud Function logs. Fall back to --source csv "
            "or run scripts/schwab_manual_reauth.py."
        )

    df = fetch_positions(client)
    if df is None or df.empty:
        raise RuntimeError(
            "fetch_positions() returned empty. Check Schwab API "
            "availability and verify the account hash in secrets.toml."
        )

    enrichment_errors: list[str] = []

    # Batch-quote enrichment: populate daily_change_pct from Schwab Market Data.
    # We prioritize the day-change data already in the positions DataFrame (from
    # the /positions endpoint). We only fall back to fetch_quotes() if the
    # current value is 0.0.
    try:
        market_client = get_market_client()
        if market_client is not None:
            # We check for tickers that still have 0.0 daily change
            zero_chg_tickers = [
                t for t in df[df["daily_change_pct"] == 0.0]["ticker"].unique()
                if t not in config.CASH_TICKERS
            ]
            if zero_chg_tickers:
                quotes_df = fetch_quotes(market_client, zero_chg_tickers)
                if not quotes_df.empty:
                    chg_map = quotes_df.set_index("ticker")["change_pct"].to_dict()
                    for ticker, quote_val in chg_map.items():
                        if quote_val != 0.0:
                            df.loc[df["ticker"] == ticker, "daily_change_pct"] = quote_val
    except Exception as _qe:
        enrichment_errors.append(f"Daily change % batch quote failed: {_qe}")

    # Mark every row with price_source="schwab_quote" unless the
    # 2026-04-10 zero-price patch fires (handled below)
    df["price_source"] = "schwab_quote"

    # Zero-price fallback: any position where Schwab returned 0
    # gets yfinance enrichment. This matches the app.py fix from
    # the 2026-04-10 bug patches.
    zero_price_mask = df["price"] <= 0
    if zero_price_mask.any():
        zero_tickers = df.loc[zero_price_mask, "ticker"].tolist()
        logger_warning = (
            f"{len(zero_tickers)} position(s) returned zero price "
            f"from Schwab; falling back to yfinance: {zero_tickers}"
        )
        enrichment_errors.append(logger_warning)
        for idx in df.index[zero_price_mask]:
            ticker = df.at[idx, "ticker"]
            if ticker in config.CASH_TICKERS:
                continue
            try:
                yt = yfinance.Ticker(ticker)
                try:
                    price = yt.fast_info["lastPrice"]
                except (AttributeError, KeyError, Exception):
                    hist = yt.history(period="1d")
                    if hist.empty:
                        raise ValueError(f"No yfinance data for {ticker}")
                    price = hist["Close"].iloc[-1]
                df.at[idx, "price"] = float(price)
                df.at[idx, "price_source"] = "yfinance_live"
                # Recompute market_value with the fallback price
                df.at[idx, "market_value"] = (
                    float(df.at[idx, "quantity"]) * float(price)
                )
            except Exception as e:
                enrichment_errors.append(
                    f"Zero-price fallback failed for {ticker}: {e}"
                )

    # Tax treatment per position. If fetch_positions() already
    # populates a tax_treatment column, trust it. Otherwise default
    # to "unknown" and log.
    if "tax_treatment" not in df.columns:
        df["tax_treatment"] = "unknown"
        enrichment_errors.append(
            "Schwab fetch_positions did not return tax_treatment — "
            "all positions marked 'unknown'. Extend fetch_positions "
            "in a follow-up if tax-loss harvesting needs this."
        )

    # Always inject the synthetic CASH_MANUAL row for schema
    # consistency, same as CSV path. If fetch_positions already
    # returned a CASH_MANUAL row (the 2026-04-10 cash aggregation
    # patch), skip the injection — don't duplicate.
    if not (df["ticker"] == "CASH_MANUAL").any():
        cash_row = {
            "ticker": "CASH_MANUAL",
            "description": "Manual Cash Entry",
            "quantity": 1.0,
            "price": float(cash_manual),
            "market_value": float(cash_manual),
            "cost_basis": float(cash_manual),
            "asset_class": "Cash",
            "asset_strategy": "Cash",
            "is_cash": True,
            "price_source": "manual",
            "tax_treatment": "unknown",
        }
        df = pd.concat([df, pd.DataFrame([cash_row])], ignore_index=True)

    # Compute data_source_fingerprint from account hash(es).
    # For MVP, use the single SCHWAB_ACCOUNT_HASH from config.
    import hashlib
    import config as _config
    account_hash = getattr(_config, "SCHWAB_ACCOUNT_HASH", "")
    source_fingerprint = hashlib.sha256(
        account_hash.encode("utf-8")
    ).hexdigest()[:16]

    # Fetch tax lots (one synthetic lot per position per account).
    # Schwab's public API does not expose individual cost lots; each lot
    # here represents the full aggregate for ticker + account.
    # acquisition_date is unknown from this endpoint; holding_period = "unknown".
    tax_lots: list[dict] = []
    try:
        tax_lots = fetch_tax_lots(client)
    except Exception as _lot_err:
        enrichment_errors.append(f"tax_lot ingestion failed: {_lot_err}")

    return df, source_fingerprint, enrichment_errors, tax_lots

def _build_from_csv(
    csv_path: Path,
    cash_manual: float,
) -> tuple[pd.DataFrame, str, list[str]]:
    """
    Parse a Schwab CSV export into the same DataFrame shape as
    _build_from_schwab(). Used for disaster recovery and for users
    without Schwab API access.
    """
    # a. Read and parse CSV
    with open(csv_path, "rb") as f:
        csv_bytes = f.read()
    
    df = parse_schwab_csv(csv_bytes)
    csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    
    enrichment_errors = []
    
    # b. Enrich with yfinance
    unique_tickers = [t for t in df['ticker'].unique() if t.upper() not in config.CASH_TICKERS]
    
    # Default every row to csv_fallback; flip to yfinance_live only on success.
    df['price_source'] = 'csv_fallback'
    df['tax_treatment'] = 'unknown' # CSV doesn't carry this info

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
    
    # c. Compute value and unrealized G/L
    df['market_value'] = df['quantity'] * df['price']
    
    # Compute unrealized G/L if cost_basis is present
    if 'cost_basis' in df.columns:
        if 'unrealized_gl' not in df.columns:
            df['unrealized_gl'] = 0.0
        
        # Always re-compute based on current market_value (which uses live prices)
        mask = (df['cost_basis'] > 0)
        df.loc[mask, 'unrealized_gl'] = df.loc[mask, 'market_value'] - df.loc[mask, 'cost_basis']
        
        if 'unrealized_gl_pct' not in df.columns:
            df['unrealized_gl_pct'] = 0.0
        df.loc[mask, 'unrealized_gl_pct'] = (df.loc[mask, 'unrealized_gl'] / df.loc[mask, 'cost_basis']) * 100
    
    # d. Always inject synthetic CASH_MANUAL row
    cash_row = {
        'ticker': 'CASH_MANUAL',
        'description': 'Manual Cash Entry',
        'quantity': 1.0,
        'price': float(cash_manual),
        'market_value': float(cash_manual),
        'cost_basis': float(cash_manual),
        'asset_class': 'Cash',
        'asset_strategy': 'Cash',
        'is_cash': True,
        'price_source': 'manual',
        'tax_treatment': 'taxable',
    }
    df = pd.concat([df, pd.DataFrame([cash_row])], ignore_index=True)

    return df, csv_sha256, enrichment_errors

def build_bundle(
    source: str = SOURCE_AUTO,
    csv_path: Path | None = None,
    cash_manual: float = 0.0,
) -> ContextBundle:
    """
    Build an immutable context bundle from the requested data source.

    Args:
        source: "schwab" | "csv" | "auto" (default)
        csv_path: required if source == "csv" or as fallback for "auto"
        cash_manual: manual cash balance (used if source doesn't
            provide one itself)

    Raises:
        ValueError: on invalid source or missing csv_path when required
        RuntimeError: on source-specific failure with no fallback available
    """
    if source not in VALID_SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Must be one of {VALID_SOURCES}."
        )

    tax_lots: list[dict] = []

    if source == SOURCE_CSV:
        if csv_path is None:
            raise ValueError(
                "source='csv' requires csv_path. "
                "Pass --csv PATH or use --source auto."
            )
        df, source_fingerprint, enrichment_errors = _build_from_csv(
            csv_path=csv_path, cash_manual=cash_manual
        )
        resolved_source = SOURCE_CSV
        source_path_repr = str(csv_path)

    elif source == SOURCE_SCHWAB:
        df, source_fingerprint, enrichment_errors, tax_lots = _build_from_schwab(
            cash_manual=cash_manual
        )
        resolved_source = SOURCE_SCHWAB
        source_path_repr = "schwab_api"

    elif source == SOURCE_AUTO:
        try:
            df, source_fingerprint, enrichment_errors, tax_lots = (
                _build_from_schwab(cash_manual=cash_manual)
            )
            resolved_source = SOURCE_SCHWAB
            source_path_repr = "schwab_api"
        except RuntimeError as schwab_err:
            if csv_path is None:
                raise RuntimeError(
                    f"Schwab source failed and no csv_path provided "
                    f"as fallback. Schwab error: {schwab_err}. "
                    f"Either provide --csv PATH or debug the Schwab "
                    f"client."
                )
            # Fall back to CSV with a loud warning
            enrichment_errors = [
                f"Schwab source failed — fell back to CSV. "
                f"Schwab error: {schwab_err}"
            ]
            df2, source_fingerprint, csv_errors = _build_from_csv(
                csv_path=csv_path, cash_manual=cash_manual
            )
            df = df2
            enrichment_errors.extend(csv_errors)
            resolved_source = SOURCE_CSV
            source_path_repr = str(csv_path)
    else:
        raise ValueError(f"Unreachable source branch: {source}")

    # Compute totals (market_value already computed in builders, but re-ensure)
    df["market_value"] = df["quantity"] * df["price"]
    total_value = float(df["market_value"].sum())
    position_count = len(df)
    if total_value > 0:
        df["weight_pct"] = (df["market_value"] / total_value) * 100
    else:
        df["weight_pct"] = 0.0

    # Sort by market_value descending
    df = df.sort_values(by="market_value", ascending=False)

    positions = _normalize_positions(df.to_dict(orient="records"))
    tax_treatment_available = any(
        p.get("tax_treatment", "unknown") != "unknown"
        for p in positions
    )

    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # source_csv_path and source_csv_sha256 are kept for backward compatibility.
    # Semantics broaden: identity and fingerprint regardless of source.
    payload = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "timestamp_utc": timestamp_utc,
        "source_csv_path": source_path_repr,
        "source_csv_sha256": source_fingerprint,
        "data_source": resolved_source,
        "data_source_fingerprint": source_fingerprint,
        "tax_treatment_available": tax_treatment_available,
        "positions": positions,
        "cash_manual": float(cash_manual),
        "total_value": float(total_value),
        "position_count": int(position_count),
        "environment": _capture_environment(),
        "enrichment_errors": enrichment_errors,
        "tax_lots": tax_lots,   # Phase 1.3: included in hash
    }

    bundle_hash = _sha256_canonical(_hashable_payload(payload))

    return ContextBundle(
        bundle_hash=bundle_hash,
        **payload,
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
    "BUNDLE_DIR", "BUNDLE_SCHEMA_VERSION",
    "SOURCE_SCHWAB", "SOURCE_CSV", "SOURCE_AUTO", "VALID_SOURCES"
]
