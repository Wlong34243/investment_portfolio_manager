# UI Improvement — Implementation Prompt Series

**Companion to:** `UI_IMPROVEMENT_PLAN.md` (the design authority — read it before any prompt)
**Date:** 2026-07-05
**Executor:** Claude Code / Sonnet / Gemini CLI

**Decisions locked in by Bill (do not re-litigate):**
1. Position table sorts by **Market Value, descending**.
2. **No tax section** on `0_DASHBOARD` — tax lives on `Tax_Control` only.
3. Nothing reads `0_DASHBOARD` programmatically — layout may change freely.

**Rules that apply to every prompt below (from CLAUDE.md — non-negotiable):**
- DRY_RUN defaults true. Every Sheet write requires explicit `--live`. Sequence is always DRY_RUN → verify output → `--live`.
- Single-batch gspread writes. Never cell-by-cell.
- Never write to `Target_Allocation`.
- Do not refactor `core/bundle.py`.
- Treat `UI_IMPROVEMENT_PLAN.md` Part 2 as the authoritative design spec. Do not re-derive or "improve" the layout.
- Each prompt starts with a Step 0 verification gate. If Step 0 findings contradict the prompt's assumptions, STOP and report — do not improvise.

Run the prompts in order. Each is standalone; do not start a prompt until the previous one's verification checklist passes.

---

## PROMPT 0 — Data-Layer Fixes

