# Investment Portfolio — Session Restart Todo

**Last updated:** 2026-04-01
**Status at restart:** All code written, nothing committed, no live Sheet writes yet.

---

## State of the Repo Right Now

| Item | Status |
|---|---|
| `utils/sheet_readers.py` | Done — smoke test passes ("Auth OK") |
| `utils/csv_parser.py` | Done — assertions pass, parses 47 positions from CSV |
| `utils/enrichment.py` | Written, untested |
| `utils/risk.py` | Written, untested |
| `utils/gl_parser.py` | Written, untested |
| `pipeline.py` | Written (large), DRY_RUN=True, untested |
| `app.py` | Written, untested |
| `pages/performance.py` | Written, untested |
| `pages/research.py` | Written, untested |
| `pages/tax.py` | Written, untested |
| `create_portfolio_sheet.py` | Written, NOT yet run — Sheet still has only "Sheet1" tab |
| Google Sheet tabs | NOT created yet — Sheet is blank |
| Git commits | Nothing committed since project init |
| DRY_RUN | `True` — no writes to Sheet have ever happened |

---

## Step 1 — Verify csv_parser still works (2 min)

The linter keeps rewriting this file. Confirm before anything else:

```bash
python utils/csv_parser.py "C:/Users/WLong/Downloads/All-Accounts-Positions-2026-03-30-103853.csv"
```

Expected: "Parsed 47 positions", Total ~$450K, assertions pass.
If it fails: restore from the known-good version (the one with _HERE/_ROOT path setup and None-returning clean_numeric).

---

## Step 2 — Create Portfolio Sheet tabs (5 min)

The Sheet (`1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA`) currently has only "Sheet1".
Run the tab/header creation script:

```bash
GOOGLE_APPLICATION_CREDENTIALS="C:/Users/WLong/Investment_Portfolio/service_account.json" \
  python create_portfolio_sheet.py
```

Expected: Creates all tabs from config (Holdings_Current, Holdings_History, Daily_Snapshots,
Transactions, Target_Allocation, Risk_Metrics, Income_Tracking, Realized_GL, Config).
Then re-run smoke test to confirm tabs appear:

```bash
GOOGLE_APPLICATION_CREDENTIALS="C:/Users/WLong/Investment_Portfolio/service_account.json" \
  python utils/sheet_readers.py
```

---

## Step 3 — First live pipeline run (10 min)

### 3a. Dry run first
```bash
GOOGLE_APPLICATION_CREDENTIALS="..." python -c "
import sys; sys.path.insert(0,'.')
from utils.csv_parser import parse_schwab_csv, inject_cash_manual
df = parse_schwab_csv(open('C:/Users/WLong/Downloads/All-Accounts-Positions-2026-03-30-103853.csv','rb').read())
df = inject_cash_manual(df, 10000)  # adjust cash_amount to actual sweep balance
print(df[['ticker','market_value','weight']].to_string())
print('Total:', df['market_value'].sum())
"
```

### 3b. Set DRY_RUN=False and write to Sheet
Edit `config.py`:
```python
DRY_RUN = False  # was True
```

Then run the pipeline write:
```bash
GOOGLE_APPLICATION_CREDENTIALS="..." python -c "
import sys; sys.path.insert(0,'.')
import config; print('DRY_RUN:', config.DRY_RUN)
from utils.csv_parser import parse_schwab_csv, inject_cash_manual
from pipeline import normalize_positions, write_to_sheets
df = parse_schwab_csv(open('C:/Users/WLong/Downloads/All-Accounts-Positions-2026-03-30-103853.csv','rb').read())
df = inject_cash_manual(df, 10000)
df = normalize_positions(df, '2026-03-30')
write_to_sheets(df)
print('Done')
"
```

Verify in Google Sheets: Holdings_Current should have 47 rows, Holdings_History appended.

---

## Step 4 — Commit everything to git

```bash
cd "C:/Users/WLong/Investment_Portfolio"
git add config.py requirements.txt CLAUDE.md CHANGELOG.md PORTFOLIO_SHEET_SCHEMA.md
git add utils/csv_parser.py utils/sheet_readers.py utils/enrichment.py utils/risk.py utils/gl_parser.py
git add pipeline.py app.py create_portfolio_sheet.py
git add pages/performance.py pages/research.py pages/tax.py
git add tasks/todo.md
# Do NOT add: service_account.json, .env, __pycache__, *.docx
git commit -m "feat: Phase 1-4 complete — full pipeline, dashboard, risk, tax, AI research"
```

---

## Step 5 — Streamlit app smoke test (5 min)

```bash
streamlit run app.py
```

Walk through each tab:
- [ ] Holdings tab loads — KPI cards show ~$480K total, allocation charts render
- [ ] Income tab loads — dividend/yield table renders
- [ ] Risk tab loads — beta, stress tests, correlation matrix render
- [ ] Performance page loads (sidebar nav)
- [ ] Tax page loads — realized G/L section
- [ ] Research page loads — AI analysis panel

Upload the Schwab CSV through the UI and verify the full pipeline runs end-to-end.

---

## Step 6 — Realized G/L ingestion (if needed)

CSV available: `All_Accounts_GainLoss_Realized_Details_20260401-101007.csv`
Transaction CSVs: `Individual_XXX119_Transactions_*.csv`

Test the realized G/L parser:
```bash
python -c "
import sys; sys.path.insert(0,'.')
from utils.gl_parser import parse_realized_gl
df = parse_realized_gl(open('All_Accounts_GainLoss_Realized_Details_20260401-101007.csv','rb').read())
print(df.head())
"
```

---

## Known Issues to Watch For

1. **Linter keeps rewriting csv_parser.py** — if assertions break, restore the version with:
   - `_HERE/_ROOT` path setup before `import config`
   - `clean_numeric` returning `None` (not `0.0`) for `--`, `""`, `None`

2. **DRY_RUN=True is the safety gate** — flip to False ONLY after dry-run output looks correct.

3. **Cash amount for CASH_MANUAL** — the Schwab CSV "Cash & Cash Investments" rows
   (skipped by parser) totaled ~$64K across accounts. Use actual sweep balance, not 10000.

4. **Sheet not shared** — if write fails with SpreadsheetNotFound, share the Sheet with
   the service account email (visible in `service_account.json` → `client_email`).

5. **pipeline.py normalize_positions** has a col_map that renames to Title Case — verify
   it maps back to config.POSITION_COLUMNS snake_case before the Sheet write.
