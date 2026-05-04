# Phase 2 Prompts — Dashboard Color-Coding & Thesis Trigger Surfacing

**Status:** QUEUED. Do not start until Phase 1 is boring (three consecutive boring mornings per the Phase 1 completion gate in `phase1_prompts.md`).

**Owner:** Bill. **Executor:** Claude Code or Gemini CLI, one prompt at a time.

**Governing rules:**
- Phase 2 does not start until Phase 1 is boring. No exceptions.
- Prompts run in order. Each is a single clean commit.
- DRY RUN → verify → `--live`, as always.
- Read existing files before writing new code. No "while I'm here" scope creep.

---

## Why this phase exists

The thesis files already carry a machine-readable `triggers:` YAML block (see `manager.py vault add-thesis` template and `vault thesis-audit`). Fields like `price_add_below` and `price_trim_above` encode Bill's predetermined action zones on a per-position basis. Today, those numbers live in the thesis files and are surfaced only indirectly through agents.

Phase 2 pulls them forward onto the live dashboard so that at a glance, on any given morning, Bill can see which positions are sitting inside his own predefined action zones — without needing any agent to tell him.

This is the same spine principle as the rest of the system: **the dashboard should show deterministic state, not narrative.** The trigger targets are Bill's decisions, already made, already written down. The dashboard's job is to reflect them next to live price.

---

## Scope

In scope:
- Two new fields end-to-end: `price_trim_above`, `price_add_below`
- Full chain: thesis YAML → vault bundle → composite bundle → sheet writers → formatting
- Two new columns on `Valuation_Card` and `Decision_View`: **Trim Target**, **Add Target**
- Conditional formatting rules in `format_sheets_dashboard_v2.py`

Out of scope for Phase 2:
- The other trigger fields (`fwd_pe_*`, `discount_from_52w_high_add`, `revenue_growth_floor_pct`, `operating_margin_floor_pct`, `style_size_ceiling_pct`). These come later if the price-based version proves useful.
- `current_weight_pct` auto-population on the thesis side (separate concern; goes with weekly snapshot work).
- New agent logic. Phase 2 surfaces existing data. Agents are unchanged.
- Any Streamlit work. The dashboard is the Google Sheet.

---

## Pre-flight

Before starting Phase 2:

- [ ] Phase 1 completion gate fully passed (three boring mornings). See `phase1_prompts.md`.
- [ ] `python manager.py vault thesis-audit` has been run. At least a meaningful subset of theses must have `price_trim_above` and `price_add_below` populated — otherwise the columns will be empty and the value of the feature is unproven. Bill backfills whichever positions matter most; nulls are fine.
- [ ] `CHANGELOG.md` Phase 1 section is complete and tagged.

---

## Prompt 2.1 — Extract trigger targets into the vault bundle

### Context

`core/vault_bundle.py` parses each `vault/theses/{TICKER}_thesis.md` file and freezes the content into an immutable bundle. The `triggers:` YAML block is already inside those files. Today the vault bundle treats the thesis mostly as opaque content; it does not extract structured fields out of the YAML block for downstream consumption.

This prompt changes that: the two price trigger fields become first-class, structured attributes on each thesis entry in the vault bundle.

### Task

1. **Read first:** `core/vault_bundle.py`, `manager.py vault add-thesis` (for the canonical thesis template), `manager.py vault thesis-audit` (for the existing YAML parsing pattern — reuse the same regex and yaml loader approach for consistency).

2. In `core/vault_bundle.py`, during thesis ingestion, parse the `triggers:` YAML block from each thesis file using the same extraction pattern as `vault_thesis_audit`. Extract at minimum:
   - `price_trim_above` (float or null)
   - `price_add_below` (float or null)

3. Attach these to the per-ticker thesis record inside the vault bundle under a new `triggers` sub-object. Shape:
   ```json
   {
     "ticker": "UNH",
     "content_hash": "...",
     "triggers": {
       "price_trim_above": 640.0,
       "price_add_below": 480.0
     }
   }
   ```

4. **Parsing must be defensive.** If the YAML block is missing, malformed, or the fields are null, the ticker still appears in the bundle with `triggers: {"price_trim_above": null, "price_add_below": null}`. A parse failure is logged to the vault skip log, never raised.

