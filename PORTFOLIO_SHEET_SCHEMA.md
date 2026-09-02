# PORTFOLIO_SHEET_SCHEMA.md
# Investment Portfolio Manager — Google Sheet Schema
# Authoritative cell-level schema — Consolidated Version (Post-Phase 5)

## Tab Authority Matrix
This matrix defines which system component is authorized to write to each tab.

| Tab Name | Authority | Write Pattern | Purpose |
| :--- | :--- | :--- | :--- |
| **0_DASHBOARD** | Pipeline | Clear-and-rebuild | Command Center — single-screen daily view |
| **Decision_View** | Pipeline | Clear-and-rebuild | Primary morning scan dashboard |
| **Valuation_Card** | Pipeline | Clear-and-rebuild | Fundamental/Technical valuation lookup |
| **Tax_Control** | Pipeline | Clear-and-rebuild | YTD tax posture and offset planning |
| **Rotation_Review** | Pipeline | Clear-and-rebuild | Post-hoc performance attribution |
| **Holdings_Current** | Pipeline | Clear-and-rebuild | Latest broker snapshot |
| **Holdings_History** | Pipeline | Append with dedup | Historical position log |
| **Daily_Snapshots** | Pipeline | Append with dedup | Portfolio total value over time |
| **Transactions** | Pipeline | Append with dedup | Broker trade history |
| **Risk_Metrics** | Pipeline (`pm build risk-metrics`) | Clear-and-rebuild | Per-ticker beta/vol/drawdown + portfolio summary row (`Portfolio Beta` last) |
| **Income_Tracking** | Pipeline (`pm build income-tracking`) | Clear-and-rebuild | Realised DIVIDEND_OR_INTEREST + TTM summary |
| **Cash_Flows** | Pipeline (`pm build cash-flows`) | Append with fingerprint dedup | External ACH/wire/journal flows (no TWR) |
| **Trade_Log_Staging**| Pipeline | Append with dedup | Queue for new rotation candidates |
| **Trade_Log** | Manual/CLI | Append with dedup | Enriched and approved rotations |
| **Decision_Log** | Manual/CLI | Append | Qualitative decision journal |
| **AI_Suggested_Alloc**| AI Sandbox | Clear-and-rebuild | Suggestions from external analysis |
| **Agent_Outputs** | AI Sandbox | Archive-and-overwrite | Deprecated agent signals (Crosshairs no longer joins) |
| **Agent_Outputs_Archive** | AI Sandbox | Append | Archived Agent_Outputs runs |
| **Realized_GL** | Manual Import| Append with dedup | Historical tax lot detail |
| **Target_Allocation**| Manual Only | Manual | Strategic model weights |
| **Config** | Manual Only | Manual | System rates and thresholds |
| **Logs** | Pipeline | Append | System audit trail |
| **Disagreements** | Manual Only | Manual | Log of LLM vs Human drift |

### Tab roles (PortfolioStore migration, 2026-08-20)

| Role | Tabs | Notes |
| :--- | :--- | :--- |
| **Authoritative** | Holdings_Current, Transactions, Trade_Log, Realized_GL | Broker/manual truth; dual-written to SQLite on `--live` |
| **Manual** | Target_Allocation, Config, Disagreements, Decision_Log, **Precommitments** | Humans only; agents never write Target_Allocation |
| **Computed** | 0_DASHBOARD, Valuation_Card, Decision_View, Tax_Control, Rotation_Review, Trade_Log_Staging, Risk/Income/History/Snapshots | Rebuildable; SQLite shadows Tax/Decision/Rotation/Holdings |
| **Sandbox** | Agent_Outputs*, AI_Suggested_Allocation | Non-authoritative |

