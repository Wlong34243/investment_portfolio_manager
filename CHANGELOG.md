# Changelog

## [Unreleased] — CLI Migration Phase 4: Schwab API as Bundle Data Source

### Added
- `core/bundle.py` — pluggable data sources via `source` parameter (`schwab` | `csv` | `auto`).
- `_build_from_schwab()` helper that calls the existing `utils/schwab_client.fetch_positions()` and wraps it in the same bundle contract as the CSV path.
- `_build_from_csv()` helper — refactor of the Phase 1b CSV logic into a named helper with a stable return signature.
- `manager.py snapshot --source` flag with 'auto' as the new default; `--csv` is now optional.
- Five new smoke tests covering invalid source, required csv_path, auto fallback, auto failure without fallback, and Schwab path data_source propagation.
- ContextBundle fields: `data_source`, `data_source_fingerprint`, `tax_treatment_available`.
- Per-position `tax_treatment` field (populated on Schwab path, "unknown" on CSV path).
- `price_source` vocabulary extended to include "schwab_quote".

### Architecture Decision
The Schwab API integration was already complete (Phase 5-S, April 2026). Phase 4's actual work was WIRING that existing client into the CLI bundle pipeline, not rebuilding it. `core/bundle.py` now dispatches on a `source` parameter and calls either `_build_from_schwab()` or `_build_from_csv()`, producing the same ContextBundle shape either way. Agents downstream see no difference — they consume the bundle, not the source.

`auto` mode is the new default: it tries Schwab first and falls back to CSV if Schwab fails, emitting a loud enrichment_error recording the fallback. `auto` mode raises if Schwab fails AND no csv_path was provided.

The zero-price yfinance fallback from the 2026-04-10 bug patch is now inside `_build_from_schwab()` rather than `app.py`, so the CLI benefits from the same fix.

The existing Schwab client module, token store, Cloud Function, and OAuth setup are UNCHANGED. Phase 4 is pure integration work.

### Unchanged
- `utils/schwab_client.py`, `utils/schwab_token_store.py`
- `cloud_functions/token_refresh/`
- `scripts/schwab_initial_auth.py`, `scripts/schwab_manual_reauth.py`
- All Phase 1-3c bundle, vault, composite, and agent logic
- The Streamlit app (still runs in parallel; Phase 7 retires it)

**Status:** `manager.py snapshot` defaults to --source auto. Schwab is the primary data path; CSV is retained for disaster recovery and explicit fallback. All Phase 3+ agents work unchanged against Schwab-sourced bundles.

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
- **Qualitative Backfill**: Created 51 investment theses (`_thesis.md` files) across core positions, ETFs, and speculative satellites to enable agent reasoning.

### Architecture Decision
Content-hash (SHA256 of file bytes) chosen over Drive revision ID.
Audit guarantee must be self-contained — verifiable at any future time
without Drive API access. Drive fallback for missing files is stubbed
(logs and continues); full Drive integration deferred to Phase 02b if needed.

### Unchanged
- `manager.py snapshot` — market bundle, unmodified
- `ask_gemini()` and `ask_gemini_bundled()` — unmodified
- `app.py` — Streamlit app continues to run in parallel

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

---

## [2026-04-12] — ADC Auth Migration

### Changed
- `utils/gemini_client.py` — Gemini client now uses Application Default
  Credentials (ADC) as the primary auth path. API key fallback preserved for
  Streamlit Cloud. No code changes needed after `gcloud auth application-default
  login` — same credential used by Gemini CLI.
- `utils/sheet_readers.py` — `get_gspread_client()` resolution chain updated:
  ADC first (local CLI), then GCP_SERVICE_ACCOUNT_JSON env var (GitHub Actions),
  then Streamlit secrets, then local service_account.json file. All existing
  paths preserved.
- `config.py` — `GEMINI_MODEL` default updated to `gemini-2.5-pro` (Vertex AI
  accessible). Override via Streamlit secret `gemini_model` if needed.

### Infrastructure
- Enabled Vertex AI API (`aiplatform.googleapis.com`) on GCP project
  `re-property-manager-487122`.

### Architecture Note
Local CLI agent runs now share auth with Gemini CLI. No API keys in environment
variables, no JSON files on disk. One-time setup:
`gcloud auth application-default login && gcloud auth application-default set-quota-project re-property-manager-487122`

**Status:** Safe to deploy. ADC path fails gracefully to next option — Streamlit
Cloud behavior unchanged.

---

