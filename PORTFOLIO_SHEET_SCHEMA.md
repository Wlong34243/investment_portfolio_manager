# PORTFOLIO_SHEET_SCHEMA.md
# Investment Portfolio Manager — Google Sheet Schema
# Authoritative cell-level schema — consult before any structural change

## Sheet: Portfolio (ID: TBD)

---

### Tab: Holdings_Current
**Purpose:** Latest snapshot of every position. Overwritten on each import.

**Source:** May be populated via Schwab API (`source = 'schwab_api'`) or manual CSV upload (`source = 'csv'`). The tab schema is identical regardless of source — both paths flow through `pipeline.normalize_positions()`.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Ticker | String | `VTI` | Primary key. `CASH_MANUAL` = manual cash entry |
| B | Description | String | `Vanguard Total Stock Market ETF` | From Schwab CSV or manual |
| C | Asset Class | String | `Equities` | Mapped via ASSET_CLASS_MAP |
| D | Asset Strategy | String | `US Large Cap Equity` | Direct from Schwab CSV |
| E | Quantity | Float | `48` | Fractional shares OK (e.g., 100.2781) |
| F | Price | Float | `313.09` | Last market price |
| G | Market Value | Float | `15061.44` | From CSV or quantity × price |
| H | Cost Basis | Float | `14500.00` | Total cost (0 for CASH_MANUAL) |
| I | Unit Cost | Float | `302.08` | Per-share cost basis |
| J | Unrealized G/L | Float | `561.44` | = Market Value − Cost Basis |
| K | Unrealized G/L % | Float | `3.87` | As percentage |
| L | Est Annual Income | Float | `41.46` | Estimated dividends |
| M | Dividend Yield | Float | `1.52` | Yield percentage |
| N | Acquisition Date | Date/String | `03/15/2025` | May be blank |
| O | Wash Sale | Boolean | `FALSE` | From Schwab Disclaimers column |
| P | Is Cash | Boolean | `FALSE` | TRUE for CASH_MANUAL, QACDS |
| Q | Weight | Float | `3.14` | Position as % of total portfolio |
| R | Import Date | Date | `2026-03-29` | When this snapshot was taken |
| S | Fingerprint | String | `2026-03-29\|VTI\|48\|15061.44` | Dedup key |

**Row 1:** Headers (frozen)
**Row 2+:** One row per position, sorted by Market Value descending
**Write pattern:** Clear all data rows, write fresh on each import. Header row preserved.

---

### Tab: Holdings_History
**Purpose:** Append-only log of every position from every import. Enables historical tracking.

**Schema:** Identical to Holdings_Current columns A–S.

**Write pattern:** Append only. Never delete rows. Dedup by fingerprint before appending.

---

### Tab: Daily_Snapshots
**Purpose:** One row per day showing portfolio totals. Used for performance charts.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Date | Date | `2026-03-29` | Primary key |
| B | Total Value | Float | `480234.50` | Sum of all position values incl. cash |
| C | Total Cost | Float | `465000.00` | Sum of all cost bases |
| D | Total Unrealized G/L | Float | `15234.50` | = Total Value − Total Cost |
| E | Cash Value | Float | `10000.00` | CASH_MANUAL + QACDS |
| F | Invested Value | Float | `470234.50` | = Total Value − Cash Value |
| G | Position Count | Integer | `52` | Including cash positions |
| H | Blended Yield | Float | `1.77` | Portfolio-wide weighted yield |
| I | Import Timestamp | DateTime | `2026-03-29 10:30:00` | Full timestamp of import |
| J | Fingerprint | String | `2026-03-29\|52\|480234.50` | Dedup key |

**Row 1:** Headers (frozen)
**Row 2+:** One row per snapshot date, newest at bottom
**Write pattern:** Append only. Check fingerprint before inserting — same date = skip.

---

