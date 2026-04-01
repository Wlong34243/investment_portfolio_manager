# REALIZED_GL_PARSER_SPEC.md
# Schwab Realized Gain/Loss Lot Details — Parser Spec + Sheet Schema
# Investment Portfolio Manager — Phase 3

---

## Overview

This document specifies the parser for the **Schwab "Realized Gain/Loss – Lot Details"**
export (`All_Accounts_GainLoss_Realized_Details_*.csv`) and the corresponding
`Realized_GL` tab in the Portfolio Google Sheet.

This is a **separate parser and separate tab** from the existing `Transactions` tab.
The two serve different purposes:

| | `Transactions` tab | `Realized_GL` tab |
|---|---|---|
| **Source file** | Schwab transaction history CSV | Schwab Realized G/L Lot Details CSV |
| **Row granularity** | One row per trade event (buy or sell) | One row per closed tax lot |
| **Lot pairing** | Raw — buy and sell are separate rows | Pre-paired by Schwab (open date + close date on same row) |
| **Primary use** | Activity ledger, cash flow, order history | Tax analysis, behavioral analysis, wash sale tracking |
| **Available now** | Phase 3 (future) | **Available now — real data exists** |

The Realized G/L file is the richer source for behavioral analysis because Schwab has
already done the lot-matching work. Each row answers: "I bought X shares on date A at
cost B, and sold them on date C at proceeds D."

---

## Source File Characteristics

### File Naming Pattern
```
All_Accounts_GainLoss_Realized_Details_YYYYMMDD-HHmmss.csv
```

### Top-Level Structure
```
Row 1:   Report header — "Realized Gain/Loss - Lot Details for All_Accounts as of..."
Row 2:   Account section label — e.g., "Individual 401(k) ...499"
Row 3:   Column headers — "Symbol","Name","Closed Date",...
Row 4+:  Data rows for that account
...
Blank row — end of account section
Next account label
Column headers (repeated)
Data rows
...
```

### Account Sections Found in Production File
| Account Label Pattern | Account Type | Row Count (2025 export) |
|---|---|---|
| `Individual 401(k) ...499` | 401(k) brokerage | 139 |
| `Contributory ...767` | IRA (contributory) | 242 |
| `Joint Tenant ...753` | Joint brokerage | 26 |
| `HSA Brokerage ...217` | HSA | 0 (empty — "no transactions") |
| `Individual ...119` | Primary taxable brokerage | 641 |

**The primary investment account is `Individual ...119`** — 61% of all closed lots.
This is the account this project tracks. All accounts should be imported with their
account label preserved for cross-account wash sale detection.

### Column Schema (25 columns, 0-indexed)
| Index | Header | Example Value | Notes |
|---|---|---|---|
| 0 | Symbol | `"XLV"` | Ticker |
| 1 | Name | `"STATE STRT HLTH CRE SLT SEC SPDR ETF"` | Full description |
| 2 | Closed Date | `"12/19/2025"` | Date lot was sold/closed |
| 3 | Opened Date | `"10/03/2025"` | Date lot was opened/purchased |
| 4 | Quantity | `"10"` | Shares in this lot (fractional OK) |
| 5 | Proceeds Per Share | `"$155.28"` | Sale price per share |
| 6 | Cost Per Share | `"$145.72"` | Cost basis per share |
| 7 | Proceeds | `"$1,552.85"` | Total proceeds (quantity × proceeds/share) |
| 8 | Cost Basis (CB) | `"$1,457.16"` | Total cost basis |
| 9 | Gain/Loss ($) | `"$95.69"` or `"-$3.43"` | Realized G/L dollars |
| 10 | Gain/Loss (%) | `"6.56688352686%"` | Realized G/L percentage |
| 11 | Long Term Gain/Loss | `"$50.34"` or `""` | Populated if Long Term, blank if Short Term |
| 12 | Short Term Gain/Loss | `"$95.69"` or `""` | Populated if Short Term, blank if Long Term |
| 13 | Term | `"Short Term"` or `"Long Term"` | Holding period classification |
| 14 | Unadjusted Cost Basis | `"$1,457.16"` | Pre-wash-sale-adjustment cost basis |
| 15 | Wash Sale? | `"No"` or `"Yes"` | Whether IRS wash sale rules apply |
| 16 | Disallowed Loss | `"$85.51"` or `""` | Disallowed amount if wash sale = Yes |
| 17 | Transaction Closed Date | `"12/19/2025"` | Usually same as Closed Date |
| 18–24 | (empty) | `""` | Schwab reserves these; always blank |

