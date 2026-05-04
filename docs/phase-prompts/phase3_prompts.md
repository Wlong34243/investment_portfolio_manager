# Phase 3 Prompts — Tax Control Tab

**Status:** QUEUED. Do not start until Phase 2 is boring.

**Owner:** Bill. **Executor:** Claude Code or Gemini CLI, one prompt at a time.

**Governing rules:**
- Phase 3 does not start until Phase 2 is boring. No exceptions.
- Prompts run in order. Each is a single clean commit.
- DRY RUN → verify → `--live`, as always.
- Deterministic. Zero LLM calls in this phase.

---

## Why this phase exists

Tax visibility today is spread across `RealizedGL` (lot-level detail, scroll-heavy), `Config` (raw rate cells), and nothing else. To see where you stand YTD on realized gains, wash-sale disallowed loss, or an estimated federal cap gains number, you have to do math in your head.

Phase 3 elevates tax state to a first-class operating view: a single `Tax_Control` tab with four KPI cards, two ST/LT bridges, and a single table of tax-relevant lots — all computed deterministically from data you already have in the sheet.

This is explicitly **numbers, not narrative**. No agent. No LLM. The KPIs are pure Python math over `RealizedGL` + `Config`.

The full conceptual spec is in `/mnt/project/plan_tax` (and already referenced in project knowledge). These prompts are the implementation of that spec.

---

## Scope

In scope:
- New `Tax_Control` tab with KPIs + bridges + table
- `tasks/build_tax_control.py` — deterministic computation task
- `tasks/format_sheets_dashboard_v2.py` — formatting rules extended to the new tab
- `manager.py tax refresh` — new CLI command
- `dashboard refresh` — optionally wire Tax_Control refresh in as a step
- `PORTFOLIO_SHEET_SCHEMA.md` — document the new tab
- User documentation updated to describe the tab

Out of scope for Phase 3:
- Capital loss carryforward modeling
- Per-account tax treatment logic beyond what's already in `RealizedGL.Account`
- State tax estimates
- Tax-loss harvesting suggestions (this tab gives you the number; the suggestion comes later, probably from the Export Engine in Phase 4)
- Any agent reasoning over tax state

---

## Pre-flight

Before starting Phase 3:

- [ ] Phase 2 completion gate fully passed (three boring mornings).
- [ ] `Config` tab has `tax_rate_short_term` and `tax_rate_long_term` populated with Bill's actual rates (not defaults). Verify with `python -c "from utils.sheet_readers import get_gspread_client; ..."`.
- [ ] `RealizedGL` tab has current-year data ingested (the 2025 realized lots CSV has already been imported per project knowledge).
- [ ] Decide: single calendar-year scope, or support a `--tax-year` flag? Default answer: single calendar year = current year. The flag is deferred unless Bill specifically wants historical tax-year views.

---

## Prompt 3.1 — Create the Tax_Control tab schema and constants

### Context

The `Tax_Control` tab is new. Before writing any computation logic, the schema, column constants, and tab registration must be in place so that the sheet exists and is writable.

### Task

1. **Read first:** `config.py`, `create_portfolio_sheet.py`, `PORTFOLIO_SHEET_SCHEMA.md`.

2. In `config.py`, add:
   ```python
   TAB_TAX_CONTROL = "Tax_Control"

   # Tax_Control has two zones: KPI strip (top) and tax-relevant lots table (bottom).
   # We model it as a single tab with section headers, not two tabs.
   TAX_CONTROL_KPI_LABELS = [
       "Net ST (YTD)",
       "Net LT (YTD)",
       "Disallowed Wash Loss (YTD)",
       "Est. Fed Cap Gains Tax",
       "Tax Offset Capacity",
       "Wash Sale Count",
       "Last Updated",
   ]

   TAX_CONTROL_LOTS_COLUMNS = [
       "Closed Date",
       "Ticker",
       "Account",
       "Term",
       "Gain Loss",
       "ST Gain Loss",
       "LT Gain Loss",
       "Wash Sale",
       "Disallowed Loss",
   ]
   ```