### Tab: Transactions (Phase 3)
**Purpose:** Trade history from Schwab transaction CSV.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Trade Date | Date | `2026-03-15` | |
| B | Settlement Date | Date | `2026-03-17` | T+2 |
| C | Ticker | String | `VTI` | |
| D | Description | String | `Vanguard Total Stock Market ETF` | |
| E | Action | String | `Buy` / `Sell` / `Dividend` / `Transfer` | |
| F | Quantity | Float | `5` | Negative for sells |
| G | Price | Float | `310.50` | Per share |
| H | Amount | Float | `-1552.50` | Gross amount |
| I | Fees | Float | `0` | Commission + fees |
| J | Net Amount | Float | `-1552.50` | Amount − Fees |
| K | Account | String | `Individual` | Which account section |
| L | Fingerprint | String | `2026-03-15\|VTI\|Buy\|-1552.50` | Dedup key |

**Write pattern:** Append only with fingerprint dedup.

---

### Tab: Target_Allocation
**Purpose:** Bill's target allocation model. Manual entry only.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Asset Class | String | `Equities` | Must match ASSET_CLASS_MAP values |
| B | Asset Strategy | String | `US Large Cap Equity` | Finer granularity |
| C | Target % | Float | `40` | Target allocation percentage |
| D | Min % | Float | `35` | Drift alert if below |
| E | Max % | Float | `45` | Drift alert if above |
| F | Notes | String | `Core position — VTI/SPY` | |

**Write pattern:** Manual only. App reads but never writes.

---

### Tab: AI_Suggested_Allocation
**Purpose:** AI-generated allocation suggestions from podcast analysis. Bill reviews
and manually promotes to Target_Allocation when accepted. App writes; Bill decides.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Date | Date | `2026-04-05` | When the analysis was generated |
| B | Source | String | `Forward Guidance EP 412` | Podcast name + episode identifier |
| C | Asset Class | String | `Technology` | Standard GICS sector or macro category (e.g., Technology, Utilities, Industrials, Materials, Real Estate, Fixed Income, Cash). AI may introduce new standard sectors for displacement opportunities. |
| D | Asset Strategy | String | `Defensive AI beneficiaries` | Thesis behind this allocation |
| E | Target % | Float | `25` | Suggested allocation. All rows must sum to 100 |
| F | Min % | Float | `20` | Lower drift band |
| G | Max % | Float | `30` | Upper drift band |
| H | Confidence | String | `High` | High / Medium / Low |
| I | Notes | String | `Capex cycle favors...` | Supporting rationale from transcript |
| J | Executive Summary | String | `Risk-off rotation...` | Same across all rows in a batch |
| K | Fingerprint | String | `2026-04-05\|Forward Guidance EP 412\|Technology` | Dedup key |

**Row 1:** Headers (frozen)
**Row 2+:** Latest AI analysis. Previous data cleared before each new write.
**Write pattern:** Clear data rows, write fresh batch. Archived to Logs tab before overwrite.

---

### Tab: Risk_Metrics (Phase 2)
**Purpose:** Snapshots of portfolio risk analytics over time.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Date | Date | `2026-03-29` | Snapshot date |
| B | Portfolio Beta | Float | `0.85` | Weighted avg beta (cash = 0) |
| C | Top Position Conc % | Float | `9.0` | Largest single position weight |
| D | Top Position Ticker | String | `UNH` | Which ticker is largest |
| E | Top Sector Conc % | Float | `28.5` | Largest sector weight |
| F | Top Sector | String | `Technology` | Which sector is largest |
| G | Estimated VaR 95% | Float | `-38400` | 95% Value at Risk (1yr) |
| H | Stress -10% Impact | Float | `-40820` | Beta-adjusted impact |
| I | Fingerprint | String | `2026-03-29\|0.85\|9.0` | Dedup key |

**Write pattern:** Append only per calculation run.

---

