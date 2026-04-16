# Prompt: Portfolio Dashboard V2 — Decision-Ready UI + Valuation Data Fix
# Handoff to: Gemini CLI / Claude Code
# Priority: HIGH — current agent outputs are not usable for investment decisions
# Script output: `tasks/format_sheets_dashboard_v2.py`
# DRY_RUN: True by default — pass `--live` to write

---

## What's Broken (Read Before Building)

Before applying any formatting, understand the three data quality problems this
prompt addresses alongside the UI work:

### Problem 1: Valuation agent output is worthless
All 53 valuation rows say "Insufficient data — MONITOR." Root cause: FMP returned
402/429 errors for ~40 of 53 tickers, so Gemini received empty valuation tables and
had nothing to reason over. The valuation signals are not usable. This prompt adds
a `Valuation_Card` tab that pulls real-time valuation data via yfinance (P/E, P/B,
forward P/E, 52-week position, market cap) for the individual equity positions —
bypassing FMP entirely. This is not an agent output; it's a Python-computed
enrichment table that refreshes on every run.

### Problem 2: Tax agent cash detection is wrong
The tax agent reported $0 cash and flagged the portfolio as underweight cash. The
portfolio actually holds $9,633 CASH_MANUAL + $63,827 SGOV (Treasury ETF) =
~$73K in cash-equivalent positions. The `Is Cash` boolean column is being misread
from Sheets (known bug). Additionally, `Target_Allocation` has only 3 rows of
AI-generated Dimon-letter content rather than Bill's actual allocation targets —
making the rebalance signals against it meaningless.

### Problem 3: $24K in disallowed wash sale losses is buried
Realized_GL shows $41,743 total G/L but $116,937 in short-term losses and $24,066
in disallowed wash sale losses. This is the most actionable number in the entire
sheet and it's invisible at the top level.

---

## Part 1: New Tab — `Valuation_Card`

Build a new script `tasks/build_valuation_card.py` that:

1. Reads `Holdings_Current` tab from the portfolio sheet, skips the KPI row (row 1),
   gets real headers from row 2, reads data from row 3+.

2. Filters to individual equity positions only — exclude:
   - `CASH_MANUAL`, `CASH & CASH INVESTMENTS`, `QACDS` (cash tickers)
   - ETFs: any ticker in this set:
     `{SGOV, JPIE, QQQM, VEA, VTI, XBI, XOM_skip, IGV, EWZ, IFRA, VTI, XLV,
       XLE, XLF, RSP, EEM, VEU, EMXC, BBJP, EFG, PPA, EWJ}`
     Actually: filter on `Asset Class != 'Fixed Income'` and exclude tickers
     ending in ETF/fund patterns. Use a simpler rule: include only tickers where
     yfinance `info['quoteType'] == 'EQUITY'` (not ETF, not MUTUALFUND).

3. For each qualifying ticker, fetch via yfinance `Ticker(t).info`:
   - `trailingPE` → "Trailing P/E"
   - `forwardPE` → "Forward P/E"  
   - `priceToBook` → "P/B"
   - `pegRatio` → "PEG"
   - `marketCap` → "Market Cap"
   - `fiftyTwoWeekHigh` → "52w High"
   - `fiftyTwoWeekLow` → "52w Low"
   - current price from Holdings_Current `Price` column
   - `52w Position %` → `(price - low) / (high - low) * 100` — Python computed
   - `Discount from 52w High %` → `(high - price) / high * 100` — Python computed
   - `revenueGrowth` → "Rev Growth %"
   - `returnOnEquity` → "ROE %"
   - `debtToEquity` → "D/E"
   - `freeCashflow` → "FCF"
   - `dividendYield` → "Div Yield %"

4. Write results to a `Valuation_Card` tab with these columns:
   ```
   Ticker | Name | Market Cap | Price | Trailing P/E | Forward P/E | P/B | PEG |
   52w Low | 52w High | 52w Position % | Discount from 52w High % |
   Rev Growth % | ROE % | D/E | FCF | Div Yield % | Last Updated
   ```

5. DRY_RUN gate: if `--live` not passed, print the table to console only.
   If `--live`: clear the existing `Valuation_Card` tab (or create it if missing)
   and write in a single `ws.update()` batch call.

6. Sort output by Market Cap descending.

7. Handle yfinance failures gracefully — if a ticker returns None for a field,
   write empty string, not NaN or 0. Never crash on a single ticker failure.

**Formatting for Valuation_Card tab** (apply after data write):
- Header row: dark navy `#1a2744`, white bold
- Freeze row 1, freeze column A
- Column widths: Ticker=70, Name=180, Market Cap=110, Price=75, Trailing P/E=95,
  Forward P/E=95, P/B=70, PEG=70, 52w Position %=110, Discount from 52w High=130,
  Rev Growth=90, ROE=70, D/E=70, FCF=110
