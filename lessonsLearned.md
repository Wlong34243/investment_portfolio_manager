# Lessons Learned: Investment Portfolio Manager

This document tracks architectural decisions, operational failures, and technical best practices discovered during the development of the Streamlit + Google Sheets investment dashboard.

## 1. Streamlit Architecture (2026+)

### The "Global Scope" Rule
**Discovery:** In the `st.navigation` architecture, the main entry point (`app.py`) is executed on *every* page load. Any UI elements (metrics, charts, tabs) written in the global scope will appear on top of every sub-page.
**Lesson:** Always encapsulate page-specific UI logic into a function and pass that function to `st.Page()`. Keep the global scope of `app.py` restricted to initialization, authentication, and sidebar logic only.

## 2. Data Integrity & Type Safety

### "Nuclear" Type Enforcement
**Discovery:** Google Sheets is a "loose" database. A single cell with a space or a character (like `$`) will cause Pandas to interpret an entire numeric column as a `string`. Comparing a string to a number (e.g., `if value < -500`) crashes the app with a `TypeError`.
**Lesson:** Never trust the data type of a column read from Sheets. Use `pd.to_numeric(df['Col'], errors='coerce').fillna(0.0)` immediately before any math or comparisons. Use a centralized `Column Guard` to ensure critical identifiers (like `Ticker`) always exist and are correctly formatted.

## 3. Operations & API Hygiene

### Placeholder UI Elements
**Discovery:** Leaving "Coming Soon" or "Sync API" buttons in the live sidebar can cause confusion during debugging and may trigger fragile logic paths that aren't fully initialized.
**Lesson:** Keep placeholders in `tasks/todo.md`. Only add UI elements to the production sidebar when the underlying "Critical Path" (API wiring, error handling) is 100% complete.

### Hardened Error Handling
**Discovery:** External APIs (FMP, FRED) can fail with `402 Payment Required` or `500 Internal Server Error`. If these aren't handled, the app's sidebar or navigation may fail to render.
**Lesson:** Globally wrap API clients in try-except blocks that return empty objects (`{}`, `pd.DataFrame()`) and log warnings rather than raising exceptions.

## 4. The Is Cash Column Anti-Pattern

### Never Use `Is Cash` as a Boolean Filter in Display Code
**Discovery:** The `Is Cash` column is written correctly by `csv_parser.py` during ingestion (Python `True`/`False`). But when read back from Google Sheets via `ws.get_all_values()`, all values return as strings. After `column_guard.ensure_display_columns` processes them, the dtype becomes `bool` — but due to a type-coercion edge case in the pipeline, the column was `True` for every row. This caused:
- Main Dashboard: Total Portfolio == Cash Balance (Invested = $0)
- Rebalancing page: 100% Cash in every drift calculation
- Cash Sweeper agent: always triggered as if all assets were idle cash
- Options agent: zero covered call candidates (all rows filtered out)

**Lesson:** Never use `df['Is Cash'] == True/False` or `df['Is Cash'].astype(bool)` to identify cash positions anywhere in display or agent code. The column can silently become all-True when read back from Google Sheets. Instead, always identify cash rows using two reliable signals:
```python
cash_mask = (
    df['Asset Class'].astype(str).str.lower() == 'cash'
    | df['Ticker'].astype(str).str.upper().isin({'QACDS', 'CASH_MANUAL', 'CASH & CASH INVESTMENTS'})
)
```
The `Asset Class` and `Ticker` columns are plain strings read directly from the sheet — they are always reliable.

### Diagnosing "Everything is Cash" Bugs
**Discovery:** The symptom (100% Cash in drift, Cash == Total Portfolio) looked like a calculation error. The root cause was a data-layer boolean coercion problem. Three hours were spent rewriting correct calculation logic before the bad column value was identified.

**Lesson:** When a calculation produces an obviously wrong result (100% of one category), add a row-count diagnostic first:
```python
st.write(f"Cash rows: {cash_mask.sum()} of {len(df)}")
```
If this shows an impossible number (e.g., 47 of 47), the bug is in the mask, not the math.

## 6. Refactoring & Multi-Function Safety

### The Refactoring "Omission" Error
**Discovery:** When using surgical text-replacement tools (like `replace`) on blocks of code that contain multiple functions or UI elements, it is easy to accidentally delete "neighboring" code by simply leaving it out of the replacement string. 
- Example 1: Overwriting the sidebar `Import Hub` to add category enrichment logic while omitting the existing `Realized G/L` and `Transactions` uploaders.
- Example 2: Updating a single function (`calculate_beta`) but omitting the second function in that same source block (`calculate_portfolio_beta`), causing an immediate `ImportError` across the app.

**Lesson:** Refactoring is an "all-or-nothing" operation for the targeted block. Always read the *full* scope of the block being replaced. If a block contains multiple distinct features (like several file uploaders or multiple math functions), ensure every single one is explicitly represented in the new version of the code.

### Verification of Runtime State (Imports & Syntax)
**Discovery:** Small omissions in imports (e.g., forgetting `import streamlit as st` or `from typing import Optional`) can pass a cursory code review but cause a catastrophic crash (`NameError`) at runtime on Streamlit Cloud.
**Lesson:** After any structural code change or refactoring:
1.  **Syntax Check:** Run `python -m py_compile path/to/file.py` to catch basic syntax and indentation errors before pushing.
2.  **Import Audit:** Specifically verify that every decorator (like `@st.cache_data`) and every type hint (like `Optional`) has its corresponding import at the top of the file.
3.  **UI Sanity Check:** Manually verify that all previously existing UI components (uploaders, buttons, tabs) are still visible in their expected locations.

## Phase 5-S Lessons

- **Two Schwab apps, two tokens, one auth flow per app** — each Schwab
  app gets its own App Key/Secret and its own OAuth token. They share
  the same browser login but generate independent refresh tokens.
  Storing them in separate GCS blobs gives the Market Data client a
  physical inability to reach account endpoints.

- **Refresh token 7-day expiry is the real constraint** — the access
  token lasts 30 minutes (auto-refreshed by schwab-py), but the
  refresh token dies in 7 days unless something keeps it warm. The
  Cloud Function exists solely to make sure that "something" is
  automated and reliable.

- **Cloud Function on 24/7 schedule, not market hours** — saves nothing
  in dollars (free tier) and removes a class of weekend edge cases
  against the 7-day window.

- **Two-failure threshold for Gmail alerts** — single transient
  failures get caught by the next 25-minute cycle without notification.
  Two consecutive failures (~50 min of trouble) means it's a real
  problem worth pinging about.

- **Never log token contents** — only log blob names and success/fail.
  Token files are gitignored AND never written to stdout/stderr.

- **`client_from_access_functions` takes no `callback_url`** — the
  callback URL is only needed during the initial browser OAuth flow
  (`schwab.auth.client_from_login_flow`). Passing it to
  `client_from_access_functions` silently shifts every arg one position
  right, causing `'str' object is not callable` at runtime.

- **Token writer must accept `**kwargs`** — schwab-py calls the
  `token_write_func` with `refresh_token=...` as a keyword argument
  on refresh. A writer with only `(token)` in its signature raises
  `TypeError` and silently kills the live data path.
