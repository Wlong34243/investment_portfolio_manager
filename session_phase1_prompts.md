# Phase 1 — Build Session Prompts
**Investment Portfolio Manager** | Bill | April 2026  
Work top-to-bottom. Do not skip steps — each one is a prereq for the next.

---

## Current Status
- ✅ Phase 0 complete (repo, secrets.toml, .gitignore)
- ✅ Phase 1A complete (scaffold stubs, requirements.txt, slash commands, todo.md)
- 🔴 BLOCKED: GCP auth (JSONDecodeError in service_account.json — fix first)
- ⬜ Phase 1B–1E: CSV parser, writer, MVP dashboard — not started

---

## Prompt 1 — Fix service_account.json `[ BLOCKER ]`

**Tool:** Terminal / Claude Code  
**Done when:** `python -m json.tool service_account.json` prints clean JSON with no errors.

```
Fix create_sa_file.py so it correctly writes service_account.json.

The problem: the private key string contains literal newline characters that
break JSON serialization. The fix requires:

1. Rewrite create_sa_file.py using triple-quoted string for private_key.
2. Ensure the private key value stored in JSON uses \n (backslash-n) NOT
   actual newline characters — JSON spec requires escape sequences inside
   string values.
3. After writing the file, the script must immediately validate it by running:
       json.loads(open('service_account.json').read())
   and printing the client_email field as confirmation.
4. If json.loads raises any error, print the exact error and exit non-zero.

Do not change any other logic in the file. Run the fixed script after saving.
```

> ⚠️ If you don't have create_sa_file.py, run this in Terminal first:
> ```bash
> python -c "import json; d=json.load(open('service_account.json')); print(d['client_email'])"
> ```
> If that throws → file is still broken. If it prints the email → file is valid, skip to Prompt 2.

---

## Prompt 2 — Create Portfolio Google Sheet `[ MANUAL — BROWSER ]`

**Tool:** Browser + Claude Code  
**Done when:** Sheet has 8 tabs with headers. Service account has Editor access.

**Browser steps:**
1. Go to sheets.google.com → click Blank spreadsheet
2. Rename it: `Investment Portfolio Manager`
3. Copy the Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/[COPY THIS]/edit`
4. Open `config.py` → paste ID into `PORTFOLIO_SHEET_ID = "PASTE_HERE"`
5. Open `.streamlit/secrets.toml` → paste ID into `portfolio_sheet_id = "PASTE_HERE"`
6. Share the sheet: Share → paste service account `client_email` → Editor role → Send

**Then run in Claude Code:**

```
Read PORTFOLIO_SHEET_SCHEMA.md and config.py.

Run create_portfolio_sheet.py to create all 8 tabs with correct headers.
The Sheet ID is now set in config.py as PORTFOLIO_SHEET_ID.

If create_portfolio_sheet.py does not exist, create it now. It must:
1. Authenticate using utils/sheet_readers.get_gspread_client()
2. Open the sheet by config.PORTFOLIO_SHEET_ID
3. Create these tabs IN ORDER if they don't exist:
   Holdings_Current, Holdings_History, Daily_Snapshots, Transactions,
   Target_Allocation, Risk_Metrics, Income_Tracking, Config
4. Write the header row for each tab using the exact column names from
   PORTFOLIO_SHEET_SCHEMA.md — no deviations
5. Freeze row 1 on Holdings_Current, Holdings_History, Daily_Snapshots
6. Print each tab name + row count after creation
7. Be idempotent — safe to re-run (skip tabs that already exist)

Run the script after creating it. Print final tab list as confirmation.
```

> ✅ Verify: Open Sheet in browser — 8 tabs visible, Holdings_Current headers match PORTFOLIO_SHEET_SCHEMA.md exactly.

---

## Prompt 3 — GCP Auth Smoke Test `[ P1-C ]`

**Tool:** Claude Code  
**Done when:** `python utils/sheet_readers.py` prints `Auth OK — tabs: [list]` with no errors.

```
Read CLAUDE.md sections on GCP auth and utils/sheet_readers.py.

Create or update utils/sheet_readers.py with:

1. get_gspread_client() function:
   - Primary: authenticate via st.secrets["gcp_service_account"] (Streamlit)
   - Fallback: authenticate via GOOGLE_APPLICATION_CREDENTIALS env variable
     pointing to service_account.json (local dev)
   - Scopes: ["https://www.googleapis.com/auth/spreadsheets"]
   - Raise clear AuthError with instructions if both methods fail

2. smoke_test() function:
   - Calls get_gspread_client()
   - Opens sheet by config.PORTFOLIO_SHEET_ID
   - Lists all worksheet tab names
   - Reads first row of Holdings_Current and prints headers
   - Prints: "Auth OK — tabs: [list of tab names]"
   - Returns True on success, raises on any failure

