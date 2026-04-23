"""
Vault bundle — freezes the unstructured side of portfolio context to disk
with a SHA256 content hash.

Reads _thesis.md files, podcast transcripts, and research notes from the
local vault/ directory (primary path) or Google Drive (fallback). Produces
an immutable, content-addressed vault_bundle JSON that composes with the
market bundle in Phase 02's composite bundle.

V2 scope: local markdown files + Drive fallback. Vault items are hashed
over their UTF-8 text content (not Drive revision IDs) for self-contained
auditability.
"""

import hashlib
import json
import logging
import platform
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd  # version capture only

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# Constants
VAULT_DIR = Path("vault")
THESES_DIR = VAULT_DIR / "theses"
TRANSCRIPTS_DIR = VAULT_DIR / "transcripts"
RESEARCH_DIR = VAULT_DIR / "research"
VAULT_BUNDLE_DIR = Path("bundles")       # same dir as market bundles
VAULT_SCHEMA_VERSION = "1.0.0"
MAX_FILE_BYTES = 512 * 1024              # 512KB hard cap per file

@dataclass
class VaultDocument:
    ticker: str | None          # None for non-thesis docs
    doc_type: str               # "thesis" | "transcript" | "research"
    filename: str
    content_hash: str           # SHA256 of UTF-8 text bytes
    content: str | None         # full text; None if over MAX_FILE_BYTES
    thesis_present: bool        # False if ticker had no file
    style: str | None           # parsed from ## Style section
    scaling_state: str | None   # parsed from ## Scaling State
    rotation_priority: str | None  # parsed from ## Rotation Priority
    size_bytes: int
    skipped: bool               # True if over MAX_FILE_BYTES
    triggers: dict = field(default_factory=lambda: {"price_trim_above": None, "price_add_below": None})

@dataclass
class VaultBundle:
    schema_version: str
    timestamp_utc: str
    vault_hash: str             # SHA256 hex, 64 chars — computed last
    documents: list[dict]       # list of VaultDocument.asdict()
    theses_present: list[str]   # tickers with a thesis file
    theses_missing: list[str]   # tickers with no thesis file
    vault_doc_count: int
    vault_skip_log: list[str]   # files skipped (size cap or parse error)
    environment: dict

def _sha256_text(text: str) -> str:
    """Compute SHA256 hex digest of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

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
        "schema_version": VAULT_SCHEMA_VERSION
    }

def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_thesis_fields(content: str) -> dict:
    """
    Parse the _thesis.md template fields.
    Looks for Style, Scaling State, Rotation Priority sections,
    and the ```yaml triggers: block for price_trim_above / price_add_below.

    On malformed YAML, triggers defaults to nulls and a "__parse_error__"
    sentinel key is set so build_vault_bundle can log it to vault_skip_log.
    """
    lines = content.splitlines()
    result = {
        "style": None,
        "scaling_state": None,
        "rotation_priority": None,
        "triggers": {"price_trim_above": None, "price_add_below": None},
    }

    for i, line in enumerate(lines):
        line = line.strip()
        if line == "## Style":
            for j in range(i + 1, len(lines)):
                val = lines[j].strip()
                if val and not val.startswith("<!--"):
                    result["style"] = val
                    break
        elif line == "## Scaling State":
            for j in range(i + 1, len(lines)):
                val = lines[j].strip()
                if val.startswith("next_step:"):
                    result["scaling_state"] = val.replace("next_step:", "").strip()
                    break
        elif line == "## Rotation Priority":
            for j in range(i + 1, len(lines)):
                val = lines[j].strip()
                if val.startswith("priority:"):
                    result["rotation_priority"] = val.replace("priority:", "").strip()
                    break

    # Extract price triggers from the ```yaml triggers: block
    trig_match = re.search(
        r"```yaml\s*\ntriggers:\s*\n(.*?)```",
        content,
        re.DOTALL,
    )
    if trig_match:
        if not _YAML_AVAILABLE:
            result["triggers"]["__parse_error__"] = "PyYAML not installed"
        else:
            try:
                trig_data = _yaml.safe_load("triggers:\n" + trig_match.group(1)) or {}
                raw = trig_data.get("triggers", {}) or {}
                result["triggers"] = {
                    "price_trim_above": _safe_float(raw.get("price_trim_above")),
                    "price_add_below":  _safe_float(raw.get("price_add_below")),
                }
            except Exception as exc:
                result["triggers"]["__parse_error__"] = str(exc)

    return result

def _load_vault_document(
    path: Path,
    doc_type: str,
    ticker: str | None = None,
) -> VaultDocument:
    """Load a single vault file into a VaultDocument dataclass."""
    size_bytes = path.stat().st_size
    if size_bytes > MAX_FILE_BYTES:
        return VaultDocument(
            ticker=ticker,
            doc_type=doc_type,
            filename=path.name,
            content_hash="skipped",
            content=None,
            thesis_present=True,
            style=None,
            scaling_state=None,
            rotation_priority=None,
            size_bytes=size_bytes,
            skipped=True
        )
    
    text = path.read_text(encoding="utf-8", errors="replace")
    content_hash = _sha256_text(text)
    
    if doc_type == "thesis":
        parsed = _parse_thesis_fields(text)
    else:
        parsed = {"style": None, "scaling_state": None, "rotation_priority": None,
                  "triggers": {"price_trim_above": None, "price_add_below": None}}

    return VaultDocument(
        ticker=ticker,
        doc_type=doc_type,
        filename=path.name,
        content_hash=content_hash,
        content=text,
        thesis_present=True,
        style=parsed["style"],
        scaling_state=parsed["scaling_state"],
        rotation_priority=parsed["rotation_priority"],
        size_bytes=size_bytes,
        skipped=False,
        triggers=parsed["triggers"],
    )

