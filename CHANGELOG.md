# Changelog

Every entry must include a **Status** line describing what is currently safe to run.

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
