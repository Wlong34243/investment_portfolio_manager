# PORTFOLIO_SHEET_SCHEMA.md
# Investment Portfolio Manager — Google Sheet Schema
# Authoritative cell-level schema — consult before any structural change

## Sheet: Portfolio (ID: TBD)

---

### Tab: Holdings_Current
**Purpose:** Latest snapshot of every position. Overwritten on each CSV import.

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
| H | Fingerprint | String | `2026-03-29\|480234.50` | Dedup key |

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
| H | Amount | Float | `-1552.50` | Negative = outflow |
| I | Fees | Float | `0` | Commission + fees |
| J | Net Amount | Float | `-1552.50` | Amount − Fees |
| K | Account | String | `Individual` | Which account section |
| L | Fingerprint | String | `2026-03-15\|VTI\|Buy\|5\|310.50` | Dedup key |

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
| G | Fingerprint | String | `2026-03-29\|8500.00\|1.77` | Dedup key |

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

## Cross-Reference: RE Dashboard Sheet (READ ONLY)
**Sheet ID:** `1DXuY1iBo2GqZCCSZ7OrUa4iaunb5s8Kf1Rms8Z237rQ`

For unified net worth view (Phase 5), read these values:
- **Performance tab Row 46–57:** Property-level NOI data
- **Debt_Schedule B19:B21:** Monthly P&I, total debt service, outstanding balance
- **CapEx_Inventory:** Reserve needs

**NEVER write to this sheet from the Investment Portfolio Manager.**
