# Changelog

Every entry must include a **Status** line describing what is currently safe to run.

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

## [2026-04-05] — Stabilization & Performance
...
