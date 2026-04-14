# CLI Migration Phase 1 — The Immutable Data Spine
# Target: Claude Code or Gemini CLI 3 Pro
# Run prompts 1–5 sequentially. Each prompt is self-contained.

## Overview

We are freezing the Streamlit UI and the agent buildout to fix a critical data
provenance issue. We are moving to a headless Typer CLI architecture.

**The core problem:** Streamlit's rerun loop and `@st.cache_data` TTLs create
race conditions where AI agents are fed a mix of stale and live data. A
Pydantic-validated agent response can be semantically wrong because the prices
it analyzed were minutes out of sync with the holdings it analyzed. For a
CPA/CISA, every AI output must be traceable to the exact data snapshot it was
fed. That requires an immutable, hashed context bundle — which Streamlit's
execution model actively prevents.

**The fix:** Every CLI run freezes inputs to disk, computes a SHA256 hash of
the canonical serialization, and stamps that hash into every downstream agent
output. If a valuation ever looks wrong, the bundle JSON tells you exactly what
the agent saw.

## Key Design Decisions

1. **V1 is quant-only.** This phase freezes market state only: CSV holdings +
   yfinance prices + manual cash. Google Drive Vault files (thesis markdowns,
   transcripts) are deliberately excluded. The hash mechanism is the thing
   being validated here — minimize surface area. Vault freezing is V2 with its
   own composite-hash design.

2. **No Streamlit imports in any new CLI module.** The existing Streamlit app
   keeps running during the transition. `config.py` already degrades gracefully
   via `_secret()` when Streamlit is not installed, so `config` can be imported
   from the CLI without pulling in `streamlit`. Do not add new Streamlit
   dependencies to any file under `core/` or to `manager.py`.

3. **Bundles are immutable and content-addressed.** Once written, a bundle file
   is never modified. Filenames include both timestamp and hash so duplicates
   can be detected by filename alone. Hash is computed over a canonical JSON
   serialization with `sort_keys=True` and no whitespace drift.

4. **Environment versions are part of the bundle.** The bundle records Python
   version, yfinance version, pandas version, and a SHA256 of the source CSV
   file. This is belt-and-suspenders for audit — if an agent output looks off,
   you can distinguish "bad data" from "library upgrade changed something".

5. **Agents receive a bundle, not live data.** The refactored `ask_gemini()`
   wrapper takes a `bundle_path` (or loaded bundle dict) and injects the
   `bundle_hash` into the Pydantic response metadata automatically. Agents
   cannot accidentally fetch live data mid-prompt because the helper doesn't
   expose that path.

6. **DRY_RUN is preserved and made louder.** The CLI defaults to dry-run. A
   `--live` flag is required for any Sheet writes. When `--live` is active,
   Rich prints a red banner. The existing `config.DRY_RUN` gotcha (currently
   `False`) does not affect the CLI — the CLI has its own flag.

7. **Bundles directory is gitignored.** Bundles are local artifacts, not
   committed to the repo. Add `bundles/` to `.gitignore`.

---

## Pre-flight Checklist

Before running these prompts, confirm:
- [ ] `config.py` imports succeed without Streamlit installed:
      `python -c "import config; print(config.PORTFOLIO_SHEET_ID)"`
- [ ] `utils/gemini_client.py` exists with `ask_gemini()` signature:
      `ask_gemini(prompt, system_instruction=None, json_mode=False, max_tokens=2000, response_schema=None)`
- [ ] `SAFETY_PREAMBLE` is defined in `utils/gemini_client.py` (auto-prepended)
- [ ] Existing CSV parser module exists at `utils/csv_parser.py` (or wherever
      the working Colab V3.2 parse logic currently lives in the repo)
- [ ] `typer` and `rich` are available to install (they are small, pure-Python,
      zero compile risk)

---

## Prompt 1 of 5: Add CLI dependencies and gitignore entry