### Tab: Income_Tracking (Phase 2)
**Purpose:** Dividend/yield snapshots over time.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Date | Date | `2026-03-29` | Snapshot date |
| B | Projected Annual Income | Float | `8500.00` | Sum of all yield × value |
| C | Blended Yield % | Float | `1.77` | Portfolio-weighted yield |
| D | Top Generator Ticker | String | `JPIE` | Highest absolute income |
| E | Top Generator Income | Float | `1200.00` | Highest absolute income $ |
| F | Cash Yield Contribution | Float | `450.00` | Cash × cash yield |
| G | Position Count | Integer | `52` | Including cash positions |
| H | Fingerprint | String | `2026-03-29\|52\|8500.00` | Dedup key |

**Write pattern:** Append only per snapshot.

---

### Tab: Config
**Purpose:** App configuration that Bill can modify without touching code.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Key | String | `rebalance_threshold_pct` | Config key name |
| B | Value | String | `5` | Config value (app parses to correct type) |
| C | Description | String | `Drift % that triggers rebalance alert` | Human-readable docs |

**Expected keys:**
- `rebalance_threshold_pct` — Drift % to trigger alert (default: 5)
- `cash_yield_pct` — Current money market yield (default: 4.5)
- `benchmark_ticker` — Primary benchmark (default: SPY)
- `tax_rate_short_term` — Short-term cap gains rate for tax impact estimates
- `tax_rate_long_term` — Long-term cap gains rate
- `contribution_target_monthly` — Target monthly contribution amount
- `risk_free_rate` — T-bill rate for CAPM (default: 0.045)
- `market_premium` — Equity risk premium for CAPM (default: 0.055)

**Write pattern:** Manual only. App reads but never writes.

---

### Tab: Decision_Log
**Purpose:** The investor's memory layer. Logs rationales for trades and
strategic holds. Append-only — never overwrite or delete rows.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Date | Date | `2026-04-10` | Date of the decision |
| B | Timestamp | DateTime | `2026-04-10 10:30:15` | Exact time of journal entry (dedup key component) |
| C | Tickers Involved | String | `NVDA, AAPL` | Comma-separated tickers |
| D | Action | String | `Buy` | Buy / Sell / Hold / Rebalance / Watch |
| E | Market Context | String | `SPY @ $510.20, VIX @ 18.5` | Auto-fetched SPY price + optional manual notes |
| F | Rationale | String | `Trimming tech after 3 consecutive...` | The "Why" — what must be true for this decision to work |
| G | Tags | String | `Macro, Tech, Rebalance` | Comma-separated, for future querying and agent context |
| H | Fingerprint | String | `2026-04-10\|10:30:15\|Buy\|NVDA, AAPL` | Dedup key using timestamp to allow multiple entries per day |

**Row 1:** Headers (frozen)
**Row 2+:** One row per journal entry, newest at bottom
**Write pattern:** Append only via Streamlit Journal UI. Never delete or overwrite.

---

### Tab: Valuation_Card
**Purpose:** Fundamental and technical valuation analysis. Overwritten on each run.

**Source:** Derived from Market Bundle + Vault Bundle (via Composite Bundle) + yfinance.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Ticker | String | `AAPL` | Primary key |
| B | Name | String | `Apple Inc.` | From yfinance |
| C | Sector | String | `Technology` | From yfinance |
| D | Market Cap | Float | `3000000000000` | From FMP / yf |
| E | Price | Float | `185.20` | Current market price |
| F | Trim Target | Float | `220.00` | Sourced from `{TICKER}_thesis.md` triggers. Empty = no trigger. |
| G | Add Target | Float | `150.00` | Sourced from `{TICKER}_thesis.md` triggers. Empty = no trigger. |
| H | Trailing P/E | Float | `28.5` | |
| I | Forward P/E (FMP) | Float | `25.2` | |
| J | Forward P/E (yf) | Float | `26.0` | |
| K | P/B | Float | `45.0` | |
| L | PEG | Float | `1.5` | |
| M | Gross Margin | Float | `0.45` | |
| N | ROIC | Float | `0.35` | |
| O | D/E | Float | `0.15` | |
| P | Rev Growth YoY | Float | `0.05` | |
| Q | Div Yield % | Float | `0.005` | |
| R | Payout Ratio | Float | `0.15` | |
| S | 52w Low | Float | `125.0` | |
| T | 52w High | Float | `199.0` | |
| U | 52w Position % | Float | `0.85` | |
| V | Discount from 52w High % | Float | `0.07` | |
| W | Valuation_Signal | String | `FAIR` | Logic: CHEAP (<15 P/E) / RICH (>30) / FAIR / MONITOR |
| X | FMP_Data_Available | Boolean | `TRUE` | |
| Y | Last Updated | String | `2026-04-23 10:30` | |