Local ledger: `data/portfolio_store.db` via `core/store`. **Phase 1 spine** = transactions + realized_gl + tax_control (holdings is cache-only). Local-only tables (not Sheet mirrors): `retrieval_log`, `ui_runs` (desk Tier 0 launcher history), evidence append-only tables. Backup: `pm store backup`. Monitoring: static HTML → Drive (`pm store publish-cockpit`), not localhost. Sheets remains phone cockpit for Tax/CC until publish is trusted.

---

---

## Thesis frontmatter (vault/theses/*_thesis.md)

| Key | Written by | Meaning |
| :--- | :--- | :--- |
| `last_reviewed` | Morning thesis sync (`write_thesis_updates`) | **Last synced** from Sheets — not Bill's last review |
| `last_ratified` | Desk ratification only (`POST /decision/ratify`) | Last date Bill confirmed a decision record for this ticker |

---

## Tab Definitions

### 0_DASHBOARD (Command Center)
**Purpose:** Single-screen at-a-glance view of portfolio state. No original computation — aggregates values from other tabs.
**Authority:** Pipeline (`tasks/build_command_center.py`, called by `pm refresh dashboard` and `pm morning`)
**Write pattern:** Clear-and-rebuild. No formulas, hard values only.

Layout:
- Rows 1-2:    Title + timestamp
- Rows 3-4:    Headline KPIs (Total Value, Cash %, Day Change, MTD/YTD, vs. SPY)
- Rows 6-8:    Tax Posture (mirrors Tax_Control KPI strip)
- Rows 10-11:  Risk Snapshot (Beta, Top Position, Top Sector, Stress -10%)
- Rows 13-19:  Top 5 Positions with Trim/Add target distances
- Rows 21-30:  Drift Alerts (Asset Classes outside ±REBALANCE_THRESHOLD_PCT)
- Rows 32-34:  System Health (Last Refresh, Bundle Hash, Schwab Token, FMP Cache Age)

---

### Holdings_Current
**Purpose:** Latest snapshot of every position. Overwritten on each import.
**Authority:** Pipeline (`manager.py snapshot`)

| Column | Header | Type | Example | Notes |
| :--- | :--- | :--- | :--- | :--- |
| A | Ticker | String | `VTI` | Primary key |
| B | Description | String | `Vanguard Total Stock Market` | |
| C | Asset Class | String | `Equities` | |
| D | Asset Strategy | String | `GARP` | Sourced from `styles.json` |
| E | Quantity | Float | `48` | |
| F | Price | Float | `313.09` | |
| G | Market Value | Float | `15028.32` | |
| H | Cost Basis | Float | `14500.00` | |
| I | Unit Cost | Float | `302.08` | |
| J | Unrealized G/L | Float | `528.32` | |
| K | Unrealized G/L % | Float | `3.6%` | |
| L | Est Annual Income| Float | | |
| M | Dividend Yield | Float | | |
| N | Acquisition Date | Date | | |
| O | Wash Sale | Boolean| | |
| P | Is Cash | Boolean| | |
| Q | Weight | Float | | |
| R | Import Date | Date | | |
| S | Fingerprint | String | | `import_date\|ticker\|quantity` |

*Since Phase 1. Updated with styles in Phase 4.*

---

### Valuation_Card
**Purpose:** Fundamental and technical valuation analysis.
**Authority:** Pipeline (`manager.py dashboard refresh`)

| Column | Header | Type | Example | Notes |
| :--- | :--- | :--- | :--- | :--- |
| A | Ticker | String | `AAPL` | |
| B | Name | String | | |
| C | Sector | String | | |
| D | Market Cap | Float | | |
| E | Price | Float | | |
| F | Trim Target | Float | `220.00` | Sourced from thesis triggers |
| G | Add Target | Float | `150.00` | Sourced from thesis triggers |
| H-V | Fundamentals | Float | | P/E, PEG, ROIC, Margins, etc. |
| W | Valuation Signal | String| `FAIR` | Logic-based status |
| Y | Last Updated | String | | |

*Since Phase 1. Updated with thesis triggers in Phase 2.*

---