### Known Format Quirks
1. **Dollar signs and commas** — all monetary values include `$` prefix and comma
   thousands separators. E.g., `"$1,552.85"`, `"-$3.43"`.
2. **Percentage signs** — G/L % values include trailing `%`. E.g., `"6.56688352686%"`.
3. **Negative values** — negatives use `-$` prefix (NOT parentheses like the positions CSV).
   E.g., `"-$3.43"`, not `"($3.43)"`. Different from positions CSV — use a separate
   numeric cleaner.
4. **Fractional quantities** — lots can have fractional shares. E.g., `"0.84"`, `"7.98"`.
   Never round.
5. **Empty "no transactions" rows** — HSA and other accounts with no activity will have
   a single row: `"There are no transactions available for your search criteria..."`.
   Skip these rows.
6. **Header repeated per section** — the `Symbol,Name,Closed Date,...` header row
   appears once per account section. Must detect and skip, not treat as data.
7. **BOM marker** — use `encoding='utf-8-sig'` to handle possible BOM at file start.
8. **Blank separator rows** — a row of 25 empty quoted strings separates account sections.
9. **Wash sale disallowed loss** — when `Wash Sale? = "Yes"`, column 16 contains the
   disallowed loss amount. The `Gain/Loss ($)` column will be `"$0.00"` (adjusted to
   zero by Schwab). The economic loss is in `Disallowed Loss`.

---

## Parser Implementation

### Module Location
```
utils/gl_parser.py
```

### Key Functions

#### `parse_realized_gl(file_or_path) -> pd.DataFrame`
Top-level function. Accepts a file path string or file-like object (Streamlit
`UploadedFile`). Returns a clean DataFrame with one row per closed lot, all accounts
combined, with `account` column populated.

```python
def parse_realized_gl(file_or_path) -> pd.DataFrame:
    """
    Parse Schwab Realized G/L Lot Details CSV.
    Returns clean DataFrame with one row per closed lot.
    Preserves account label for cross-account wash sale detection.
    """
```

#### `_find_account_sections_gl(df_raw) -> list[dict]`
Scan raw DataFrame for account section boundaries. Returns list of dicts:
```python
[
    {"account": "Individual ...119", "header_row": 418, "data_start": 419, "data_end": 641},
    ...
]
```

Account label detection pattern (mirrors positions CSV parser logic):
```python
ACCOUNT_PATTERNS = [
    "individual 401",
    "contributory",
    "joint tenant",
    "hsa brokerage",
    "individual ...",
    "roth",
    "custodial",
    "trust",
    "rollover",
    "beneficiary",
]
```
Match by checking if the first cell of a row (lowercased) starts with any of these
patterns AND remaining cells in the row are empty.

#### `_clean_dollar(value) -> float`
```python
def _clean_dollar(value) -> float:
    """
    Parse Schwab G/L dollar values.
    Handles: "$1,552.85", "-$3.43", "$0.00", "", None
    NOTE: G/L CSV uses -$ prefix for negatives (NOT parentheses).
    Different from positions CSV clean_numeric() — do not reuse.
    """
    if pd.isna(value) or str(value).strip() in ("", "-", "N/A"):
        return 0.0
    s = str(value).strip().replace(",", "").replace("$", "")
    try:
        return float(s)
    except ValueError:
        return 0.0
```

#### `_clean_pct(value) -> float`
```python
def _clean_pct(value) -> float:
    """
    Parse percentage strings like "6.56688352686%" or "-0.567674026017%"
    Returns float (e.g., 6.567) — NOT divided by 100. Store as-is.
    """
    s = str(value).strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return 0.0
```

#### `_parse_date(value) -> str`
```python
def _parse_date(value) -> str:
    """
    Parse MM/DD/YYYY to ISO YYYY-MM-DD string.
    Returns "" on failure (don't crash — some lots may have quirks).
    """
    try:
        return datetime.strptime(str(value).strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""
```