3. if __name__ == "__main__": block that calls smoke_test()

After creating the file, run it:
   python utils/sheet_readers.py

If it fails, diagnose and fix. Common issues:
- JSONDecodeError: service_account.json still malformed
- SpreadsheetNotFound: Sheet ID wrong or not shared with service account
- AuthError: credentials path wrong in fallback

Do not proceed until "Auth OK" is printed.
```

> ⚠️ Do NOT set DRY_RUN=False yet. That happens after Prompt 5 passes.

---

## Prompt 4 — Port Schwab CSV Parser `[ P1-D ]`

**Tool:** Claude Code  
**Done when:** `python utils/csv_parser.py "-Positions-2025-12-31-082029.csv"` prints 50+ positions. GOOG shows 100.2781 shares (not rounded). Total value close to Schwab balance.

**Test file on disk:** `-Positions-2025-12-31-082029.csv`

```
Read CLAUDE.md sections: "Schwab CSV Parsing Rules", "Architecture Rules #2",
"Common Pitfalls 1-6", and "Known Portfolio Edge Cases".

Build utils/csv_parser.py with these exact functions:

1. clean_numeric(value) -> float | None
   Handle: "3,535.86" (commas), "(694.72)" (parens=negative),
   "nan", "--", "-", "", None -> return None or 0.0
   Must handle numpy NaN and Python None.
   Add these assertions at bottom of file:
     assert clean_numeric("3,535.86") == 3535.86
     assert clean_numeric("(694.72)") == -694.72
     assert clean_numeric("--") is None
     assert clean_numeric("") is None

2. find_column_indices(df_raw) -> dict
   Scan rows for the row containing "symbol" (case-insensitive).
   Return dict: {"symbol": 0, "description": 1, "quantity": 2, ...}
   NEVER use hardcoded column positions.
   Raise ValueError with clear message if Symbol row not found.

3. find_account_sections(df_raw) -> list[dict]
   Scan for account type labels from config.ACCOUNT_SECTION_PATTERNS.
   Return: [{"account_type": str, "start_row": int, "end_row": int}]
   Handle single-account CSVs gracefully (return one section).

4. get_sector_fast(description: str) -> str
   Description-based sector from config.ETF_KEYWORDS.
   Return sector string or "Other" if no match.

5. parse_schwab_csv(file_bytes: bytes) -> pd.DataFrame
   Orchestrate full parse:
   a. Read with header=None, names=range(25), encoding="utf-8-sig"
   b. find_column_indices()
   c. find_account_sections()
   d. Extract positions, skip summary/total rows
   e. clean_numeric() on all numeric columns
   f. Aggregate across accounts (groupby Symbol, sum Market_Value + Quantity)
   g. Return DataFrame with POSITION_COLUMNS schema from config.py
   CRITICAL: do NOT round fractional quantities (GOOG = 100.2781)

6. inject_cash_manual(df, cash_amount: float) -> pd.DataFrame
   Add CASH_MANUAL row: beta=0.0, yield=4.5%, is_cash=True.
   Only add if CASH_MANUAL not already present.

At end of file add:
   if __name__ == "__main__":
       import sys
       df = parse_schwab_csv(open(sys.argv[1], "rb").read())
       df = inject_cash_manual(df, 10000)
       print(f"Parsed {len(df)} positions")
       print(df[["Ticker","Market_Value","Quantity"]].head(10).to_string())

After writing, run:
   python utils/csv_parser.py "-Positions-2025-12-31-082029.csv"

Fix any parse errors. Output should show 50+ positions.
```

> 📝 Known edge cases: CRWV may show 0 cost basis. ET shows very high yield. SPY "dust" position (0.00003 shares) should parse but be tiny. BABA description is long — don't truncate it.

---

## Prompt 5 — Build Sheet Writer `[ P1-E ]`

**Tool:** Claude Code  
**Done when:** Dry-run test prints correct row counts with no numpy errors. After setting DRY_RUN=False, Sheet gains rows.

```
Read CLAUDE.md sections: "Architecture Rules #1, 4, 7", the Gotha file
(Gotchas 1-3), and PORTFOLIO_SHEET_SCHEMA.md for exact column layouts.

Build pipeline.py with these functions:

1. sanitize_for_sheets(df: pd.DataFrame) -> list[list]
   GOTCHA #1: df.fillna("") first, then cast every value to native Python.
   No numpy.float64, no NaN, no None passed to gspread. Ever.
   Return list of lists (one inner list per row, values in column order).