3. In `create_portfolio_sheet.py`, add `"Tax_Control"` to the SCHEMA dict with a minimal header row (will be fully populated by the build task). Header row should be descriptive enough that a human opening the tab before first build sees "this will be populated by `manager.py tax refresh`."

4. Update `PORTFOLIO_SHEET_SCHEMA.md` with the new tab section. Document:
   - The KPI strip structure (rows 1–3: section header, labels, values)
   - The bridge row (rows 5–7: section header, ST bridge, LT bridge)
   - The lots table (rows 9+: section header, column headers, data rows)
   - Data sources: `RealizedGL` and `Config` only
   - Write pattern: clear-and-rebuild each time (not append)
   - **Explicit disclaimer:** "Planning tool, not tax advice or a filing-ready figure"

5. Do **not** build the computation task yet. That's 3.2.

### Constraints

- **No computation logic in this prompt.** Only schema, constants, and tab creation.
- **Do not modify `RealizedGL` or `Config`.** Tax_Control is read-only with respect to its inputs.
- **Do not hardcode tax rates anywhere.** Rates come from `Config` only.

### Gate criteria

- [ ] `python create_portfolio_sheet.py` creates the `Tax_Control` tab on first run and prints "already exists" on subsequent runs
- [ ] `PORTFOLIO_SHEET_SCHEMA.md` has the new section, placed alphabetically or in the tax-relevant cluster
- [ ] `config.py` has the new constants, verified with `python -c "import config; print(config.TAB_TAX_CONTROL, config.TAX_CONTROL_KPI_LABELS)"`
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 3.1: Tax_Control tab schema and constants`

### What NOT to do

- Do not write any KPI math
- Do not touch `tasks/format_sheets_dashboard_v2.py`
- Do not register a `manager.py tax` command yet

---

## Prompt 3.2 — Build the tax KPI computation task

### Context

This is the core of Phase 3: deterministic Python that reads `RealizedGL` and `Config`, computes the KPIs, and writes them to `Tax_Control`. No LLMs, no heuristics — just arithmetic that would survive a CPA audit.

### Task

1. **Read first:** `/mnt/project/plan_tax` (the full conceptual spec — especially sections 3.2.1 through 3.2.3). `pipeline.py::write_risk_metrics` for the pattern of "read sheet, compute, write back" that works well in this codebase.

2. Create `tasks/build_tax_control.py`. The task:

   a. Reads `RealizedGL` tab into a pandas DataFrame. Filters to rows where `Closed Date` falls in the current calendar year.

   b. Reads `Config` tab. Extracts `tax_rate_short_term` and `tax_rate_long_term` as floats. If either is missing or unparseable, abort with a clear error — do not silently default to zero.

   c. Computes the KPIs per the plan_tax spec:
      - `YTD_Realized_ST_Gains` = sum of positive `ST Gain Loss`
      - `YTD_Realized_ST_Losses` = absolute sum of negative `ST Gain Loss`
      - `YTD_Realized_LT_Gains` = sum of positive `LT Gain Loss`
      - `YTD_Realized_LT_Losses` = absolute sum of negative `LT Gain Loss`
      - `YTD_Net_ST` = gains − losses (signed)
      - `YTD_Net_LT` = gains − losses (signed)
      - `YTD_Disallowed_Wash_Loss` = sum of `Disallowed Loss` where `Wash Sale == True`
      - `Wash_Sale_Count` = count of rows where `Wash Sale == True`
      - `Net_Taxable_Capital_Gain_Est` = `max(YTD_Net_ST, 0) + max(YTD_Net_LT, 0)`
      - `Estimated_Federal_CapGains_Tax` = `max(YTD_Net_ST, 0) * rate_ST + max(YTD_Net_LT, 0) * rate_LT`
      - `Tax_Offset_Capacity` = `Net_Taxable_Capital_Gain_Est` if positive, else 0
      - `Last_Updated` = most recent `Import Date` in the filtered rows

   d. Assembles the tax-relevant lots table: same year-filtered rows, sorted by `abs(Gain Loss)` descending, **with all `Wash Sale == True` rows pinned to the top** regardless of size.

   e. Writes everything to `Tax_Control` in a single batch update. Layout:
      ```
      Row 1:  "TAX CONTROL — YTD Realized Tax Posture"                         (merged, header style)
      Row 2:  [Net ST]  [Net LT]  [Disallowed Wash Loss]  [Est. Fed Cap Gains Tax]  [Tax Offset Capacity]  [Wash Sale Count]  [Last Updated]
      Row 3:  (values for above)
      Row 4:  (blank spacer)
      Row 5:  "Short-Term Bridge (gains vs losses)"     "Long-Term Bridge (gains vs losses)"
      Row 6:  (ST gains / ST losses)                    (LT gains / LT losses)
      Row 7:  (blank spacer)
      Row 8:  "Tax-Relevant Realized Lots (YTD) — wash sales pinned on top"    (merged, section header)
      Row 9:  Closed Date | Ticker | Account | Term | Gain Loss | ST Gain Loss | LT Gain Loss | Wash Sale | Disallowed Loss
      Row 10+: data rows
      ```

   f. **Single batch write.** Use `ws.batch_update()` or `ws.update(range, values)` with one call per logical block (KPIs, bridge, table), not per cell.

   g. **Planning disclaimer.** Add a small row above or below the KPI strip: `"Planning tool — not tax advice. Estimates based on configured rates and realized data only."`

3. Add a companion helper in the same file: `compute_tax_control_data()` that returns a dict of all computed values. This decoupling allows future callers (Export Engine in Phase 4) to consume the computation without writing to the sheet.

4. Add a CLI command in `manager.py`:
   ```python
   tax_app = typer.Typer(help="Tax visibility and control.")
   app.add_typer(tax_app, name="tax")

   @tax_app.command("refresh")
   def tax_refresh(live: bool = typer.Option(False, "--live")):
       """Compute YTD tax KPIs and refresh the Tax_Control tab."""
       ...
   ```

5. Add loud DRY RUN / LIVE banners consistent with the rest of `manager.py`. On DRY RUN, print the computed KPI values to the terminal in a Rich table so Bill can spot-check before `--live`.

### Constraints

- **No LLM calls. Ever. In any path.** Tax numbers are arithmetic, not narrative.
- **No external tax APIs.** Everything comes from the sheet.
- **Do not model carryforward losses, state taxes, per-account tax treatment beyond what's already in RealizedGL.Account, or NIIT.** That's out of scope.
- **Do not subtract `YTD_Disallowed_Wash_Loss` from `Net_Taxable_Capital_Gain_Est`** — those losses are not currently usable, per the spec.
- **If both Net_ST and Net_LT are ≤ 0, Est Tax shows $0**, never a negative number.
- **Wash sale rows pin to top of the lots table** regardless of dollar size — visibility matters more than magnitude here.

### Gate criteria

- [ ] `python manager.py tax refresh` (DRY RUN) prints a Rich table with all KPI values and the first 10 rows of the lots table, with wash sales at the top
- [ ] Values match hand-calculation against a small test set (build one from the `All_Accounts_GainLoss_Realized_Details_20260330-220148.csv` in `/mnt/project/`)
- [ ] `python manager.py tax refresh --live` writes `Tax_Control` cleanly in a single batch
- [ ] Second `--live` run produces identical content (idempotent)
- [ ] If `Config` is missing tax rates, command aborts with a clear error (not a silent zero)
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 3.2: Build Tax_Control KPIs and lots table`