#### `_holding_days(opened: str, closed: str) -> int`
```python
def _holding_days(opened: str, closed: str) -> int:
    """
    Compute calendar days held. Both args are ISO date strings.
    Returns -1 if either date is missing/invalid.
    """
```

#### `_make_fingerprint(row: dict) -> str`
```python
def _make_fingerprint(row: dict) -> str:
    """
    Content-based dedup key. Uniquely identifies a closed lot.
    Format: closed_date|ticker|opened_date|quantity|proceeds|cost_basis
    Example: "2025-12-19|XLV|2025-10-03|10|1552.85|1457.16"
    """
    return "|".join([
        str(row["closed_date"]),
        str(row["ticker"]),
        str(row["opened_date"]),
        str(row["quantity"]),
        str(row["proceeds"]),
        str(row["cost_basis"]),
    ])
```

### Parsing Algorithm

```python
def parse_realized_gl(file_or_path):
    # 1. Read raw with no assumed header
    df_raw = pd.read_csv(
        file_or_path,
        header=None,
        names=range(25),
        encoding="utf-8-sig",
        dtype=str,
        skip_blank_lines=False,
    )

    # 2. Find account sections
    sections = _find_account_sections_gl(df_raw)

    # 3. For each section, extract data rows
    all_rows = []
    for section in sections:
        for idx in range(section["data_start"], section["data_end"] + 1):
            row = df_raw.iloc[idx]
            symbol = str(row[0]).strip().strip('"')

            # Skip: empty rows, header repeats, "no transactions" messages
            if not symbol or symbol.lower() in ("symbol", ""):
                continue
            if "no transactions" in symbol.lower():
                continue

            # Parse each field
            lot = {
                "ticker":              symbol,
                "description":         str(row[1]).strip().strip('"'),
                "closed_date":         _parse_date(row[2]),
                "opened_date":         _parse_date(row[3]),
                "quantity":            float(str(row[4]).strip().strip('"') or 0),
                "proceeds_per_share":  _clean_dollar(row[5]),
                "cost_per_share":      _clean_dollar(row[6]),
                "proceeds":            _clean_dollar(row[7]),
                "cost_basis":          _clean_dollar(row[8]),
                "gain_loss_dollars":   _clean_dollar(row[9]),
                "gain_loss_pct":       _clean_pct(row[10]),
                "lt_gain_loss":        _clean_dollar(row[11]),
                "st_gain_loss":        _clean_dollar(row[12]),
                "term":                str(row[13]).strip().strip('"'),
                "unadjusted_cost":     _clean_dollar(row[14]),
                "wash_sale":           str(row[15]).strip().strip('"').upper() == "YES",
                "disallowed_loss":     _clean_dollar(row[16]),
                "account":             section["account"],
            }

            # Derived fields
            lot["holding_days"]  = _holding_days(lot["opened_date"], lot["closed_date"])
            lot["is_primary_acct"] = "individual" in section["account"].lower() \
                                     and "401" not in section["account"].lower() \
                                     and "contributory" not in section["account"].lower()
            lot["fingerprint"]   = _make_fingerprint(lot)

            all_rows.append(lot)

    return pd.DataFrame(all_rows)
```

---

## Google Sheet Tab: `Realized_GL`

### Purpose
Append-only ledger of every closed tax lot across all accounts. Primary source for
behavioral analysis, tax reporting, and wash sale intelligence.

### Write Pattern
Append only. Dedup by `fingerprint` before writing. Re-uploading the same CSV file
must produce zero new rows (idempotency rule from CLAUDE.md).

### Schema