```text
Read requirements.txt and .gitignore fully before making changes.

1. Append the following to requirements.txt, preserving alphabetical order
   within the existing block. Do not remove or reorder any existing entries:

   typer>=0.12.0
   rich>=13.7.0

2. Append the following to .gitignore (create the file if it doesn't exist):

   # CLI bundle artifacts — immutable snapshots, regenerable, do not commit
   bundles/

3. Install locally:
   pip install typer rich

Verify:
   python -c "import typer, rich; print('OK')"
   grep -q "^bundles/" .gitignore && echo "gitignore OK"
```

---

## Prompt 2 of 5: Create core/bundle.py — the state freezer

```text
Read these files before writing code:
- config.py  (to understand the _secret() pattern and available constants)
- utils/csv_parser.py  (or the existing module containing the Colab V3.2
  parser — find it with: grep -rl "find_column_indices\|clean_numeric" .)
- pipeline.py  (to understand how holdings + yfinance enrichment currently flow)

Create a new directory core/ with an empty __init__.py.

Create: core/bundle.py

Module docstring:
    """
    Immutable context bundle — freezes market state to disk with a SHA256
    content hash. Every AI agent downstream receives a bundle path and stamps
    the hash into its output metadata, creating an auditable chain from
    input snapshot to agent conclusion.

    V1 scope: CSV holdings + yfinance enrichment + manual cash. Vault
    documents are NOT included in V1 — see cli_migration_02 for vault
    bundling.
    """

Imports (no streamlit anywhere):
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

Constants:
    BUNDLE_DIR = Path("bundles")
    BUNDLE_SCHEMA_VERSION = "1.0.0"

Define a dataclass:

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

Functions to implement:

1. _sha256_file(path: Path) -> str
   Stream-read the file in 64KB chunks and return hex digest.

2. _sha256_canonical(payload: dict) -> str
   json.dumps(payload, sort_keys=True, separators=(",", ":"),
              ensure_ascii=True, default=str).encode("utf-8")
   then hashlib.sha256(...).hexdigest()

3. _capture_environment() -> dict
   Returns dict with:
     - python: sys.version.split()[0]
     - platform: platform.platform()
     - pandas: pd.__version__
     - yfinance: yfinance.__version__
     - schema_version: BUNDLE_SCHEMA_VERSION

4. build_bundle(csv_path: Path, cash_manual: float) -> ContextBundle
   Steps:
     a. Read and parse CSV using the existing project parser. Import it;
        do not duplicate parsing logic.
     b. Enrich with yfinance: for each unique ticker (excluding CASH_MANUAL,
        QACDS), fetch last price. Use yfinance.Ticker(t).fast_info when
        possible for speed; fall back to history(period="1d") if fast_info
        fails. Wrap each fetch in try/except and log failures to the
        bundle as a field 'enrichment_errors: list[str]' (add this to the
        dataclass).
     c. Compute value = qty * price for each position, then weight_pct.
     d. Inject the synthetic CASH_MANUAL row with the provided cash_manual.
     e. Compute total_value and position_count.
     f. Build the payload dict with bundle_hash="" (placeholder).
     g. Compute bundle_hash = _sha256_canonical(payload_without_hash_field).
        IMPORTANT: Hash the payload with the bundle_hash field REMOVED,
        then insert the hash. Otherwise the hash would have to hash itself.
     h. Return the ContextBundle dataclass.

5. write_bundle(bundle: ContextBundle) -> Path
   Steps:
     a. BUNDLE_DIR.mkdir(exist_ok=True)
     b. Filename: f"context_bundle_{bundle.timestamp_utc.replace(':','')}"
                  f"_{bundle.bundle_hash[:12]}.json"
     c. Write JSON with indent=2 for human readability. (Readability copy;
        the hash was computed over the canonical form, not this one.)
     d. Return the path.

6. load_bundle(path: Path) -> dict
   Read, parse, and verify the hash matches. Recompute the canonical hash
   with bundle_hash removed and raise ValueError if mismatch. This is the
   audit verification entry point.

Return from this module:
    __all__ = ["ContextBundle", "build_bundle", "write_bundle", "load_bundle",
               "BUNDLE_DIR", "BUNDLE_SCHEMA_VERSION"]

Do NOT:
- Import streamlit anywhere
- Write to Google Sheets from this module
- Call any LLM from this module
- Duplicate the CSV parser logic — import it from utils/csv_parser.py
```

