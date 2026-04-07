# Changelog

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