2. normalize_positions(df: pd.DataFrame, import_date: str) -> pd.DataFrame
   Add import_date column.
   Calculate weight = market_value / total_portfolio_value * 100.
   Build fingerprint = "{import_date}|{ticker}|{quantity}|{market_value}".
   Ensure all POSITION_COLUMNS from config.py present (fill missing with "").
   Sort by market_value descending.

3. write_holdings_current(ws, data: list[list]) -> None
   GOTCHA #2: Clear data rows (keep header row 1), then single API call:
       ws.update("A2", data)
   Add time.sleep(1.0) after. Log row count.

4. append_holdings_history(ws, data: list[list], existing_fps: set) -> int
   Filter to rows whose fingerprint not in existing_fps.
   Append new rows in single batch call: ws.append_rows(new_rows).
   time.sleep(1.0) after. Return count of rows appended.

5. append_daily_snapshot(ws, df: pd.DataFrame, existing_fps: set) -> bool
   Build snapshot row: date, total_value, total_cost, unrealized_gl,
   cash_value, invested_value, position_count, blended_yield, import_ts.
   Check fingerprint (date|total_value) before inserting.
   Return True if inserted, False if duplicate.

6. write_to_sheets(df: pd.DataFrame, cash_amount: float,
                   dry_run: bool = True) -> dict
   Orchestrate: Holdings_Current -> Holdings_History -> Daily_Snapshots.
   time.sleep(1.0) between each tab operation.
   If dry_run=True: log what WOULD be written, write nothing, return counts.
   Retry with 60s backoff on gspread.exceptions.APIError.
   Return {"holdings_written": N, "history_appended": N, "snapshot": bool}.

DRY_RUN=True must be respected — no writes when True.
config.DRY_RUN is the master gate.

After building, run this dry-run test:
   python -c "
   from utils.csv_parser import parse_schwab_csv, inject_cash_manual
   from pipeline import normalize_positions, write_to_sheets
   import datetime
   df = parse_schwab_csv(open('-Positions-2025-12-31-082029.csv', 'rb').read())
   df = inject_cash_manual(df, 10000)
   df = normalize_positions(df, str(datetime.date.today()))
   result = write_to_sheets(df, 10000, dry_run=True)
   print(result)
   "

Expected: {"holdings_written": 50+, "history_appended": 50+, "snapshot": True}
with DRY_RUN log messages. No Sheet writes yet.
```

> ⚠️ After dry-run passes: set `DRY_RUN=False` in config.py, re-run the test — this time it WILL write to Sheet. Open Sheet in browser and confirm rows appear in Holdings_Current.

---

## Prompt 6 — Build MVP Dashboard `[ P1-F ]`

**Tool:** Claude Code  
**Done when:** `streamlit run app.py` opens in browser. Upload CSV → KPI cards + pie chart + holdings table appear. UNH shows concentration warning.

```
Read CLAUDE.md section "Dashboard Sections (app.py)", Gotcha #3, and
config.py for SINGLE_POSITION_WARN_PCT and SECTOR_CONCENTRATION_WARN_PCT.

Build app.py with:

1. PASSWORD GATE
   check_password(): reads app_password from st.secrets.
   Store auth state in st.session_state["authenticated"].
   Skip gate entirely if app_password secret not set (local dev mode).

2. SIDEBAR
   - st.file_uploader("Upload Schwab CSV", type=["csv"])
   - st.number_input("Cash Amount ($)", value=10000, step=500)
   - st.button("Process CSV")
   - Red warning badge if config.DRY_RUN == True
   - Show last import date and position count if session_state has data

3. MAIN TABS: ["📊 Holdings", "💰 Income", "⚠️ Risk"]

4. HOLDINGS TAB
   KPI row (st.metric):
     Total Value | Total Cost | Unrealized G/L | Cash | Invested | Positions
   Allocation pie chart by Asset Class (Plotly, exclude CASH from invested %)
   Allocation pie chart by Asset Strategy
   Top 10 positions bar chart by market_value (horizontal, Plotly)
   Holdings table:
     - All positions, columns: Ticker | Description | Value | Weight% |
       Cost | Unrealized G/L | G/L% | Yield%
     - Search box filter by Ticker or Description
     - Pagination: 20 rows per page
     - Highlight rows where weight > config.SINGLE_POSITION_WARN_PCT in yellow

5. INCOME TAB
   Placeholder: st.info("Phase 2 — Income analytics coming in next session")

6. RISK TAB
   Placeholder: st.info("Phase 2 — Risk analytics coming in next session")
   Show concentration alert if any position > SINGLE_POSITION_WARN_PCT:
   st.warning("Concentration: " + ticker + " = " + str(weight) + "% of portfolio")