---

## Prompt 3 of 5: Create manager.py — the Typer CLI entry point

```text
Read these files before writing code:
- core/bundle.py  (the module from Prompt 2)
- config.py

Create: manager.py  (at the repo root, same level as app.py and pipeline.py)

Module docstring:
    """
    Investment Portfolio Manager — CLI entry point.

    Headless, auditable, linear execution. Every run freezes its inputs to
    an immutable bundle and exits. No reruns, no state leakage, no hidden
    caches.

    Usage:
        python manager.py snapshot --csv path/to/positions.csv --cash 10000
        python manager.py snapshot --csv path/to/positions.csv --cash 10000 --live

    Default is DRY RUN. --live is required for any downstream Sheet writes.
    The snapshot subcommand itself never writes to Sheets — it only produces
    the bundle. --live is plumbed through for future subcommands that do.
    """

Imports:
    from pathlib import Path
    import typer
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from core.bundle import build_bundle, write_bundle

    app = typer.Typer(help="Investment Portfolio Manager CLI", no_args_is_help=True)
    console = Console()

Implement the snapshot subcommand:

    @app.command()
    def snapshot(
        csv: Path = typer.Option(..., "--csv", help="Path to Schwab positions CSV",
                                 exists=True, file_okay=True, dir_okay=False,
                                 readable=True, resolve_path=True),
        cash: float = typer.Option(0.0, "--cash", help="Manual cash position (USD)"),
        live: bool = typer.Option(False, "--live",
                                  help="Enable live mode. Default is DRY RUN."),
    ):
        """Freeze current market state to an immutable context bundle."""

        # Banner
        if live:
            console.print(Panel.fit(
                "[bold white on red] LIVE MODE — Sheet writes enabled in downstream commands [/]",
                border_style="red",
            ))
        else:
            console.print(Panel.fit(
                "[bold black on yellow] DRY RUN — No Sheet writes. Use --live to enable. [/]",
                border_style="yellow",
            ))

        # Build
        with console.status("[cyan]Freezing market state..."):
            bundle = build_bundle(csv_path=csv, cash_manual=cash)
            path = write_bundle(bundle)

        # Summary table
        table = Table(title="Context Bundle", show_header=False, box=None)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_row("Timestamp (UTC)", bundle.timestamp_utc)
        table.add_row("Bundle Hash", f"[bold green]{bundle.bundle_hash}[/]")
        table.add_row("Positions", str(bundle.position_count))
        table.add_row("Total Value", f"${bundle.total_value:,.2f}")
        table.add_row("Cash (manual)", f"${bundle.cash_manual:,.2f}")
        table.add_row("Source CSV", str(csv.name))
        table.add_row("Source SHA256", bundle.source_csv_sha256[:16] + "...")
        table.add_row("Bundle Path", str(path))
        console.print(table)

        # Enrichment errors — visible, not silent
        if getattr(bundle, "enrichment_errors", None):
            console.print(f"\n[yellow]⚠ {len(bundle.enrichment_errors)} enrichment warning(s):[/]")
            for err in bundle.enrichment_errors[:10]:
                console.print(f"  [yellow]•[/] {err}")

    if __name__ == "__main__":
        app()

Do NOT:
- Add any streamlit imports
- Call ask_gemini or any agent from this file (agents come in Prompt 4)
- Write to Google Sheets from manager.py in V1
```

---

## Prompt 4 of 5: Refactor utils/gemini_client.py for bundle-based calls

