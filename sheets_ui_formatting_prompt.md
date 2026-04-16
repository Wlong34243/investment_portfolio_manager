# Prompt: Google Sheets UI Formatting & Dashboard Improvements
# Handoff to: Gemini CLI
# Project: Investment Portfolio Manager
# Script output: `tasks/format_sheets_ui.py`
# DRY_RUN: True by default — pass `--live` to write

---

## Context

You are working inside the Investment Portfolio Manager project. The authoritative
Google Sheet ID is `1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA`.

The sheet is the primary UI surface. It currently has raw data but no visual formatting.
Your task is to write a Python script (`tasks/format_sheets_ui.py`) that uses the
`gspread` client (already configured in `utils/sheet_readers.py`) plus the
`gspread_formatting` library to apply a consistent, review-optimized visual layer to
four key tabs. The script must follow all project conventions — DRY_RUN gate, single
batch writes, no new dependencies beyond `gspread` and `gspread_formatting`.

Credentials: use `get_gspread_client()` from `utils/sheet_readers.py`.
Config constants: import from `config.py` (`PORTFOLIO_SHEET_ID`, `DRY_RUN`, etc.).
Install requirement: add `gspread-formatting` to `requirements.txt` if not already present.

---

## Tab 1: `Agent_Outputs` — Priority Review View

**Problem:** Columns are too narrow to read signal_type, ticker, action, rationale,
scale_step, and severity. The first 3 columns (run_id, agent, timestamp) have no
review value and push the actionable columns off-screen.

**Known column layout (11-column standard schema):**

| Col | Header | Review Priority |
|-----|--------|----------------|
| A | Run ID | Low — hide |
| B | Agent | Low — hide |
| C | Timestamp | Low — hide |
| D | Ticker | HIGH |
| E | Signal Type | HIGH |
| F | Action | HIGH |
| G | Scale Step | HIGH |
| H | Severity | HIGH |
| I | Rationale | HIGH (needs width) |
| J | Style Alignment | Medium |
| K | Summary Narrative | Medium (needs width) |

**Formatting tasks:**

1. **Hide columns A, B, C** (Run ID, Agent, Timestamp). Use `gspread_formatting`
   `hide_columns()`. Do NOT delete — hide only.

2. **Set column widths (pixels):**
   - D (Ticker): 80
   - E (Signal Type): 110
   - F (Action): 120
   - G (Scale Step): 110
   - H (Severity): 90
   - I (Rationale): 420
   - J (Style Alignment): 150
   - K (Summary Narrative): 380

3. **Freeze row 1** (header) and freeze column D (first visible column after hidden cols).

4. **Header row formatting (row 1):**
   - Background: dark navy `#1a2744`
   - Font: white, bold, 10pt
   - Text wrap: clip (not wrap) for headers

5. **Signal Type conditional color coding (column E):**
   Apply background color to each data cell in column E based on value:
   - `"accumulate"` → light green `#d9ead3`
   - `"trim"` → light red `#fce8e6`
   - `"hold"` → light yellow `#fff2cc`
   - `"monitor"` → light blue `#cfe2f3`
   - `"exit"` → dark red `#ea4335`, white font

6. **Severity conditional color coding (column H):**
   - `"high"` or `"HIGH"` → `#ea4335` background, white font
   - `"medium"` or `"MEDIUM"` → `#ff9900` background
   - `"low"` or `"LOW"` → `#93c47d` background

7. **Rationale and Summary Narrative columns (I, K):**
   - Set row height to 80px for all data rows (rows 2+)
   - Text wrap: WRAP (so text is fully readable)

8. **Alternating row banding** on data rows:
   - Odd rows: white `#ffffff`
   - Even rows: `#f8f9fa` (very light grey)

9. **Apply a thick bottom border** under row 1 (header separator).

---

## Tab 2: `Holdings_Current` — Daily P&L Review View

**Problem:** No P&L summary header, no visual distinction of accumulate vs. trim
candidates, no highlighting of positions at meaningful gain/loss levels.

**Known column layout:**

| Col | Header |
|-----|--------|
| A | Ticker |
| B | Description |
| C | Asset Class |
| D | Asset Strategy |
| E | Quantity |
| F | Price |
| G | Market Value |
| H | Cost Basis |
| I | Unit Cost |
| J | Unrealized G/L |
| K | Unrealized G/L % |
| L | Est Annual Income |
| M | Dividend Yield |
| N | Acquisition Date |
| O | Wash Sale |
| P | Is Cash |
| Q | Weight |
| R | Import Date |
| S | Fingerprint |

**Formatting tasks:**

1. **Freeze row 1** and freeze column A (Ticker).