def _discover_vault_files() -> dict[str, list[Path]]:
    """Scans local vault directories for relevant files."""
    return {
        "theses": sorted(list(THESES_DIR.glob("*_thesis.md"))),
        "transcripts": sorted(list(TRANSCRIPTS_DIR.glob("*.md"))),
        "research": sorted(list(RESEARCH_DIR.glob("*.md"))),
    }

def build_vault_bundle(
    ticker_list: list[str] | None = None,
    include_drive: bool = False,
) -> VaultBundle:
    """
    Builds a VaultBundle by scanning the vault directory and optional Drive fallback.
    """
    if include_drive:
        logging.info("Drive fallback not yet implemented — continuing with local files only.")

    # 1. Discover files
    files = _discover_vault_files()
    
    documents = []
    theses_present = []
    vault_skip_log = []
    
    # 2. Load theses
    for path in files["theses"]:
        # TICKER_thesis.md -> TICKER
        ticker = path.name.split("_")[0].upper()
        doc = _load_vault_document(path, "thesis", ticker)
        
        # Check for trigger parse errors
        if "__parse_error__" in doc.triggers:
            vault_skip_log.append(f"Trigger parse error in {path.name}: {doc.triggers['__parse_error__']}")
            # Remove sentinel before bundling
            del doc.triggers["__parse_error__"]

        documents.append(asdict(doc))
        if doc.skipped:
            vault_skip_log.append(f"Skipped {path.name}: over size cap")
        else:
            theses_present.append(ticker)
            
    # 3. Handle missing theses if ticker_list provided
    theses_missing = []
    if ticker_list:
        present_set = set(theses_present)
        for t in ticker_list:
            if t.upper() not in present_set:
                theses_missing.append(t.upper())
                # Append synthetic missing document
                doc = VaultDocument(
                    ticker=t.upper(),
                    doc_type="thesis",
                    filename=f"SYNTHETIC_{t.upper()}_MISSING",
                    content_hash="missing",
                    content=None,
                    thesis_present=False,
                    style=None,
                    scaling_state=None,
                    rotation_priority=None,
                    size_bytes=0,
                    skipped=False
                )
                documents.append(asdict(doc))
                
    # 4. Load transcripts and research
    for path in files["transcripts"]:
        doc = _load_vault_document(path, "transcript")
        documents.append(asdict(doc))
        if doc.skipped:
            vault_skip_log.append(f"Skipped {path.name}: over size cap")
            
    for path in files["research"]:
        doc = _load_vault_document(path, "research")
        documents.append(asdict(doc))
        if doc.skipped:
            vault_skip_log.append(f"Skipped {path.name}: over size cap")
            
    # 5. Build payload
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    payload = {
        "schema_version": VAULT_SCHEMA_VERSION,
        "timestamp_utc": timestamp_utc,
        "documents": documents,
        "theses_present": sorted(theses_present),
        "theses_missing": sorted(theses_missing),
        "vault_doc_count": len(documents),
        "vault_skip_log": vault_skip_log,
        "environment": _capture_environment()
    }

    # 6. Compute hash
    vault_hash = _sha256_canonical(payload)

    return VaultBundle(
        vault_hash=vault_hash,
        **payload
    )

def write_vault_bundle(bundle: VaultBundle) -> Path:
    """Writes the vault bundle to VAULT_BUNDLE_DIR as a JSON file."""
    VAULT_BUNDLE_DIR.mkdir(exist_ok=True)
    
    filename = (
        f"vault_bundle_{bundle.timestamp_utc.replace(':', '')}"
        f"_{bundle.vault_hash[:12]}.json"
    )
    path = VAULT_BUNDLE_DIR / filename
    
    with open(path, "w") as f:
        json.dump(asdict(bundle), f, indent=2)
        
    return path

def load_vault_bundle(path: Path) -> dict:
    """Loads and verifies a vault bundle from disk."""
    with open(path, "r") as f:
        data = json.load(f)
        
    stored_hash = data.get("vault_hash")
    if not stored_hash:
        raise ValueError(f"Vault bundle missing vault_hash: {path.name}")
        
    # Recompute hash to verify
    payload = {k: v for k, v in data.items() if k != "vault_hash"}
    expected_hash = _sha256_canonical(payload)
    
    if stored_hash != expected_hash:
        raise ValueError(
            f"Vault bundle hash mismatch! Filename: {path.name}\n"
            f"Stored:   {stored_hash}\n"
            f"Computed: {expected_hash}"
        )
        
    return data

__all__ = [
    "VaultDocument", "VaultBundle",
    "build_vault_bundle", "write_vault_bundle", "load_vault_bundle",
    "VAULT_DIR", "THESES_DIR", "VAULT_SCHEMA_VERSION",
]
