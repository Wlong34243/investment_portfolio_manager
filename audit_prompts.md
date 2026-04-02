# Investment Portfolio Manager — Audit & Maintenance Prompts
## For use in Claude Code sessions | April 2, 2026

---

## How to Use This File

Each section below is a self-contained prompt. Copy-paste the prompt text (inside the code fence) directly into Claude Code. Run them in order — later prompts build on findings from earlier ones.

After each prompt completes, review the output before moving to the next. If Claude Code finds issues, fix them before proceeding.

---

## 1. Structure & Missing Files Audit

```
Read CLAUDE.md and then verify the actual repo structure matches what CLAUDE.md says should exist. Specifically check:

1. Does `utils/` exist with these files: csv_parser.py, sheet_readers.py, enrichment.py, risk.py, gl_parser.py?
2. Does `pages/` exist with: performance.py, research.py?
3. Does `.streamlit/` exist with secrets.toml?
4. Does `.claude/commands/` exist with session-start.md, review.md, deploy.md?
5. Does `tasks/` exist with todo.md and lessons.md?
6. Is there a .gitignore that protects service_account.json and secrets.toml?

For every file that CLAUDE.md references but does NOT exist, list it. For every file that exists but is NOT in CLAUDE.md, list it. Flag any orphaned imports in app.py or pipeline.py that reference modules that don't exist.

Do NOT create or fix anything yet — just report findings.
```

---

## 2. Config Consistency Audit

```
Read config.py and PORTFOLIO_SHEET_SCHEMA.md side by side. Check for these specific issues:

1. POSITION_COLUMNS in config.py — does the list match the Holdings_Current schema in PORTFOLIO_SHEET_SCHEMA.md exactly? Same column names, same order?

2. SNAPSHOT_COLUMNS in config.py — does it match Daily_Snapshots schema? The pipeline.py append_daily_snapshot() function writes 10 values (Date, Total Value, Total Cost, Unrealized G/L, Cash Value, Invested Value, Position Count, Blended Yield, Import Timestamp, Fingerprint) but the schema and config may not list all 10. Flag any mismatch.

3. GL_COLUMNS in config.py — does it match the Realized_GL tab schema?

4. TRANSACTION_COLUMNS in config.py — does it match the Transactions tab schema in PORTFOLIO_SHEET_SCHEMA.md? The schema says columns are Trade Date, Settlement Date, Ticker, Description, Action, Quantity, Price, Amount, Fees, Net Amount, Account, Fingerprint — but config.py has a different set: Date, Action, Symbol, Description, Quantity, Price, Fees & Comm, Amount, Import Date, Fingerprint. These do NOT match. Document exactly what differs.

5. Are there any hardcoded column names in pipeline.py or app.py that don't match what config.py defines?

Report all mismatches. Do NOT fix yet.
```

---

## 3. CSV Parser Deep Audit

```
Read utils/csv_parser.py thoroughly. Check against the parsing rules in CLAUDE.md (section "Schwab CSV Parsing Rules") and the sample CSV format (multi-account with sections like "Individual_401(k)", "Contributory", etc.).

Specifically audit:

1. Does parse_schwab_csv() handle BOM markers (utf-8-sig)?
2. Does it scan for the "Symbol" row dynamically (not hardcoded row numbers)?
3. Does it correctly identify account section boundaries? The CSV has account labels like "Individual_401(k) ...499" as standalone rows between header rows.
4. Does clean_numeric() handle ALL these formats: "$2,144.00", "-$0.27", "($694.72)", "--", "N/A", "", None, NaN, "0%", "77284.85%"?
5. Does it aggregate positions across accounts (same ticker in Individual + Contributory = sum)?
6. Does inject_cash_manual() correctly create a CASH_MANUAL row with beta=0, is_cash=True, and the right yield?
7. Are fractional shares preserved (not rounded)?
8. Is there any hardcoded column index (like df.iloc[:, 4])? This is explicitly forbidden.
9. Does it handle the "Cash & Cash Investments" row and "Account Total" row correctly (skip or exclude)?

For each issue found, explain the bug and suggest the fix. Rate severity: CRITICAL (data corruption), HIGH (wrong calculations), MEDIUM (edge case failure), LOW (style/cleanup).
```