### What NOT to do

- Do not add formatting rules (that's 3.3)
- Do not wire into `dashboard refresh` yet (that's 3.4)
- Do not touch any other tab

---

## Prompt 3.3 — Apply conditional formatting to Tax_Control

### Context

The raw numbers work, but the tab needs color discipline so Bill can scan it in five seconds. The plan_tax spec has clear rules: green for positive gains / remaining tax-loss capacity, red for wash-sale disallowed loss and large estimated tax, amber for high net short-term gains.

### Task

1. **Read first:** `tasks/format_sheets_dashboard_v2.py`. Understand the existing conditional formatting request pattern (batch format requests to the Sheets API, how the existing Valuation_Card / Decision_View rules are structured and deduplicated).

2. Add a new formatting function — either `format_tax_control()` in the same file, or a dedicated `tasks/format_tax_control.py` that follows the same pattern. Either works; match the project's style. The function applies:

   **KPI cell rules (row 3 values):**
   - **Net ST (col B of row 3):** amber background if value > 0 AND value ≥ 2% of portfolio value; green if ≤ 0; neutral otherwise.
   - **Net LT (col C of row 3):** green if > 0; muted grey if slightly negative; neutral otherwise.
   - **Disallowed Wash Loss (col D of row 3):** red background if non-zero; neutral if zero.
   - **Est. Fed Cap Gains Tax (col E of row 3):** red background if ≥ $5,000 (configurable via a `Config` key `tax_estimated_tax_alert_threshold`, default 5000); amber if ≥ $1,000; neutral otherwise.
   - **Tax Offset Capacity (col F of row 3):** green if > 0 (opportunity); neutral if 0.
   - **Wash Sale Count (col G of row 3):** amber if ≥ 3 (cluster threshold, configurable via `tax_wash_sale_cluster_threshold`); neutral otherwise.

   **Lots table rules (rows 10+):**
   - Any row where `Wash Sale == TRUE`: full-row light red background (background, not bold, not red text — keep it readable).
   - `Gain Loss` column: green text if positive, red text if negative. No background.

3. Rules must be idempotent — re-running `tax refresh --live` does not stack duplicate rules. Use the same approach as the existing Valuation_Card formatting: remove prior conditional formatting rules on the tab before re-applying.

4. Add the two new `Config` keys mentioned above to the `Config` tab via `create_portfolio_sheet.py` if not already present (and document them in `PORTFOLIO_SHEET_SCHEMA.md`):
   - `tax_estimated_tax_alert_threshold` (default 5000)
   - `tax_wash_sale_cluster_threshold` (default 3)

### Constraints

- **Read thresholds from `Config`, never hardcode.** Defaults are fallbacks if `Config` is missing the keys.
- **No animations, no borders, no cell comments.** Background + text color only.
- **Preserve any existing formatting on `Config` and `RealizedGL`.** This prompt touches `Tax_Control` formatting only.

### Gate criteria

- [ ] After `python manager.py tax refresh --live`, the Tax_Control tab shows correct coloring: wash-sale rows light red, Est Tax red if above threshold, Disallowed Wash Loss red if non-zero, etc.
- [ ] Re-running does not stack conditional format rules (verify rule count on the tab)
- [ ] Thresholds pulled from `Config` work: manually change `tax_estimated_tax_alert_threshold`, re-run, formatting reflects the new threshold
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 3.3: Conditional formatting for Tax_Control`

### What NOT to do

- Do not color-code the lots table beyond wash-sale row highlighting and G/L sign coloring
- Do not add a legend tab
- Do not introduce new color palettes

---

## Prompt 3.4 — Wire Tax_Control into `dashboard refresh` and user docs

### Context

`Tax_Control` now works standalone (`tax refresh`). The final step is integrating it into the existing refresh workflow so Bill's weekly cycle is one command, not two, and updating the user-facing documentation.

### Task

1. **Read first:** `manager.py` dashboard_app group (`dashboard refresh`), `portfolio_manager_user_docs.html`.

2. In `manager.py dashboard refresh`, add a new step after `format_v2` and before the final success banner:
   ```
   Step 4: Refreshing Tax_Control...
   ```
   It calls the same `tax_refresh` function. Use `tax_refresh(live=live)` — the same `--live` flag propagates.

3. Add a flag to `dashboard refresh` so the tax step can be skipped if desired:
   - `--skip-tax` (boolean, default False)
   - When set, prints "Tax_Control refresh skipped." and continues.

4. Update `portfolio_manager_user_docs.html`:
   - Add a new section "Tax Visibility" after the existing "Reasoning Strategy" section.
   - Document the `Tax_Control` tab: what each KPI means, how to read the lots table, the planning disclaimer.
   - Update the "Weekly Operational Cycle" to mention that `dashboard refresh --live` now also refreshes Tax_Control.
   - Add a new line to the CLI command reference for `tax refresh`.
   - Bump the version from "Version 2.0 (Phase 2 Pivot)" to "Version 2.1 (Tax Visibility Added)".

5. Add a one-liner health check (if `manager.py health` is implemented per Phase 1.4): report the age of the last `Tax_Control` refresh by reading the `Last_Updated` KPI cell. Treat "stale" as > 7 days.

### Constraints

- **Do not break `dashboard refresh`** for people who don't want the tax step — the skip flag is there for that.
- **Preserve all existing refresh steps and order.** Tax refresh is additive, always last.
- **User docs update goes in the same commit.** Code and docs ship together.

### Gate criteria

- [ ] `python manager.py dashboard refresh --live` now includes a Step 4 that refreshes Tax_Control
- [ ] `python manager.py dashboard refresh --live --skip-tax` skips the tax step cleanly
- [ ] `portfolio_manager_user_docs.html` has a new Tax Visibility section with screenshots or at minimum textual description of the KPIs
- [ ] `python manager.py health -v` (if Phase 1.4 is in place) shows the age of the last Tax_Control refresh
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 3.4: Wire Tax_Control into dashboard refresh + user docs`

### What NOT to do

- Do not change the behavior of `snapshot` or `sync transactions`
- Do not auto-promote tax loss harvesting suggestions (that's Phase 4 Export Engine territory)
- Do not touch the RE Property Manager sheet

---

## Phase 3 Completion Gate

Phase 3 is complete when all four prompts have been executed, gated, and committed, **and** the following test passes:

```bash
# Full cycle
python manager.py health
python manager.py snapshot --live
python manager.py sync transactions --live
python manager.py dashboard refresh --live

# Verify
# 1. Tax_Control tab exists with four KPI cards + bridges + lots table
# 2. KPI values match hand-calc against current RealizedGL year-filtered data
# 3. Wash-sale rows pin to top of lots table with light red background
# 4. Est. Fed Cap Gains Tax reads both rates from Config (not hardcoded)
# 5. Planning disclaimer visible on tab
# 6. Second run produces identical content (idempotent)
```

All of the following must be true:

- [ ] `Tax_Control` tab renders cleanly, KPIs match hand-calculation
- [ ] Conditional formatting is correct and idempotent
- [ ] `dashboard refresh` includes Tax_Control as Step 4
- [ ] User documentation updated
- [ ] `CHANGELOG.md` has four Phase 3 entries
- [ ] No regressions in Phase 1 or Phase 2

Only after Phase 3 is boring do we start Phase 4 (Export Engine).

---

## Notes for Bill

- **This is the deliverable that makes the redesign real.** The old description said "tax visibility is a first-class concern." After Phase 3, it actually is.
- **The planning disclaimer matters.** You're a CPA, so you know this more viscerally than most — but the tab needs to clearly label itself as a planning tool, not a filing-ready number. The disclaimer is not optional.
- **The estimated tax number will be conservative.** It doesn't subtract wash-sale disallowed losses (correctly, since they're not usable this year), doesn't account for carryforwards, and doesn't consider state taxes. That's the right default for a "think about this" number — it errs on the side of "you might owe more than you think."
- **Tax Offset Capacity is the number that creates behavioral leverage.** When you see "$X,XXX still available to offset" you're much more likely to do the year-end harvesting. That's the whole point.
