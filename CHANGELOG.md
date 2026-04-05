# Changelog

Every entry must include a **Status** line describing what is currently safe to run.

## [2026-04-05] — Authentication & Logic Centralization

### fix: Centralized Authentication Gate
**What changed:**
- **Unified Auth Agent:** Created `utils/auth.py` to house the `require_auth()` logic. This extracts the redundant password check that was previously duplicated across 7 different files.
- **Improved UX:** Called `require_auth()` once at the top level of `app.py`. This ensures that once a user is authenticated, they remain so across all sub-pages without seeing "Please login on the main page" error messages.
- **De-cluttered Pages:** Removed over 100 lines of redundant authentication code from all sub-pages in the `pages/` directory.

### fix: Boot Sequence & Structural Stabilization

### fix: Centralized Page Configuration
**What changed:**
- **App Entry Point:** Moved `st.set_page_config` to the absolute top of `app.py`, ensuring it is the first Streamlit command executed. This resolves "set_page_config can only be called once" warnings.
- **Removed Duplicates:** Excised redundant `st.set_page_config` calls from all 6 sub-pages (`pages/*.py`).
- **Cleaned Imports:** Removed legacy `sys.path` manipulation blocks from all page files, as they are no longer necessary with the standard `pages/` directory structure.

### fix: Navigation & Routing
**What changed:**
- **Routing Fix:** Verified and stabilized `st.navigation` paths in `app.py` to correctly map to the `pages/` directory.
- **Audit Completion:** Finalized the repository cleanup by committing the removal of 25+ staged obsolete files.

**Status: Production ready. Application boot sequence is optimized and follows Streamlit 2026 best practices. All page routing is verified.**

## [2026-04-05] — Spring Cleaning & Consolidation

### refactor: Agent Consolidation (Tax & Rebalancing)
**What changed:**
- **New Unified Agent:** Created `utils/agents/tax_intelligence_agent.py` to house all tax-aware logic, including Tax-Loss Harvesting (TLH), Drift Analysis, and AI Rebalancing Proposals.
- **De-cluttered Utils:** Deleted the redundant `tax_harvester.py` and `tax_rebalancer.py` files.
- **Robustness:** Consolidated wash-sale logic into a single, high-reliability function used by both the Rebalancing and Tax pages.

### maintenance: Repository Hygiene
**What changed:**
- **Deleted 25+ Obsolete Files:** Removed legacy diagnostic scripts (`diagnose_*.py`), older setup files (`create_sa_file.py`, `populate_config.py`), and superseded documentation/prompts to reduce codebase complexity.
- **Log Purge:** Cleaned up untracked diagnostic logs and temporary session scripts.
- **Dependency Refresh:** Verified `requirements.txt` aligns with the current modular structure.

**Status: Production ready. Repository is streamlined and easier to maintain. Logic is fully consolidated into high-signal agents.**

## [2026-04-04] — Real Estate Integration & Valuation Stabilization

### fix: YTD Tax Filtering (2026 vs Prior)
**What changed:**
- **Year-Specific Filtering:** Updated `pages/4_Tax.py` to strictly filter the "Year-to-Date Realized Summary" for the current year (2026). This prevents 2025 gains/losses from inflating current year tax estimates.
- **Historical Data Access:** Added a new "Historical Realized (2025 & Prior)" expander to the Tax page, allowing you to see previous years' totals without affecting the YTD metric.

### fix: Valuation Fallbacks & API Hardening
**What changed:**
- **yfinance Fallback:** Implemented a smart fallback in `utils/agents/valuation_agent.py`. If the FMP API returns a "Payment Required" (402) error or restricted data for a ticker (like **BE**), the app now automatically fetches P/E, Market Cap, and Sector info from **Yahoo Finance**.
- **Robust Error Handling:** Hardened `utils/fmp_client.py` to globally handle 402 errors without crashing. It now returns clean empty objects, allowing the rest of the application to continue and trigger fallbacks where necessary.
- **Improved Valuation Logic:** Refined the logic to ensure that even if some data sources are restricted, the user still receives a valid valuation snapshot and narrative report.

