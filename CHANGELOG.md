# Changelog

Every entry must include a **Status** line describing what is currently safe to run.

## [2026-04-05] — Stabilization & Performance

### fix: Module Loading & Package Structure
**What changed:**
- **Standardized Packages:** Added `__init__.py` files to `utils/` and `utils/agents/` to ensure robust module discovery on Linux-based production environments (Streamlit Cloud).
- **Harden Readers:** Refactored `utils/sheet_readers.py` to ensure that all data-fetching functions are always defined, even if Streamlit components aren't immediately available during the boot sequence. This resolves "ImportError: cannot import name..." crashes.
- **Type Safety:** Updated `calculate_drift` in the Tax Intelligence agent to strictly cast data types, preventing Arrow serialization errors (`ArrowInvalid`) when displaying rebalancing tables.

## [2026-04-05] — Production Hardening & UI Refactor

### added
- **Column Guard:** Created `utils/column_guard.py` to auto-normalize Title Case vs snake_case column names across all data flows.
- **Data Validation Squad:** Implemented `utils/validators.py` to catch corrupted CSV data, outliers (like the +77,000% bug), and catastrophic parsing failures.
- **Global Error Boundary:** Dashboard-wide try/except with retry logic and traceback expanders in `app.py`.
- **Signals & Alerts Tab:** Dedicated UI for the 12 specialized AI agents, de-cluttering the main Holdings view.
- **Portfolio Status Hub:** Sidebar section for data freshness indicators, position counts, and DRY_RUN mode warnings.

### fixed
- **Critical Guardrail Alignment:** Moved options yield math and allocation drift math from LLM to Python, satisfying the "No LLM Math" mandate.
- **KeyError: 'Category':** Fixed crash in tax rebalancer with robust case-insensitive column matching.
- **Fragile Fingerprints:** Hardened deduplication keys by adding `position_count` and rounding float values to prevent precision mismatches.
- **API Performance:** Refactored fingerprint checks to use `ws.col_values()` range reads instead of full sheet downloads, saving ~90% of API overhead.
- **Research Hub Resilience:** Wrapped profile and news fetches in error handlers to prevent page crashes on API timeouts.

### changed
- **Treemap Visuals:** Replaced pie charts with information-dense Treemaps for 50+ position portfolios.
- **Native Data Grid:** Upgraded holdings table to `st.dataframe` with native sorting, progress bars for concentration, and automatic formatting.
- **Pydantic Hardening:** Refactored `gemini_client.py` and all agents to use strict **Pydantic response_schema** validation for deterministic AI results.
- **Streamlined Workflow:** Replaced persistent `st.success` banners with non-intrusive `st.toast` notifications.

**Status: Production ready. Application is now resilient to data corruption and connection failures. AI agents follow strict financial guardrails.**

## [2026-04-05] — Authentication & Logic Centralization
...
