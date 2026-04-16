"""
Composite bundle — combines a market bundle and a vault bundle into a
single agent-ready artifact with one hash.

The composite bundle does NOT merge the two JSON blobs. It stores both
sub-bundle paths, both sub-hashes, and a composite hash computed over
(market_hash + vault_hash). Agents receive the composite path and stamp
composite_hash into their response metadata.

If either sub-bundle is absent or its hash fails verification, this module
raises ValueError before writing anything.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle

# Constants
COMPOSITE_BUNDLE_DIR = Path("bundles")
COMPOSITE_SCHEMA_VERSION = "1.0.0"

@dataclass
class CompositeBundle:
    composite_schema_version: str
    timestamp_utc: str
    composite_hash: str         # SHA256 of (market_hash + vault_hash)
    market_bundle_hash: str
    vault_bundle_hash: str
    market_bundle_path: str     # relative path string
    vault_bundle_path: str      # relative path string
    position_count: int
    vault_doc_count: int
    theses_present: list[str]
    theses_missing: list[str]
    recent_rotations: list[dict] # From Trade_Log Sheet tab

def _composite_hash(market_hash: str, vault_hash: str, recent_rotations: list[dict] = None) -> str:
    """Compute SHA256 hex digest of (market_hash + vault_hash + rotations)."""
    payload = f"{market_hash}{vault_hash}"
    if recent_rotations:
        payload += json.dumps(recent_rotations, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def build_composite_bundle(
    market_bundle_path: Path,
    vault_bundle_path: Path,
) -> CompositeBundle:
    """
    Combines market and vault bundles into a CompositeBundle metadata object.
    Includes recent rotations from Trade_Log.
    """
    # 1. Load and verify sub-bundles
    market_data = load_bundle(market_bundle_path)
    vault_data = load_vault_bundle(vault_bundle_path)
    
    market_hash = market_data["bundle_hash"]
    vault_hash = vault_data["vault_hash"]
    
    # 2. Fetch recent rotations from Trade_Log (Tier 2 data - baked into composite)
    from utils.sheet_readers import get_trade_log
    try:
        trade_log_df = get_trade_log()
        if not trade_log_df.empty:
            recent_rotations = trade_log_df.sort_values("Date", ascending=False).head(10).to_dict(orient="records")
        else:
            recent_rotations = []
    except Exception as e:
        print(f"Warning: Could not fetch Trade_Log for composite bundle: {e}")
        recent_rotations = []

    # 3. Compute composite hash
    comp_hash = _composite_hash(market_hash, vault_hash, recent_rotations)
    
    # 4. Extract metadata
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    return CompositeBundle(
        composite_schema_version=COMPOSITE_SCHEMA_VERSION,
        timestamp_utc=timestamp_utc,
        composite_hash=comp_hash,
        market_bundle_hash=market_hash,
        vault_bundle_hash=vault_hash,
        market_bundle_path=str(market_bundle_path),
        vault_bundle_path=str(vault_bundle_path),
        position_count=market_data["position_count"],
        vault_doc_count=vault_data["vault_doc_count"],
        theses_present=vault_data["theses_present"],
        theses_missing=vault_data["theses_missing"],
        recent_rotations=recent_rotations
    )

def write_composite_bundle(bundle: CompositeBundle) -> Path:
    """Writes the composite bundle to COMPOSITE_BUNDLE_DIR as a JSON file."""
    COMPOSITE_BUNDLE_DIR.mkdir(exist_ok=True)
    
    filename = (
        f"composite_bundle_{bundle.timestamp_utc.replace(':', '')}"
        f"_{bundle.composite_hash[:12]}.json"
    )
    path = COMPOSITE_BUNDLE_DIR / filename
    
    with open(path, "w") as f:
        json.dump(asdict(bundle), f, indent=2)
        
    return path

def load_composite_bundle(path: Path) -> dict:
    """Loads and verifies a composite bundle from disk."""
    with open(path, "r") as f:
        data = json.load(f)
        
    stored_comp_hash = data.get("composite_hash")
    market_hash = data.get("market_bundle_hash")
    vault_hash = data.get("vault_bundle_hash")
    recent_rotations = data.get("recent_rotations", [])
    
    if not all([stored_comp_hash, market_hash, vault_hash]):
        raise ValueError(f"Composite bundle missing required hash fields: {path.name}")
        
    # Recompute composite hash to verify
    expected_comp_hash = _composite_hash(market_hash, vault_hash, recent_rotations)
    
    if stored_comp_hash != expected_comp_hash:
        raise ValueError(
            f"Composite bundle hash mismatch! Filename: {path.name}\n"
            f"Stored:   {stored_comp_hash}\n"
            f"Computed: {expected_comp_hash}"
        )
        
    return data

def resolve_latest_bundles(bundle_dir: Path = Path("bundles")) -> tuple[Path, Path]:
    """ Finds the latest market and vault bundles in the specified directory. """
    market_bundles = sorted(list(bundle_dir.glob("context_bundle_*.json")), key=lambda p: p.stat().st_mtime)
    vault_bundles = sorted(list(bundle_dir.glob("vault_bundle_*.json")), key=lambda p: p.stat().st_mtime)
    
    if not market_bundles:
        raise FileNotFoundError(f"No market bundles found in {bundle_dir}")
    if not vault_bundles:
        raise FileNotFoundError(f"No vault bundles found in {bundle_dir}")
        
    return market_bundles[-1], vault_bundles[-1]

def load_composite(path: Path) -> dict:
    """Preferred alias for load_composite_bundle — used by agent code."""
    return load_composite_bundle(path)


__all__ = [
    "CompositeBundle",
    "build_composite_bundle", "write_composite_bundle",
    "load_composite_bundle", "load_composite",
    "resolve_latest_bundles",
    "COMPOSITE_SCHEMA_VERSION",
]
