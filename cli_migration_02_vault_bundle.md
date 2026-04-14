# CLI Migration Phase 02 — Vault Bundling
# Target: Claude Code or Gemini CLI
# Run prompts 1–5 sequentially. Each prompt is self-contained.
# PREREQUISITE: Phase 01 green — test_bundle_smoke.py passing, at least one
# bundles/context_bundle_*.json verified.

## Overview

Phase 01 froze the quant side of the portfolio: positions, prices, cash.
Phase 02 freezes the unstructured side: `_thesis.md` files, podcast
transcripts, and research notes. These are the qualitative inputs that let
agents reason about *why* a position is held, not just what it is worth.

**Three deliverables:**

1. `core/vault_bundle.py` — reads markdown files from `vault/` (local-first,
   Drive fallback). Produces `vault_bundle_<timestamp>_<hash>.json` with its
   own independent SHA256.

2. `core/composite_bundle.py` — thin wrapper combining `market_hash +
   vault_hash` into a single composite bundle. Agents receive one path and
   one hash; they don't need to know there are two sources.

3. `manager.py` — extended with `vault` and `bundle` subcommand groups.

**Key design decisions (non-negotiable):**

- **Content-hash, not Drive revision ID.** The audit guarantee must hold
  without Drive being reachable. Hash the file's text bytes directly.
- **Local-first.** Check `vault/theses/`, `vault/transcripts/`,
  `vault/research/` before making any Drive API call.
- **Missing thesis = warning, not failure.** The bundle builds. Agent sees
  `thesis_present: false` and reduces confidence. Never block the run.
- **Composite bundle is a wrapper, not a merge.** It stores both sub-bundle
  paths and hashes. Agents reconstruct full context from both files.
- **Per-file size cap: 512KB.** Files over this are skipped and logged in
  `vault_skip_log`. Never fail silently.
- **No Streamlit imports anywhere in core/.**

---

## Prompt 1 of 5: Create core/vault_bundle.py