```text
Read utils/gemini_client.py fully before making changes. Do NOT break the
existing ask_gemini() signature — the Streamlit app still depends on it.

Add a NEW function alongside the existing ask_gemini() — do not replace it.

New function:

    def ask_gemini_bundled(
        prompt: str,
        bundle_path: Path | str,
        response_schema: type[BaseModel],
        system_instruction: str | None = None,
        max_tokens: int = 2000,
    ) -> BaseModel | None:
        """
        Bundle-aware Gemini call. Loads an immutable context bundle, verifies
        its hash, injects the hash into the Pydantic response metadata, and
        returns the parsed model instance.

        The response_schema MUST include a `bundle_hash: str` field. This is
        enforced at call time — if the schema lacks the field, raise ValueError
        before the LLM is invoked.

        This function is the ONLY sanctioned path for CLI agents. The legacy
        ask_gemini() remains for the Streamlit app during the transition.
        """

Implementation steps:

1. Import: from core.bundle import load_bundle
2. Verify the response_schema has a 'bundle_hash' field:
       if "bundle_hash" not in response_schema.model_fields:
           raise ValueError(
               f"{response_schema.__name__} must include a 'bundle_hash: str' field "
               "to be used with ask_gemini_bundled()"
           )
3. bundle = load_bundle(Path(bundle_path))  # raises on hash mismatch
4. Build the full prompt by prepending a structured bundle preamble:
       bundle_preamble = (
           f"CONTEXT BUNDLE (immutable snapshot):\n"
           f"  bundle_hash: {bundle['bundle_hash']}\n"
           f"  timestamp_utc: {bundle['timestamp_utc']}\n"
           f"  total_value: {bundle['total_value']}\n"
           f"  position_count: {bundle['position_count']}\n"
           f"  positions: {json.dumps(bundle['positions'], default=str)}\n\n"
           f"You MUST include bundle_hash='{bundle['bundle_hash']}' in your "
           f"response. This is how the output is traced to its input snapshot.\n\n"
           f"USER PROMPT:\n{prompt}"
       )
5. Call the existing ask_gemini() with the built prompt and response_schema.
   SAFETY_PREAMBLE is still auto-prepended by ask_gemini() — do not duplicate.
6. After parsing, verify the returned model's bundle_hash matches
   bundle['bundle_hash']. If the LLM hallucinated a different hash, overwrite
   it with the correct one and log a warning. (Trust the file, not the LLM.)
7. Return the model instance.

Do NOT:
- Remove or modify the existing ask_gemini() function
- Import streamlit
- Change SAFETY_PREAMBLE handling
```

---

## Prompt 5 of 5: Update CHANGELOG.md and add a smoke test

```text
1. Add a new entry to the TOP of CHANGELOG.md (before any existing entries):

   ## [Unreleased] — CLI Migration Phase 1: Immutable Data Spine

   ### Added
   - `manager.py` — Typer CLI entry point with `snapshot` subcommand
   - `core/bundle.py` — Immutable context bundle with SHA256 content hashing
   - `core/__init__.py` — New CLI-only package (no Streamlit imports)
   - `utils/gemini_client.py::ask_gemini_bundled()` — Bundle-aware Gemini call
     with mandatory bundle_hash verification
   - `bundles/` directory (gitignored) for local bundle artifacts
   - `typer>=0.12.0` and `rich>=13.7.0` dependencies

   ### Architecture Decision
   Streamlit's rerun loop and cache TTLs create race conditions where AI
   agents receive a mix of stale and live data. To establish an auditable
   chain from input snapshot to agent conclusion, the CLI freezes all
   market state to a SHA256-hashed JSON bundle before any LLM call. Every
   agent response must include the bundle_hash in its Pydantic output,
   forcing permanent linkage between the snapshot and the conclusion
   drawn from it.

   V1 scope is quant-only (CSV + yfinance + manual cash). Google Drive
   Vault bundling is deferred to CLI Migration Phase 2 with a separate
   composite-hash design.

   ### Unchanged
   - The Streamlit app (`app.py`) continues to run during the transition
   - `ask_gemini()` legacy function preserved for existing Streamlit agents
   - `config.py`, Google Sheet schema, existing agents

   **Status:** CLI defaults to DRY RUN. `manager.py snapshot` produces
   bundles locally and does not touch Google Sheets. Safe to use in
   parallel with the existing Streamlit app.

2. Create a smoke test at tests/test_bundle_smoke.py (create tests/ if needed):

   """Smoke test for core/bundle.py hashing and round-trip integrity."""
   import json
   from pathlib import Path
   from core.bundle import build_bundle, write_bundle, load_bundle

   def test_bundle_roundtrip(tmp_path, monkeypatch):
       # Point BUNDLE_DIR at tmp_path
       monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)
       # Use the sample CSV in the repo root
       sample_csv = Path("-Positions-2025-12-31-082029.csv")
       if not sample_csv.exists():
           import pytest
           pytest.skip("sample CSV not present")
       bundle = build_bundle(csv_path=sample_csv, cash_manual=10000.0)
       assert len(bundle.bundle_hash) == 64
       assert bundle.position_count > 0
       assert bundle.total_value > 0
       path = write_bundle(bundle)
       assert path.exists()
       loaded = load_bundle(path)  # raises on hash mismatch
       assert loaded["bundle_hash"] == bundle.bundle_hash

   def test_bundle_hash_tamper_detection(tmp_path, monkeypatch):
       monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)
       sample_csv = Path("-Positions-2025-12-31-082029.csv")
       if not sample_csv.exists():
           import pytest
           pytest.skip("sample CSV not present")
       bundle = build_bundle(csv_path=sample_csv, cash_manual=10000.0)
       path = write_bundle(bundle)
       # Tamper: change total_value
       data = json.loads(path.read_text())
       data["total_value"] = 999999999.99
       path.write_text(json.dumps(data, indent=2))
       # load_bundle should raise
       import pytest
       with pytest.raises(ValueError, match="hash"):
           load_bundle(path)
```