---

## 4. Pipeline & Sheet Writer Audit

```
Read pipeline.py end to end. Audit for these categories of bugs:

**A. Data Integrity:**
1. In normalize_positions(), the col_map maps 'wash_sale' to 'Wash Sale' but the CSV parser may output 'wash_sale_flag'. Check if the internal column name is consistent between csv_parser output and pipeline input.
2. In sanitize_for_sheets(), are ALL numpy types caught? Check for np.bool_ which is often missed.
3. The fingerprint in normalize_positions() uses x.get('quantity', 0) — but after the col_map rename, the column would be 'Quantity' not 'quantity'. Is the fingerprint built BEFORE or AFTER the rename? If after, it's broken.

**B. Idempotency:**
4. In append_holdings_history(), existing fingerprints are fetched with get_all_records(). If the sheet has 5000+ rows, this will be slow and may hit API limits. Is there a better approach?
5. In append_daily_snapshot(), the fingerprint is date|total_value. If you re-import the same CSV on the same day but with updated enrichment data (different total_value due to live prices), this creates a "different" fingerprint and would duplicate. Is this the intended behavior?
6. In append_income_snapshot(), it calls ws.get_all_records() INSIDE the write_to_sheets() call chain. This means 4 separate get_all_records() calls happen per import (history, snapshots, income, plus holdings_current clear). That's 4 API reads in addition to the writes. Flag if this could cause quota issues.

**C. Error Handling:**
7. If the Google Sheet API fails on step 2 (Holdings_History) but step 1 (Holdings_Current) already succeeded, the data is in an inconsistent state. Is there any rollback or recovery logic?
8. The retry loop in write_to_sheets() retries the ENTIRE sequence on APIError. If Holdings_Current was already written, it gets written again (which is fine since it's an overwrite). But Holdings_History might double-append if the first attempt partially succeeded. Check this.

**D. Excess Complexity:**
9. sanitize_for_sheets() and sanitize_gl_for_sheets() and sanitize_transactions_for_sheets() are nearly identical functions. Should these be one generic function?
10. The col_map in normalize_positions() and sanitize_gl_for_sheets() duplicate mapping logic. Is there a DRYer approach?

Report findings with severity ratings.
```

---

## 5. App.py UI & Logic Audit

```
Read app.py completely. Audit for:

**A. Broken Logic:**
1. Line 144: `cash_val = df[df['Is Cash'] == True]['Market Value'].sum()` — does the 'Is Cash' column contain actual boolean True/False or string "TRUE"/"FALSE"? If it comes from Google Sheets via get_holdings_current(), it's likely strings. This comparison would silently return 0.
2. The Income tab imports calculate_income_metrics inside the tab block (line 244). This means it re-imports on every Streamlit rerun. Should it be at the top level?
3. Line 309: `df['Beta'] = df['Ticker'].apply(lambda x: calculate_beta(x, hist, spy_returns))` modifies the session_state dataframe in place. On re-run, this column already exists. Does this cause issues?

**B. UX Issues:**
4. The pagination uses st.number_input which requires typing a number. For 50+ positions across 3 pages, would st.selectbox or prev/next buttons be better?
5. If no CSV has been uploaded and the Sheet is empty, get_holdings_current() returns an empty DataFrame. Does the app handle this gracefully on ALL three tabs, or does any tab crash on empty data?
6. The Risk tab's "Calculate Risk Analytics" button fetches 1yr of price history for 20+ tickers via yfinance on every click. There's a 300s TTL cache in session_state, but is there a loading indicator beyond the spinner? Does the user know it could take 30+ seconds?

**C. Security:**
7. The password gate stores auth in session_state. Is there any session timeout? Could someone leave a browser tab open indefinitely?
8. Are there any st.write(traceback.format_exc()) calls that could leak sensitive info (API keys, sheet IDs) in production?

**D. Performance:**
9. get_holdings_current() is called once on app load. But after processing a new CSV, session_state is updated directly without calling the Sheet reader again. Is the Sheet the source of truth, or is session_state? What happens if the user refreshes the page — does it re-read from Sheet or show stale session data?

Report all findings with severity.
```