| Col | Header | Type | Example | Notes |
|-----|--------|------|---------|-------|
| A | Ticker | String | `XLV` | |
| B | Description | String | `STATE STRT HLTH CRE SLT SEC SPDR ETF` | Truncated Schwab name |
| C | Closed Date | Date (ISO) | `2025-12-19` | |
| D | Opened Date | Date (ISO) | `2025-10-03` | |
| E | Holding Days | Integer | `77` | Computed: closed − opened |
| F | Quantity | Float | `10` | Fractional shares OK |
| G | Proceeds Per Share | Float | `155.28` | |
| H | Cost Per Share | Float | `145.72` | |
| I | Proceeds | Float | `1552.85` | Total proceeds |
| J | Cost Basis | Float | `1457.16` | Adjusted cost basis |
| K | Unadjusted Cost | Float | `1457.16` | Pre-wash-sale-adjustment |
| L | Gain Loss $ | Float | `95.69` | Negative = loss |
| M | Gain Loss % | Float | `6.567` | Negative = loss |
| N | LT Gain Loss | Float | `0.00` | Long-term component |
| O | ST Gain Loss | Float | `95.69` | Short-term component |
| P | Term | String | `Short Term` | `Short Term` or `Long Term` |
| Q | Wash Sale | Boolean | `FALSE` | |
| R | Disallowed Loss | Float | `0.00` | Populated if wash sale = TRUE |
| S | Account | String | `Individual ...119` | Schwab account label |
| T | Is Primary Acct | Boolean | `TRUE` | Primary taxable account flag |
| U | Import Date | Date (ISO) | `2026-03-30` | When row was written |
| V | Fingerprint | String | `2025-12-19\|XLV\|...` | Dedup key |

**Row 1:** Headers (frozen)
**Row 2+:** Append-only, oldest lots first (sorted by closed_date ascending at write time)

---

## Behavioral Analysis Queries

Once the `Realized_GL` tab is populated, the following analyses are directly computable.
These feed the **Behavioral Analytics** sub-module planned for Phase 4.

### 1. Win Rate by Account
```python
df["winner"] = df["gain_loss_dollars"] > 0
win_rate = df.groupby("account")["winner"].mean()
```

### 2. Disposition Effect Test
Compare average gain on winning lots vs. average loss on losing lots.
Classic disposition effect: avg_gain < abs(avg_loss) AND winners held shorter than losers.
```python
winners = df[df["gain_loss_dollars"] > 0]
losers  = df[df["gain_loss_dollars"] < 0]

avg_gain_days = winners["holding_days"].mean()
avg_loss_days = losers["holding_days"].mean()
avg_gain_amt  = winners["gain_loss_dollars"].mean()
avg_loss_amt  = losers["gain_loss_dollars"].mean()
```
Signal: if `avg_gain_days < avg_loss_days`, the disposition effect is present.

### 3. Wash Sale Concentration
```python
wash = df[df["wash_sale"] == True]
wash_by_ticker = wash.groupby("ticker").agg(
    occurrences=("wash_sale", "count"),
    total_disallowed=("disallowed_loss", "sum")
).sort_values("total_disallowed", ascending=False)
```
High `occurrences` on a single ticker = repeated pattern of selling at loss + re-buying
within 30 days. Flag for behavioral review.

### 4. Holding Period Distribution
```python
import plotly.express as px
fig = px.histogram(df, x="holding_days", color="term",
                   title="Holding Period Distribution",
                   labels={"holding_days": "Days Held"})
```
Look for bimodal distribution: very short-term traders cluster < 30 days.

### 5. Ticker-Level P&L Summary
```python
ticker_summary = df.groupby("ticker").agg(
    lots_closed=("ticker", "count"),
    total_proceeds=("proceeds", "sum"),
    total_cost=("cost_basis", "sum"),
    total_gl=("gain_loss_dollars", "sum"),
    avg_holding_days=("holding_days", "mean"),
    wash_sale_count=("wash_sale", "sum"),
    total_disallowed=("disallowed_loss", "sum"),
    wins=("winner", "sum"),
).assign(win_rate=lambda x: x["wins"] / x["lots_closed"])
```

### 6. Short-Term vs. Long-Term Tax Exposure
```python
st_gl = df[df["term"] == "Short Term"]["gain_loss_dollars"].sum()
lt_gl = df[df["term"] == "Long Term"]["gain_loss_dollars"].sum()
# Apply rates from Config tab
st_tax = st_gl * config["tax_rate_short_term"]
lt_tax = lt_gl * config["tax_rate_long_term"]
```

### 7. Pattern: Chasing / Re-Entry
Tickers that appear multiple times (sold → re-bought → sold again). Indicate either
a deliberate trading strategy or loss-chasing behavior.
```python
multi_entry = df.groupby("ticker")["closed_date"].count()
repeat_tickers = multi_entry[multi_entry > 2].index.tolist()
```
Cross-reference with wash sale flags on repeat tickers to identify the problematic pattern.