2. **Hide columns B, D, I, N, O, P, R, S** — Description, Asset Strategy, Unit Cost,
   Acquisition Date, Wash Sale, Is Cash, Import Date, Fingerprint are audit columns.
   Keep them present but hidden for daily review.

3. **Set column widths:**
   - A (Ticker): 75
   - C (Asset Class): 130
   - E (Quantity): 80
   - F (Price): 80
   - G (Market Value): 110
   - H (Cost Basis): 110
   - J (Unrealized G/L): 115
   - K (Unrealized G/L %): 110
   - L (Est Annual Income): 120
   - M (Dividend Yield): 100
   - Q (Weight): 75

4. **Header row formatting:** Same dark navy `#1a2744`, white bold 10pt as Agent_Outputs.

5. **Unrealized G/L $ conditional formatting (column J):**
   - Value > 0: font color green `#34a853`
   - Value < 0: font color red `#ea4335`
   - Value == 0: default

6. **Unrealized G/L % conditional formatting (column K) — color scale:**
   Apply 3-point color scale:
   - Min (≤ -15%): red `#ea4335`
   - Mid (0%): white `#ffffff`
   - Max (≥ +20%): green `#34a853`

7. **Weight column (Q) — bar-style formatting:**
   Apply a data bar or bold the font if weight > 5.0% to make concentration visible
   at a glance. If data bars aren't supported, apply background `#fce8e6` for weight > 8%
   (single position concentration threshold per `config.CONCENTRATION_SINGLE_THRESHOLD`).

8. **Wash Sale flag (column O) — even though hidden:**
   When unhidden, any TRUE value should display `#ff9900` background.
   Apply the conditional format even to the hidden column so it's ready when surfaced.

9. **Summary KPI row — insert at row 1, push headers to row 2:**
   > NOTE: This is the highest-impact change. Insert a new row 1 with merged cells
   > showing portfolio-level KPIs derived from column formulas (not Python — use
   > Google Sheets native ARRAYFORMULA/SUM so they auto-update):

   - Cell A1 (merged A1:B1): Label "📊 PORTFOLIO SNAPSHOT" — bold, dark navy bg, white font
   - Cell C1 (merged C1:D1): Formula `=TEXT(SUM(G3:G200),"$#,##0")` — label "Total Value"
   - Cell E1 (merged E1:F1): Formula `=TEXT(SUM(J3:J200),"$#,##0")` — label "Unrealized G/L"
   - Cell G1 (merged G1:H1): Formula `=TEXT(SUM(J3:J200)/SUM(H3:H200)*100,"0.0")&"%"` — label "Total Return %"
   - Cell I1 (merged I1:J1): Formula `=TEXT(SUMIF(P3:P200,TRUE,G3:G200),"$#,##0")` — label "Cash"
   - Cell K1 (merged K1:L1): Formula `=TEXT(COUNTA(A3:A200)-COUNTIF(P3:P200,TRUE),"0")&" positions"` — label "Positions"

   Row 1 height: 40px. All KPI cells: font size 11, bold, center-aligned.
   Row 2 (original headers): dark navy `#1a2744`, white bold 10pt, height 30px.

   **IMPORTANT:** All data row references in subsequent formatting must use rows 3+
   (not 2+) since row 1 is now the KPI summary and row 2 is headers.

10. **Alternating row banding** on data rows (rows 3+): same odd/even pattern as Agent_Outputs.

---

## Tab 3: `Daily_Snapshots` — Portfolio Trend View

**Problem:** Raw numbers with no visual trend or gain context.

**Formatting tasks:**

1. **Freeze row 1**, freeze column A (Date).

2. **Hide column J** (Fingerprint).

3. **Column widths:**
   - A (Date): 100
   - B (Total Value): 120
   - C (Total Cost): 120
   - D (Total Unrealized G/L): 140
   - E (Cash Value): 110
   - F (Invested Value): 120
   - G (Position Count): 90
   - H (Blended Yield): 100
   - I (Import Timestamp): 150 (keep for audit)

4. **Header formatting:** Same dark navy, white bold.

5. **Total Unrealized G/L column (D) — conditional formatting:**
   - Value > 0: background `#d9ead3` (light green)
   - Value < 0: background `#fce8e6` (light red)

6. **Sort data rows newest-first** (column A descending). Use `sort_range()` on the
   data range only (exclude header). This makes the most recent snapshot immediately
   visible without scrolling.

7. **Bold the most recent data row** (last appended = first after sort). This gives
   instant visual confirmation of today's portfolio state.