## [2026-04-10] — Phase 5-S: Post-Integration Bug Fixes

### fix: Portfolio total, prices, descriptions, and valuation accuracy

**Cash from all accounts:**
- `fetch_positions()` now reads `currentBalances.cashBalance` from every account and appends a single `CASH_MANUAL` row. Previously, all CASH_EQUIVALENT positions were silently skipped, leaving ~$49K in cash invisible and Total Portfolio ~$52K below Schwab's reported total.

**Price showing as $0.00:**
- Quote enrichment in `app.py` was overwriting Schwab account-snapshot prices with `last_price = 0` when the Market Data API returned 0 (common outside market hours). Fixed mask: only overwrite when `last_price > 0`.
- Research Hub: added yfinance `fast_info` live-price fallback for any ticker where holdings price is still 0.

**Descriptions incomplete:**
- `enrich_positions()` previously only ran name lookups for the top 20 positions by market value. Added a second yfinance bulk pass for all remaining invested tickers that have empty descriptions. Absolute fallback: ticker symbol used if yfinance also returns nothing.

**AVGO / Valuation always showing 0% discount:**
- `get_valuation_snapshot()` now detects FMP 402 (subscription limit). When `hist_pe` is empty, `avg_5yr_pe`, `pe_discount_pct`, and `is_below_average` are set to `None` rather than using `current_pe` as both sides of the comparison.
- Gemini prompt updated to evaluate on absolute sector-norm basis when historical data is unavailable.
- Research Hub signal updated: shows "Historical P/E unavailable — FMP subscription required" instead of the misleading "trading above historical average."

**Performance period returns:**
- Historical snapshots scaled by `live_total / last_snapshot_total` when ratio > 5%, correcting for the period when only 1 account was tracked.

**Tax page — G/L disclaimer:**
- Added caption noting that Realized G/L only reflects manually imported CSVs and may not include HSA/401k/IRA/custodial activity.

**Status: All 5 accounts loading, total matches Schwab (~$545K), prices correct, descriptions populated.**

---

## [2026-04-09] — Phase 5-S: Schwab API Integration

### feat: Automated position, transaction, and quote pulls via Schwab API

**What changed:**
- `utils/schwab_client.py` — read-only Schwab API client (positions,
  balances, transactions, quotes); two scoped factory functions for
  the Accounts and Market Data apps
- `utils/schwab_token_store.py` — GCS-backed OAuth token persistence
  plus alert read/write/clear helpers
- `cloud_functions/token_refresh/` — Cloud Function keep-alive that
  refreshes both tokens every 25 min, 24/7; Gmail escalation after
  2+ consecutive failures
- `scripts/schwab_initial_auth.py` — one-time browser OAuth setup for
  both apps; uploads tokens to GCS and prints account hashes
- `scripts/schwab_manual_reauth.py` — emergency token recovery
- `app.py` sidebar — Schwab API as the primary data source with CSV
  upload as the explicit fallback; manual refresh button included

**Architecture:**
- Two Schwab apps, two GCS-stored tokens, one keep-alive Cloud Function
- Market Data client physically cannot reach account endpoints (separate
  app key, separate token, separate client object)
- DRY_RUN safety gate unchanged — still gates all Sheet writes
- Graceful degradation to CSV on any Schwab API failure

**Bug fixes during integration:**
- `client_from_access_functions` called with spurious `callback_url` arg — removed
- `token_saver` needed `**kwargs` to accept `refresh_token` kwarg from schwab-py
- `fetch_positions` returned Title Case columns — fixed to snake_case to match pipeline convention
- `unrealized_gl` returned as int64 — coerced to float64 for pipeline consistency

**Status:** Live API confirmed — 43 positions fetched, weights sum to 100.0. UI wiring pending (P5-S-C).
# Changelog

## [2026-04-09] — Phase 5-S: Schwab API Integration (Scaffolding)

### Added
- **🤖 Schwab API Clients:** Created `utils/schwab_client.py` with two scoped clients (Accounts vs. Market Data) to ensure physical isolation of sensitive data.
- **🔐 Token Persistence:** Created `utils/schwab_token_store.py` to handle OAuth token storage in Google Cloud Storage (GCS) with local fallback for development.
- **🔄 Token Keep-Alive:** Created `cloud_functions/token_refresh/` (Python Cloud Function) to automatically refresh Schwab tokens every 25 minutes, preventing 7-day expiry.
- **🛠️ Auth Utility Scripts:** Added `scripts/schwab_initial_auth.py` for one-time browser OAuth setup and `scripts/schwab_manual_reauth.py` for emergency recovery.
- **🚦 API Status Indicators:** Added `is_api_available()` and `read_alert()` helpers to monitor connectivity and surface Schwab maintenance/auth alerts in the UI.