### 8. Monthly Realized G/L Trend
```python
df["month"] = pd.to_datetime(df["closed_date"]).dt.to_period("M")
monthly = df.groupby("month")["gain_loss_dollars"].sum()
```
Useful for tax-loss harvesting review: are losses being realized late in the year
reactively, or distributed through the year proactively?

---

## Edge Cases and Pitfalls

| Edge Case | Handling |
|---|---|
| Fractional lots (e.g., 0.84 shares) | Store as `float` — never cast to `int` |
| Wash sale `Gain/Loss ($)` = $0.00 | Economic loss is in `Disallowed Loss` col — always store both |
| HSA "no transactions" row | Skip rows where symbol starts with "There are no" |
| Cross-account wash sales | Preserve `account` column — same ticker sold in one account and re-bought in another still triggers wash sale |
| ET (Energy Transfer) fractional dividend reinvestment lots | Very small quantities (0.84, 7.98) — normal, don't filter |
| Repeated column headers | Each account section starts with a fresh header row — detect `symbol` in col[0] (case-insensitive) and skip |
| `Unadjusted Cost` = `Cost Basis` when no wash sale | Both columns are stored; equal values are expected and valid |
| Long-term lot with Opened Date > 1yr before Closed Date | Validate: if `term == "Long Term"` then `holding_days` should be >= 365. Log warning if not — Schwab's classification is authoritative, don't override |
| Report date range | File header says "from 01/01/2025 to 12/31/2025" — store this metadata in a `_metadata` dict returned alongside DataFrame for display |

---

## Integration with Existing Code

### File: `utils/gl_parser.py` (new file)
Standalone module. Does not import from `utils/csv_parser.py` — the G/L CSV has
different numeric formats (`-$` prefix vs. parentheses in positions CSV).

### File: `pipeline.py` (add function)
```python
def ingest_realized_gl(uploaded_file, sheet_client, dry_run=True):
    """
    Parse Schwab G/L CSV, dedup against Realized_GL tab, append new rows.
    Returns: {"parsed": int, "new": int, "skipped": int, "errors": list}
    """
```

### File: `app.py` (add upload widget + Phase 4 tab)
Add a second file uploader in the sidebar:
```python
gl_file = st.sidebar.file_uploader(
    "Upload Realized G/L CSV (optional)",
    type=["csv"],
    help="Schwab: Accounts > History > Realized Gain/Loss > Export"
)
```

### New Streamlit Tab: `Tax & Behavior`
Add as a new tab in `app.py` (Phase 3+). Contains:
- Wash sale summary table with disallowed loss totals
- Realized G/L YTD (ST vs. LT breakdown with estimated tax impact)
- Top repeat-traded tickers
- Behavioral analytics panel (Phase 4): disposition effect score, holding period
  distribution histogram, win rate by ticker and sector

---

## Testing Checklist

Before marking Phase 3 complete, verify:

- [ ] Re-upload of same CSV produces 0 new rows (idempotency)
- [ ] All 5 account sections parsed (including empty HSA — 0 rows, no crash)
- [ ] `Individual ...119` produces 641 rows from production file
- [ ] Fractional lots (ET 0.84 shares) stored correctly — not rounded
- [ ] Wash sale rows: `wash_sale=True`, `disallowed_loss > 0`, `gain_loss_dollars = 0`
- [ ] `holding_days` computed correctly for both ST and LT lots
- [ ] `is_primary_acct` = True for `Individual ...119`, False for all others
- [ ] No crash on HSA "no transactions" row
- [ ] Fingerprint uniqueness: no two rows in production file share a fingerprint
- [ ] Dollar values with `-$` prefix parse as negative (not zero)
- [ ] Percentage values strip `%` correctly
- [ ] `DRY_RUN=True` gate respected — no Sheet writes during test runs

---

## Data Summary (Production File: 2025 Full Year)

| Metric | Value |
|---|---|
| Total closed lots | 1,049 |
| Date range | 2025-01-03 to 2025-12-30 |
| Short-term lots | 969 (92%) |
| Long-term lots | 76 (8%) |
| Wash sale flags | 81 |
| Primary account lots (`Individual ...119`) | 641 |
| Unique tickers traded | TBD (approx. 50+) |
| Accounts with activity | 4 of 5 |

The high proportion of short-term lots (92%) confirms active trading. The 81 wash sale
flags across a single year warrant close attention in the behavioral analysis module —
this is meaningful data, not noise.