---

## 6. Risk Analytics Audit

```
Read utils/risk.py (if it exists). Audit against the Colab V3.2 specifications in CLAUDE.md:

1. Beta calculation: Does it use covariance method (cov(stock, spy) / var(spy))? Does it require MIN_BETA_DATA_POINTS (30) common data points? Does it fall back to beta=1.0 for insufficient data?

2. Portfolio beta: Is it weighted by market value? Is cash excluded (beta=0)?

3. Stress test: Does it use beta-adjusted impact (not simple percentage)? Formula should be: impact = total_value * portfolio_beta * market_change

4. CAPM projection: Does it use scipy.stats.norm for Z-scores at 10th/90th percentile? Are risk_free_rate and market_premium read from config (not hardcoded)?

5. Correlation matrix: Is it limited to top 20 positions by value? Does it use pct_change() on daily closing prices?

6. build_price_histories(): Does it use yf.download() bulk method or individual Ticker objects? Bulk is faster and less likely to hit rate limits.

7. Edge cases: What happens for CRWV (recent IPO, <1yr history)? What happens for BABA (ADR)? What happens for ET (limited partnership)?

8. Does concentration_alerts() correctly use the thresholds from config.py (10% single position, 30% sector)?

Report findings. Compare any formulas to standard financial calculations.
```

---

## 7. Cross-File Dependency & Import Audit

```
Trace every import across the entire codebase. For each file, list:
- What it imports
- Whether that import target exists
- Whether the imported names (functions, classes, constants) actually exist in the target

Specifically check:
1. app.py imports from pipeline.py: normalize_positions, write_to_sheets, write_risk_snapshot, ingest_realized_gl, ingest_transactions, calculate_income_metrics — do ALL of these exist in pipeline.py?
2. app.py imports from utils/: csv_parser (parse_schwab_csv, inject_cash_manual), enrichment (enrich_positions), risk (build_price_histories, calculate_beta, calculate_portfolio_beta, run_stress_tests, capm_projection, concentration_alerts, calculate_correlation_matrix), sheet_readers (get_holdings_current, get_gspread_client) — verify each exists.
3. pipeline.py imports from utils/: gl_parser (parse_realized_gl, parse_transaction_history) — does gl_parser.py exist? Do these functions exist in it?
4. Are there circular imports? (e.g., pipeline imports from utils, utils imports from pipeline)
5. Are there any unused imports in any file?

Also check: does requirements.txt include ALL packages actually imported? Scan for imports of finnhub, langchain, pandas_ta, or other Phase 2+ libraries that may be imported but not in requirements.txt.

Report the full dependency graph and any broken links.
```

---

## 8. Complexity & Dead Code Sweep

```
Scan the entire codebase for:

1. **Dead code:** Functions defined but never called from anywhere. Variables assigned but never used. Commented-out blocks longer than 5 lines.

2. **Duplicated logic:** The three sanitize_*_for_sheets() functions in pipeline.py (sanitize_for_sheets, sanitize_gl_for_sheets, sanitize_transactions_for_sheets) appear nearly identical. Propose a single generic version.

3. **Overly complex functions:** Any function longer than 50 lines. Any function with more than 3 levels of nesting. Any function doing more than one conceptual thing.

4. **Magic numbers:** Hardcoded values that should be in config.py. Examples: sleep durations, retry counts, page sizes, color codes, column indices.

5. **Inconsistent naming:** Mix of snake_case and camelCase. Mix of 'Ticker' vs 'ticker' vs 'Symbol' for the same concept across files.

6. **Files that should be deleted:** fix_json_again.py is a one-time utility script. Any other temporary/scaffolding files that shouldn't be in the repo?

For each finding, suggest whether to: FIX (refactor now), BACKLOG (track for later), or IGNORE (acceptable as-is).
```