```text
Read these files before writing code:
- core/bundle.py            (mirror the pattern exactly — dataclass, hash, write, load)
- config.py                 (check for any vault-related constants)
- utils/sheet_readers.py    (understand ADC credential path for Drive fallback)

Create: core/vault_bundle.py

Module docstring:
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

Imports (no streamlit anywhere):
    import hashlib
    import json
    import platform
    import sys
    from dataclasses import dataclass, field, asdict
    from datetime import datetime, timezone
    from pathlib import Path
    from typing import Any

    import pandas as pd  # version capture only

Constants:
    VAULT_DIR = Path("vault")
    THESES_DIR = VAULT_DIR / "theses"
    TRANSCRIPTS_DIR = VAULT_DIR / "transcripts"
    RESEARCH_DIR = VAULT_DIR / "research"
    VAULT_BUNDLE_DIR = Path("bundles")       # same dir as market bundles
    VAULT_SCHEMA_VERSION = "1.0.0"
    MAX_FILE_BYTES = 512 * 1024              # 512KB hard cap per file

Define a dataclass:

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

Functions to implement:

1. _sha256_text(text: str) -> str
   hashlib.sha256(text.encode("utf-8")).hexdigest()

2. _sha256_canonical(payload: dict) -> str
   Identical to core/bundle.py implementation — import or copy.
   (Prefer import: from core.bundle import _sha256_canonical if it is
   exported, otherwise copy the three-liner.)

3. _capture_environment() -> dict
   Same fields as core/bundle.py but include vault_schema_version instead
   of bundle schema_version.

4. _parse_thesis_fields(content: str) -> dict
   Parse the _thesis.md template fields. Use simple line scanning — no
   regex required for V2. Look for lines starting with:
     "## Style" — next non-blank, non-comment line is the style value
     "## Scaling State" — extract next_step value from "next_step: ..."
     "## Rotation Priority" — extract priority value from "priority: ..."
   Return dict with keys: style, scaling_state, rotation_priority.
   All values default to None if not found. Never raise — log parse
   failures to vault_skip_log.

5. _load_vault_document(
       path: Path,
       doc_type: str,
       ticker: str | None = None,
   ) -> VaultDocument
   Steps:
     a. size_bytes = path.stat().st_size
     b. If size_bytes > MAX_FILE_BYTES: return skipped VaultDocument with
        content=None, content_hash="skipped", skipped=True.
     c. text = path.read_text(encoding="utf-8", errors="replace")
     d. content_hash = _sha256_text(text)
     e. If doc_type == "thesis": parsed = _parse_thesis_fields(text)
        else: parsed = {style: None, scaling_state: None, rotation_priority: None}
     f. Return VaultDocument with thesis_present=True (caller sets False for
        synthetic missing-thesis entries).

6. _discover_vault_files() -> dict[str, list[Path]]
   Returns:
     {
       "theses": sorted(THESES_DIR.glob("*_thesis.md")),
       "transcripts": sorted(TRANSCRIPTS_DIR.glob("*.md") + TRANSCRIPTS_DIR.glob("*.txt")),
       "research": sorted(RESEARCH_DIR.glob("*.md")),
     }
   Create missing directories silently (exist_ok=True). Never raise if dirs
   don't exist.

7. build_vault_bundle(
       ticker_list: list[str] | None = None,
       include_drive: bool = False,
   ) -> VaultBundle
   Parameters:
     ticker_list — if provided, check these tickers for missing theses
     include_drive — if True, attempt Drive fallback for missing files
                     (Drive integration is a stub in V2 — log "Drive fallback
                     not yet implemented" and continue)
   Steps:
     a. Create vault directories if missing.
     b. Discover vault files via _discover_vault_files().
     c. Load all thesis files. For each, extract ticker from filename
        (TICKER_thesis.md → TICKER).
     d. If ticker_list provided, compute theses_missing = set(ticker_list) -
        set of loaded thesis tickers.
     e. For each missing ticker: append a synthetic VaultDocument with
        thesis_present=False, content=None, content_hash=None.
     f. Load all transcript and research files.
     g. Collect vault_skip_log entries.
     h. Build payload dict with vault_hash="" placeholder.
     i. Compute vault_hash = _sha256_canonical(payload_without_hash_field).
        IMPORTANT: Remove vault_hash from payload before hashing.
     j. Return VaultBundle.

8. write_vault_bundle(bundle: VaultBundle) -> Path
   Filename: f"vault_bundle_{bundle.timestamp_utc.replace(':','')}"
             f"_{bundle.vault_hash[:12]}.json"
   Write with indent=2. Return path.

9. load_vault_bundle(path: Path) -> dict
   Read, parse, verify hash (same raise-on-mismatch pattern as
   core/bundle.load_bundle). Return dict.

Return from this module:
    __all__ = [
        "VaultDocument", "VaultBundle",
        "build_vault_bundle", "write_vault_bundle", "load_vault_bundle",
        "VAULT_DIR", "THESES_DIR", "VAULT_SCHEMA_VERSION",
    ]

Do NOT:
- Import streamlit
- Write to Google Sheets
- Call any LLM
- Implement Drive integration beyond the stub (Phase 02 Drive fallback is
  deferred — log and continue)
```

---

## Prompt 2 of 5: Create core/composite_bundle.py

```text
Read these files before writing code:
- core/bundle.py
- core/vault_bundle.py  (the module from Prompt 1)

Create: core/composite_bundle.py

Module docstring:
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

Constants:
    COMPOSITE_BUNDLE_DIR = Path("bundles")
    COMPOSITE_SCHEMA_VERSION = "1.0.0"

Define a dataclass:

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

Functions to implement:

1. _composite_hash(market_hash: str, vault_hash: str) -> str
   hashlib.sha256(f"{market_hash}{vault_hash}".encode("utf-8")).hexdigest()

2. build_composite_bundle(
       market_bundle_path: Path,
       vault_bundle_path: Path,
   ) -> CompositeBundle
   Steps:
     a. Load and verify both sub-bundles using their respective load_ functions.
        Raise ValueError with clear message if either fails hash verification.
     b. Extract market_hash, vault_hash.
     c. Compute composite_hash.
     d. Extract position_count from market bundle, vault_doc_count +
        theses_present + theses_missing from vault bundle.
     e. Return CompositeBundle.

3. write_composite_bundle(bundle: CompositeBundle) -> Path
   Filename: f"composite_bundle_{bundle.timestamp_utc.replace(':','')}"
             f"_{bundle.composite_hash[:12]}.json"
   Write with indent=2. Return path.

4. load_composite_bundle(path: Path) -> dict
   Read and parse. Verify composite_hash by recomputing from the stored
   market_bundle_hash and vault_bundle_hash. Raise ValueError on mismatch.
   Return dict.

5. resolve_latest_bundles(bundle_dir: Path = Path("bundles")) -> tuple[Path, Path]
   Find the latest market bundle (glob context_bundle_*.json, sort by mtime)
   and the latest vault bundle (glob vault_bundle_*.json, sort by mtime).
   Raise FileNotFoundError with a clear message if either is absent.
   Return (market_path, vault_path).

Return from this module:
    __all__ = [
        "CompositeBundle",
        "build_composite_bundle", "write_composite_bundle",
        "load_composite_bundle", "resolve_latest_bundles",
        "COMPOSITE_SCHEMA_VERSION",
    ]

Do NOT:
- Import streamlit
- Call any LLM
- Merge the sub-bundle data into a flat dict — preserve the pointer structure
```