### feat: Perplexity-Style Valuation Narratives
**What changed:**
- **Rich Narrative Generation:** Upgraded `utils/agents/valuation_agent.py` to generate professional "Valuation Verdicts" using Gemini. The report now includes sections for "What the market is pricing in" and "Valuation signals."
- **Enhanced Data Points:** The valuation engine now fetches and incorporates Market Cap, Dividend Yield, 52-Week Range, and Sector context into its analysis.
- **Robustness & Persistence:** Added session-state persistence to the Research Hub to keep reports visible during user interactions. Hardened the data parser to prevent `NoneType` crashes when specific financial metrics are missing.

### feat: Real Estate Dashboard "Wiring"
**What changed:**
- **Dynamic RE Metrics:** Hardwired `utils/agents/grand_strategist.py` to pull live data from the **Real Estate Dashboard** (`1DXu...rQ`).
- **Cell Mapping:** Specifically mapped Annualized NOI (`Dashboard!B23`), Total Debt (`Debt_Schedule!D6`), and Terminal Cap Rate (`Assumptions!E16`) to the Net Worth engine.
- **Valuation Documentation:** Created `re_portfolio_math.md` to provide a transparent breakdown of the exact formulas and constants used for RE equity and net worth.

### fix: FMP Valuation & "No PE Found" Errors
**What changed:**
- **FMP Stable Migration (Complete):** Fixed `utils/fmp_client.py` to handle 403 Legacy errors by switching fully to the `stable` endpoint patterns for both key metrics and historical ratios.
- **PE Ratio Fallback:** Implemented a smart fallback in `get_key_metrics` that calculates P/E from `earningsYieldTTM` ($1 / Yield$) when the direct `peRatioTTM` field is missing.
- **Historical Ratio Mapping:** Fixed `get_historical_pe` to correctly map the `priceToEarningsRatio` field from the newer FMP JSON structure.

### maintenance: Schema & Infrastructure
**What changed:**
- **Realized_GL Schema:** Completed the `Realized_GL` schema in `create_portfolio_sheet.py` to include all 22 columns (Wash Sales, LT/ST Gain, etc.) and enabled row freezing for the new tab.
- **Tab Initialization:** Verified and re-ran `create_portfolio_sheet.py` to ensure all 10 project tabs are correctly initialized with headers in the live Google Sheet.

### fix: CSV Parser Resilience & "As Of" Dates
**What changed:**
- **Date Parsing Fix:** Updated `utils/gl_parser.py` to handle Schwab's "as of" date strings (e.g., `"01/06/2026 as of 01/05/2026"`) which were previously causing `ValueError` crashes during transaction ingestion.
- **Transaction History Mapping:** Standardized fingerprint case-sensitivity and header mapping in `pipeline.py` to ensure reliable deduplication of trade history.

### feat: Automated Pipeline Logging
**What changed:**
- **New 'Logs' Tab:** Added a dedicated `Logs` tab to the Portfolio Sheet to track ingestion events (Timestamp, Level, Source, Message, Details).
- **Audit Trail:** Integrated `write_pipeline_log` into `ingest_realized_gl`, `ingest_transactions`, and `write_to_sheets` to provide a permanent record of all data updates and any skipped duplicates.
- **Header Initialization:** Updated `create_portfolio_sheet.py` to automatically provision the `Logs` tab with the correct schema.

### fix: Realized G/L Metadata Filtering
**What changed:**
- **Strict Validation:** Updated `parse_realized_gl` in `utils/gl_parser.py` to strictly require a valid `closed_date`. This automatically filters out Schwab's account metadata and summary rows that contain placeholder zeros.
- **Data Cleanup:** Manually purged 12 legacy metadata rows from the live `Realized_GL` sheet to ensure accurate YTD calculations.