---

## Post-Build Verification

```bash
# 1. Imports clean without streamlit
python -c "from core.bundle import build_bundle, load_bundle; print('OK')"
python -c "import manager; print('OK')"

# 2. CLI help works
python manager.py --help
python manager.py snapshot --help

# 3. Dry-run snapshot against the sample CSV
python manager.py snapshot --csv -Positions-2025-12-31-082029.csv --cash 10000

# 4. Verify a bundle was written
ls -lh bundles/

# 5. Verify hash round-trip
python -c "
from pathlib import Path
from core.bundle import load_bundle
latest = sorted(Path('bundles').glob('*.json'))[-1]
b = load_bundle(latest)
print(f'Loaded {latest.name}: hash={b[\"bundle_hash\"][:16]}..., positions={b[\"position_count\"]}')
"

# 6. Verify tamper detection
python -m pytest tests/test_bundle_smoke.py -v
```

## Gemini CLI Peer Review

After all prompts pass verification:

```bash
gemini -p "Review the CLI migration Phase 1 files: manager.py, core/bundle.py,
and the additions to utils/gemini_client.py. Check: 1) Are there any
streamlit imports in core/ or manager.py (there should be ZERO)? 2) Is the
bundle_hash computed BEFORE the hash field is inserted (otherwise it would
have to hash itself)? 3) Does load_bundle() actually raise on hash mismatch,
or does it silently pass? 4) Does ask_gemini_bundled() verify the schema has
a bundle_hash field BEFORE calling the LLM (wasted tokens if after)? 5) Is
the --live flag actually wired to anything in manager.py snapshot, or is it
just a stub for future subcommands (both are acceptable — confirm which)?
6) Does the bundle capture library versions so future library upgrades are
auditable?"
```

---

## What This Unlocks (Not in this build)

- **Phase 2: Vault bundling.** Freeze `_thesis.md` files and earnings
  transcripts into a companion bundle with its own hash. The agent-ready
  bundle becomes a composite of `market_hash + vault_hash`.
- **Phase 3: Port the first agent to the spine.** Re-Buy Analyst is the
  natural first candidate — it needs live prices AND thesis context, so it
  exercises the full bundle pipeline.
- **Phase 4: Schwab API ingestion.** Swap the CSV reader inside `build_bundle`
  for a Schwab REST call. The bundle interface does not change — only the
  source changes. This is the payoff: the spine is source-agnostic.
- **Phase 5: Retire app.py.** Once all agents are bundle-aware and the
  dashboard views can be satisfied by Google Sheets + optional Rich TUI,
  `app.py` and the Streamlit dependency come out of `requirements.txt`.
