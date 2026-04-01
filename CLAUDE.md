# Investment Portfolio Manager — CLAUDE.md

## Project Identity
Streamlit web app for tracking, analyzing, and managing a ~$480K liquid investment portfolio (50+ positions). Ingests Schwab brokerage CSV exports, writes to Google Sheets, provides AI-assisted research and rebalancing guidance. Single user: Bill (CPA/CISA, intermediate Python). Companion system to the RE Property Manager — separate repo, separate Sheet, shared GCP credentials.

## Repo Structure
```
investment-portfolio-manager/
├── app.py                        # Streamlit UI — Portfolio Dashboard + Income + Risk
├── pages/
│   ├── performance.py            # Performance tracking (benchmarks, snapshots, returns)
│   └── research.py               # AI research panel (earnings, news, signals) — Phase 4
├── pipeline.py                   # Ingestor, Normalizer, Enricher, Snapshot, Writer
├── config.py                     # All IDs, tickers, thresholds, API keys, constants
├── requirements.txt
├── PORTFOLIO_SHEET_SCHEMA.md     # Authoritative cell-level schema for the Google Sheet
├── CHANGELOG.md                  # Every entry includes Status line
├── .streamlit/
│   └── secrets.toml              # GCP service account JSON + API keys (NEVER commit)
├── utils/
│   ├── csv_parser.py             # Schwab CSV parsing — ported from Colab V3.2
│   ├── sheet_readers.py          # Cached Google Sheets readers
│   ├── enrichment.py             # yfinance, news API, AI research helpers
│   └── risk.py                   # Beta, correlation, stress test, CAPM projection
├── .claude/
│   └── commands/
│       ├── session-start.md      # Load CLAUDE.md, CHANGELOG.md, check lessons
│       ├── review.md             # Pre-commit review checklist
│       └── deploy.md             # Push + verify Streamlit Cloud
└── tasks/
    ├── todo.md                   # Current plan with checkable items
    └── lessons.md                # Accumulated patterns and mistakes
```

## Critical Infrastructure

### Google Sheets (source of truth)
| Sheet | ID | Purpose |
|---|---|---|
| Portfolio Sheet | TBD (create Phase 1) | Holdings, snapshots, transactions, targets, risk, income, config |
| RE Dashboard | `1DXuY1iBo2GqZCCSZ7OrUa4iaunb5s8Kf1Rms8Z237rQ` | Cross-reference for unified net worth (READ ONLY — never write) |

### Portfolio Sheet Tab Structure
| Tab | Purpose | Write Pattern |
|---|---|---|
| Holdings_Current | Latest position snapshot per ticker | Full overwrite on each import |
| Holdings_History | Append-only log of every import | Append rows, never delete |
| Daily_Snapshots | End-of-day portfolio value | Append with date-based dedup |
| Transactions | Trade history (Phase 3) | Append with fingerprint dedup |
| Target_Allocation | Asset class/strategy targets | Manual entry by Bill |
| Risk_Metrics | Beta, correlation snapshots | Append per calculation run |
| Income_Tracking | Dividend/yield history | Append per snapshot |
| Config | App configuration | Manual entry by Bill |

### GCP
- Project ID: `re-property-manager-487122` (shared with RE project)
- Auth: Service account via `st.secrets["gcp_service_account"]`
- Scopes: `https://www.googleapis.com/auth/spreadsheets`
- IMPORTANT: Same service account, NEW Sheet. Share the new Portfolio Sheet with the service account email.

### Brokerage Account
- **Primary investment account** (~$480K, 50+ positions) — THIS project
- **Reserve account ...8895** (~$12.5K) — tracked in RE project, NOT this one
- CSV format: Schwab "Positions" export, multi-account sections

### Colab Prototype (V3.2)
The Colab script is the working prototype. Production code should port these functions:

| Colab Function | Port To | What It Does |
|---|---|---|
| `clean_numeric()` | `utils/csv_parser.py` | Robust number parsing (commas, parens, NaN, dashes) |
| `find_column_indices()` | `utils/csv_parser.py` | Dynamic header detection (scan for "Symbol" row) |
| `find_account_sections()` | `utils/csv_parser.py` | Multi-account section parsing |
| `get_sector_fast()` | `utils/csv_parser.py` | Description-based sector classification |
| Beta calculation | `utils/risk.py` | Covariance vs SPY, 1yr history, min 30 data points |
| Correlation matrix | `utils/risk.py` | Top 20 positions, pct_change correlation |
| Stress test scenarios | `utils/risk.py` | Beta-adjusted market impact estimation |
| CAPM projection | `utils/risk.py` | Risk-free + beta × market premium, scipy norm |
| Income dashboard | `pipeline.py` or `app.py` | Yield × market value, blended portfolio yield |