### Fixed
- **☁️ Streamlit Cloud Pathing:** Switched to `sys.executable` for all internal subprocess calls in `tasks/stax_sync.py` and `tasks/weekly_podcast_sync.py`, resolving `ModuleNotFoundError` during remote execution.
- **📦 Missing Imports:** Fixed a crash on the Rebalancing page caused by a missing `import datetime.date`.

## [Unreleased] — Cash Aggregation Fix

### Fixed
- **Cash Normalization:** Fixed a bug in the Rebalancing page where cash-sweep tickers (like `QACDS`) were not being aggregated into the "Cash" category. The logic now robustly identifies cash by both Asset Class and Ticker before grouping.

## [Unreleased] — STAX Market Intelligence Ingestion

### Added
- **📊 STAX Integration:** Added a new "Ingest STAX Report" UI to the Rebalancing page. Users can now paste raw text from Schwab's Trading Activity Index (STAX) reports for instant Gemini-driven sector rotation analysis.
- **Backend Orchestrator:** Created `tasks/stax_sync.py` to handle raw text analysis, schema validation, and "clear-and-replace" writing to the `AI_Suggested_Allocation` tab.
- **Assertive Signal Derivation:** Enhanced the podcast agent to more assertively derive sector signals (Overweight/Underweight) from raw STAX report text, improving rebalancing suggestions.

### Fixed
- **Parser Flexibility:** Updated the strategy JSON parser to handle multiple schemas (e.g., `allocations` vs `target_allocations`) and nested metadata, fixing a `KeyError` when importing STAX-formatted JSON.

## [Unreleased] — Sidebar UI Restoration

### Fixed
- **Missing Uploaders:** Restored the "Realized G/L" and "Transactions" file uploaders in the sidebar. These were accidentally removed during the Risk tab overhaul.
- **CSV Processing:** Restored the ingestion logic for Gains and Transactions in the main processing loop.

## [Unreleased] — Risk Refinements: Beta Dilution & Heatmap UX

### Added
- **🔥 On-Demand Heatmap:** Added a "Generate Correlation Heatmap" button to the Risk tab. This allows users to view persistent beta/stress results instantly while deferring heavy data downloads until needed.
- **Improved Stress Matrix:** Added "Total New Value" column to stress tests, showing the projected total portfolio balance (Cash + Invested) for each scenario.

### Changed
- **Beta Dilution (Cash Handling):** Updated `calculate_portfolio_beta` to properly dilute risk based on the **Total Portfolio Value**. Cash positions are now explicitly beta-zeroed, ensuring stress tests accurately reflect high cash buffers.
- **Import Hardening:** Fixed missing imports (`streamlit`, `typing`) in `utils/risk.py` that caused runtime NameErrors.

## [Unreleased] — Risk Persistence & Beta Hardening

### Added
- **Risk Persistence:** Added `write_risk_metrics` to the pipeline. Deep risk results (Beta, stress impacts, concentration) are now saved to the `Risk_Metrics` tab in Google Sheets.
- **Auto-Load Analytics:** The Risk tab now automatically restores the latest metrics from the Sheet on app startup, eliminating the need to re-run scans on every refresh.

### Changed
- **Authority Beta Chain:** Upgraded `utils/risk.py` to use a multi-source fallback: `yfinance` info -> 1yr Covariance -> Default 1.0.
- **Performance:** Implemented `st.cache_data` for price history downloads and beta lookups to reduce API latency and prevent rate-limiting.
- **UI State Management:** Integrated `get_risk_metrics` into the main dashboard initialization to ensure session persistence.

## [Unreleased] — Rebalancing UI Overhaul

### Added
- **Triple-Source Comparative Matrix:** Rewrote the core rebalancing logic to perform a "grand merge" of Current Holdings, Manual Targets, and AI Suggested Allocations using a unified `Asset Class` key.
- **AI Delta Analysis:** Added automated calculations for `AI Delta %`, showing the variance between manual targets and AI podcast recommendations.
- **Grouped Visualization:** Integrated a new Plotly bar chart comparing Actual, Target, and AI allocations side-by-side.