---

## 9. Enrichment & External API Audit

```
Read utils/enrichment.py (if it exists). Audit:

1. Does enrich_positions() respect the TOP_N_ENRICH limit (top 20 by value)?
2. Is yfinance data cached with TTL >= 300 seconds?
3. What happens if yfinance is down or rate-limited? Is there a fallback?
4. Does it handle tickers that yfinance doesn't recognize (CRWV, CASH_MANUAL)?
5. Is the sector classification for non-enriched positions using the ETF_KEYWORDS from config.py?
6. Does it correctly calculate est_annual_income as dividend_yield * market_value / 100?
7. Are there any API keys being logged or exposed in error messages?

Also check utils/sheet_readers.py:
8. Does get_gspread_client() use st.secrets for the service account?
9. Is it cached with @st.cache_resource to avoid re-authenticating on every rerun?
10. Does get_holdings_current() use @st.cache_data with TTL?
11. What happens if the Google Sheet is unreachable? Does the app crash or show a friendly error?
```

---

## 10. Test Coverage & Test Quality Audit

```
Read test_e2e_phase1.py. Assess:

1. Does it actually test anything, or is it just a script that prints output? Are there assert statements?
2. It references a hardcoded file "All-Accounts-Positions-2026-03-30-103853.csv" — does this file exist in the repo? If not, the test is broken.
3. Line 20 has a bug: `print(f"Total market value: ${total_val:,.2f}" if 'total_val' in locals() else ...)` — total_val is never defined; total_mkt_val is. This line will always take the else branch. Flag this.
4. There are no unit tests for: clean_numeric(), find_column_indices(), find_account_sections(), inject_cash_manual(), normalize_positions(), sanitize_for_sheets(), calculate_income_metrics(), any risk functions.

Propose a minimal test suite that covers:
- CSV parsing with the actual Schwab multi-account format
- clean_numeric() with all edge cases (commas, parens, dashes, NaN, dollar signs, percentages)
- normalize_positions() column mapping and fingerprint generation
- sanitize_for_sheets() numpy type elimination
- calculate_income_metrics() with a small synthetic DataFrame
- Idempotency: same data processed twice produces zero new rows

Output the proposed test file structure (just function signatures and docstrings, not full implementations).
```

---

## 11. Google Sheet Schema Validation

```
Connect to the live Google Sheet (1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA) and validate:

1. Does each tab exist as specified in config.py tab names?
2. For Holdings_Current: does Row 1 match POSITION_COLUMNS from config.py exactly?
3. For Daily_Snapshots: does Row 1 match the actual columns being written by append_daily_snapshot()?
4. For Income_Tracking: does Row 1 match what append_income_snapshot() writes?
5. For Risk_Metrics: does Row 1 match what write_risk_snapshot() writes?
6. For Realized_GL: does Row 1 match GL_COLUMNS from config.py?
7. Are there any data rows that have the wrong number of columns (misaligned data)?
8. Are fingerprints actually unique within each tab?

If you can't connect to the Sheet (no credentials in this context), instead trace the code path and compare: what pipeline.py WRITES vs what config.py DECLARES vs what PORTFOLIO_SHEET_SCHEMA.md DOCUMENTS. Report any three-way mismatches.
```

---

## 12. Security & Secrets Audit