## Architecture Rules (MUST follow)

### 1. Idempotency
- Position snapshots: fingerprint = `import_date|ticker|quantity|value`
- Daily snapshots: fingerprint = `snapshot_date|total_value`
- Transactions: fingerprint = `trade_date|ticker|action|quantity|price`
- Check existing records before inserting — same CSV uploaded twice = zero new rows
- Use content-based fingerprinting (NOT MD5 hash — lesson learned from RE project)

### 2. Schwab CSV Parsing Rules
```python
# CRITICAL: Multi-account Schwab CSV has specific quirks

# 1. Read with no assumed header — columns may vary
df_raw = pd.read_csv(file, header=None, names=range(25), encoding='utf-8-sig')

# 2. Dynamic header detection — scan for "Symbol" row
for idx, row in df_raw.iterrows():
    row_str = [str(x).lower() for x in row.values]
    if 'symbol' in row_str:
        # Map column positions dynamically
        break

# 3. Account sections — look for account type labels
# (Individual, Contributory, Joint, Custodial, Trust, Roth)

# 4. Numeric cleaning — commas, parentheses, NaN, dashes
def clean_numeric(value):
    # Handle: "3,535.86", "(694.72)", "nan", "-", "", None
    ...

# 5. Aggregate across accounts — same ticker in multiple accounts = sum
symbol_agg = positions_df.groupby('Symbol').agg({
    'Market_Value': 'sum', 'Quantity': 'sum', 'Description': 'first'
})

# 6. Cash injection — manual entry for money market
CASH_MANUAL row with Symbol='CASH_MANUAL', zero beta

# 7. WRONG — hardcoded column positions
ticker = df.iloc[:, 4]  # ← NEVER DO THIS
```

### 3. Cash Position Handling
- `CASH_MANUAL` is a synthetic position injected by the app (not from CSV)
- Cash has beta = 0.0, counts toward total portfolio value
- Cash yield (~4.5%) counts toward income calculations
- Exclude from allocation percentage denominators when calculating "invested allocation"
- Include in total portfolio value for net worth calculations
- `CASH_TICKERS = {'CASH_MANUAL', 'QACDS'}` — both are non-investment positions

### 4. Batch API Operations
Google Sheets API has rate limits. Always use `batch_update()` instead of cell-by-cell writes. Add `time.sleep(1.0)` between tab operations. Retry with 60s backoff on APIError.

### 5. Config Over Code
- Ticker-specific settings in Google Sheet Config tab, not Python constants
- Target allocations in Google Sheet Target_Allocation tab
- API keys in `.streamlit/secrets.toml`
- Only structural constants (column names, tab names, CASH_TICKERS) belong in `config.py`

### 6. No Auto-Trading
This system NEVER executes trades. It provides information and suggestions only. All buy/sell decisions are Bill's. The app displays signals and rebalancing suggestions — it does not connect to any trading API.

### 7. Cast Pandas Types Before gspread Calls
```python
# CORRECT — native Python types for JSON serialization
row = [str(ticker), float(value), int(quantity), str(date)]

# WRONG — numpy types break gspread JSON serialization
row = [ticker, df['value'].sum(), df['qty'].iloc[0], date]
```

### 8. yfinance Rate Limiting
- Cache all yfinance calls with TTL (300s minimum)
- Use bulk download for multiple tickers: `yf.download(tickers, period="1y")`
- Limit enrichment to top 20 positions by value (Colab pattern)
- Smaller positions get description-based sector classification only
- Never call yfinance on every page load — cache in session_state or Google Sheet

### 9. Separation from RE Property Manager
- SEPARATE repo, SEPARATE Streamlit app, SEPARATE Google Sheet
- Shares only GCP service account credentials
- Reserve account ...8895 is the RE project's concern, not this one
- No code imports between the two projects
- Future unified net worth view reads from both Sheets (read-only cross-reference)

## Pipeline Phases

| Phase | Function | Input | Output |
|---|---|---|---|
| 1 Ingestor | `parse_schwab_csv()` | CSV bytes | Raw DataFrame (multi-account) |
| 2 Normalizer | `normalize_positions()` | Raw DF | Clean DF with standard columns + cash injection |
| 3 Enricher | `enrich_positions()` | Clean DF | DF with live prices, sector, yield, beta (Phase 2+) |
| 4 Snapshot | `take_snapshot()` | Enriched DF | Summary record for Daily_Snapshots |
| 5 Writer | `write_to_sheets()` | All above | Google Sheet tabs updated |

