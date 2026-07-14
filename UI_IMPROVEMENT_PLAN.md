# Portfolio Sheet UI Improvement Plan

**Date:** 2026-07-05
**Scope:** `0_DASHBOARD`, `Valuation_Card`, `Holdings_Current`, `Decision_View`
**Goal:** One informationally dense, trustworthy view centered on what Bill actually uses: **valuations + current market value per position**, with trim/add distances as the action layer.

---

## Part 1 — What the audit found (read this first)

The four tabs were pulled live on 2026-07-05. The problem is not layout density — it's that
**the same per-ticker data is fragmented across four tabs, and the numbers on three of them
are visibly wrong.** A denser view built on broken numbers is worse than what exists.

### Data-quality bugs (blocker — fix before any redesign)

| # | Bug | Where | Evidence | Root cause |
|---|-----|-------|----------|-----------|
| 1 | Day Change shows `#NAME?` | 0_DASHBOARD B4 | `#NAME?` in cell | `_dollar_signed()` emits `+$530.00 (…)`; leading `+` with `USER_ENTERED` makes Sheets parse it as a formula. |
| 2 | Percent scaling chaos (×100 errors) | All four tabs | QQQM weight "0.10%" (really 7.9%); GOOG UGL "0.426" next to "7.80%"; Decision_View LLY "97.00%" weight (really 0.97%), Daily Chg "-429.00%", Fwd P/E "2705.00%" | `_normalize_pct()` guesses fraction-vs-percent per column, but Holdings_Current stores mixed formats ("6.77%" strings and raw floats in the same column). Percent number-format also applied to non-percent columns (P/E). |
| 3 | Decision_View sort is corrupted by bug #2 | Decision_View | LLY/AMD/BBJP/SPCX/DELL/XLF (all sub-1% positions) sit at the top because 0.97% became "97%" | Same scaling bug feeds the sort key. |
| 4 | Est Annual Income ~100× too big | Holdings_Current col L | JEPI shows $350,701/yr income on a $41.5K position (8.45% yield ⇒ ~$3,507) | Yield × MV computed with percent already ×100. |
| 5 | Risk snapshot is dead weight | 0_DASHBOARD row 11 | "Top Sector: Equity (100.0%)" (that's an asset class, not a sector); "Stress -10%: $0.00" | Risk_Metrics feeding wrong/empty fields. |
| 6 | Wash Sale count formatted as dollars | 0_DASHBOARD row 7 | "Wash Sales $111.00" — it's a count | Label/format mismatch in tax KPI strip. |
| 7 | `Forward P/E (FMP)` column is 100% empty | Valuation_Card col I | Empty for all 42 rows; some rows have 13 cells vs 14 headers → misalignment risk | FMP fundamentals not baked into bundle yet (see `project_fmp_bundle_migration` memory). Dead column should go. |
| 8 | RSI column is 100% empty | Decision_View col F | Empty for all rows | Never populated — remove or populate. |
| 9 | Rationale text truncated mid-sentence | Decision_View col N | "…discount f" | No wrap strategy; long text in a grid cell. |
| 10 | Asset Class column mixes taxonomies | Holdings_Current col C | Same column holds "Equity", "Technology", "Utilities", "Financial Services", "Consumer Cyclical" | Two different source taxonomies merged; this corrupts drift aggregation (bug #11). |
| 11 | Drift alerts are misleading | 0_DASHBOARD | "Industrials -18.1% UNDER" — Target_Allocation covers only 6 of 13 asset classes, and bug #10 splits equity across fake classes | Known gap (`project_target_allocation_gap` memory) + bug #10. |
| 12 | Stale data presented without warning | All | Dashboard "As of 2026-07-02" (3 days old), FMP cache 36d | No staleness banner; user can't tell at a glance. |
| 13 | Market cap unreadable | Valuation_Card col D | `4787764985856` | No `$4.79T` formatting. |

### Structural problem

Every tab re-lists the same ~42 tickers with overlapping columns:

- **Holdings_Current** — MV, weight, G/L, income (20 cols, includes plumbing like Fingerprint)
- **Valuation_Card** — P/E, PEG, P/B, margins, trim/add targets
- **Decision_View** — weight, MV, G/L, targets, 52w position, signals
- **0_DASHBOARD** — top-10 subset of the above + KPI strips

To answer "should I trim GOOG?" you currently cross-reference three tabs. The information
exists; the *join* is what's missing.

---

## Part 2 — Target design

### Principle

**One dense position table is the product.** KPIs are a two-row strip above it, not a page
of section headers with blank rows between them. Everything Bill uses daily fits on one
screen with frozen headers; sections he checks weekly (tax, system health) move down or
to a side block.

### New `0_DASHBOARD` layout (redo)

```
R1   PORTFOLIO COMMAND CENTER — As of <ts>          [STALE >24h banner, red]
R2   Total $613,146 | Day +$530 (+0.1%) | MTD +0.1% | YTD +8.5% | vs SPY -1.7% | Cash 0.4% / $2,392
R3   Net ST $31,334 | Net LT $11,061 | Est Fed Tax $8,553 | Offset Cap $42,396 | Wash: 3 | Beta 1.04
R4   (blank)
R5   ALL POSITIONS — sorted by Market Value                    (frozen through R5)
R6   Ticker | MV | Wt% | Px | Day% | UGL$ | UGL% | Fwd P/E | PEG | 52w% | Trim | Add | →Trim% | →Add% | Signal
R7+  ...42 rows, one per position, no pagination, no top-10 subset...
```

Column notes for the position table:

| Column | Source | Why |
|---|---|---|
| MV, Wt%, Px, Day%, UGL$/% | Holdings_Current | The core Bill uses most — MV gets the widest column and bold face |
| Fwd P/E, PEG | Valuation_Card / bundle | The valuation lens, inline — no tab-switch |
| 52w% | Decision_View calc | Position in 52-week range (0–100%) |
| Trim / Add / →Trim% / →Add% | Valuation_Card targets | →Trim% = (trim−px)/px; **conditional color scale: green as it approaches 0** |
| Signal | Decision_View agent output | Single word (ADD/TRIM/—); full rationale via cell **note** (hover), not a truncated column |

What gets **cut** from 0_DASHBOARD:
- Top-10 section (superseded — the full table is sorted by MV, top 10 are rows 7–16)
- Risk snapshot row (broken; restore only when Risk_Metrics produces real sector/stress numbers)
- Drift alerts (misleading until Target_Allocation covers all classes — move to a `Drift` section that renders **only** when target coverage ≥ 90% of portfolio MV)
- Account balances (empty; render only when `data/account_balances.json` exists)
- System health → single compact line at the very bottom (`refresh | bundle e38827a3 | token OK | fmp 36d`)

### Tab roles after the redesign

| Tab | Role |
|---|---|
| `0_DASHBOARD` | **The** daily UI: KPI strip + full joined position table. Read-only, rebuilt by CLI. |
| `Holdings_Current` | Raw data layer (unchanged schema — other tasks read it). Move `Fingerprint`, `Import Date`, `Is Cash`, `Wash Sale` to the far right so the human-relevant columns lead. |
| `Valuation_Card` | Deep-dive valuation reference (fundamentals, margins, ROIC, P/B). Drop the dead `Forward P/E (FMP)` column until bundle-baked FMP lands; format market cap as $X.XXT/B. |
| `Decision_View` | Agent-signal surface: **only rows with a signal** (ADD/TRIM/alerts), full rationale in a wide wrapped column. Stops duplicating the all-positions table. |

### Formatting rules (applies to every rebuilt tab)

1. **Write raw numbers, not pre-baked strings.** Use `value_input_option="RAW"` for text and
   real numeric values + `NumberFormat` (via `gspread_formatting` / `batch_update`) for
   `$#,##0`, `0.0%`, `0.00`. This kills the entire ×100 bug class, makes columns sortable,
   and fixes `#NAME?` (no leading-`+` strings).
2. Percent values stored as fractions (0.079) with percent number format — one convention,
   enforced at write time, never guessed at read time. Delete `_normalize_pct()` once all
   writers comply.
3. Conditional formatting instead of value-baked color: red/green on Day% and UGL%,
   color scale on →Trim% / →Add%, grey text on rows with no valuation data (ETFs).
4. Row banding + frozen header row + frozen ticker column for horizontal scroll.
5. One decimal on percents, whole dollars on MV (cents add noise, not information).

---

## Part 3 — Build sequence

Per repo convention: each phase is a prompt file, Step 0 verification gate, DRY_RUN → verify → `--live`.

### Phase 0 — Fix the data layer (blocker, do first)
**Touches:** `tasks/build_command_center.py`, `tasks/build_decision_view.py`, whatever writes Holdings_Current.
1. Standardize all percent writes to numeric fractions + number format (bugs #1, #2, #3).
2. Fix Est Annual Income ×100 (bug #4).
3. Fix wash-sale count formatting (bug #6).
4. Normalize Asset Class taxonomy at snapshot time — one canonical class list (bug #10).
5. Verification: re-run all builders in DRY_RUN, assert no cell renders `#NAME?`, weights sum to ~100%, JEPI income ≈ $3.5K.

### Phase 1 — Redo `0_DASHBOARD`
**Touches:** `tasks/build_command_center.py` (rewrite of `_build_grid` + `_apply_formatting`).
1. Implement the layout in Part 2: 3-row KPI strip + full 42-row joined table.
2. Join Holdings_Current × Valuation_Card × Decision_View signals in pandas (already all read by this task).
3. Staleness banner: red fill on R1 if snapshot date > 24h old.
4. Signal rationale as cell notes (`ws.update_notes` / batch note request), not a column.
5. Gate drift/accounts/risk sections behind data-existence checks.
6. Verification checklist: single batch write, sortable numeric columns, dashboard readable at 100% zoom on one screen.

### Phase 2 — Slim `Decision_View` + `Valuation_Card`
1. Decision_View: filter to signal rows only; wide wrapped Rationale column; drop empty RSI; fix or drop Fwd P/E scaling.
2. Valuation_Card: drop `Forward P/E (FMP)` (until FMP-in-bundle migration lands), format market cap, pad all rows to header width.
3. Reorder Holdings_Current columns (plumbing to the right) — **verify first** that no reader indexes columns by position rather than name.

### Phase 3 — Polish (optional, after living with Phases 0–2)
1. 30-day portfolio sparkline in the KPI strip via `=SPARKLINE(Daily_Snapshots!...)`.
2. Per-position 30d sparkline column if Daily_Snapshots granularity supports it.
3. Restore Risk + Drift sections once Risk_Metrics and Target_Allocation are fixed upstream
   (Target_Allocation expansion is Bill's manual task — 6 of 13 classes covered today).
4. FMP-in-bundle migration (`tasks/enrich_fmp.py`) then re-add real Forward P/E.

---

## Part 4 — Explicitly out of scope

- No writes to `Target_Allocation` (manual-only surface).
- No new data vendors; no live FMP calls from builders.
- No Streamlit / web UI — Sheets remains the visual layer.
- No buy/sell recommendations added to any view; Signal column only surfaces existing sandboxed agent output.

---

## Decisions (Bill, 2026-07-05)

1. **Sort default:** Market Value, descending.
2. **Tax strip:** dropped from 0_DASHBOARD entirely — tax lives on `Tax_Control` only.
3. **Dependencies:** nothing reads `0_DASHBOARD` programmatically; layout may change freely.

Implementation prompt series: `UI_IMPROVEMENT_PROMPTS.md`.