---

## Prompt 3 of 5: Extend utils/gemini_client.py for composite bundles

```text
Read utils/gemini_client.py fully before making changes.
Do NOT modify ask_gemini() or ask_gemini_bundled() — the existing signatures
are already in use.

Add a NEW function: ask_gemini_composite()

    def ask_gemini_composite(
        prompt: str,
        composite_bundle_path: Path | str,
        response_schema: type[BaseModel],
        ticker: str | None = None,
        system_instruction: str | None = None,
        max_tokens: int = 2000,
    ) -> BaseModel | None:
        """
        Composite-bundle-aware Gemini call.

        Loads the composite bundle, verifies hashes on both sub-bundles,
        and builds a structured context prompt that includes:
          - Full market bundle positions (from market sub-bundle)
          - Relevant thesis content (from vault sub-bundle)
            If ticker is provided: include only that position's thesis.
            If ticker is None: include all available theses.
          - theses_missing list so the agent can note coverage gaps.

        The response_schema MUST include a `bundle_hash: str` field.
        bundle_hash will be populated with composite_hash, not the
        individual sub-bundle hashes.

        SAFETY_PREAMBLE is still auto-prepended by the underlying ask_gemini()
        call — do NOT add it here.
        """

Implementation steps:

1. Enforce bundle_hash field on schema (same check as ask_gemini_bundled).
2. Load composite bundle: from core.composite_bundle import load_composite_bundle.
   Verify composite hash raises on mismatch.
3. Load market sub-bundle: from core.bundle import load_bundle.
4. Load vault sub-bundle: from core.vault_bundle import load_vault_bundle.
5. Filter vault documents:
   - If ticker provided: find the matching thesis. If missing, include the
     synthetic missing-thesis entry.
   - If ticker is None: include all theses (exclude transcripts/research to
     control context length in V2).
6. Build composite_preamble:

   bundle_preamble = (
       f"COMPOSITE CONTEXT BUNDLE (immutable snapshot):\n"
       f"  composite_hash: {composite['composite_hash']}\n"
       f"  market_bundle_hash: {composite['market_bundle_hash']}\n"
       f"  vault_bundle_hash: {composite['vault_bundle_hash']}\n"
       f"  timestamp_utc: {composite['timestamp_utc']}\n\n"
       f"MARKET STATE:\n"
       f"  total_value: {market['total_value']}\n"
       f"  position_count: {market['position_count']}\n"
       f"  positions: {json.dumps(market['positions'], default=str)}\n\n"
       f"VAULT STATE:\n"
       f"  theses_present: {composite['theses_present']}\n"
       f"  theses_missing: {composite['theses_missing']}\n"
       f"  thesis_context: {json.dumps(thesis_docs, default=str)}\n\n"
       f"You MUST include bundle_hash='{composite['composite_hash']}' "
       f"in your response.\n\n"
       f"USER PROMPT:\n{prompt}"
   )

7. Call ask_gemini() with the full preamble and response_schema.
8. After parsing: overwrite bundle_hash field with composite_hash (same
   trust-the-file pattern as ask_gemini_bundled).
9. Return model instance.

Do NOT:
- Modify ask_gemini() or ask_gemini_bundled()
- Import streamlit
- Add Drive API calls here — vault content comes from the pre-built vault bundle
```

---

## Prompt 4 of 5: Extend manager.py with vault and bundle subcommand groups