### Decision_View
**Purpose:** Full ranked Crosshairs list + pending precommitment firings.
**Authority:** Pipeline (`tasks/build_decision_view.py` — clear-and-rebuild)

| Column | Header | Notes |
| :--- | :--- | :--- |
| A–J | (Crosshairs) | Ticker, Reason, MV, Wt%, Price, Trim, Add, distances, Rationale |
| K | Days_To_LT | Trim-side rows only (`NEAR_TRIM`, `HOLD_TAX`) |
| L | Wash_Window | `OPEN through YYYY-MM-DD` or blank |
| M | Est_Tax_Low (ESTIMATE) | Prompt 9 labelled bound — not authoritative |
| N | Est_Tax_High (ESTIMATE) | Prompt 9 labelled bound — not authoritative |

Amber conditional formatting: non-blank wash window; `Days_To_LT` ≤ 30.

---

### Precommitments
**Purpose:** Declare a thesis-band intention before it fires — typed on phone, ingested by morning.
**Authority:** **Manual** (Bill writes A–G). Pipeline **append-and-mark only** on H–J — **never clear-and-rebuild.**

| Col | Header | Writer |
| :--- | :--- | :--- |
| A | Date_Declared | Bill → becomes `declared_at` |
| B | Ticker | Bill |
| C | Trigger_Type | Bill |
| D | Side | Bill (`trim` / `add`) |
| E | Level | Bill |
| F | Intended_Action | Bill |
| G | Note | Bill |
| H | Ingested_At | Pipeline |
| I | Precommit_ID | Pipeline |
| J | Status | Pipeline (`open` / `fired` / `closed_*`) |

Rows with blank `Ingested_At` are ingested by `tasks/ingest_precommitments.py` immediately before precommit firing detection in `pm morning`. Blank `Date_Declared` → skip and report (no date substitution).

---

### Tax_Control
**Purpose:** Compact tax-state view: realized posture and harvesting planning.
**Authority:** Pipeline (`manager.py tax refresh`)

**Layout Zones:**
- **KPI Strip (Rows 1-3):** Net ST, Net LT, Disallowed Wash Loss, Est Tax, Offset Capacity.
- **Bridge Row (Rows 5-7):** ST/LT Gains vs Losses comparison.
- **Lots Table (Rows 9+):** Tax-relevant realized lots with wash sales pinned to top.

*Since Phase 3.*

---

### Trade_Log
**Purpose:** Bill's "permanent record" of accepted rotations with captured context.
**Authority:** Manual promotion via CLI (`manager.py journal promote`)

| Column | Header | Type | Example | Notes |
| :--- | :--- | :--- | :--- | :--- |
| A | Date | Date | | Date of trade cluster |
| B | Sell_Ticker | String | | |
| C | Sell_Proceeds | Float | | |
| D | Buy_Ticker | String | | |
| E | Buy_Amount | Float | | |
| F | Implicit_Bet | String | | **Bill's words only** — never machine-written |
| G | Thesis_Brief | String | | Link to thesis docs |
| H | Rotation_Type | String | | upgrade / rebalance / tax_loss |
| I-N | Technical Snap | Float/Str| | RSI, Trend, MA200 at trade time |
| O | Trade_Log_ID | String | | |
| P | Fingerprint | String | | |
| Q | Proposed_Bet | String | | Machine proposal text (retained on edit). Appended 2026-08-27 after P so A–P stay stable. |
| R | Rationale_Provenance | String | | `declared_before` \| `reconstructed_after` |
| S | Rationale_Evidence | String | | Citation tokens for the proposal |

*Since Phase 5. Rationale columns Q–S: Instrument prompt 7, 2026-08-27.*

---

### Rotation_Review
**Purpose:** Post-hoc performance attribution for rotations.
**Authority:** Pipeline (`manager.py trade review`)

