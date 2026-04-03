# Changelog

Every entry must include a **Status** line describing what is currently safe to run.

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