```text
Read manager.py and core/vault_bundle.py and core/composite_bundle.py
before making changes.

Add two new Typer subcommand groups to manager.py (do not modify the
existing `snapshot` subcommand):

--- VAULT GROUP ---

vault_app = typer.Typer(help="Manage the vault bundle (thesis files, transcripts).")
app.add_typer(vault_app, name="vault")

@vault_app.command("snapshot")
def vault_snapshot(
    drive: bool = typer.Option(False, "--drive", help="Pull from Google Drive for missing files."),
    live: bool = typer.Option(False, "--live"),
):
    """Freeze vault documents (theses, transcripts) to an immutable vault bundle."""
    # 1. Print DRY RUN / LIVE banner (same Rich pattern as snapshot).
    # 2. Discover ticker list from latest market bundle (if one exists).
    #    Sort bundles/context_bundle_*.json by mtime, load the latest,
    #    extract position tickers. If no market bundle exists, pass
    #    ticker_list=None and print a yellow warning.
    # 3. with console.status("Freezing vault..."):
    #        bundle = build_vault_bundle(ticker_list=tickers, include_drive=drive)
    #        path = write_vault_bundle(bundle)
    # 4. Print a Rich table:
    #    - Timestamp UTC
    #    - Vault Hash (bold green)
    #    - Vault Doc Count
    #    - Theses Present (count + list)
    #    - Theses Missing (yellow if > 0)
    #    - Skipped Files (yellow if > 0)
    #    - Bundle Path
    # 5. If vault_skip_log: print each entry in yellow.

@vault_app.command("add-thesis")
def vault_add_thesis(
    ticker: str = typer.Argument(..., help="Ticker symbol (e.g. UNH)"),
):
    """Scaffold a new _thesis.md file from template for a given ticker."""
    # 1. target = THESES_DIR / f"{ticker.upper()}_thesis.md"
    # 2. If target exists: print yellow warning and abort (never overwrite).
    # 3. Write the thesis template (hardcoded string — the template from the
    #    planning doc). Include all section headers.
    # 4. Print: "Created vault/theses/{ticker}_thesis.md — fill in the sections."


--- BUNDLE GROUP ---

bundle_app = typer.Typer(help="Build and inspect composite bundles.")
app.add_typer(bundle_app, name="bundle")

@bundle_app.command("composite")
def bundle_composite(
    market: Path | None = typer.Option(None, "--market", help="Explicit market bundle path."),
    vault: Path | None = typer.Option(None, "--vault", help="Explicit vault bundle path."),
    live: bool = typer.Option(False, "--live"),
):
    """Combine latest (or specified) market + vault bundles into a composite."""
    # 1. Print DRY RUN / LIVE banner.
    # 2. If market/vault not provided: call resolve_latest_bundles().
    #    Print which paths were resolved.
    # 3. with console.status("Building composite bundle..."):
    #        composite = build_composite_bundle(market_path, vault_path)
    #        path = write_composite_bundle(composite)
    # 4. Print a Rich table:
    #    - Timestamp UTC
    #    - Composite Hash (bold green)
    #    - Market Bundle Hash
    #    - Vault Bundle Hash
    #    - Positions
    #    - Vault Docs
    #    - Theses Missing (yellow if > 0)
    #    - Bundle Path

@bundle_app.command("verify")
def bundle_verify(
    path: Path = typer.Argument(..., help="Path to any bundle file to verify."),
):
    """Verify the hash of a market, vault, or composite bundle."""
    # Detect type by checking for 'composite_schema_version', 'vault_hash',
    # or 'bundle_hash' fields in the JSON. Call the appropriate load_ function.
    # Print: "✓ Hash verified: <hash>" or raise with clear message.

Do NOT:
- Modify the existing snapshot() subcommand
- Import streamlit
- Write to Google Sheets from any of these subcommands
```

---

## Prompt 5 of 5: Add vault smoke tests and update CHANGELOG.md