### Changed
- **Matrix UI:** Enhanced the data table with `st.column_config` for professional percentage formatting and included `Asset Strategy` and `AI Notes` for thesis-driven rebalancing.
- **Robustness:** Added defensive type-casting for all percentage columns and explicit error handling for empty sheet states.

## [Unreleased] — UI Strategy Import & Rebalancing Consolidation

### Added
- **Offline Strategy Import:** Added drag-and-drop JSON uploader to the Rebalancing page. Users can now import strategies from Claude/ChatGPT and execute the sync pipeline (`weekly_podcast_sync.py`) directly from the UI.
- **Consolidated Drift Engine:** Moved the robust `_compute_drift` logic into a central `calculate_drift` function in `tax_intelligence_agent.py`.
- **Hardened Cash Logic:** Rebalancing and drift calculations now use a dual-check (Asset Class + Ticker) to identify cash, bypassing the unreliable `Is Cash` sheet column.

### Changed
- **Code Cleanup:** Removed the redundant `_compute_drift` function from `pages/1_Rebalancing.py` and synchronized diagnostic debug tools.
- **DRY Data Flow:** Removed the duplicate `get_target_allocation` reader from the agent module; it now uses the standard reader from `utils/sheet_readers.py`.

## [Unreleased] — Risk & Signals Tab Wiring

### Added
- **🛡️ Risk Analytics Tab:** Wired up dormant logic for Portfolio Beta, Correlation Heatmaps, Stress Testing, and CAPM Expected Returns.
- **🔔 Signals Tab:** Consolidated Macro Monitor (FRED/YFinance), Earnings Sentinel (FMP), and Daily Price Narrator into a single real-time intelligence hub.
- **Agent Activation:** Fully wired 5 "ghost" agents into the UI: `cash_sweeper`, `concentration_hedger`, `correlation_optimizer`, `earnings_sentinel`, and `macro_monitor`.
- **Diversification Advisor:** Integrated AI suggestions for reducing high-correlation pairs and managing single-position concentration.

### Changed
- **`app.py` Architecture:** Refined the main dashboard tab structure to support the new Risk and Signals hubs.
- **`chat_engine.py`:** Updated the AI Advisor's navigation rules to correctly direct users to the new Risk and Signals tabs.

### Removed
- `utils/smart_enrichment.py` — Redundant CLI-only script (functionality merged into `portfolio_enricher.py`).

## [Unreleased] — Scheduled Podcast Automation

### Added
- `tasks/batch_podcast_sync.py` — Batch orchestrator: YouTube RSS → episode detection
  → dedup check → calls `weekly_podcast_sync.py` for new episodes
- `.github/workflows/podcast_sync.yml` — GitHub Actions cron: runs every Friday at
  5:00 PM EST, commits dedup log back to repo
- `data/processed_videos.json` — Dedup log tracking which video IDs have been processed
- GCP credential resolution chain in `utils/sheet_readers.py`: env var → Streamlit
  secrets → local file (enables GitHub Actions without Streamlit)

### Architecture Decision
Batch orchestrator shells out to `weekly_podcast_sync.py` via subprocess rather than
importing internals. This keeps the single-video CLI usable for ad-hoc runs and the
batch script focused on episode detection + dedup. Last podcast processed wins the
AI_Suggested_Allocation tab (clear-and-replace pattern). Multi-podcast consensus is
a future enhancement.

**Status:** Dry-run by default. GitHub Actions workflow passes --live explicitly.


## [2026-04-06] — Is Cash Column Anti-Pattern Fix

### fix: Cash Balance = Total Portfolio on Main Dashboard / 100% Cash on Rebalancing Page
**Root Cause:** `Is Cash` column is written correctly during CSV ingestion but becomes `True` for all rows when read back from Google Sheets via `ws.get_all_values()`. Any code using `df['Is Cash'].astype(bool)` or `df['Is Cash'] == True` was silently treating every holding as cash.

**Symptoms observed:**
- Main Dashboard: Total Portfolio == Cash Balance, Invested = $0
- Rebalancing page: All drift Actual % = 0% except Cash = 100%
- Cash Sweeper: Permanently triggered (all assets appeared idle)
- Options Agent: Zero covered call candidates

**What changed:**
- **`app.py`** — `cash_mask` in Holdings tab now uses `Asset Class == 'cash'` + `Ticker.isin(CASH_TICKERS)` instead of `Is Cash.astype(bool)`
- **`pipeline.py`** — Both `calculate_income_metrics()` cash filters updated (x2)
- **`utils/agents/cash_sweeper.py`** — `get_cash_sweep_alert()` and `analyze_cash_position()` updated (x2)
- **`utils/agents/options_agent.py`** — `find_covered_call_candidates()` cash exclusion updated
- **`pages/1_Rebalancing.py`** — `_compute_drift()` already fixed; `Is Cash` column not referenced