### fix: Net Worth Calculation & Cap Rate Units
**What changed:**
- **Unit Mismatch Fix:** Updated `utils/agents/grand_strategist.py` to robustly handle different Cap Rate formats (e.g., "6.5", "6.5%", or "0.065"). Previously, a double-division was causing property valuations to explode into the hundreds of millions.
- **Valuation Sanity Guard:** Implemented a $50M cap-check on the income-based valuation. If the math results in an astronomical number, the system now logs a warning and falls back to a manual property value rather than displaying garbage data.

### fix: Dashboard Math & Cash Calibration
**What changed:**
- **Eliminated False Gains:** Updated `utils/csv_parser.py` to ensure that Schwab's cash rows (e.g., "Cash & Cash Investments") automatically set `Cost Basis = Market Value`. This prevents the system from misinterpreting cash as a 100% capital gain and fixes the Unrealized G/L discrepancy.
- **Manual Cash Calibration:** Changed the default `cash_amount` in `app.py` from $10,000 to **$0.0**. This prevents unintended "double-counting" of cash for users who already have their sweep accounts reflected in the Schwab CSV.
- **Robust Cash Detection:** Enhanced the parser to recognize more variants of Schwab's cash descriptions and map them to standard tickers (`QACDS`).

**Status: Production ready. Tax Intelligence now accurately reflects 2026 realized gains only. Valuation engine is hardened with yfinance fallbacks. Dashboard KPIs are aligned with Schwab.**

## [2026-04-03] — Connectivity, Intelligence & Robustness Upgrade

### feat: AI & API Modernization
**What changed:**
- **Model Upgrade:** Migrated core AI logic from Gemini 2.5 Pro to **Gemini 3.1 Pro Preview** for enhanced strategic reasoning.
- **FMP Stable Migration:** Rebuilt `utils/fmp_client.py` to use the **Financial Modeling Prep Stable API** pattern, resolving 403 Legacy Endpoint errors for new API keys.
- **FRED Integration:** Successfully verified and tested St. Louis Fed API connectivity for macro economic data.

### fix: Data Robustness & Parsing
**What changed:**
- **GSheet Header Resilience:** Implemented `read_gsheet_robust` in `utils/sheet_readers.py` to handle worksheets with duplicate or empty headers (common in manual sheet edits).
- **Net Worth Calculation:** Added robust currency parsing and float conversion in `grand_strategist.py` to prevent `TypeError` when reading RE Dashboard data.
- **Cash Ticker Expansion:** Added "CASH & CASH INVESTMENTS" to `CASH_TICKERS` to prevent yfinance 404 errors during enrichment.
- **JSON Parsing:** Enhanced `utils/gemini_client.py` with surgical JSON extraction logic to handle non-strict model responses.

### maintenance: UI & Navigation
**What changed:**
- **Navigation Fix:** Updated AI Advisor's system context to prevent hallucinations regarding non-existent pages; correctly routes users to Dashboard Tabs vs Sub-pages.
- **Streamlit Modernization:** Replaced 60+ occurrences of deprecated `use_container_width=True` with `width='stretch'` to clean logs and ensure 2026+ compatibility.
- **App Restructuring:** Renamed `app.py` to `Main.py` and updated page title to "Main Dashboard" for better sidebar clarity.

**Status: Production ready. AI logic is now running on Gemini 3.1 Pro. All API connections (FMP, Finnhub, FRED, Gemini) are verified green.**

## [2026-04-02] — Structural Audit & Refinement

### refactor: Data Pipeline & Sanitization
**What changed:** 
- Consolidated redundant `sanitize_*_for_sheets` functions into a single universal `sanitize_dataframe_for_sheets` in `pipeline.py`.
- Improved type casting to include `np.bool_` and handle `pd.NaT` gracefully.
- Re-ordered `normalize_positions` logic to ensure fingerprints are built before renaming.
- Updated `write_holdings_current` to use an atomic "Header + Data" write pattern to prevent data loss.

### fix: Schema & Config Alignment
**What changed:**
- Updated `config.py` `SNAPSHOT_COLUMNS` from 8 to 10 to match actual pipeline output (added 'Blended Yield' and 'Import Timestamp').
- Synchronized `TRANSACTION_COLUMNS` in `config.py` with the authoritative `PORTFOLIO_SHEET_SCHEMA.md`.
- Updated `PORTFOLIO_SHEET_SCHEMA.md` to reflect the 10-column snapshot structure.