```text
1. Create tests/test_vault_bundle_smoke.py:

   """Smoke test for core/vault_bundle.py and core/composite_bundle.py."""
   import json
   from pathlib import Path
   import pytest

   from core.vault_bundle import (
       build_vault_bundle, write_vault_bundle, load_vault_bundle,
       THESES_DIR, VAULT_DIR,
   )
   from core.composite_bundle import (
       build_composite_bundle, write_composite_bundle, load_composite_bundle,
   )
   from core.bundle import build_bundle, write_bundle

   SAMPLE_CSV = Path("-Positions-2025-12-31-082029.csv")

   @pytest.fixture
   def sample_thesis(tmp_path, monkeypatch):
       """Write a minimal thesis file and point THESES_DIR at tmp."""
       theses = tmp_path / "theses"
       theses.mkdir()
       monkeypatch.setattr("core.vault_bundle.THESES_DIR", theses)
       monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path)
       (theses / "UNH_thesis.md").write_text(
           "# UNH — Investment Thesis\n\n"
           "## Style\nBoring Fundamentals\n\n"
           "## Scaling State\nnext_step: hold\n\n"
           "## Rotation Priority\npriority: medium\n"
       )
       return theses

   def test_vault_bundle_roundtrip(sample_thesis, tmp_path, monkeypatch):
       monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path)
       monkeypatch.setattr("core.vault_bundle.VAULT_DIR", tmp_path)
       monkeypatch.setattr("core.vault_bundle.TRANSCRIPTS_DIR", tmp_path / "transcripts")
       monkeypatch.setattr("core.vault_bundle.RESEARCH_DIR", tmp_path / "research")
       bundle = build_vault_bundle(ticker_list=["UNH", "GOOG"])
       assert len(bundle.vault_hash) == 64
       assert "UNH" in bundle.theses_present
       assert "GOOG" in bundle.theses_missing
       path = write_vault_bundle(bundle)
       loaded = load_vault_bundle(path)
       assert loaded["vault_hash"] == bundle.vault_hash

   def test_vault_hash_tamper_detection(sample_thesis, tmp_path, monkeypatch):
       monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path)
       monkeypatch.setattr("core.vault_bundle.VAULT_DIR", tmp_path)
       monkeypatch.setattr("core.vault_bundle.TRANSCRIPTS_DIR", tmp_path / "transcripts")
       monkeypatch.setattr("core.vault_bundle.RESEARCH_DIR", tmp_path / "research")
       bundle = build_vault_bundle(ticker_list=["UNH"])
       path = write_vault_bundle(bundle)
       data = json.loads(path.read_text())
       data["vault_doc_count"] = 999
       path.write_text(json.dumps(data, indent=2))
       with pytest.raises(ValueError, match="hash"):
           load_vault_bundle(path)

   def test_composite_bundle_roundtrip(sample_thesis, tmp_path, monkeypatch):
       if not SAMPLE_CSV.exists():
           pytest.skip("sample CSV not present")
       monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)
       monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path)
       monkeypatch.setattr("core.vault_bundle.VAULT_DIR", tmp_path)
       monkeypatch.setattr("core.vault_bundle.TRANSCRIPTS_DIR", tmp_path / "transcripts")
       monkeypatch.setattr("core.vault_bundle.RESEARCH_DIR", tmp_path / "research")
       monkeypatch.setattr("core.composite_bundle.COMPOSITE_BUNDLE_DIR", tmp_path)
       market = build_bundle(csv_path=SAMPLE_CSV, cash_manual=10000.0)
       market_path = write_bundle(market)
       vault = build_vault_bundle(ticker_list=["UNH"])
       vault_path = write_vault_bundle(vault)
       composite = build_composite_bundle(market_path, vault_path)
       assert len(composite.composite_hash) == 64
       comp_path = write_composite_bundle(composite)
       loaded = load_composite_bundle(comp_path)
       assert loaded["composite_hash"] == composite.composite_hash


2. Add a new entry to the TOP of CHANGELOG.md:

   ## [Unreleased] — CLI Migration Phase 2: Vault Bundling

   ### Added
   - `core/vault_bundle.py` — Immutable vault bundle: thesis files, transcripts,
     research notes. SHA256 content-hash (not Drive revision ID) for
     self-contained auditability. Missing thesis = warning, not failure.
   - `core/composite_bundle.py` — Composite bundle wrapper: combines
     market_hash + vault_hash into a single agent-ready artifact with one
     composite_hash. Sub-bundles are pointers, not merges.
   - `utils/gemini_client.py::ask_gemini_composite()` — Composite-bundle-aware
     Gemini call. Loads both sub-bundles, builds unified context preamble,
     filters thesis content by ticker. composite_hash propagates to all
     agent response metadata.
   - `manager.py vault snapshot` — Freeze vault docs to disk.
   - `manager.py vault add-thesis --ticker X` — Scaffold a new thesis file.
   - `manager.py bundle composite` — Build composite from latest sub-bundles.
   - `manager.py bundle verify <path>` — Verify any bundle hash.
   - `tests/test_vault_bundle_smoke.py` — Vault and composite round-trip tests.
   - `vault/` directory structure: theses/, transcripts/, research/

   ### Architecture Decision
   Content-hash (SHA256 of file bytes) chosen over Drive revision ID.
   Audit guarantee must be self-contained — verifiable at any future time
   without Drive API access. Drive fallback for missing files is stubbed
   (logs and continues); full Drive integration deferred to Phase 02b if needed.

   ### Unchanged
   - `manager.py snapshot` — market bundle, unmodified
   - `ask_gemini()` and `ask_gemini_bundled()` — unmodified
   - `app.py` — Streamlit app continues to run in parallel
```

