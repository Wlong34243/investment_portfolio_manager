# PORTFOLIO_SHEET_SCHEMA.md
# Investment Portfolio Manager — Google Sheet Schema
# Authoritative cell-level schema — Consolidated Version (Post-Phase 5)

## Tab Authority Matrix
This matrix defines which system component is authorized to write to each tab.

| Tab Name | Authority | Write Pattern | Purpose |
| :--- | :--- | :--- | :--- |
| **Decision_View** | Pipeline | Clear-and-rebuild | Primary morning scan dashboard |
| **Valuation_Card** | Pipeline | Clear-and-rebuild | Fundamental/Technical valuation lookup |
| **Tax_Control** | Pipeline | Clear-and-rebuild | YTD tax posture and offset planning |
| **Rotation_Review** | Pipeline | Clear-and-rebuild | Post-hoc performance attribution |
| **Holdings_Current** | Pipeline | Clear-and-rebuild | Latest broker snapshot |
| **Holdings_History** | Pipeline | Append with dedup | Historical position log |
| **Daily_Snapshots** | Pipeline | Append with dedup | Portfolio total value over time |
| **Transactions** | Pipeline | Append with dedup | Broker trade history |
| **Risk_Metrics** | Pipeline | Append with dedup | Portfolio Beta / VaR history |
| **Income_Tracking** | Pipeline | Append with dedup | Dividend projection history |
| **Trade_Log_Staging**| Pipeline | Append with dedup | Queue for new rotation candidates |
| **Trade_Log** | Manual/CLI | Append with dedup | Enriched and approved rotations |
| **Decision_Log** | Manual/CLI | Append | Qualitative decision journal |
| **AI_Suggested_Alloc**| AI Sandbox | Clear-and-rebuild | Suggestions from external analysis |
| **Realized_GL** | Manual Import| Append with dedup | Historical tax lot detail |
| **Target_Allocation**| Manual Only | Manual | Strategic model weights |
| **Config** | Manual Only | Manual | System rates and thresholds |
| **Logs** | Pipeline | Append | System audit trail |
| **Disagreements** | Manual Only | Manual | Log of LLM vs Human drift |

---

## Tab Definitions

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
**Purpose:** High-level dashboard combining holdings and signals.
**Authority:** Pipeline (`manager.py dashboard refresh`)

| Column | Header | Type | Example | Notes |
| :--- | :--- | :--- | :--- | :--- |
| A | Ticker | String | `UNH` | |
| B | Weight % | Float | | |
| C | Market Value | Float | | |
| D | Unreal G/L % | Float | | |
| E | Daily Chg % | Float | | |
| F | Price | Float | | |
| G | Trim Target | Float | | From thesis |
| H | Add Target | Float | | From thesis |
| I | Fwd P/E | Float | | |
| J | 52w Pos % | Float | | |
| K | Disc from High %| Float | | |
| L | Valuation Signal| String | | |
| M | Top Rationale | String | | |

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
| F | Implicit_Bet | String | | Bill's core assumption |
| G | Thesis_Brief | String | | Link to thesis docs |
| H | Rotation_Type | String | | upgrade / rebalance / tax_loss |
| I-N | Technical Snap | Float/Str| | RSI, Trend, MA200 at trade time |
| O | Trade_Log_ID | String | | |
| P | Fingerprint | String | | |

*Since Phase 5.*

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

*Since Phase 5.*

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

## 🛠️ Fingerprint Formats
Standardized keys used to prevent duplicate data entry.

| Tab | Format |
| :--- | :--- |
| `Holdings_History` | `import_date\|ticker\|quantity` |
| `Daily_Snapshots` | `import_date\|pos_count\|total_value` |
| `Transactions` | `date\|ticker\|action\|net_amount` |
| `Realized_GL` | `closed_dt\|ticker\|opened_dt\|qty\|proceeds\|cost` |
| `Income_Tracking` | `import_date\|pos_count\|projected_income` |
| `Risk_Metrics` | `import_date\|beta\|top_pos_pct` |
| `Rotation_Review` | `Trade_Log_ID\|Attribution_As_Of` |
| `Decision_Log` | `date\|timestamp\|action\|tickers` |