- Conditional: `52w Position %` color scale — 0% = red, 50% = white, 100% = green
  (high position = near 52w high = expensive; low = potential entry)
- Conditional: `Discount from 52w High %` — values > 30% = green bg `#d9ead3`
  (meaningful dip from high), values < 10% = red bg `#fce8e6` (near highs)
- Conditional: `Trailing P/E` — values > 40 = light red, < 15 = light green
- Conditional: `PEG` — values > 2 = light red, < 1 = light green
- Alternating row banding

---

## Part 2: New Tab — `Decision_View`

This is the primary decision-making surface. It joins data from multiple tabs into
one scannable view, one row per position. Build `tasks/build_decision_view.py`:

### Source joins:
- **Base:** `Holdings_Current` — Ticker, Market Value, Weight, Unrealized G/L %,
  Daily Change %
- **Valuation_Card** (if exists): Trailing P/E, Forward P/E, 52w Position %,
  Discount from 52w High %
- **Agent_Outputs** latest run (max `run_ts` per ticker):
  - From `agent='valuation'`: signal_type, rationale (first 120 chars)
  - From `agent='macro'`: action (first 60 chars)
  - From `agent='thesis'`: action (first 60 chars)
  - From `agent='tax'`: signal_type (TLH flag if present)

### Output columns:
```
Ticker | Weight % | Market Value | Unreal G/L % | Daily Chg % |
Fwd P/E | 52w Pos % | Disc from High % |
Valuation Signal | Macro Signal | Thesis Signal | TLH Flag |
Top Rationale
```

### Decision View logic:
- **TLH Flag**: mark "⚠️ TLH" if ticker appears in Agent_Outputs with
  `signal_type='tlh_candidate'` from the tax agent
- **Top Rationale**: use valuation rationale if non-trivially different from
  "Insufficient data"; otherwise use macro action; otherwise thesis action
- Sort: positions with TLH flag first, then by Weight % descending
- Exclude CASH_MANUAL, QACDS from display

### Formatting for Decision_View:
- Header: dark navy, white bold, freeze row 1 + column A
- Column widths: Ticker=70, Weight=70, Market Value=110, Unreal G/L %=100,
  Daily Chg %=90, Fwd P/E=80, 52w Pos %=90, Disc from High=100,
  Valuation Signal=120, Macro Signal=200, Thesis Signal=200,
  TLH Flag=90, Top Rationale=400
- **TLH Flag cells**: red bg `#ea4335`, white bold — these are action items
- **Valuation Signal conditional** (same color scheme as Agent_Outputs):
  accumulate=green, trim=red, hold=yellow, monitor=blue
- **Unreal G/L %**: green font if > 0, red font if < 0
- **52w Pos %** color scale: low=green (potential entry), high=red (stretched)
- Row height 60px, text wrap on rationale column
- Alternating row banding
- **Bold + light yellow bg** for any row where TLH Flag is set

---

## Part 3: Improve `Agent_Outputs` Tab Readability

Revise `format_agent_outputs()` from any prior formatting script:

1. **Add Agent column back as visible** — hide Run ID (col A) and Timestamp (col C)
   but KEEP Agent (col B) visible, renamed display. Users need to know which agent
   fired a signal.

2. **Group rows visually by agent**: Insert a light separator (thick top border +
   light grey `#f3f3f3` background) at the first row of each new agent group.
   Agent order: tax → valuation → concentration → macro → thesis → bagger

3. **Filter out noise rows**: The 53 valuation "Insufficient data — MONITOR" rows
   are not useful. Add a note in column K (Summary Narrative): flag these with
   italic grey text "No FMP data — see Valuation_Card tab" rather than displaying
   the full repeated rationale. This makes the tab scannable.

4. **Highlight the 3 actionable tax rebalance rows** with a stronger yellow
   background `#fff2cc` and bold ticker text — these are the most immediately
   actionable signals in the whole dataset.

5. **Add a frozen summary row** at the top of Agent_Outputs (above the header)
   showing signal counts:
   - "Accumulate: N | Trim: N | TLH: N | Rebalance: N | Monitor: N"
   - Formula-based using COUNTIF on column E

---

## Part 4: Fix `Holdings_Current` KPI Row

The existing KPI row has formula errors because the `Is Cash` boolean detection
is broken. Replace the Cash KPI cell formula with a ticker-based approach:

Replace the Cash formula `=SUMIF(P3:P200,TRUE,G3:G200)` with:
```
=SUMIF(A3:A200,"CASH_MANUAL",G3:G200)+SUMIF(A3:A200,"SGOV",G3:G200)+SUMIF(A3:A200,"QACDS",G3:G200)
```