---

## Post-Build Verification

```bash
# 1. Imports clean without streamlit
python -c "from core.vault_bundle import build_vault_bundle; print('OK')"
python -c "from core.composite_bundle import build_composite_bundle; print('OK')"
python -c "from utils.gemini_client import ask_gemini_composite; print('OK')"

# 2. New CLI subcommands appear in help
python manager.py --help
python manager.py vault --help
python manager.py bundle --help

# 3. Scaffold a test thesis
python manager.py vault add-thesis --ticker TEST
cat vault/theses/TEST_thesis.md

# 4. Build a vault bundle (dry run)
python manager.py vault snapshot

# 5. Build a composite bundle (requires a market bundle from Phase 01)
python manager.py snapshot --csv -Positions-2025-12-31-082029.csv --cash 10000
python manager.py vault snapshot
python manager.py bundle composite

# 6. Verify composite bundle
ls -lh bundles/composite_bundle_*.json
python manager.py bundle verify bundles/composite_bundle_$(ls -t bundles/composite_bundle_* | head -1 | xargs basename)

# 7. Run smoke tests
python -m pytest tests/test_vault_bundle_smoke.py -v
python -m pytest tests/ -v     # all tests, including Phase 01

# 8. Verify theses_missing is populated correctly (GOOG should appear since
#    no GOOG_thesis.md was created in the test run above)
python -c "
from pathlib import Path, import json
latest = sorted(Path('bundles').glob('vault_bundle_*.json'))[-1]
b = json.loads(latest.read_text())
print('Missing:', b['theses_missing'][:5])
print('Present:', b['theses_present'][:5])
"
```

## Gemini CLI Peer Review

After all prompts pass verification:

```bash
gemini -p "Review the CLI migration Phase 2 files: core/vault_bundle.py,
core/composite_bundle.py, and the additions to utils/gemini_client.py.
Check: 1) Are there any streamlit imports in any of these files (there
should be ZERO)? 2) Does vault_bundle.py use content-hash (SHA256 of file
text bytes) rather than any Drive API revision ID? 3) Does build_vault_bundle()
produce a synthetic VaultDocument entry (thesis_present=False) for each missing
ticker rather than raising or skipping silently? 4) Does composite_bundle.py
store sub-bundle paths as pointers rather than merging the JSON payloads?
5) Does ask_gemini_composite() populate bundle_hash with composite_hash (not
either sub-bundle hash) and overwrite any LLM-hallucinated value? 6) Is the
512KB per-file cap enforced before reading file content (not after)?
7) Does load_composite_bundle() verify the composite hash by recomputing from
stored market_hash and vault_hash (not by re-loading the sub-bundles)?
8) Does manager.py vault add-thesis abort without overwriting an existing file?"
```

---

## What This Unlocks (Not in This Build)

- **Phase 03: Re-Buy Analyst.** The composite bundle is now the input interface
  for all agents. Phase 03 ports the first agent onto this interface. The CLI
  gets: `python manager.py agent rebuy --ticker UNH --bundle latest`
- **Thesis backfill.** Now that `manager.py vault add-thesis` scaffolds files,
  the backfill is: run the command for each ticker, fill in the sections.
  50+ files; a focused weekend. Agent quality improves linearly with coverage.
- **Drive fallback (Phase 02b, optional).** If transcripts live in Drive and
  are too large/numerous to commit, implement the Drive fallback stub. Not
  required for Phase 03 to work.