### Normalized Position Schema
```python
POSITION_COLUMNS = [
    'import_date',         # Date of CSV import
    'ticker',              # Stock ticker symbol (CASH_MANUAL for cash)
    'description',         # Full security name
    'asset_class',         # Equity, Fixed Income, Alternative, Cash
    'asset_strategy',      # US Large Cap, Emerging Market, etc.
    'quantity',            # Share count (float — fractional OK)
    'price',               # Current market price per share
    'market_value',        # quantity × price (or manual entry for cash)
    'cost_basis',          # Total cost basis (0 for cash)
    'unit_cost',           # Per-share cost basis
    'unrealized_gl',       # Market value − cost basis
    'unrealized_gl_pct',   # Unrealized G/L as percentage
    'est_annual_income',   # Estimated dividend income
    'dividend_yield',      # Yield percentage
    'acquisition_date',    # For tax lot tracking (blank OK)
    'wash_sale_flag',      # Boolean — wash sale indicator
    'is_cash',             # Boolean — True for CASH_MANUAL, QACDS
    'weight',              # Position as % of total portfolio
    'fingerprint',         # Dedup key: import_date|ticker|quantity|value
]
```

## Dashboard Sections (app.py)

### Tab 1: Holdings
- KPI Cards: Total Value (~$480K), Total Cost, Unrealized G/L, Cash Position, Invested Amount, Position Count
- Allocation pie chart by Asset Class (Equity/Fixed Income/Alternatives/Cash)
- Allocation pie chart by Asset Strategy (US Large Cap/Emerging Market/etc.)
- Holdings table: sortable, filterable, with weight and G/L columns
- Top 10 positions bar chart

### Tab 2: Income
- Projected annual dividend income
- Blended portfolio yield
- Top income generators table (from Colab pattern)
- Income by sector breakdown
- Cash yield contribution

### Tab 3: Risk (Phase 2)
- Portfolio beta (weighted by position value, cash = 0 beta)
- Stress test scenarios (from Colab: -2%, +1.5%, -10% market moves)
- 1-year projection (bad/expected/good case from CAPM-lite)
- Correlation matrix heatmap (top 20 positions)
- Concentration risk alerts (single position > 10%, sector > 30%)

### Performance Page (pages/performance.py — Phase 2)
- Portfolio value over time (from Daily_Snapshots)
- Benchmark comparison (SPY, VTI, QQQM)
- Period returns (MTD, QTD, YTD, 1Y)
- Per-position contribution to returns
- Contribution modeling (monthly add projections, from Colab)

### Research Page (pages/research.py — Phase 4)
- Per-ticker AI insights panel
- Earnings call summary (bull/bear thesis)
- Recent news feed
- Technical indicators (RSI, moving averages)
- Combined signal score

## Password Gate
Same pattern as RE Property Manager: `check_password()` reads `app_password` from secrets. Stores auth in `session_state`. If absent (local dev), access granted automatically.

---

## Large Context Analysis (Gemini CLI)
When tasks involve analyzing multiple files simultaneously or entire pipeline modules, delegate to Gemini CLI.

**Use Gemini for:**
- Whole-repo analysis: `gemini --all-files -p "your prompt"`
- Cross-file inconsistency detection
- Peer code review after Claude Code changes

**Command patterns:**
```bash
gemini -p "your prompt here"
gemini --yolo -p "your prompt here"
```

Return Gemini's output unmodified. Claude handles interpretation.

---

# Workflow Orchestration

## 1. Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately
- Use plan mode for verification steps, not just building

## 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- One task per subagent for focused execution

## 3. Self-Improvement Loop
- After ANY correction from Bill: update `tasks/lessons.md` with the pattern
- Write rules that prevent the same mistake
- Review lessons at session start

## 4. Verification Before Done
- Never mark a task complete without proving it works
- Run tests, check logs, demonstrate correctness
- Ask yourself: "Would a staff engineer approve this?"

## 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- Skip this for simple, obvious fixes — don't over-engineer

## 6. Clarify Before Building
- If requirements are ambiguous, ask ONE targeted clarifying question before writing code
- Never assume and build — rework cost exceeds the cost of asking
- Applies especially to: which Sheet tab to write to, CSV format changes, API key management