**Write pattern:** Clear tab, write fresh batch. derive from Composite Bundle.

---

### Tab: Decision_View
**Purpose:** High-level dashboard combining holdings and agent signals. Overwritten on each run.

**Source:** Derived from Holdings_Current + Valuation_Card + Agent_Outputs + Composite Bundle.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Ticker | String | `UNH` | Primary key |
| B | Weight % | Float | `5.2` | From Holdings_Current |
| C | Market Value | Float | `25000.0` | |
| D | Unreal G/L % | Float | `12.5` | |
| E | Daily Chg % | Float | `-1.2` | |
| F | Price | Float | `305.50` | Current market price |
| G | Trim Target | Float | `380.00` | Sourced from `{TICKER}_thesis.md` triggers. Empty = no trigger. |
| H | Add Target | Float | `280.00` | Sourced from `{TICKER}_thesis.md` triggers. Empty = no trigger. |
| I | Fwd P/E | Float | `16.5` | From Valuation_Card |
| J | 52w Pos % | Float | `0.35` | From Valuation_Card |
| K | Disc from High % | Float | `0.45` | From Valuation_Card |
| L | Valuation Signal | String | `BUY` | From Agent_Outputs (valuation) |
| M | Top Rationale | String | `Regulatory risk fully priced...` | Highest severity rationale across agents |

**Write pattern:** Clear tab, write fresh batch. derive from Composite Bundle + Sheets.

---

## Cross-Reference: RE Dashboard Sheet (READ ONLY)
**Sheet ID:** `1DXuY1iBo2GqZCCSZ7OrUa4iaunb5s8Kf1Rms8Z237rQ`

For unified net worth view (Phase 5), read these values:
- **Performance tab Row 46–57:** Property-level NOI data
- **Debt_Schedule B19:B21:** Monthly P&I, total debt service, outstanding balance
- **CapEx_Inventory:** Reserve needs

**NEVER write to this sheet from the Investment Portfolio Manager.**

---

## 🛠️ Fingerprint Formats
Authoritative list of deduplication keys used across the system to prevent duplicate appends.

| Tab | Format | Logic / Purpose |
|-----|--------|-----------------|
| `Holdings_History` | `import_date\|ticker\|quantity` | Unique position snapshot per import. |
| `Daily_Snapshots` | `import_date\|pos_count\|total_value` | Prevents duplicate snapshots if re-running same CSV with same cash. |
| `Transactions` | `date\|ticker\|action\|net_amount` | Prevents duplicate trade entries on overlapping CSV uploads. |
| `Realized_GL` | `closed_dt\|ticker\|opened_dt\|qty\|proceeds\|cost` | Exact lot match for tax ledger. |
| `Income_Tracking` | `import_date\|pos_count\|projected_income` | One income snapshot per unique portfolio state per day. |
| `Risk_Metrics` | `import_date\|beta\|top_pos_pct` | One risk profile per unique portfolio state per day. |
| `AI_Suggested_Allocation` | `date\|source\|asset_class` | One row per sector per podcast analysis. |
| `Decision_Log` | `date\|timestamp\|action\|tickers` | Timestamp prevents dedup collision on same-day entries. |

