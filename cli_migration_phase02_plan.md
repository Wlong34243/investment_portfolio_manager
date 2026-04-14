# CLI Migration Phase 02 — Vault Bundling
## Planning Document

**Status:** Ready to build — pending Phase 01 green round-trip  
**Prerequisite:** `core/bundle.py` hash round-trip passing; `test_bundle_smoke.py` green; at least one `bundles/context_bundle_*.json` committed to repo  
**Target:** Claude Code or Gemini CLI  
**Output file:** `cli_migration_02_vault_bundle.md`

---

## What This Phase Does

Phase 01 froze the *quant* side of the portfolio: CSV positions, yfinance prices, manual cash. Every field in the market bundle is deterministic and numeric.

Phase 02 freezes the *unstructured* side: `_thesis.md` files, podcast transcripts, and any research notes sitting in Google Drive. These are the qualitative inputs agents need to reason about *why* a position is held — not just *what* it is worth.

The output of Phase 02 is two things:

1. **`core/vault_bundle.py`** — mirrors `core/bundle.py` in structure and discipline, but reads markdown files and Drive documents instead of CSVs and prices. Produces a `vault_bundle_<timestamp>_<hash>.json` with its own independent SHA256.

2. **`core/composite_bundle.py`** — a thin wrapper that combines `market_hash + vault_hash` into a single agent-ready bundle. Agents receive one composite bundle and one hash. They don't know (and don't care) that the data came from two sources.

---

## Design Decisions

### Decision 1: Content-hash, not Drive revision ID

Two options exist for hashing Drive documents:

| Option | Mechanism | Tradeoff |
|--------|-----------|----------|
| **Content hash** | SHA256 of the file's text bytes | Self-contained; stable at audit time without Drive API |
| **Drive revision ID** | Hash of the Drive API `revisionId` field | Lightweight; but requires Drive reachable at audit time |

**Decision: content-hash for V2.**

The audit guarantee is the point. If you're reviewing an agent output six months from now and asking "what thesis file did this agent see?", you want to be able to verify that with only the bundle JSON — no Drive API call required. Content-hash is self-contained and that property is worth the slightly larger bundle size.

Drive revision IDs are not stable identifiers for audit purposes because a revision can be deleted. Content bytes can always be recomputed from the archived bundle.

### Decision 2: Vault scope in V2

The vault bundle includes:

| Source | Location | Format |
|--------|----------|--------|
| Position thesis files | `vault/theses/<TICKER>_thesis.md` (local) or Drive folder | Markdown |
| Podcast transcripts | `vault/transcripts/` or Drive | Plain text / Markdown |
| Research notes | `vault/research/` or Drive (optional) | Markdown |

**V2 does NOT include:**
- Schwab transaction history (that's the market bundle's domain)
- Google Sheets tabs (those feed the market bundle via future Schwab API path)
- Any file larger than 512KB (logged as a skip, not a failure)

### Decision 3: Local-first vault path, Drive as fallback