8. **Insert a sparkline summary row at the top** (row 1, KPI summary):
   - Cell A1 (merged A1:B1): "📈 DAILY SNAPSHOT" label
   - Cell C1: `=SPARKLINE(D2:D50,{"charttype","line";"color","#34a853"})` — G/L trend sparkline
   - Cell D1: `=TEXT(D2,"$#,##0")` — most recent unrealized G/L (row 2 after sort = newest)
   - Cell E1: `=TEXT(B2,"$#,##0")` — most recent total value
   Same KPI row style as Holdings_Current row 1.

---

## Tab 4: `Realized_GL` — Tax Intelligence View

**Problem:** Tax-relevant columns (wash sales, disallowed losses, ST vs LT) are buried
among lot-detail columns. No visual flag on disallowed losses.

**Known columns:** Ticker, Description, Closed Date, Opened Date, Holding Days,
Quantity, Proceeds Per Share, Cost Per Share, Proceeds, Cost Basis, Unadjusted Cost,
Gain Loss $, Gain Loss %, LT Gain Loss, ST Gain Loss, Term, Wash Sale,
Disallowed Loss, Account, Is Primary Acct, Import Date, Fingerprint

**Formatting tasks:**

1. **Freeze row 1**, freeze column A (Ticker).

2. **Hide columns:** Description (B), Proceeds Per Share (G), Cost Per Share (H),
   Unadjusted Cost (K), Import Date (V), Fingerprint (W).
   These are lot-detail audit columns — not needed for daily review.

3. **Column widths:**
   - A (Ticker): 75
   - C (Closed Date): 110
   - D (Opened Date): 110
   - E (Holding Days): 90
   - F (Quantity): 75
   - I (Proceeds): 110
   - J (Cost Basis): 110
   - L (Gain Loss $): 110
   - M (Gain Loss %): 100
   - N (LT Gain Loss): 110
   - O (ST Gain Loss): 110
   - P (Term): 80
   - Q (Wash Sale): 90
   - R (Disallowed Loss): 120
   - S (Account): 110

4. **Gain Loss $ (column L) conditional formatting:**
   - Value > 0: font color green `#34a853`
   - Value < 0: font color red `#ea4335`

5. **Disallowed Loss (column R) — HIGH PRIORITY FLAG:**
   Any cell in column R that is not empty AND not "0" AND not "$0.00":
   - Background: `#ea4335` (red)
   - Font: white, bold
   This is the most important tax signal — disallowed wash sale losses that need
   attention before year-end.

6. **Wash Sale (column Q) TRUE rows:**
   - Background `#fff2cc` (yellow) for the entire row when column Q = TRUE.
   Use a conditional format on the full row range (A:S) keyed on column Q value.

7. **Term (column P) conditional formatting:**
   - "Short-term" or "ST": background `#fce8e6` (light red — higher tax impact)
   - "Long-term" or "LT": background `#d9ead3` (light green — lower tax impact)

8. **KPI summary row 1 (same pattern as Holdings_Current):**
   - A1: "🧾 REALIZED G/L" label
   - C1: `=TEXT(SUM(L3:L500),"$#,##0")` — Total Realized G/L
   - E1: `=TEXT(SUMIF(O3:O500,">0",O3:O500),"$#,##0")` — LT Gains
   - G1: `=TEXT(SUMIF(N3:N500,"<0",N3:N500),"$#,##0")` — LT Losses
   - I1: `=TEXT(SUMIF(P3:P500,">0",P3:P500),"$#,##0")` — ST Gains
   - K1: `=TEXT(SUMIF(Q3:Q500,TRUE,R3:R500),"$#,##0")` — Total Disallowed (wash sale)

---

## Implementation Requirements

### Script structure

```python
# tasks/format_sheets_ui.py
"""
Google Sheets UI Formatting Script
Applies visual formatting to Agent_Outputs, Holdings_Current,
Daily_Snapshots, and Realized_GL tabs.

Usage:
    python tasks/format_sheets_ui.py           # DRY RUN (default)
    python tasks/format_sheets_ui.py --live    # Write formatting to Sheet
"""

import typer
import config
from utils.sheet_readers import get_gspread_client
from gspread_formatting import (
    CellFormat, Color, TextFormat, borders, Border, Borders,
    format_cell_range, format_cell_ranges, set_frozen,
    set_column_width, ConditionalFormatRule, BooleanRule,
    BooleanCondition, GradientRule, InterpolationPoint,
    get_conditional_format_rules, set_conditional_format_rules,
    DataValidationRule, BandedRange
)

app = typer.Typer()

@app.command()
def main(live: bool = typer.Option(False, "--live", help="Write formatting (default: dry run)")):
    dry_run = not live
    if dry_run:
        typer.echo("DRY RUN — no changes will be written. Pass --live to apply.")
        return
    
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    
    format_agent_outputs(spreadsheet)
    format_holdings_current(spreadsheet)
    format_daily_snapshots(spreadsheet)
    format_realized_gl(spreadsheet)
    
    typer.echo("✅ All tabs formatted successfully.")

if __name__ == "__main__":
    app()
```

