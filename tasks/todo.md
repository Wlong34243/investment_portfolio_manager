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


---

## Phase 5 Test Run — 2026-04-13

Bundle hash used: _______________

| Group | Test | Result | Notes |
|-------|------|--------|-------|
| G1 | T1.1 Bundle integrity | PASS | Snapshot 706d57b18f25 verified. |
| G1 | T1.2 Vault coverage | PASS | 49 present, 3 missing (BA, MSFT, VTI). |
| G1 | T1.3 Composite assembly | PASS | Composite 259063061506 assembled. |
| G1 | T1.4 Cash exclusion | PASS | CASH_MANUAL exists in bundle but is marked is_cash: true. |
| G1 | T1.5 Fallback behavior | PASS | Logic verified in core/bundle.py; Schwab API was UP. |
| G2 | T2.1 Rebuy dry run | FAIL | Pydantic parsing failed (truncated JSON) on 52 positions. |
| G2 | T2.2 Single ticker | PASS | UNH analyzed successfully. |
| G2 | T2.3 Framework override | PASS | AMZN framework evaluation present, no overrides. |
| G2 | T2.4 Missing thesis | PASS | GOOG flagged in coverage_warnings when thesis missing. |
| G3 | T3.1 TLH candidates | PASS | 8 candidates identified after fixing unrealized_gl. |
| G3 | T3.2 Wash sale flags | PASS | UNH, CRWD, IGV flagged correctly. |
| G3 | T3.3 Rebalancing drift | PASS | 6 actions, CASH_MANUAL excluded from results. |
| G3 | T3.4 Short/long term | PASS | Defaults to short_term=True when unknown, correct. |
| G3 | T3.5 No Target_Alloc writes | PASS | Row count remained 7 after --live run. |
| G4 | T4.1 P/E from Python | FAIL | FMP API rate-limited (402), P/E values were null. |
| G4 | T4.2 Small-step accum | PASS | UNH plan: 'Scale in 10-15% on each 3-5% pullback'. |
| G4 | T4.3 Data gaps | PASS | GOOG gap logged correctly. |
| G4 | T4.4 Style from vault | PASS | UNH, AMZN mapped to GARP from thesis. |
| G5 | T5.1 UNH flag fires | PASS | UNH at 11.1% flagged (threshold 8%). |
| G5 | T5.2 Tech sector flag | FAIL | Groups by Equity (92%), not Tech. UNH included. |
| G5 | T5.3 Beta Python-computed | PASS | Beta 1.03, stress tests match arithmetic. |
| G5 | T5.4 Corr pairs | FAIL | Only QQQM/VTI found; AMZN/GOOG missed. |
| G5 | T5.5 Hedge small-step | PASS | Suggestions use '10-15% each over several weeks'. |
| G6 | T6.1 ATR Python-computed | PASS | ATR $290.15 for UNH from composite bundle. |
| G6 | T6.2 Paradigm enum | PASS | Phase 'maturity' assigned to UNH. |
| G6 | T6.3 Rotation from vault | PASS | Rotation targets CRWV, IREN, XBI, etc. identified. |
| G7 | T7.1 Thesis content used | PASS | UNH rationale mentions 'regulatory and operational' from thesis. |
| G7 | T7.2 Guardrails fire | PASS | Used 'inner scorecard' and 'stewardship' from Joys framework. |
| G7 | T7.3 Missing transcript | PASS | Output notes absence of transcript for UNH. |
| G8 | T8.1 Quant gate Python | PASS | AMZN ROIC 10.7%, BABA ROIC 4.5% computed in Python. |
| G8 | T8.2 Schema separated | PASS | Mayer quantitative gates identified in output. |
| G9 | T9.1 Framework loads | PASS | Joys and Mayer frameworks used by Thesis and Bagger agents. |
| G9 | T9.2 No VanTharp.py | PASS | VanTharp.py removed; logic moved to framework_selector.py. |
| G9 | T9.3 1R Python-computed | FAIL | compute_van_tharp_sizing exists but is not yet called by any agent. |
| G10 | T10.1 All agents run | FAIL | Full portfolio (46 pos) causes truncation/Pydantic errors. |
| G10 | T10.2 Single batch write | PASS | Tax agent --live wrote 16 rows in one batch. |
| G10 | T10.3 Failure isolation | PASS | Tax and Concentration ran after Rebuy/Valuation failed. |
| G10 | T10.4 Subset flag | PASS | Macro and Valuation support --ticker / --tickers. |
| G10 | T10.5 Fresh bundle | PASS | Fresh bundles built correctly during analyze-all prep. |
| G11 | T11.1 workflow_dispatch | PASS | weekly_analysis.yml has manual trigger. |
| G11 | T11.2 GCP creds in Actions | PASS | GCP_SERVICE_ACCOUNT_JSON secret used in workflow. |
| G11 | T11.3 Token expiry fallback | PASS | build_bundle(source='auto') catches RuntimeError and falls back to CSV. |
| G12 | T12.1 Hash provenance | PASS | Manifest 00a0c757 matches composite bundle 71def3350c04. |
| G12 | T12.2 No LLM math | PASS | UNH gain/loss correctly reflects (qty * live_price) - cost_basis. |
| G12 | T12.3 DRY_RUN gate | PASS | Agent_Outputs row count remained 17 during dry runs. |
| G12 | T12.4 SAFETY_PREAMBLE | PASS | Defined in gemini_client.py and used in ask_gemini. |
| G12 | T12.5 Small-step audit | PASS | All agents use 10-15% increments in plans. |
| G12 | T12.6 Agent_Outputs schema | PASS | Sheet headers match _AGENT_OUTPUTS_HEADERS exactly. |

Blockers: Gemini Flash response truncation on full portfolio (46+ pos); FMP 402 Payment Required.
Next action: Add Van Tharp sizing to agents; optimize context for full portfolio analysis.