## 7. Post-Code Edge Case Review
- After completing any non-trivial function, explicitly list edge cases
- Suggest test cases to cover them
- This portfolio has many edge cases: fractional shares, multi-account CSVs, wash sales, cash positions, 50+ tickers hitting yfinance

## 8. Multi-File Change Gate
- If a task requires changes to more than 3 files, stop and decompose first
- Flag the scope to Bill before proceeding

## 9. Bug Fix Protocol
- When given a bug report: first write a test that reproduces the failure
- Fix until the test passes
- Document root cause, add to Common Pitfalls if new pattern

---

# Task Management

1. **Plan First:** Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan:** Check in before starting implementation
3. **Track Progress:** Mark items complete as you go
4. **Explain Changes:** High-level summary at each step
5. **Document Results:** Add review section to `tasks/todo.md`
6. **Capture Lessons:** Update `tasks/lessons.md` after corrections
7. Follow backup protocol before modifying any existing file. Update CHANGELOG.md after every working change.
8. **Every CHANGELOG entry must include a `Status:` line** describing what is currently safe to run.

---

# Core Principles

- **Simplicity First:** Make every change as simple as possible. Impact minimal code.
- **No Laziness:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact:** Changes should only touch what's necessary.
- **Config Over Code:** Business logic in Google Sheets, infrastructure in config.py.
- **Spec Before Code:** Understand the full context before writing. Search project files first.
- **No Auto-Trading:** This system provides information only. Never connect to trading APIs.
- **Tax Awareness:** Every position display should surface cost basis and holding period implications.
- **Port, Don't Reinvent:** Colab V3.2 is the working prototype. Extract and refactor its logic into production modules.

---

# Common Pitfalls (Anticipated + Learned from RE Project)

1. **Schwab CSV is multi-account format.** Don't assume a single header row. Scan for the "Symbol" row dynamically. Account type labels are embedded between position rows.
2. **Schwab CSV may have a BOM marker.** Use `encoding='utf-8-sig'` or `header=None` with dynamic detection.
3. **Comma-formatted amounts and parentheses negatives.** `"3,535.86"` and `"(694.72)"` need the `clean_numeric()` function from Colab.
4. **Cash sweep is not an investment.** `CASH_MANUAL` and `QACDS` should be excluded from allocation percentages and performance calculations. Track separately. Beta = 0.
5. **Fractional shares are real.** Don't round quantities — Schwab supports fractional share purchases.
6. **Wash sale tracking matters.** Bill is a CPA — surface wash sale flags prominently. Affects tax lot decisions.
7. **Don't write cell-by-cell to Google Sheets.** Always batch. Rate limits apply. Same lesson as RE project.
8. **Cast pandas types to native Python before gspread calls.** `numpy.float64` is not JSON serializable.
9. **yfinance rate limits are real.** Cache aggressively (TTL 300s+). Use bulk download. Limit enrichment to top 20.
10. **50+ positions means UI must handle density.** Pagination, filtering, sorting are not optional. Don't try to show everything at once.
11. **This is NOT the reserve account.** The reserve account (Schwab ...8895, ~$12.5K) is tracked in the RE project. This project tracks the primary investment account (~$480K). Different CSVs, different parsers, different purposes.
12. **Beta calculation needs sufficient data.** Colab requires 30+ common data points between ticker and SPY returns. Fall back to beta=1.0 for new/illiquid tickers.
13. **CAPM projection uses scipy.stats.norm.** The Colab uses Z-scores at 10th and 90th percentile for bad/good case. Risk-free rate and market premium should be configurable, not hardcoded.
14. **pandas version matters.** Streamlit Cloud pins Python version. Test locally with matching version.
15. **Sleep BEFORE reads, not after writes.** Same lesson as RE project — pre-read sleep prevents quota exhaustion.

## Known Portfolio Edge Cases
- **UNH at 9% weight** — single-position concentration risk. Surface this in risk analytics.
- **CRWV (CoreWeave)** — recent IPO, may not have 1yr of yfinance history. Handle missing data gracefully.
- **BABA** — ADR, may have data quirks in yfinance. Description includes "SPONSORED ADR" with complex naming.
- **ET (Energy Transfer LP)** — limited partnership, K-1 tax implications, very high yield. Dividend yield parsing may differ from standard equities.
- **JPIE** — income ETF, yield is the primary value proposition. Ensure yield calculation is accurate.
- **SPY at 0.00003 shares** — dust position from the reserve account export. May appear in primary account CSV too. Handle gracefully.
