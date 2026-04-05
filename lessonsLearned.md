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

## 4. Engineering Workflow

### Git Verification
**Discovery:** Local "fixes" that aren't pushed to the remote repository are the #1 cause of "But it works on my machine" failures in Streamlit Cloud.
**Lesson:** Verification is not complete until `git status` shows a clean tree and `git push` has successfully completed. Use a `smoke_test.py` to verify imports and syntax locally before pushing.