```
Scan the entire codebase for security issues:

1. Is service_account.json in .gitignore?
2. Is .streamlit/secrets.toml in .gitignore?
3. Are there any hardcoded API keys, passwords, or secrets anywhere in the code?
4. Does config.py's _secret() function safely fall back without exposing secrets in error messages?
5. Is the Portfolio Sheet ID hardcoded in config.py? (It is — is this acceptable or should it be in secrets?)
6. The fix_json_again.py script reads/writes service_account.json — is this file tracked in git?
7. Are there any print() or st.write() statements that could log sensitive data?
8. Does the password gate have any bypass conditions that could be exploited?
9. The traceback display in the Risk tab (line 360: st.write(traceback.format_exc())) — could this expose the service account email, sheet ID, or API keys in production?

Report all findings with remediation steps.
```

---

## 13. Performance & Scalability Audit

```
Analyze the codebase for performance bottlenecks assuming the portfolio grows to 100+ positions:

1. get_all_records() is called multiple times during a single write_to_sheets() execution. Each call fetches ALL rows. With 100 positions × 12 monthly imports × 3 tabs = thousands of rows. Will this hit Google Sheets API quota?

2. The Holdings_Current tab is cleared and rewritten entirely each import. This is fine. But Holdings_History appends ~100 rows per import. After 2 years: 2400 rows. After 5 years: 6000 rows. Is get_all_records() still viable for dedup at that scale?

3. The Risk tab calls build_price_histories() which downloads 1yr daily data for 20+ tickers. That's ~5000 data points. Is this cached between page reruns effectively?

4. The correlation matrix computation on 20 tickers with 252 trading days — is this CPU-bound enough to matter on Streamlit Cloud's free tier?

5. Plotly charts with 50+ data points in pie charts — any rendering concerns?

6. Session state stores the entire holdings DataFrame. With 100+ positions and all columns, is this a memory concern on Streamlit Cloud?

Propose specific optimizations for any P0/P1 issues found.
```

---

## Quick-Fix Prompts (Run After Audits)

### Fix: Consolidate Sanitize Functions
```
In pipeline.py, there are three nearly identical functions: sanitize_for_sheets(), sanitize_gl_for_sheets(), and sanitize_transactions_for_sheets(). Refactor these into a single generic function:

def sanitize_dataframe_for_sheets(df: pd.DataFrame, columns: list[str], col_map: dict = None) -> list[list]:

The function should:
1. Apply col_map rename if provided
2. Ensure all columns from the columns list are present
3. Reorder to match columns list
4. fillna("")
5. Cast every value to native Python types (handle np.float64, np.int64, np.bool_, pd.NaT, None)
6. Return list of lists

Then update all callers. Run the existing test to verify nothing breaks.
```

### Fix: Update CHANGELOG.md
```
Read the git log and update CHANGELOG.md to reflect ALL changes made since the initial March 30 entry. Include:
- Phase 1-4 code delivery
- Pipeline and dashboard implementation
- Any fixes made today

Each entry must have a Status line describing what is currently safe to run. Follow the existing format in CHANGELOG.md.
```

### Fix: Add Missing Tests
```
Create a proper test file at tests/test_core.py with unit tests for:
1. clean_numeric() — test all edge cases from the Schwab CSV
2. normalize_positions() — test with a 3-row synthetic DataFrame
3. sanitize_for_sheets() — verify no numpy types in output
4. calculate_income_metrics() — verify math with known inputs
5. Idempotency — fingerprint dedup logic

Use pytest. Include a conftest.py with shared fixtures (sample DataFrame, sample CSV content).
Do NOT mock Google Sheets — test only the pure Python logic.
```

### Fix: Snapshot Column Mismatch
```
The Daily_Snapshots schema in PORTFOLIO_SHEET_SCHEMA.md lists 8 columns, but pipeline.py append_daily_snapshot() writes 10 values (it adds Blended Yield and Import Timestamp that aren't in the schema).

Determine the correct set of columns. Update EITHER the schema doc OR the pipeline code to match. Also update SNAPSHOT_COLUMNS in config.py. Document the decision in CHANGELOG.md.
```