This hardcodes the known cash-equivalent tickers rather than relying on the
broken `Is Cash` boolean column. SGOV is a 0-3 month Treasury ETF that functions
as cash — including it gives a true dry powder number of ~$73K.

Also add a `Dry Powder` KPI cell (unrealized cash available to deploy):
```
=SUMIF(A3:A200,"CASH_MANUAL",G3:G200)+SUMIF(A3:A200,"SGOV",G3:G200)
```
Label it "💰 Dry Powder" — this is the strategic cash position.

---

## Part 5: `Realized_GL` — Surface the Wash Sale Number

The $24,066 in disallowed wash sale losses needs to be the first thing visible
on this tab. The existing KPI row has this but it's not prominent enough.

1. Make the Disallowed KPI cell bold, red font `#ea4335`, larger (12pt).
2. Add a second KPI row below the existing one with:
   - "⚠️ WASH SALE RISK: Review before year-end. Disallowed losses cannot offset gains."
   - Merged across full width, orange bg `#ff9900`, white bold text
3. Flag ALL rows where `Disallowed Loss > 0` with a full-row orange background
   `#fff2cc` AND a red border on the Disallowed Loss cell itself.

---

## Script Structure

```
tasks/
  build_valuation_card.py    # Fetches yfinance data, writes Valuation_Card tab
  build_decision_view.py     # Joins all sources, writes Decision_View tab
  format_sheets_dashboard_v2.py  # Applies formatting to all tabs
```

Each script:
- `python tasks/build_valuation_card.py` — dry run (prints table)
- `python tasks/build_valuation_card.py --live` — writes to sheet
- Same pattern for `build_decision_view.py`
- `format_sheets_dashboard_v2.py --live` — applies all formatting

All scripts use:
- `get_gspread_client()` from `utils/sheet_readers.py`
- `config.PORTFOLIO_SHEET_ID`
- `DRY_RUN` default True, `--live` flag to enable writes
- Single-batch `ws.update()` — no per-row appends
- Fingerprint dedup on any append operations
- Try/except per ticker for yfinance failures

---

## Run Order

```bash
python tasks/build_valuation_card.py --live      # First — builds valuation data
python tasks/build_decision_view.py --live       # Second — needs valuation_card
python tasks/format_sheets_dashboard_v2.py --live  # Third — formatting pass
```

Add these three to `manager.py` as:
```
python manager.py dashboard refresh --live
```
which runs all three in sequence.

---

## Acceptance Criteria

- [ ] `Valuation_Card` tab exists with real P/E, P/B, PEG, 52w data for all
      individual equity positions (not ETFs)
- [ ] `Valuation_Card` color-codes stretched vs. discounted positions visually
- [ ] `Decision_View` tab joins holdings + valuation + agent signals into one row
      per position, sorted with TLH candidates at top
- [ ] TLH flag rows are visually distinct (red cell, bold row)
- [ ] `Holdings_Current` KPI row shows correct dry powder (~$73K SGOV + CASH)
- [ ] `Agent_Outputs` valuation noise rows replaced with "See Valuation_Card"
- [ ] `Realized_GL` wash sale warning is the first thing visible on that tab
- [ ] All scripts are idempotent — safe to re-run on next agent output cycle

---

## Separate Fix Required (Not This Script)

Tell Claude Code separately:

**Fix the valuation agent FMP dependency.** The `agents/valuation_agent.py`
pre-computation calls FMP for P/E and earnings surprises for all 53 positions.
FMP returns 402 (subscription limit) for ETFs and 429 (rate limit) for the tail
end of equities. The agent receives empty tables and produces useless signals.

Fix: extend `fmp_client.py` to fall back to yfinance `info` fields when FMP
returns 402/429. The `_YF_MAP` in `fmp_client.py` already maps yfinance fields —
use `trailingPE`, `forwardPE`, `priceToBook`, `pegRatio` as the fallback tier.
ETFs should be excluded from the valuation agent entirely (they have no P/E) —
filter them out in the pre-computation step before the FMP calls, same exclusion
list as the Valuation_Card script above.

**Fix the tax agent cash detection.** In `agents/tax_agent.py`, the cash
detection uses `df['Is Cash'].astype(bool)` or equivalent. Replace with:
```python
CASH_EQUIVALENT_TICKERS = {'CASH_MANUAL', 'QACDS', 'CASH & CASH INVESTMENTS', 'SGOV'}
cash_value = df[df['Ticker'].isin(CASH_EQUIVALENT_TICKERS)]['Market Value'].sum()
```
SGOV is a 0-3 month Treasury ETF functioning as strategic dry powder — it must
be counted as cash for the tax agent's position sizing and cash sufficiency checks.