The vault bundle reader checks `vault/` directory first (local markdown files), then falls back to Drive for files not found locally. This keeps the common case (thesis files you've already written locally) fast and offline-capable.

Drive credentials reuse the ADC path from `utils/sheet_readers.py`. No new auth surface.

### Decision 4: Composite bundle is a wrapper, not a merge

The composite bundle does NOT merge the two JSON blobs. It stores:

```json
{
  "composite_schema_version": "1.0.0",
  "composite_hash": "<sha256 of market_hash + vault_hash concatenated>",
  "market_bundle_hash": "<from market bundle>",
  "vault_bundle_hash": "<from vault bundle>",
  "market_bundle_path": "bundles/context_bundle_...",
  "vault_bundle_path": "bundles/vault_bundle_...",
  "timestamp_utc": "...",
  "position_count": 52,
  "vault_doc_count": 14
}
```

Agents receive the composite bundle path. `ask_gemini_bundled()` loads both sub-bundles and constructs the full context prompt. The `bundle_hash` field in every agent response schema is populated with `composite_hash`.

This design means either sub-bundle can be updated independently and the composite hash reflects the change. A market refresh (new CSV, new prices) without any thesis changes produces a new `market_hash` and a new `composite_hash`, but the `vault_hash` is unchanged — auditors can see exactly what changed.

### Decision 5: Missing thesis files are warnings, not failures

If a position has no `_thesis.md`, the vault bundler logs a warning and includes a placeholder:

```json
{
  "ticker": "CRWV",
  "thesis_present": false,
  "thesis_hash": null,
  "thesis_content": null,
  "warning": "No thesis file found. Run: manager.py vault add-thesis --ticker CRWV"
}
```

The bundle still builds. Agents downstream will note the missing thesis and reduce confidence accordingly — that's intentional behavior, not a failure mode.

---

## New CLI Subcommands (Phase 02 additions to manager.py)

```
python manager.py vault snapshot               # Build vault bundle from local vault/
python manager.py vault snapshot --drive       # Pull from Drive, then build
python manager.py vault add-thesis --ticker X  # Scaffold a new _thesis.md from template
python manager.py bundle composite             # Combine latest market + vault into composite
python manager.py bundle composite --market <path> --vault <path>  # Explicit paths
```

The `snapshot` subcommand from Phase 01 remains unchanged. These are additive.

---

## File Layout After Phase 02

```
repo root/
├── core/
│   ├── __init__.py
│   ├── bundle.py              ← Phase 01 (market bundle, unchanged)
│   ├── vault_bundle.py        ← NEW: vault bundle assembly
│   └── composite_bundle.py    ← NEW: composite wrapper
├── vault/
│   ├── theses/
│   │   ├── UNH_thesis.md
│   │   ├── GOOG_thesis.md
│   │   └── ... (one per position)
│   ├── transcripts/
│   │   └── ... (podcast transcripts)
│   └── research/
│       └── ... (optional ad-hoc notes)
├── bundles/
│   ├── context_bundle_<ts>_<hash>.json        ← market bundles
│   ├── vault_bundle_<ts>_<hash>.json          ← NEW: vault bundles
│   └── composite_bundle_<ts>_<hash>.json      ← NEW: composite bundles
├── manager.py                 ← extended with vault + bundle subcommands
└── tests/
    ├── test_bundle_smoke.py   ← Phase 01
    └── test_vault_bundle_smoke.py  ← NEW
```

`bundles/` remains gitignored. `vault/` is committed (thesis files are source-controlled).

---

## Thesis File Template

Each `_thesis.md` follows the template already specced in the agent kit. Required fields for the vault bundler to parse:

```markdown
# <TICKER> — Investment Thesis

## Style
<!-- One of: GARP-by-intuition | Thematic Specialist | Boring Fundamentals | Sector/Thematic ETF -->

## Core Thesis
<!-- Why you own it -->

## Scaling State
<!-- current_position: small / medium / full -->
<!-- last_action: [date] [bought/sold] [shares] -->
<!-- next_step: scale_in / hold / scale_out / exit_watch -->

## Rotation Priority
<!-- If forced to fund something else, this position is: low / medium / high priority to reduce -->

## Exit Conditions
<!-- What would change your mind -->

## Notes
<!-- Anything else -->
```

The vault bundler extracts `Style`, `Scaling State`, and `Rotation Priority` as structured fields. Everything else is included as raw markdown for agent context.

---

## Integration with ask_gemini_bundled()

Phase 01 added `ask_gemini_bundled(prompt, bundle_path, response_schema)`. Phase 02 extends it to accept a composite bundle path. The function detects whether the bundle is a composite (by checking `composite_schema_version` field) and loads both sub-bundles accordingly.

The bundle preamble injected into agent prompts gains a new section:

```
VAULT CONTEXT (immutable snapshot):
  vault_hash: <hash>
  vault_doc_count: 14
  theses_present: [UNH, GOOG, AMZN, ...]
  theses_missing: [CRWV, CORZ]    ← agents see this and factor it in
  thesis_for_<TICKER>: <full markdown content>
```

---

## Phase 02 → Phase 03 Interface Contract

Phase 03 (Re-buy Analyst) consumes the composite bundle. The contract it depends on:

| Field | Source | Required |
|-------|--------|----------|
| `composite_hash` | composite bundle | Yes — goes in agent response |
| `market_bundle.positions[].{ticker, price, value, weight_pct, cost_basis}` | market bundle | Yes |
| `vault_bundle.theses[].{ticker, style, scaling_state, rotation_priority, content}` | vault bundle | Yes (may be null if missing) |
| `vault_bundle.theses_missing[]` | vault bundle | Yes — agent uses for confidence scoring |

Phase 03 should not begin until a composite bundle round-trip has been manually verified:
```bash
python manager.py snapshot --csv <csv> --cash <n>
python manager.py vault snapshot
python manager.py bundle composite
# verify bundles/composite_bundle_*.json exists and hashes verify
```

---

## Sequencing Note

Per the architecture discussion that produced this plan: **do not write the Phase 02 implementation prompt until Phase 01 is fully green and committed.** The exact shape of `core/bundle.py` after any Phase 01 patches influences how `core/vault_bundle.py` composes with it.

This planning document is safe to commit now. The implementation prompt (`cli_migration_02_vault_bundle.md`) should be written *after* Phase 01 is landed and the bundle round-trip is verified against the real CSV.

---

## Risk Log

| Risk | Mitigation |
|------|-----------|
| Drive API latency makes vault snapshot slow | Local-first: check `vault/` before Drive. Most thesis files will be local. |
| Thesis files not yet written (backfill incomplete) | Missing thesis = warning, not failure. Bundle builds. Agent notes missing context. Backfill in parallel with Phase 05. |
| Large transcript files bloat bundle | 512KB per-file cap, logged as skip. Transcripts can be summarized before inclusion if needed. |
| Composite hash changes on every market refresh even if theses unchanged | By design — composite hash reflects both inputs. Vault hash stability is the signal that theses haven't changed. |
| `vault/` directory not yet created | `manager.py vault snapshot` creates it on first run with a Rich warning prompt. |