| Column | Header | Type | Notes |
| :--- | :--- | :--- | :--- |
| A-J | Context | | Copied from Trade_Log |
| K-P | Returns | Float | Sell/Buy Return at 30/90/180 trading days |
| Q-S | Pair Returns | Float | Buy Return - Sell Return (Additive check) |
| T | As Of | Date | Calculation timestamp |
| U | Fingerprint | String | `Trade_Log_ID\|Attribution_As_Of` |
| V+ | Basket cols | … | Status, betas, residual/explained, benches (see `config.ROTATION_REVIEW_COLUMNS`) |
| last | Price_Source | String | Gate C: `yfinance\|frozen_pre_schwab_2026-08-25` on frozen rows; live `schwab`/`yfinance`/`schwab+yfinance` on recomputed |

*Since Phase 5; Price_Source Gate C 2026-08-25.*

---

### Trade_Log_Staging
**Purpose:** Queue for rotation candidates derived from transactions.
**Authority:** Pipeline (`tasks/derive_rotations.py`)

*Same columns as Trade_Log plus Status and Cluster metadata.*

---

### Transactions
**Purpose:** Broker trade history.
**Authority:** Pipeline (`manager.py sync transactions`)

| Column | Header | Example |
| :--- | :--- | :--- |
| A | Trade Date | |
| B | Settlement Date| |
| C | Ticker | |
| J | Net Amount | |
| L | Fingerprint | `date\|ticker\|action\|net_amount` |

---

### Target_Allocation & Config
**Purpose:** Manual control surfaces for model weights and system constants.
**Authority:** Manual Only.

---

### Income_Tracking
**Purpose:** Realised DIVIDEND_OR_INTEREST (Block A) + TTM summary by ticker (Block B).
**Authority:** Pipeline (`pm build income-tracking`). Clear-and-rebuild. `--live` required.
**Source:** Schwab typed transaction fetch; Est Annual Income from positions. Qualified column only when `qualifiedDividend` is present on the payload (not inferred).
**Note:** Schwab often omits equity symbols on dividend payloads; writer resolves description → ticker against holdings / alias table; unresolved rows tagged `UNRESOLVED`.

### Cash_Flows
**Purpose:** External cash movements (ACH/wire/journal/cash receipt-disbursement) for future TWR/IRR input. No return figure computed here.
**Authority:** Pipeline (`pm build cash-flows`). Append with fingerprint dedup. `--live` required.
**Columns:** Date, Account, Type, Amount (signed, + into portfolio), Description, Transaction ID, Classification (`external` / `internal` / `unclassified`), Fingerprint.

### Risk_Metrics
**Purpose:** Descriptive per-ticker risk stats + one portfolio-summary row (`Ticker=_PORTFOLIO_`) **last** so dashboard `_compute_beta` can read `[-1]["Portfolio Beta"]`.
**Authority:** Pipeline (`pm build risk-metrics`; morning STEP 5 sub-step). Clear-and-rebuild. `--live` required.
**Bars:** `utils.price_history.get_bars` — does **not** call `build_price_histories`. Does **not** write capm_projection / stress / van_tharp (Hard Rule 4).

---

## 🛠️ Fingerprint Formats
Standardized keys used to prevent duplicate data entry.

| Tab | Format |
| :--- | :--- |
| `Holdings_History` | `import_date\|ticker\|quantity` |
| `Daily_Snapshots` | `import_date\|pos_count\|total_value` |
| `Transactions` | `date\|ticker\|action\|net_amount` |
| `Realized_GL` | `closed_dt\|ticker\|opened_dt\|qty\|proceeds\|cost` |
| `Income_Tracking` | clear-and-rebuild (no append fingerprint) |
| `Cash_Flows` | sha256 prefix of Date\|Account\|Type\|Amount\|Transaction ID |
| `Risk_Metrics` | clear-and-rebuild (portfolio row last) |
| `Rotation_Review` | `Trade_Log_ID\|Attribution_As_Of` |
| `Decision_Log` | `date\|timestamp\|action\|tickers` |