Implement `format_agent_outputs()`, `format_holdings_current()`,
`format_daily_snapshots()`, and `format_realized_gl()` as separate functions.
Each function should:
1. Open the worksheet by tab name
2. Apply all formatting described above
3. Print a status line: `"  ✓ formatted {tab_name}"`

### gspread_formatting API patterns to use

For hiding columns, use the Google Sheets API directly via `spreadsheet.batch_update()`:
```python
spreadsheet.batch_update({
    "requests": [{
        "updateDimensionProperties": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 0,  # 0-based
                "endIndex": 3,    # exclusive
            },
            "properties": {"hiddenByUser": True},
            "fields": "hiddenByUser"
        }
    }]
})
```

For column widths:
```python
set_column_width(ws, "D", 80)  # column letter, pixel width
```

For cell formatting:
```python
header_fmt = CellFormat(
    backgroundColor=Color(0.10, 0.15, 0.27),  # #1a2744 as 0-1 RGB floats
    textFormat=TextFormat(bold=True, foregroundColor=Color(1,1,1), fontSize=10),
    wrapStrategy="CLIP"
)
format_cell_range(ws, "A1:K1", header_fmt)
```

For conditional formatting (value-based):
```python
rules = get_conditional_format_rules(ws)
rules.append(ConditionalFormatRule(
    ranges=[GridRange.from_a1_range("E2:E500", ws)],
    booleanRule=BooleanRule(
        condition=BooleanCondition("TEXT_EQ", ["accumulate"]),
        format=CellFormat(backgroundColor=Color(0.85, 0.92, 0.83))
    )
))
set_conditional_format_rules(ws, rules)
```

### Error handling

- Wrap each `format_*()` call in try/except — a formatting failure on one tab must not
  abort the others.
- If a worksheet doesn't exist (tab not yet created), log a warning and skip.
- If `gspread_formatting` is not installed, print a clear error:
  `"ERROR: pip install gspread-formatting"` and exit.

### Do NOT do

- Do not delete any data rows or columns — only hide.
- Do not insert rows unless explicitly implementing the KPI summary row.
- Do not touch `Target_Allocation` (manual-only tab).
- Do not write cell values (formulas only belong in the KPI summary row insert).
- Do not call `ws.update()` or `ws.batch_update()` for data — this script touches
  formatting and structure only.
- Do not add any new gspread imports to `utils/sheet_readers.py`.

---

## Acceptance Criteria

Run `python tasks/format_sheets_ui.py --live` and verify:

- [ ] `Agent_Outputs`: Columns A-C hidden; columns D-K at specified widths; row 1
      dark navy header; signal_type cells color-coded green/yellow/blue/red;
      severity cells color-coded; rationale column wraps text at 80px row height.
- [ ] `Holdings_Current`: KPI summary in row 1 with live portfolio totals;
      headers in row 2; unrealized G/L column shows green/red font by sign;
      concentration >8% weight flagged in red; audit columns hidden.
- [ ] `Daily_Snapshots`: Sorted newest-first; most recent row bolded; G/L column
      green/red by sign; sparkline in KPI row; fingerprint hidden.
- [ ] `Realized_GL`: Disallowed Loss cells red-highlighted; wash sale rows yellow-
      banded; Term ST/LT color-coded; KPI totals in row 1 including wash sale
      disallowed amount.
- [ ] Script exits cleanly in dry run mode with no Sheet writes.
- [ ] Script exits cleanly if any tab is missing (warning, not crash).

---

## Post-build note for Bill

After running `--live`, you may want to manually:
1. Resize the browser zoom in Sheets to ~85% to see more columns at once
2. On `Agent_Outputs`, use View → Freeze → Up to current column (D) after
   unhiding is confirmed — the freeze applies to the first visible column
3. On `Holdings_Current`, verify the KPI row formulas reference the correct
   row offsets (row 3+ for data if KPI row was inserted successfully)
4. The `Realized_GL` disallowed loss flag is the single most important tax
   signal — confirm it fires on any row where the `Disallowed Loss` column
   is non-zero before year-end review

This script is idempotent — safe to re-run after agent writes update the sheet.
Formatting rules accumulate; running twice does not double-apply conditionals
(gspread_formatting replaces the full rules list on each call).