5. **Content hash unchanged.** The `content_hash` already covers the entire thesis file including the YAML block, so no hash logic needs to change. Verify that `vault_hash` still computes cleanly after this change.

6. Add a one-line summary to the `vault snapshot` Rich table output: how many theses have at least one of the two trigger fields populated. Reuse the same status-color scheme as `thesis-audit`.

### Constraints

- **Do not change the thesis file format.** The YAML block template in `vault add-thesis` is the source of truth.
- **Do not extract the other trigger fields yet.** Only `price_trim_above` and `price_add_below` in this phase. The YAML parser can ignore the rest.
- **No changes to how thesis content is stored in the bundle.** Triggers are additive metadata, not a replacement for content.

### Gate criteria

- [ ] `python manager.py vault snapshot` runs cleanly against the current vault
- [ ] `vault_bundle.py` produces a bundle where at least one thesis has non-null `price_trim_above` / `price_add_below` (assumes at least one thesis has been backfilled; if not, Bill backfills one before this gate closes)
- [ ] Malformed YAML in a thesis file does not abort the snapshot — it produces a vault skip log entry
- [ ] `vault_hash` is stable across re-runs with unchanged inputs
- [ ] `tests/test_vault_bundle_smoke.py` (or a new focused test) covers: YAML present + populated, YAML present + null, YAML missing, YAML malformed
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 2.1: Extract price triggers into vault bundle`

### What NOT to do

- Do not surface triggers on any sheet yet — that's 2.3
- Do not touch composite bundle — that's 2.2
- Do not expand to the other trigger fields

---

## Prompt 2.2 — Propagate triggers through the composite bundle

### Context

`core/composite_bundle.py` combines the market bundle and the vault bundle into a single agent-ready artifact. Today it treats the vault bundle as a pointer. Phase 2 needs the trigger fields to be readable by downstream sheet-writer tasks (`build_valuation_card.py`, `build_decision_view.py`) without those tasks having to re-open the vault bundle.

The goal is **clean propagation**, not duplication. The composite bundle exposes an accessor; consumers use the accessor; the vault bundle remains the source of truth.

### Task

1. **Read first:** `core/composite_bundle.py`, `utils/gemini_client.py::ask_gemini_composite` (to understand how composite bundles are consumed today), `tasks/build_valuation_card.py`, `tasks/build_decision_view.py`.

2. Add a per-ticker accessor to the composite bundle — either a method or a resolved sub-dict — that returns `{"price_trim_above": float|None, "price_add_below": float|None}` for any ticker, sourced from the vault bundle.

3. The composite bundle continues to store sub-bundles as pointers (this is the existing architecture; do not flatten). The accessor is a convenience layer, not a merge.

4. For tickers without a thesis, the accessor returns `{"price_trim_above": None, "price_add_below": None}`. No exceptions raised, no log noise beyond a single debug-level line.

5. `composite_hash` remains a function of `market_hash + vault_hash` as today. Nothing in this prompt changes hash computation.

### Constraints

- **Do not duplicate data.** Triggers live in the vault bundle; the composite bundle references them.
- **Do not add triggers to the Gemini context preamble yet.** Agents don't need them for Phase 2 — this phase is about the dashboard, not agents.
- **No changes to `ask_gemini_composite`'s signature or behavior.**

### Gate criteria

- [ ] Composite bundle exposes a working accessor for the two trigger fields
- [ ] Accessor returns `None` cleanly for tickers without theses or without populated YAML
- [ ] `composite_hash` is stable across re-runs with unchanged inputs
- [ ] `manager.py bundle composite` output still matches the current Rich table shape, plus one new row showing how many tickers in the bundle have at least one trigger populated
- [ ] `manager.py bundle verify` still passes on the new composite bundles
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 2.2: Propagate price triggers through composite bundle`

### What NOT to do

- Do not write to any sheet
- Do not change agent behavior
- Do not flatten the composite bundle

---

## Prompt 2.3 — Add Trim Target / Add Target columns to the sheet writers

### Context

`tasks/build_valuation_card.py` and `tasks/build_decision_view.py` both write to the dashboard. They currently show live price alongside various valuation and decision signals. Phase 2 adds two new columns to each: **Trim Target** (from `price_trim_above`) and **Add Target** (from `price_add_below`), positioned directly next to the live price column.