**Rule going forward:** Never use `Is Cash` for filtering in display/agent code. Use `Asset Class.str.lower() == 'cash'` and `Ticker.isin(CASH_TICKERS)`. Documented in `lessonsLearned.md` §4.

**Status: Production ready. Pushed to main.**



## [Unreleased] — Smart Category Enrichment

### Added
- `utils/agents/portfolio_enricher.py` — Gemini-powered ticker categorization agent
  (Asset Class + Sector/Strategy via GICS taxonomy). Produces `data/ticker_mapping.json`.
  Includes `enrich_holdings_from_df()` for direct DataFrame use from the Streamlit UI.
- `utils/smart_enrichment.py` — Earlier standalone draft of the enrichment script (CLI only)
- `apply_smart_categorization()` in `utils/enrichment.py` — reads `ticker_mapping.json`
  and overwrites `asset_class`/`asset_strategy` columns; no-ops gracefully if file absent

### Changed
- `utils/csv_parser.py` — Added lazy-import hook to `apply_smart_categorization()` in
  `parse_schwab_csv()`. Runs after `get_sector_fast()` baseline so Gemini categories
  override "Other" before data reaches Google Sheets. Lazy import avoids circular
  dependency (enrichment.py imports get_sector_fast from csv_parser.py).
- `app.py` — Added "AI Category Enrichment" expander to sidebar. "Run Enrichment"
  button calls `enrich_holdings_from_df()` against current session holdings, writes
  mapping JSON, toasts on success. Button disabled until a CSV is imported.

### Architecture Note
Enrichment is a two-step process: (1) click "Run Enrichment" in sidebar to regenerate
`data/ticker_mapping.json` whenever holdings change; (2) next CSV import automatically
applies the mapping via the hook in `parse_schwab_csv()`.

**Status:** Safe to deploy. Enrichment is opt-in (button-triggered). Missing mapping
file is handled gracefully — pipeline never blocked.

## [Unreleased] — Podcast Pipeline + Decision Journal

### Added
- `utils/agents/podcast_analyst.py` — Gemini-powered podcast transcript analyzer
  with Pydantic schema (PodcastStrategy, SectorTarget)
- `tasks/weekly_podcast_sync.py` — CLI: YouTube transcript -> Gemini -> AI_Suggested_Allocation tab
- `AI_Suggested_Allocation` tab in Portfolio Sheet — AI suggestions kept separate from
  Bill's manual Target_Allocation
- `Decision_Log` tab in Portfolio Sheet — Investor memory layer for trade rationales
- `pages/7_Journal.py` — Decision Journal UI with auto-fetched SPY context
- `append_decision_log()` in pipeline.py — DRY_RUN-gated append to Decision_Log
- `youtube-transcript-api` dependency

### Changed
- `config.py` — Added TAB_AI_SUGGESTED_ALLOCATION, AI_SUGGESTED_ALLOCATION_COLUMNS,
  AI_SUGGESTED_ALLOCATION_COL_MAP, TAB_DECISION_LOG, DECISION_LOG_COLUMNS
- `create_portfolio_sheet.py` — Added AI_Suggested_Allocation and Decision_Log to
  SCHEMA and TABS_TO_FREEZE
- `PORTFOLIO_SHEET_SCHEMA.md` — Documented AI_Suggested_Allocation and Decision_Log
  tab schemas and fingerprints
- `app.py` — Added Decision Journal page to st.navigation

### Architecture Decisions
1. AI suggestions write to AI_Suggested_Allocation (new tab), never to Target_Allocation.
   Target_Allocation remains Bill's manual-only authoritative allocation.
2. Decision_Log is append-only via the Journal UI. Captures the "why" behind trades
   for year-end review, behavioral pattern analysis, and future AI agent context.

**Status:** Podcast script defaults to DRY RUN (--live flag required). Decision Journal
respects config.DRY_RUN. Safe to deploy.

Every entry must include a **Status** line describing what is currently safe to run.

## [2026-04-05] — Dashboard Architecture Fix & Tax Intelligence Repair

