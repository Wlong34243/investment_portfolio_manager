# CHANGELOG — Investment Portfolio Manager

## [Unreleased]

### Added
- **Idea Generator Agent (v1)**: New `pm agent ideas` command that consumes the composite bundle and recent podcast transcripts and writes a markdown report of investment candidates to `agent_outputs/ideas/`.
  - Pydantic schema: `Candidate` (ticker, company, style fit, portfolio relationship, concerns) + `IdeaGeneratorOutput` wrapper with `bundle_hash` traceability.
  - System prompt in `prompts/idea_generator.md` — style-aware, no price targets, no buy/sell recommendations.
  - Candidates sorted: new exposures first, then complements, then overlaps.
  - `--since-days N` to control transcript lookback window (default 7).
  - `--bundle-path` to override composite bundle (auto-detects latest if omitted).
  - `--dry-run` to print report to stdout without writing to disk.
- **`pm agent` CLI group**: New Typer group for AI agents. `agent ideas` is the first command under it.
- **`podcast_batch()` implementation**: The `pm ingest podcasts` / `pm podcast batch` function body was a stub. Fully implemented: iterates `PODCAST_CHANNELS` via YouTube RSS, checks dedup log, downloads transcripts via `fetch_transcript_to_file()`, reports per-channel status with Rich output.

### Changed
- **`config.py` — Gemini model**: Default `GEMINI_MODEL` corrected from `gemini-3.1-pro-preview-customtools` (invalid, 404 on this project) to `gemini-2.5-flash` (confirmed accessible).
- **`utils/agents/idea_generator.py` — transcript directory**: Reads from `data/podcast_transcripts/` (where `podcast_fetcher.py` writes `.txt` files) instead of `vault/transcripts/` (which holds vault `.md` docs — a different purpose).

### Fixed
- **`pm ingest podcasts` silent exit**: Command printed "Checking channels..." and immediately returned because `podcast_batch()` had no implementation. Now runs the full RSS → dedup → download loop.

---

## [Prior]

### Added
- **0_DASHBOARD Command Center**: Single-screen daily view aggregating headline KPIs, tax posture, risk snapshot, top 5 positions (with trim/add target distances), drift alerts, and system health. Built by `tasks/build_command_center.py` and refreshed automatically as part of `pm refresh dashboard` and `pm morning`.
- **Unified Ingestion Workflow**: Introduced `pm ingest` group to centralize all data pull operations.
  - `pm ingest transactions`: Syncs Schwab transaction history (aliased from `pm sync transactions`).
  - `pm ingest realized-gl`: Imports Schwab Realized G/L CSV (aliased from `pm sync realized-gl`).
  - `pm ingest podcasts`: Fetches latest transcripts and runs optional AI analysis.
  - `pm ingest all`: Orchestrated command to run transactions and podcast updates in sequence.
- **Centralized Hygiene**: Introduced `pm clean` group for filesystem maintenance.
  - `pm clean exports`: Deletes old LLM context packages.
  - `pm clean podcasts`: Deletes old transcript files.
  - `pm clean bundles`: Deletes old market/vault/composite JSON bundles.
  - `pm clean all`: Runs all cleanup tasks using shared retention windows.
- **Consistent View Refresh**: introduced `pm refresh` group for rebuilding computed Sheet views.
  - `pm refresh dashboard`: Rebuilds Valuation_Card and Decision_View (aliased from `pm dashboard refresh`).
  - `pm refresh tax`: Rebuilds Tax_Control KPIs and lots (aliased from `pm tax refresh`).
  - `pm refresh rotations`: Rebuilds Rotation_Review attribution (aliased from `pm trade review`).
- **Shared Retention Constants**: Defined default purge windows in `config.py`:
  - `PURGE_DEFAULT_DAYS_PODCASTS = 30`
  - `PURGE_DEFAULT_DAYS_BUNDLES = 30`
  - `PURGE_DEFAULT_DAYS_EXPORTS = 7`
- **Session Purge Flag**: Added `--purge` flag to all `pm ingest` commands, allowing for "fresh start" hygiene automatically after data ingestion.

### Changed
- **CLI Architecture**: Major reorganization of `manager.py` to consolidate Typer app definitions at the module level. This resolves decorator dependency issues and supports cleaner command aliasing.
- **Deprecation Aliases**: Existing commands (`sync`, `tax`, `dashboard`, `trade review`) are preserved as hidden aliases to maintain compatibility with existing scripts.
- **CLI Docs**: Updated `CLAUDE.md` and `portfolio_manager_user_docs.html` to reflect the new workflow-oriented surface.

### Fixed
- **`tasks/sync_transactions.py`**: Fixed `UnboundLocalError` in the dry-run path when no new transactions were found. (Note: This bug only affected dry-runs and did not impact `pm morning --live` runs).