7. CSV PROCESSING FLOW (on "Process CSV" button click):
   a. parse_schwab_csv(uploaded_file.read())
   b. inject_cash_manual(df, cash_amount)
   c. normalize_positions(df, today_str)
   d. write_to_sheets(df, cash_amount, dry_run=config.DRY_RUN)
   e. st.success() with position count and total value
   f. Store df in st.session_state["holdings_df"]
   g. st.rerun()

8. SHEET READER (GOTCHA #3):
   In utils/sheet_readers.py, add:
   @st.cache_data(ttl=300)
   def get_holdings_current() -> pd.DataFrame:
       ... reads Holdings_Current tab and returns DataFrame ...

   Use this in app.py to populate dashboard from Sheet on load.
   If Sheet is empty, show st.info("Upload a CSV to begin.")

Chart color scheme: blues and teals (#1F4E79, #2E86AB, #A8DADC, #457B9D).
Use st.spinner("Processing...") during CSV processing and Sheet reads.

After building, run: streamlit run app.py
Test: upload -Positions-2025-12-31-082029.csv with $10,000 cash.
```

> 📝 If Streamlit reruns feel slow when filtering the table — Gotcha #3 is not applied. Check that get_holdings_current() has @st.cache_data(ttl=300).

---

## Prompt 7 — E2E Smoke Test + CHANGELOG `[ P1-G / P1-H ]`

**Tool:** Claude Code  
**Done when:** Values match Schwab website. CHANGELOG updated with Status line. Phase 1 complete.

```
Run an end-to-end validation of the Phase 1 pipeline using the real
Schwab CSV file: -Positions-2025-12-31-082029.csv

Test each step and print results:

1. PARSE
   df = parse_schwab_csv(open("-Positions-2025-12-31-082029.csv","rb").read())
   Print: position count, list of all tickers, total market value
   Flag: any tickers expected but missing
   Flag: any quantities that were rounded (fractional shares check)

2. CASH INJECTION
   df = inject_cash_manual(df, 10000)
   Print: CASH_MANUAL row values

3. NORMALIZE
   df = normalize_positions(df, str(date.today()))
   Print: first 5 rows (Ticker, Market_Value, Weight, Fingerprint)
   Flag: any position with weight > 8% (should show UNH ~9%)
   Flag: any row where Fingerprint is null or empty

4. SANITIZE CHECK
   data = sanitize_for_sheets(df)
   Verify: no numpy types in data (check type of every value in first row)
   Print: "Serialization check passed" or list all type violations

5. DRY RUN WRITE
   result = write_to_sheets(df, 10000, dry_run=True)
   Print result dict

6. LIVE WRITE (only if config.DRY_RUN == False)
   result = write_to_sheets(df, 10000, dry_run=False)
   Print result dict. Open Holdings_Current tab and verify row count.

7. SUMMARY — print comparison table:
   Metric            | Pipeline Value | Notes
   Total Value       | $X             | Compare to Schwab website manually
   Position Count    | N              | Should be 50+
   Largest Position  | UNH ~9%        | Concentration alert should fire
   Cash Included     | $10,000        | CASH_MANUAL present

After test, list any issues in tasks/todo.md with severity labels.
```

```
Add a new entry to CHANGELOG.md for today following the exact format of
existing entries.

Include:
  - Files created/modified: list ALL files created or modified today
  - Key architectural decisions made
  - Gotchas addressed: #1 sanitize_for_sheets, #2 batch update, #3 cache
  - Known issues or deferred items (Income tab, Risk tab = Phase 2)
  - Status line: exactly what is safe to run right now

Status line format:
  "Status: Phase 1 MVP complete. Safe to run: streamlit run app.py and
  upload Schwab CSV. DRY_RUN=[True/False]. Sheet ID: [ID]."

Do not omit the Status line. Match the existing CHANGELOG.md format exactly.
```

---

## Quick Reference — The Three Gotchas

| # | Name | Fix |
|---|------|-----|
| **#1** | Numpy/JSON Crash | `sanitize_for_sheets()`: `df.fillna("")` then cast all to native Python types before any gspread call |
| **#2** | API Quota Exhaustion | Batch only: `ws.update("A2", data)` — never cell-by-cell. `time.sleep(1.0)` between tabs |
| **#3** | Streamlit Rerun Sluggish | `@st.cache_data(ttl=300)` on every Sheet reader function in `utils/sheet_readers.py` |

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Idempotency** | `fingerprint = date\|ticker\|qty\|value` — check before every append |
| **Cash Handling** | `CASH_TICKERS = {'CASH_MANUAL','QACDS'}` — beta=0, excluded from allocation % |
| **DRY_RUN Gate** | `config.DRY_RUN=True` blocks ALL writes — only set False after Sheet is live |
| **No Auto-Trading** | Never connect to trading APIs. Display signals only. |
| **Config Over Code** | Thresholds in Google Sheet Config tab. Constants only in config.py. |
