# Investment Portfolio Manager: Codebase Inventory

This document provides a technical map of the Python scripts within the repository, detailing their purpose, data sources, and impact on Google Sheets.

## 核心 Orcherstration & Pipeline
| Script | Purpose | Data Source | Writes To | Key Command |
| :--- | :--- | :--- | :--- | :--- |
| `manager.py` | Primary CLI Entry Point. Orchestrates snapshots, agent runs, and maintenance. | Varies by command | Agent_Outputs, Bundles | `python manager.py` |
| `pipeline.py` | The "Data Spine". Handles normalization, aggregation, and core sheet writing logic. | Schwab API / CSV | Holdings_Current, Daily_Snapshots, Holdings_History | Internal use by manager.py |
| `config.py` | Single source of truth for IDs, Tickers, and Tab names. | `.env` | N/A | N/A |

---

## 🚀 Execution Tasks (`tasks/`)
Scripts that perform specific, scheduled, or triggered operations.

| Script | Purpose | Data Source | Writes To | Key Command |
| :--- | :--- | :--- | :--- | :--- |
| `format_sheets_dashboard_v2.py` | Injects KPI formulas and professional styling into sheet headers. | `config.py` | All Tab Headers (Row 1/2) | `python tasks/format_sheets_dashboard_v2.py --live` |
| `weekly_podcast_sync.py` | Scrapes YouTube transcripts and uses AI to derive sector weightings. | YouTube RSS | AI_Suggested_Allocation | `python tasks/weekly_podcast_sync.py --live` |
| `build_decision_view.py` | Joins holdings, valuation data, and agent signals into a single "Master Action" view. | Holdings_Current, Agent_Outputs | Decision_View | `python tasks/build_decision_view.py --live` |
| `derive_rotations.py` | Analyzes transactions to group "Sells" and "Buys" into cohesive rotation entries. | Transactions | Trade_Log_Staging | `python tasks/derive_rotations.py` |
| `enrich_atr.py` | Computes 14-day Average True Range (ATR) for technical stop-loss levels. | yfinance (1mo daily) | Composite Bundle | `python manager.py snapshot --enrich-atr` |
| `sync_transactions.py` | Fetches recent trades from Schwab API. | Schwab API | Transactions | `python manager.py snapshot` |

---

## 🤖 Intelligence Agents (`agents/`)
Gemini-powered analysis scripts. All agents write to the `Agent_Outputs` tab.

| Script | Purpose | Pre-Computation (Python) | LLM Rationale |
| :--- | :--- | :--- | :--- |
| `valuation_agent.py` | PE Ratio vs Historical Avg | FMP Quote, Earnings History | Style Alignment, Signal (Accumulate/Trim) |
| `tax_agent.py` | Tax Loss Harvesting (TLH) | Unrealized G/L, Wash Sale Check | Scale-step narrative, TLH Candidates |
| `macro_cycle_agent.py` | Paradigm shift analysis | ATR Stops, 52w Range | Cycle Phase, Rotation Priority |
| `concentration_hedger.py` | Risk mitigation | Weighted Beta, Correlations | Hedge suggestions, Stress Impact |
| `thesis_screener.py` | Qualitative alignment | Vault Thesis files, Transcripts | Management Candor, Pre-mortem checks |
| `bagger_screener.py` | High-growth screening | ROIC, Revenue CAGR, Gross Margin | Mayer Framework evaluation |
| `analyze_all.py` | Sequentially runs all 7 agents. | All of the above | Unified Run Manifest |

---

## 🛠️ Utilities (`utils/`)
The engine room — shared logic used across the codebase.

| Script | Purpose |
| :--- | :--- |
| `schwab_client.py` | Handles OAuth2 handshake and raw data fetching from Schwab endpoints. |
| `fmp_client.py` | Tiered data fetch: Schwab Quote -> yfinance -> FMP (with 7-day cache). |
| `risk.py` | Portfolio Beta, Correlation Matrix, and Historical VaR math. |
| `column_guard.py` | Prevents `KeyError` by ensuring required headers exist in Pandas DataFrames. |
| `sheet_readers.py` | Robust gspread wrappers with ADC / Service Account fallback logic. |
| `gemini_client.py` | Bundle-aware LLM calls with mandatory hash verification. |

---

## 🔧 Maintenance Scripts (`scripts/`)
Utility scripts for one-off fixes or debugging.

| Script | Purpose |
| :--- | :--- |
| `read_sheet_debug.py` | Fast console-dump of any sheet tab to verify raw data. |
| `schwab_initial_auth.py` | Run once to establish the OAuth token link via browser. |
| `repair_sheet_data.py` | Fixes corrupted sheet data (e.g., converting "Unnamed_0" back to "Ticker"). |
| `audit_cost_basis.py` | Compares Schwab cost basis vs manual staging to find discrepancies. |
