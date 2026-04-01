# Changelog

Every entry must include a **Status** line describing what is currently safe to run.

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