### fix: App Logic & Security
**What changed:**
- Fixed `cash_val` calculation in `app.py` to handle potential string booleans from Google Sheets.
- Moved `calculate_income_metrics` import to top-level for performance.
- Removed sensitive `traceback.format_exc()` display from the Risk tab UI to prevent data leaks.
- Added missing `requests` and `numpy` dependencies to `requirements.txt`.

### maintenance: Parser & Configuration Refinement
**What changed:**
- Fixed `csv_parser.py` bug where the parser stopped prematurely after the first account section; now correctly aggregates all 48+ positions.
- Improved `csv_parser.py` to skip account label rows (e.g., "Individual ...119") that were being incorrectly parsed as tickers.
- Added 'HSA' to `ACCOUNT_SECTION_PATTERNS` in `config.py` for full account coverage.
- Implemented `TICKER_OVERRIDES` in `config.py` to centralize manual data corrections (e.g., ET dividend yield).
- Created `.streamlit/secrets.toml` template and configured password gate for local/production consistency.
- Fixed syntax error in `pages/research.py` and missing `anthropic`/`plotly` in `requirements.txt`.

**Status: Audit complete. Pipeline is now more robust, schemas are fully aligned, and multi-account parsing is verified.**

## [2026-04-01] — Final Delivery: Full Suite Operational

### feat: Phase 3 & 4 (Tax, Performance, and AI Research)

**What changed:**
- utils/gl_parser.py — robust parser for Schwab Realized G/L lot details
- pages/performance.py — benchmark comparison and contribution modeling
- pages/tax.py — tax intelligence with wash sale tracking and YTD realized G/L
- utils/fmp_client.py — Financial Modeling Prep API integration
- utils/ai_research.py — Claude 3.5 Sonnet analysis of earnings and news
- pages/research.py — AI Research Hub for deep-dive ticker analysis
- pipeline.py — updated with Realized G/L ingestion and fingerprint dedup

**Key architectural decisions made:**
- Content-based fingerprinting for realized lots (closed_date|ticker|opened_date|quantity|proceeds|cost_basis)
- Multi-page Streamlit architecture for cleaner navigation
- Sentiment-aware prompting for Claude analysis with forced JSON output
- Local-first caching for API responses to manage rate limits

**Status: Full system live. Safe to run: streamlit run app.py. Navigation sidebar provides access to Holdings, Performance, Tax, and AI Research pages.**

## [2026-04-01] — Phase 2 Live Data & Risk Analytics

### feat: yfinance enrichment and risk engine

**What changed:**
- utils/enrichment.py — yfinance enrichment module for live prices, yields, and sectors
- utils/risk.py — port of Colab V3.2 risk logic (beta, stress tests, CAPM, correlations)
- pipeline.py — updated with write_risk_snapshot and calculate_income_metrics
- app.py — implemented Income and Risk tabs with full analytics and visualizations
- pages/performance.py — new performance tracking page with benchmark comparison and contribution modeling
- utils/sheet_readers.py — added cached readers for risk and income history

**Status: Phase 2 complete. Safe to run: streamlit run app.py. Upload Schwab CSV -> Process -> Calculate Risk to see full dashboard.**

## [2026-04-01] — Phase 1 MVP Complete

### feat: Schwab CSV pipeline and dashboard

**What changed:**
- utils/csv_parser.py — robust multi-account parser with section detection and numeric cleaning
- pipeline.py — Gspread writer with fingerprint dedup and batch updates
- app.py — Streamlit dashboard with password gate, KPI cards, allocation charts, and holdings table
- utils/sheet_readers.py — authenticated client and cached holdings reader
- create_portfolio_sheet.py — idempotent tab/header creation

**Status: Phase 1 MVP complete.**

## [2026-03-30] — Project Initialization

### setup: project structure and documentation

**What changed:** Initial project setup.