This is the first user-visible surface of the feature. It is intentionally boring: raw numbers in columns, no logic beyond lookup.

### Task

1. **Read first:** `tasks/build_valuation_card.py`, `tasks/build_decision_view.py`, `PORTFOLIO_SHEET_SCHEMA.md` (to understand current column ordering and document what's changing).

2. In both writers:
   - Add two new columns: `Trim Target` and `Add Target`.
   - Position: immediately to the right of the current live price column (the exact price column name may differ between the two writers — verify before editing; the rule is "next to current price", not "column N").
   - Values pulled via the composite bundle accessor from 2.2.
   - Format: currency, two decimals. Null values render as empty cell, not `None` or `0`.
   - Empty cells are a legitimate state — this is how Bill knows a position has no trigger backfilled yet.

3. Update `PORTFOLIO_SHEET_SCHEMA.md` to reflect the new columns. Document:
   - Column letter positions will shift for anything to the right of price — note this explicitly
   - Source: `vault/theses/{TICKER}_thesis.md` → `triggers.price_trim_above` / `triggers.price_add_below`
   - Null semantics: empty cell means no trigger set in the thesis
   - These columns are derived from the composite bundle, not manually maintained in the sheet

4. Do **not** add headers or data for the other trigger fields. Only the two price fields.

5. Verify single-batch gspread write behavior is preserved. Adding two columns must not fragment writes into per-cell updates.

### Constraints

- **No formatting in this prompt.** This is data only. Color-coding is Prompt 2.4.
- **Do not rename or reorder any existing columns** beyond what's forced by the insertion. If a column shift is unavoidable, document it in `PORTFOLIO_SHEET_SCHEMA.md` in the same commit.
- **Do not add formulas.** These are written values from Python, not `=` formulas.
- **Single-batch writes preserved.** Fingerprint dedup, existing archive-before-overwrite semantics, everything unchanged.

### Gate criteria

- [ ] `Valuation_Card` and `Decision_View` both show `Trim Target` and `Add Target` columns next to current price
- [ ] Tickers with populated triggers show correct numeric values
- [ ] Tickers without triggers show empty cells, not zeroes or `None` strings
- [ ] `PORTFOLIO_SHEET_SCHEMA.md` updated with new columns and their source
- [ ] DRY RUN output looks right before `--live`
- [ ] Single-batch write semantics preserved (verify by running a second time — zero net changes)
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 2.3: Surface Trim Target / Add Target on dashboard`

### What NOT to do

- Do not apply any conditional formatting in this prompt
- Do not touch any other columns
- Do not add tooltips, notes, or cell comments
- Do not introduce any new dependencies

---

## Prompt 2.4 — Conditional formatting for action-zone visibility

### Context

With Trim Target and Add Target now rendered next to live price, Phase 2's final step is making them visually legible at a glance. `tasks/format_sheets_dashboard_v2.py` already owns all dashboard formatting. This prompt adds two conditional rules.

The rules are deliberately strict: the goal is for Bill to see at a glance which positions are currently sitting inside his own predefined action zones, without having to mentally compute anything.

### Task

1. **Read first:** `tasks/format_sheets_dashboard_v2.py`. Understand how existing conditional formatting is currently applied (batch format requests, range references, existing color palette).

2. Add two conditional formatting rules on the live price cell of both `Valuation_Card` and `Decision_View`:

   **Rule A — Trim Zone (hot)**
   - Condition: `Current Price >= Trim Target` AND `Trim Target is not empty`
   - Cell formatting: bold, background `#F4CCCC` (light red) or existing palette equivalent, text `#990000` (dark red)
   - This says: "you said you'd trim at this price; you're there"

   **Rule B — Add Zone (opportunity)**
   - Condition: `Current Price <= Add Target` AND `Add Target is not empty`
   - Cell formatting: bold, background `#D9EAD3` (light green) or existing palette equivalent, text `#274E13` (dark green)
   - This says: "you said you'd add at this price; you're there"

   **Neutral:** when price is between the two targets, or when either target is empty, no additional formatting on the price cell — use existing default formatting.

3. Use the existing palette in `format_sheets_dashboard_v2.py` if it already defines semantic red and green. Do not introduce new hex codes if equivalents exist. The specific codes above are fallbacks.

4. Apply rules to both `Valuation_Card` and `Decision_View`. Do not apply to any other tab.

5. Rules must be idempotent — re-running `dashboard refresh --live` must not stack duplicate conditional format requests. The pattern in `format_sheets_dashboard_v2.py` today already handles this; preserve that pattern.

### Constraints

- **Apply only to the live price cell** — do not color the Trim Target or Add Target cells themselves. Those stay neutral and readable.
- **No blinking, no borders, no notes.** Background + bold text only.
- **Preserve existing formatting rules.** This is additive.
- **Do not introduce a "warning" or "near-zone" third rule.** Two states plus neutral is the whole spec.

### Gate criteria

- [ ] After `python manager.py dashboard refresh --update --live`, the Valuation_Card and Decision_View show red-highlighted price cells for any position where price ≥ trim target, and green-highlighted price cells where price ≤ add target
- [ ] Positions with no trigger data show no new formatting
- [ ] Re-running `dashboard refresh --live` does not stack duplicate format requests (verify by checking conditional format count on the tab before/after)
- [ ] No regressions to any other conditional formatting already on those tabs
- [ ] Manually spot-check at least three positions: one in trim zone, one in add zone, one neutral
- [ ] `CHANGELOG.md` updated with a screenshot-worthy one-line description
- [ ] Single commit: `Phase 2.4: Conditional formatting for thesis action zones`

### What NOT to do

- Do not color the Trim Target / Add Target columns themselves
- Do not add a legend tab or comment cells
- Do not add warning thresholds (e.g., "within 2% of trim target")
- Do not add formatting to `Holdings_Current` or any other tab

---

## Phase 2 Completion Gate

Phase 2 is complete when all four prompts have been executed, gated, and committed, **and** the following end-to-end test passes:

```bash
# 1. Refresh vault + composite from scratch
python manager.py vault snapshot --live
python manager.py bundle composite --live

# 2. Verify triggers are flowing
python manager.py vault thesis-audit   # shows populated counts
python manager.py bundle verify <latest composite path>

# 3. Push to sheet
python manager.py dashboard refresh --update --live

# 4. Visual verification
# Open the Sheet → Valuation_Card and Decision_View
# Confirm: Trim Target and Add Target columns present, next to price
# Confirm: at least one price cell is highlighted red or green per the rules
# Confirm: positions without triggers show empty target cells, no highlight
```

All of the following must be true:

- [ ] `vault snapshot` extracts the two trigger fields into the vault bundle
- [ ] `bundle composite` exposes them via the accessor
- [ ] Both sheet writers render `Trim Target` and `Add Target` columns next to price
- [ ] Conditional formatting lights up correctly on the live price cell
- [ ] Idempotent: running the full refresh a second time produces zero new diffs
- [ ] `CHANGELOG.md` has four Phase 2 entries dated and committed
- [ ] No regression in Phase 1 health (`python manager.py health` still clean)

Only after Phase 2 is boring do we queue Phase 3.

---

## Notes for Bill

- **The whole value of Phase 2 depends on thesis backfill.** Empty columns look bad. Before running 2.3, make sure a meaningful subset of your positions have `price_trim_above` / `price_add_below` filled in. `vault thesis-audit` tells you where you stand. Backfill is transcription, not research.
- **Saturday-morning edits to thesis files are the right cadence** for keeping triggers fresh. Mid-week edits risk bundle hash mismatches if you're also running agents.
- **The two fields are deliberately the only ones.** We chose price because it's the most universally applicable trigger across all four investment styles — GARP, thematic, fundamentals, and ETFs. Valuation triggers like `fwd_pe_trim_above` are style-specific and more appropriate for the next phase.
- **If Phase 2 proves out**, the natural next phase is extending the same pipeline to the remaining trigger fields with style-aware conditional logic (e.g., only apply P/E-based rules to GARP and FUND, not ETFs). That is explicitly out of scope here.
- **If Phase 2 does not prove out** — if the columns stay mostly empty or the formatting feels like noise — the right move is to kill the feature and let agents do this work instead. The spine architecture makes that easy: remove the columns and the conditional format rules; the bundle layer stays.