### fix: Main Dashboard Not Rendering on Load
**What changed:**
- **`app.py` — Navigation Architecture:** Moved all dashboard rendering (title, KPI metrics, treemap, holdings table, income tab) from module-level code into a dedicated `def main_dashboard()` function. `st.navigation` now references `main_dashboard` directly instead of `lambda: None`, so dashboard content no longer prepends every other page.
- **Deprecated API Cleanup:** Replaced `use_container_width=True` with `width='stretch'` in `st.plotly_chart` and `st.dataframe` calls to eliminate deprecation warnings on Streamlit 1.55.0+.

### fix: Tax Intelligence Page — TypeError on Unrealized G/L Comparison
**What changed:**
- **`utils/agents/tax_intelligence_agent.py` — `scan_harvest_opportunities()`:** Added explicit `pd.to_numeric(..., errors='coerce').fillna(0.0)` cast on the `Unrealized G/L` column before the `<= -min_loss_dollars` comparison. Prevents `TypeError: '<=' not supported between instances of 'str' and 'float'` when data is read back from Google Sheets as mixed string/float types.

**Status: Production ready. All 7 pages verified — Main Dashboard, Rebalancing, Research Hub, Performance, Tax Intelligence, Unified Net Worth, and AI Advisor all render without errors.**

## [2026-04-05] — Final Stability & Header Hardening

### fix: Empty Header & Ticker Coercion
**What changed:**
- **Robust Header Mapping:** Updated `utils/sheet_readers.py` to specifically detect when the first column in Google Sheets has an empty header (becoming `Unnamed_0`). It now re-maps this to `Ticker` immediately.
- **Coercion Protection:** Added protection to ensure that ticker symbols (strings) are never accidentally converted to numeric `0.0` during the data cleaning process, even if the header is temporarily missing.
- **Pipeline Precision:** Verified that `pipeline.py` explicitly writes the correct `Ticker` header to prevent future "unnamed" column issues.

**Status: Production ready. All identified root causes for KeyError: 'Ticker' have been resolved and hardened.**

## [2026-04-05] — Research Hub Stability & Syntax Audit

### fix: Syntax & Runtime Crashes
**What changed:**
- **App Syntax Audit:** Resolved a `SyntaxError` in `app.py` (unmatched brackets) that was preventing the main dashboard from loading.
- **Hardened Research Hub:** Updated `pages/2_Research.py` with defensive checks to prevent `IndexError` when retrieving ticker data and ensured robust handling of missing `Ticker` columns.
- **Encoding Safety:** Re-saved core files with UTF-8 encoding to prevent character corruption in production environments.

**Status: Production ready. All pages verified for syntax and runtime stability.**

## [2026-04-05] — Performance Accuracy & Data Recovery

### fix: KeyError 'Ticker' & Data Integrity
**What changed:**
- **Robust Column Guard:** Updated `utils/column_guard.py` to handle cases where the first column header in Google Sheets is empty (becoming `Unnamed_0`). It now automatically re-maps these to `Ticker`.
- **Guaranteed Schema:** The column guard now explicitly ensures that all 20 required columns (including `Ticker` and `Unrealized G/L`) exist in the DataFrame, preventing `KeyError` crashes throughout the app.
- **Fail-Safe Research Hub:** Added an explicit column check in `pages/2_Research.py` to provide a clean error message rather than a traceback if data integrity issues occur.

### feat: System Maintenance Tools
**What changed:**
- **Cache Clearing:** Added a "🧹 Clear System Cache" button to the sidebar. This allows users to manually force a refresh of both Streamlit's data cache and the browser session state, which is useful for resolving persistent data glitches or stuck API calls.
- **Improved Sidebar Layout:** Refined the sidebar organization to prioritize high-value status metrics and maintenance tools.

**Status: Production ready. Data integrity is hardened against empty sheet headers. User-driven cache clearing is live.**

## [2026-04-05] — Final Stability & Hardening

### fix: Architectural Hardening & Logic Isolation
**What changed:**
- **Dashboard Isolation:** Fully encapsulated the main dashboard UI into `main_dashboard()` to prevent "global scope leakage" where holdings logic would appear on sub-pages.
- **Systematic Type Safety:** Hardened the `Cash Sweeper` agent against mixed string/float data from Google Sheets, preventing comparison crashes.
- **Automated Verification:** Implemented `smoke_test.py` to locally verify imports and data-type resilience before production deployment.
- **Lessons Learned:** Created `lessonsLearned.md` to document architectural best practices for future developers (or AI agents) working on this project.

**Status: Production ready. All pages isolated, math is type-hardened, and automated verification is active.**

## [2026-04-05] — Stabilization & Performance
...