You are working in `C:\Users\WLong\Investment_Portfolio`. Read `CLAUDE.md` and `UI_IMPROVEMENT_PLAN.md` Part 1 first. This prompt fixes the data bugs (plan bugs #1, #2, #4, #6, #10) that corrupt every downstream view. No layout changes in this prompt.

### Step 0 — Verify before writing any code
1. Confirm these files exist and read them: `tasks/build_command_center.py`, `pipeline.py` (the Holdings_Current writer is around line 201 and its orchestrator around line 567), `utils/enrichment.py` (income calc around line 108–124), `utils/column_guard.py`.
2. In `pipeline.py`, identify exactly how the Holdings_Current row values are serialized before writing — find where Weight, Unrealized G/L %, Daily Change %, Dividend Yield, and Est Annual Income become strings or numbers. Record the current format of each (string with `%`, raw float fraction, raw float percent).
3. Run `python manager.py --help` to identify the CLI command that triggers the snapshot/Holdings_Current write, and the command that rebuilds the dashboard.
4. Report findings before proceeding.

### Task 0.1 — One percent convention, enforced at write time
Standardize: **all percent-like columns are written as numeric fractions** (0.079, not 7.9 and not "7.9%") with a Sheets number format of `0.0%` applied via `gspread_formatting`/batch format request. Apply to Holdings_Current writer in `pipeline.py` for: Weight, Unrealized G/L %, Daily Change %, Dividend Yield.
- Write values with `value_input_option="RAW"` so nothing is string-parsed by Sheets.
- Dollar columns (Market Value, Cost Basis, Unit Cost, Unrealized G/L, Est Annual Income) become numeric floats with `$#,##0.00` format — not pre-formatted strings.
- Quantity and Price stay numeric.

### Task 0.2 — Fix Est Annual Income (~100× too big)
Evidence: JEPI shows $350,701 annual income on a $41.5K position with an 8.45% yield (correct ≈ $3,507). `utils/enrichment.py:124` computes `MV * dividend_yield` and the comment claims yield is a raw decimal. Diagnose whether yfinance is returning percent-scale yields (yfinance changed `dividendYield` units in 2025 — 8.45 instead of 0.0845). Fix at the source so the stored Dividend Yield fraction and Est Annual Income are both correct. Add a sanity clamp: if computed yield > 0.25 (25%), divide by 100 and log a warning.

### Task 0.3 — Retire the `_normalize_pct` guessing heuristic
After Tasks 0.1–0.2 land and a fresh snapshot is written, `tasks/build_command_center.py` and `tasks/build_decision_view.py` must read percent columns as plain floats (fractions). Delete `_normalize_pct()` and every call to it. Readers must not guess scale.

### Task 0.4 — Fix `#NAME?` Day Change
In `tasks/build_command_center.py`, `_dollar_signed()` output like `+$530.00` is written with `USER_ENTERED` and parsed as a formula. This dies anyway in Prompt 1's rewrite, but fix the class of bug now: all writes in this task switch to `value_input_option="RAW"`.

### Task 0.5 — Wash Sale count is a count
The Tax_Control KPI strip renders "Wash Sales $111.00" — wherever the wash sale *count* is formatted as dollars (check the Tax_Control writer and `_read_tax_kpis`), make it an integer.

### Task 0.6 — Canonical Asset Class taxonomy
Holdings_Current "Asset Class" mixes classes ("Equity", "Fixed Income", "Cash") with sectors ("Technology", "Utilities", "Consumer Cyclical", "Financial Services", "Healthcare", "Industrials"). Root cause: `utils/enrichment.py:107` writes yfinance `sector` into the Asset Class column when the column name matches. Fix:
1. Define one canonical asset-class list in `config.py` (e.g., `ASSET_CLASSES = ["Equity", "Fixed Income", "Cash", "Commodity", "Real Estate"]`).
2. Enrichment must never overwrite Asset Class with a sector. If a sector column is wanted, add a separate `Sector` column — do NOT reorder or rename existing columns in this prompt.
3. Add a normalization map (sector name → "Equity", etc.) applied at snapshot-write time so existing bad values self-heal on the next snapshot.

### Verification checklist (all must pass before Prompt 1)
- [ ] Run snapshot in DRY_RUN: no percent column mixes formats; all values numeric.
- [ ] Run snapshot `--live`, then pull Holdings_Current: Weight column sums to 0.99–1.01 (as fractions); JEPI Est Annual Income between $3,000 and $4,000; Asset Class column contains only canonical values.
- [ ] Rebuild dashboard `--live`: no cell anywhere renders `#NAME?`; QQQM weight displays ≈ 7.9%; GOOG UGL % displays ≈ 42.6%.
- [ ] `grep -n "_normalize_pct" tasks/ utils/` returns nothing.
- [ ] `git diff --stat` touches only the files named above.

---

## PROMPT 1 — Rebuild `0_DASHBOARD`

Read `CLAUDE.md` and `UI_IMPROVEMENT_PLAN.md` Part 2. This prompt rewrites `_build_grid()` and `_apply_formatting()` in `tasks/build_command_center.py`. Prompt 0's checklist must already pass. Nothing reads 0_DASHBOARD programmatically — you may change the layout freely, but implement exactly the spec below.

### Step 0 — Verify before writing any code
1. Confirm Prompt 0 checklist passes (spot-check: Holdings_Current weights are numeric fractions).
2. Read `tasks/build_command_center.py` end to end. Read `get_latest_agent_outputs()` in `tasks/build_decision_view.py` (you will reuse it).
3. Confirm `gspread_formatting` is installed and note which of `CellFormat`, `NumberFormat`, `ConditionalFormatRule` it exposes in the installed version.
4. Check how cell notes can be written in the installed gspread version (`worksheet.update_notes` or a `batch_update` `updateCells` request with the `note` field).

### Layout spec (authoritative)

```
R1  PORTFOLIO COMMAND CENTER — As of <snapshot ts>        ← red background if snapshot >24h old
R2  Total Value | Day Change $ | Day % | MTD % | YTD % | vs SPY YTD | Cash % | Strategic Cash $ | Beta
R3  (blank)
R4  Ticker|MV|Wt%|Price|Day%|UGL $|UGL %|Fwd P/E|PEG|52w %|Trim|Add|→Trim %|→Add %|Signal
R5+ one row per position (~42), sorted by Market Value DESC, cash rows (config.CASH_TICKERS) excluded
... (blank)
Last row:  refresh <ts> | bundle <hash8> | token <status> | fmp cache <age>
```

**Removed vs. the old dashboard (do not carry over):** TAX POSTURE section, RISK SNAPSHOT section, TOP 10 section, DRIFT ALERTS section, ACCOUNT BALANCES section. R2 keeps only what's listed. Beta comes from Risk_Metrics `Portfolio Beta` (the one field there that works).

**Column sources and formats:**

| Col | Source | Format |
|---|---|---|
| Ticker | Holdings_Current | text, bold |
| MV | Holdings_Current Market Value | `$#,##0`, bold — this is Bill's primary column |
| Wt% | Holdings_Current Weight (fraction) | `0.0%` |
| Price | Holdings_Current Price | `$#,##0.00` |
| Day% | Holdings_Current Daily Change % | `+0.0%;-0.0%` |
| UGL $ | Holdings_Current Unrealized G/L | `$#,##0` |
| UGL % | Holdings_Current Unrealized G/L % | `+0.0%;-0.0%` |
| Fwd P/E | Valuation_Card "Forward P/E (yf)" | `0.0`, blank if missing |
| PEG | Valuation_Card PEG | `0.00`, blank if missing |
| 52w % | compute: (price − 52w low)/(52w high − 52w low) via one bulk `yf.download` call | `0%` |
| Trim / Add | Valuation_Card Trim/Add Target | `$#,##0.00`, blank if none |
| →Trim % | (trim − price)/price | `+0.0%;-0.0%`, blank if no trim |
| →Add % | (price − add)/add | `+0.0%;-0.0%`, blank if no add |
| Signal | Agent_Outputs latest run (reuse `get_latest_agent_outputs`), signal per ticker | text chip: ADD / TRIM / blank |

**Rationale:** the agent's rationale text goes into a **cell note** on the Signal cell (full text, not truncated). No rationale column.

**Formatting (single batch where the API allows):**
- Freeze rows 1–4 and column A.
- R1 navy background, white bold 12pt (existing style); switch background to red if snapshot timestamp (from Holdings_Current Import Date or Daily_Snapshots latest date) is >24h older than now.
- R2: label-value pairs bold; values with the number formats above (write raw numbers, RAW input option — the Day Change `+$` `#NAME?` bug must be impossible by construction).
- R4 header row: grey background, bold.
- Row banding on the position table (alternating white/light grey).
- Conditional format rules (real Sheets conditional formatting, not value-baked colors):
  - Day% and UGL %: red text if < 0, green text if > 0.
  - →Trim %: 3-color scale — green at 0% (at/past trim), white at +15%, grey beyond +30%.
  - →Add %: same scale mirrored (green at 0%, i.e., price at/below add target).
- Rows where Fwd P/E, PEG, Trim, and Add are all blank (pure ETFs with no targets): grey text for the valuation columns only — MV/weight/price stay full-contrast.

**Code requirements:**
- Data assembly: pandas join of Holdings_Current × Valuation_Card × agent signals on Ticker, inside `build_command_center.py`. Do not read Decision_View (it becomes signal-only in Prompt 2).
- One `ws.clear()` + one values write + batched formatting, as today (`safe_execute` wrappers).
- DRY_RUN prints the table via rich, plus a line stating how many conditional-format rules and notes *would* be written.
- Keep `main(live: bool)` signature so the existing `manager.py` wiring keeps working; verify in Step 0 how manager.py invokes it.

### Verification checklist
- [ ] DRY_RUN output shows ~42 position rows sorted by MV descending, QQQM first.
- [ ] `--live` run: open the sheet. R2 Day Change renders as a number (no `#NAME?`). Every percent column shows one decimal, sane magnitudes (no 2705%, no −429%).
- [ ] Clicking column headers → Data > Sort works on MV and Wt% (values are numeric).
- [ ] Signal cells for tickers with agent output (per current sheet: AMD, VTI, COF, NVDA, UNH, META, IFRA, NOW) carry hover notes with full rationale text.
- [ ] Tax, Risk, Top-10, Drift, and Account sections are gone.
- [ ] Whole view fits one screen at 100% zoom with frozen headers; horizontal scroll keeps Ticker visible.

---

## PROMPT 2 — Slim `Decision_View`, clean `Valuation_Card`

Read `CLAUDE.md` and `UI_IMPROVEMENT_PLAN.md` Parts 1–2. Prompt 1 must be live. These tabs stop duplicating the dashboard: Decision_View becomes the agent-signal surface; Valuation_Card stays the fundamentals deep-dive.

### Step 0 — Verify before writing any code
1. Read `tasks/build_decision_view.py` and `tasks/build_valuation_card.py` end to end.
2. Grep for any code that **reads** Decision_View or Valuation_Card (`grep -rn "Decision_View\|Valuation_Card" --include="*.py" .` excluding `archive/`). `build_command_center.py` reads Valuation_Card — list every column it consumes; those columns must survive unchanged. Confirm nothing outside these builders reads Decision_View.
3. Report findings before proceeding.

### Task 2.1 — Decision_View → signal rows only
- Filter to tickers with a signal from the latest agent run (currently ~8 rows). No signal, no row.
- Columns: `Ticker | Signal | Market Value | Wt% | Price | Trim | Add | →Trim % | →Add % | Fwd P/E | 52w % | Rationale`.
- Rationale is one wide column (~500px) with text wrap ON — full text, never truncated.
- Drop the empty RSI column. Drop "Disc from High %" (redundant with 52w %).
- Same write conventions as Prompt 1: RAW values, number formats, single batch, DRY_RUN default.
- Add a header row above the table: `AGENT SIGNALS — run <run_id> <run_ts>` so staleness of the signal set is visible.

### Task 2.2 — Valuation_Card cleanup
- Remove the `Forward P/E (FMP)` column entirely (100% empty; re-add only after the FMP-in-bundle migration ships). Update `build_command_center.py` if it references the column by name — Step 0 told you what it reads.
- Every data row must be padded to exactly the header width (current sheet has 13-cell rows under 14 headers).
- Market Cap: keep the raw number in the cell, apply a custom format so it displays as `$4.79T` / `$388B` (Sheets pattern: `[>999999999999]$0.00,,,,"T";[>999999999]$0.0,,,"B";$0.0,,"M"`).
- Sort by Market Value of the *position* (join Holdings_Current), descending — not by company market cap — so the card ranks by what Bill owns most of. Add a `Position MV` column right after Name, format `$#,##0`.
- Percent/ratio columns get proper number formats (Gross Margin `0.0%`, P/E and P/B `0.0`, PEG `0.00`).

### Task 2.3 (optional — skip if Step 0 finds positional readers) — Holdings_Current column order
- Grep every reader of Holdings_Current for positional column access (`iloc`, numeric indexes, `row[0]`-style). `utils/column_guard.py` is the likely enforcement point — read it first.
- Only if all access is name-based: reorder columns so plumbing (`Acquisition Date`, `Wash Sale`, `Is Cash`, `Import Date`, `Fingerprint`) sits at the far right, human columns (`Ticker`, `Description`, `Market Value`, `Weight`, `Price`, `Daily Change %`, `Unrealized G/L`, `Unrealized G/L %`, ...) lead.
- If ANY positional access exists, skip this task and note it in the completion report.

### Verification checklist
- [ ] Decision_View shows only signal rows, each with complete untruncated rationale, run_id visible in the header.
- [ ] Valuation_Card: no empty FMP column, market caps human-readable, rows aligned to headers, sorted by position MV.
- [ ] Rebuild 0_DASHBOARD (DRY_RUN) after the Valuation_Card change — the dashboard's Fwd P/E, PEG, Trim, Add columns still populate.
- [ ] If 2.3 executed: run the full snapshot + all builders in DRY_RUN with no KeyErrors.

---

## PROMPT 3 — Polish (optional; run only after living with 0–2 for a while)

### Step 0
Confirm Prompts 0–2 are live and Bill has used the new dashboard. Read `UI_IMPROVEMENT_PLAN.md` Phase 3.

### Tasks (independent — do any subset, in order of value)
1. **Portfolio sparkline:** in R2 (or a merged cell right of it), `=SPARKLINE(...)` over the last 30 rows of Daily_Snapshots Total Value. This is the one permitted `USER_ENTERED` write; isolate it as its own single-cell update.
2. **Drift section (conditional):** re-add a compact drift block below the position table **only if** Target_Allocation rows now cover ≥90% of portfolio MV (Bill must expand the tab manually first — check, don't assume; it covered 6 of 13 classes as of 2026-07-05).
3. **Risk row:** re-add a one-line risk strip only after Risk_Metrics produces a real Top Sector (not "Equity 100%") and non-zero Stress values. Fixing Risk_Metrics upstream is its own task — investigate its builder, report scope, and get sign-off before implementing.
4. **FMP forward P/E:** after `tasks/enrich_fmp.py` (bundle-bake migration) ships, re-add a real Forward P/E column to Valuation_Card and switch the dashboard to prefer it over yfinance.

### Verification
- [ ] Each added element renders correctly AND degrades gracefully (missing data → element absent, never an error cell).

---

## Completion report format (every prompt)

End each prompt's run with:
1. Files changed (`git diff --stat`).
2. Checklist status, item by item.
3. Anything found in Step 0 that contradicted this document.
4. Suggested commit message (do not commit unless asked).
