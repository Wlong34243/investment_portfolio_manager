# Claude Code Prompt: Agent Utility Improvements + Thesis Quantitative Tightening

**Context for Claude Code:** This prompt is executed sequentially. Each section is a separate, self-contained work unit. Complete one before starting the next. Commit after each section with the indicated message. All work is DRY RUN by default — the `--live` flag is explicit per section.

**Pre-flight reading (do this first, once):**
- `CHANGELOG.md` — most recent 20 entries
- `CLAUDE.md` — full file
- `agents/analyze_all.py` — understand the orchestrator and `_result_to_sheet_rows`
- `agents/prompts/` — read all eight `.txt` prompt files
- `agents/schemas/` — read `valuation_schema.py`, `thesis_screener_schema.py`, `concentration_schema.py`, `macro_cycle_schema.py`, `bagger_schema.py`
- `config.py` — Phase 5 constants section (token budgets, thresholds)
- `utils/fmp_client.py` — yfinance fallback tier and error handling
- `tasks/enrich_technicals.py`, `tasks/enrich_atr.py` — bundle enrichment pattern

**Status reporting:** At the end of each section, print a verification block in this exact format:

```
SECTION [N] COMPLETE
Files changed: [list]
Tests run: [list with PASS/FAIL]
Known issues: [list, or "None"]
Ready for next section: [yes/no]
```

---

## Section 1 — Fix the three agent failures (infrastructure, not tuning)

The April 20 `analyze-all --live` run produced three failures visible in the terminal log:

1. `macro: AttributeError: 'list' object has no attribute 'get'`
2. `thesis: RuntimeError: Gemini returned no result` (Pydantic parse failed because Gemini hit `FinishReason.MAX_TOKENS`)
3. `bagger: RuntimeError: Gemini returned no result` (same MAX_TOKENS cause)

Fix all three before touching anything else. No amount of prompt tuning matters if agents never finish speaking.

### 1a — Macro agent AttributeError

**Action:**
- Open `agents/macro_cycle_agent.py`. Locate the `.get(` call that's being called on a list.
- The most likely culprit is accessing `composite["calculated_technicals"]` or `composite["calculated_technical_stops"]` — if either has been restructured to a list-of-dicts instead of dict-keyed-by-ticker, the agent code may still be calling `.get(ticker)` on it.
- Check the shape actually injected by `tasks/enrich_technicals.py` and `tasks/enrich_atr.py` (both inject by ticker key, but verify).
- Fix the dereference. Add a guard: if the enrichment key is missing or wrong-shaped, log a warning and fall back to fundamentals-only mode (this agent already has graceful degradation — preserve it).
- Do NOT change the Gemini prompt or schema.

**Test:**
```bash
python manager.py agent macro analyze --bundle latest
```
Expect completion without exception. Output may be limited if `calculated_technicals` is empty; that is acceptable.

### 1b — Thesis and Bagger token truncation

Per `config.py`, token budgets exist per agent. The run shows both thesis and bagger agents hit `FinishReason.MAX_TOKENS`. The current budget values in `config.py` for these two agents are under-sized for the current ~50-position portfolio, even with chunking.

**Action:**
- Open `config.py`. Find the `GEMINI_MAX_TOKENS_*` constants.
- If `GEMINI_MAX_TOKENS_THESIS` and `GEMINI_MAX_TOKENS_BAGGER` exist, raise them. If they don't exist, add them:
  ```python
  GEMINI_MAX_TOKENS_THESIS = 12000   # per chunk — thesis narrative is verbose
  GEMINI_MAX_TOKENS_BAGGER = 10000   # per chunk — bagger candidate narratives
  ```
- Open `agents/thesis_screener.py` and `agents/bagger_screener.py`. Locate every `ask_gemini(..., max_tokens=...)` call. Replace hardcoded values with `config.GEMINI_MAX_TOKENS_THESIS` / `config.GEMINI_MAX_TOKENS_BAGGER`.
- Verify chunk size is appropriate: if `CHUNK_SIZE` in `agents/utils/chunked_analysis.py` is still 15, leave it. If larger, drop to 12 for these two agents only (chunk-level override).

**Test:**
```bash
python manager.py agent thesis analyze --bundle latest
python manager.py agent bagger analyze --bundle latest
```
Expect completion. Check the debug output — `FinishReason.STOP`, not `FinishReason.MAX_TOKENS`.

### 1c — FMP earnings-surprises endpoint is dead (404 for every ticker)

The terminal log shows `FMP earnings surprises error for [ticker]: 404 Client Error: Not Found` for every ticker the Valuation Agent queried. The `/stable/earnings-surprises` endpoint either moved or is now paywalled.

**Action:**
- Open `utils/fmp_client.py`. Locate `get_earnings_surprises_cached`.
- Check the current endpoint URL. If it's `/stable/earnings-surprises`, try `/v3/earnings-surprises/{symbol}` (older FMP path). Test with a single ticker (`UNH`) via a quick script.
- If neither works on the free tier, acknowledge the degradation: update the function to return an empty list without logging a warning per-ticker, and set a module-level flag `FMP_EARNINGS_AVAILABLE = False`.
- In `agents/valuation_agent.py`, the pre-computation should check this flag and not request earnings-surprises data if unavailable. Log once at the start of the agent run: "FMP earnings-surprises endpoint unavailable; skipping earnings surprise pre-computation."
- This removes ~50 lines of 404 warnings from every `analyze-all` run.

**Test:**
```bash
python manager.py agent valuation analyze --bundle latest 2>&1 | grep -c "404 Client Error"
```
Should print `0`.

**Commit:** `fix: resolve macro AttributeError, raise thesis/bagger token budgets, suppress dead FMP endpoint warnings`

---

## Section 2 — Make Agent_Outputs readable

The sheet currently has:
- No real column headers (only `run_id` and `signal_type` are labeled; 9 columns are unnamed)
- Every row carries a full 64-char UUID `run_id` and ISO timestamp — 80% of each row is noise
- 43 of 50 rows from the April 20 run are `signal=hold` with nearly identical narrative
- The `action` column on Concentration rows is truncated mid-sentence at ~100 chars, while the full text is in `scale_step` — two columns, one truncated
- One row flags "97.24% of portfolio in 'Unknown' sector" — that's a data quality fire, not a finding

Goal: make this sheet something Bill can actually skim on Sunday morning.

### 2a — Add a proper header row

**Action:**
- Open `agents/analyze_all.py`. Locate `_AGENT_OUTPUTS_HEADER` or wherever the column header list is defined. If no header row is being written, write one.
- Use these 11 column names (matches the current 11-column write schema):
  ```
  run_id | timestamp | bundle_hash | agent | signal | ticker | action | narrative | scale_step | severity | score
  ```
- The header row should be row 1, frozen. The write path should NOT overwrite row 1 on subsequent `--live` runs — archive-before-overwrite should preserve it.

**Test:** Open the sheet after a dry-run write preview; verify the header row is present and correct.

### 2b — Collapse run_id and timestamp into a single compact "Run" column

**Action:**
- In `agents/analyze_all.py`, change `_result_to_sheet_rows` (or whichever function emits rows to `Agent_Outputs`) to:
  - Replace the full UUID `run_id` with the first 8 characters
  - Format timestamp as `YYYY-MM-DD HH:MM` (no seconds, no microseconds, no T, no Z)
  - Drop `bundle_hash` entirely from the sheet output — it's in the manifest file for provenance; it doesn't belong in a human-readable sheet
- New column set becomes:
  ```
  run_date | run_id_short | agent | signal | ticker | action | narrative | scale_step | severity | score
  ```
  (10 columns)
- Update the header row constant accordingly.
- Update the archive tab format to match.

**Test:**
```bash
python manager.py analyze-all --fresh-bundle --agents valuation
```
Dry run. Inspect the preview output. Verify `run_date` is `2026-04-20 07:52`, `run_id_short` is 8 chars, no `bundle_hash` column.

### 2c — Deduplicate repetitive HOLD rows

The April 20 run produced 43 HOLD rows from the Valuation Agent with the same recommendation and nearly identical narrative structure ("Trading close to its 52-week high, thesis says hold, fair value"). The information value of these rows is zero on a per-row basis — they're collectively saying "no signals today."

**Action:**
- Add a post-processing step in `agents/analyze_all.py` that collapses `severity=info` + `signal=hold` rows from the Valuation Agent into a single summary row per agent:
  - `ticker` column: `[HOLD SUMMARY — N positions]`
  - `action` column: `Hold — see narrative for position list`
  - `narrative` column: comma-separated list of tickers, capped at 50 tickers then `+N more`
  - `scale_step`: empty
  - `severity`: `info`
  - `score`: empty
- The individual HOLD rows are still written to the archive tab for audit.
- Only rows with `severity=action` OR `severity=alert` go to the main `Agent_Outputs` tab as individual rows.

**Rationale:** Bill opens the sheet on Sunday to see what needs his attention, not to read 43 variations of "nothing here." The summary row preserves the information that all those positions were evaluated.

**Test:**
Run `analyze-all` in dry mode. Verify the preview shows:
- 1 HOLD_SUMMARY row for Valuation (listing all HOLD tickers in the narrative)
- Individual rows for each ACCUMULATE/TRIM/EXIT signal
- Individual rows for each Concentration flag
- The Tax agent's portfolio_summary row
- Total row count should drop from ~50 to ~10-15 per week in normal market conditions

### 2d — Fix the `action` column truncation and redundancy with `scale_step`

The Concentration rows show `action` truncated mid-word while `scale_step` holds the full text. Two columns, redundant data, one broken.

**Action:**
- Pick one: either use `action` for a short (≤100 char) headline AND `scale_step` for full narrative, OR drop one of them.
- Recommended: keep both but make them semantically distinct:
  - `action`: a short imperative headline, ≤80 chars, NEVER truncated (if the agent generates a longer one, truncate cleanly on a word boundary with "…")
  - `scale_step`: the full recommendation text, no length cap
- Add a helper function in `agents/analyze_all.py`:
  ```python
  def _clean_headline(text: str, max_len: int = 80) -> str:
      if len(text) <= max_len:
          return text
      truncated = text[:max_len].rsplit(" ", 1)[0]
      return truncated + "…"
  ```
- Apply this to all `action` column values regardless of source agent.

**Test:** Verify no `action` cell in the preview exceeds 80 characters or ends mid-word.

### 2e — Surface data quality problems separately from findings

The Concentration Agent flagged `97.24% of portfolio in 'Unknown' sector` as a sector-concentration finding. This is not a portfolio risk — it's a data pipeline problem. The `asset_class` field isn't being populated for most positions.

**Action:**
- In `agents/concentration_hedger.py`, before the sector-concentration check runs, add a data quality guard:
  ```python
  unknown_pct = sum_weights_where(asset_class in ("Unknown", "", None))
  if unknown_pct > 0.10:  # more than 10% unclassified
      add_data_quality_flag(f"{unknown_pct:.1%} of portfolio has unclassified asset_class; sector analysis unreliable")
      skip_sector_concentration_check = True
  ```
- Data quality flags go to a new row with `severity=data_quality` (not `info` or `action`). Display these at the TOP of the `Agent_Outputs` tab sort order.
- If `skip_sector_concentration_check` is true, the agent returns sector findings as empty and notes the skip in its summary narrative.

**Rationale:** A dashboard that says "97% of your portfolio is in Unknown" makes the agent look broken. The data quality flag makes it clear the pipeline needs attention, separately from any portfolio insight.

**Commit:** `refactor: Agent_Outputs readability — proper header, compact run_id, HOLD summary, column discipline, data quality surfacing`

---

## Section 3 — Decision View integration with filtered Agent_Outputs

Now that Agent_Outputs is readable, wire it into the existing Decision_View so Bill has one dashboard scan point.

**Action:**
- Open `tasks/build_decision_view.py`.
- Add a new column (or columns) to Decision_View that pulls the latest per-ticker signal from Agent_Outputs, where severity in (`action`, `alert`, `data_quality`).
- Each position row in Decision_View should show: latest Valuation signal (if non-hold), latest Thesis verdict (once Section 4 lands), latest Concentration flag (if flagged).
- If no active signal for a ticker, the cell is empty (not "Not Evaluated").

**Test:**
```bash
python manager.py dashboard refresh
```
Open Decision_View in Sheets. Verify UNH shows an Accumulate signal, JPIE shows a Concentration flag, and most other positions have empty cells in the new signal columns.

**Commit:** `feat: Decision_View integrates Agent_Outputs action signals`

---

## Section 4 — Thesis + Valuation verdict alignment (tuning, finally)

Only start this section after Sections 1-3 are complete AND a clean `analyze-all --live` run has been verified end-to-end. The previous tuning conversation established the pairing logic; this implements it.

### 4a — Add per-position verdict to Thesis Screener

**Action:**
- Open `agents/schemas/thesis_screener_schema.py`. In `ManagementEvaluation`, add:
  ```python
  per_position_verdict: Literal["HOLD", "TRIM", "ADD", "EXIT", "MONITOR"] = Field(
      description="Single verdict grounded in the position's _thesis.md exit_conditions. "
                  "MONITOR if no thesis file exists (forcing function for backfill)."
  )
  verdict_reasoning: str = Field(
      max_length=600,
      description="One paragraph citing the specific thesis-break condition from _thesis.md "
                  "that is or isn't triggered. No generic risks."
  )
  ```
- Open `agents/prompts/thesis_screener_system.txt`. Add a new section near the end:

  ```
  ## Verdict Discipline

  For each position, produce a single per_position_verdict grounded in the position's thesis file, not in the Baid framework alone.

  - HOLD: thesis intact, no exit condition triggered.
  - ADD: thesis intact AND an asymmetric add opportunity exists. Only if the position is not at its style's size ceiling (see styles.json position_size_guidance).
  - TRIM: one exit condition triggering OR rotation_priority is high/medium AND a better opportunity exists. Default to staged sizing language.
  - EXIT: two or more exit conditions triggering, OR "What Would Break This" conditions in the thesis file are demonstrably true now.
  - MONITOR: no thesis file exists for this position (has_thesis=false in the bundle). Do NOT invent a thesis. Verdict reasoning: "Thesis file needs backfill before a verdict can be issued."

  If a position's last_reviewed date is older than 90 days, append to verdict_reasoning: "Thesis last reviewed [date]; consider re-examining before acting."
  ```

- Open `agents/thesis_screener.py`. In the pre-computation step, parse `exit_conditions` and `last_reviewed` from thesis frontmatter, inject into the per-ticker bundle. Compute `has_thesis` and `stale_thesis` flags in Python, inject as facts for Gemini.

**Test:**
```bash
python manager.py agent thesis analyze --bundle latest --ticker UNH
```
Expect output JSON with a `per_position_verdict` field for UNH.

### 4b — Align Valuation Agent verdict vocabulary with Thesis Screener

**Action:**
- Open `agents/schemas/valuation_schema.py`. Add alongside the existing `signal` field:
  ```python
  verdict: Literal["HOLD", "TRIM", "ADD", "EXIT", "MONITOR"] = Field(
      description="Uppercase verdict aligned with Thesis Screener vocabulary. "
                  "Maps from signal: accumulate->ADD, hold->HOLD, trim->TRIM, monitor->MONITOR."
  )
  ```
- Do NOT remove the existing `signal` field — keep for backward compatibility with downstream code.
- In `agents/valuation_agent.py`, after Gemini returns the Pydantic instance, map `signal` to `verdict` in Python (deterministic mapping, not a second LLM call):
  ```python
  _SIGNAL_TO_VERDICT = {"accumulate": "ADD", "hold": "HOLD", "trim": "TRIM", "monitor": "MONITOR"}
  ```

### 4c — Style-aware valuation logic in the prompt

**Action:**
- Open `agents/prompts/valuation_agent_system.txt`. Add a new section near the end (the bundle already has `calculated_technicals` and style tags available — this is prompt-only tuning):

  ```
  ## Style-Aware Valuation

  Apply valuation framing according to the position's style tag from styles.json:

  - GARP: Compare forward P/E to the position's own historical range and to sector median. The signal is re-rate potential. ADD when P/E is in bottom quartile of its historical range AND growth trajectory is intact. TRIM only when P/E exceeds historical median AND growth has visibly decelerated.

  - FUND (Boring Fundamentals): The key question is "is this dip a nothing-burger?" A nothing-burger setup is discount_from_52w_high > 15% AND no earnings miss in last 2 quarters AND calculated_technicals.rsi_14 < 40 (oversold) AND price within 5% of MA200 or above. When all four conditions hold, lean ADD — this is Bill's highest-hit-rate setup. Do NOT signal TRIM on FUND positions from valuation alone; only the Thesis Screener should trigger exits.

  - THEME: Forward P/E is mostly irrelevant. Focus on whether the theme is still live: prefer ADD only on theme-confirming strength (price above MA50 and MA200, trend_score >= 1). Default to MONITOR on thematic names showing indecision.

  - ETF: If the position passed VALUATION_SKIP_ASSET_CLASSES exclusion and still reached here, treat as MONITOR — ETF valuation is macro-driven, not P/E-driven.
  ```

- No Python changes needed for 4c — the bundle already carries style tags and calculated_technicals.

**Test:**
```bash
python manager.py agent valuation analyze --bundle latest --tickers UNH,XOM,CRWV,QQQM
```
Expect:
- UNH (GARP): verdict reflects GARP framing
- XOM (FUND): narrative mentions nothing-burger criteria
- CRWV (THEME): narrative mentions theme/trend_score
- QQQM (ETF): should have been excluded at pre-computation or signal MONITOR

**Commit:** `feat: Thesis per_position_verdict + Valuation style-aware logic + aligned verdict vocabulary`

---

## Section 5 — Tighten thesis files with quantitative measures

Bill's current `_thesis.md` template has Exit Conditions as free text. That's readable but doesn't give the Thesis Screener's pre-mortem guardrails anything crisp to check against. This section adds a structured quantitative section while preserving the narrative sections.

### 5a — Extend the thesis template with a Quantitative Triggers section

**Action:**
- Open `vault/thesis_template.md` (or wherever the canonical template lives — check `manager.py vault add-thesis` to find the source).
- Add a new section AFTER the existing "Exit Conditions" section and BEFORE "Position State":

  ```markdown
  ---

  ## Quantitative Triggers

  <!-- Machine-readable triggers. Keep the YAML block EXACT — parsers depend on it.
       Use null for fields that don't apply to this position's style. -->

  ```yaml
  triggers:
    # Valuation triggers (GARP, FUND)
    fwd_pe_add_below: null      # ADD if forward P/E drops below this
    fwd_pe_trim_above: null     # TRIM if forward P/E rises above this
    fwd_pe_historical_median: null  # the position's own 5-year median, for reference

    # Price/technical triggers (all styles)
    price_add_below: null       # ADD if price drops below this dollar level
    price_trim_above: null      # TRIM if price rises above this dollar level
    discount_from_52w_high_add: null   # ADD if % discount exceeds this (e.g., 0.15 for 15%)

    # Fundamental triggers (GARP, FUND)
    revenue_growth_floor_pct: null     # concern if YoY revenue growth drops below this
    operating_margin_floor_pct: null   # concern if operating margin drops below this

    # Position management
    style_size_ceiling_pct: null       # max weight for this position, per its style
    current_weight_pct: null           # auto-populated by weekly snapshot; do not edit
  ```
  ```

- The YAML block is parseable by `yaml.safe_load` — standard Python frontmatter pattern.

### 5b — Parse Quantitative Triggers in the thesis screener pre-computation

**Action:**
- Open `agents/thesis_screener.py`. In the thesis frontmatter parsing step, extend `parse_thesis_frontmatter()` to extract the `triggers:` YAML block (or add a companion function `parse_thesis_triggers()`).
- Inject the parsed triggers into each position's bundle context so Gemini sees them alongside the prose exit_conditions.
- Compute two Python-side facts and inject them:
  - `trigger_fired: List[str]` — which quantitative triggers in the thesis are currently firing (comparing trigger values to current price, weight, forward P/E from bundle)
  - `trigger_missing: List[str]` — which trigger fields are null in the thesis (backfill needed)
- These two computed lists become part of the Gemini context for that position.

- Update the Thesis Screener prompt to prefer firing quantitative triggers over prose exit_conditions when they conflict:
  ```
  ## Trigger Precedence
  Quantitative triggers from the thesis file (price levels, P/E thresholds, weight ceilings) override narrative exit_conditions when they conflict. If trigger_fired contains any entries, the per_position_verdict must cite at least one fired trigger in verdict_reasoning.
  ```

### 5c — CLI command to validate thesis quant completeness

**Action:**
- Add a new Typer command `manager.py vault thesis-audit` that:
  - Reads all `_thesis.md` files in the vault
  - Parses the `triggers:` YAML block from each
  - Reports: (a) positions with 100% trigger fields populated, (b) positions with partial population, (c) positions with no triggers block at all
  - Exits 0 regardless — this is reporting, not enforcement
- Output format: Rich table with columns `ticker | style | triggers_populated | triggers_total | status`
- Sort by `triggers_populated / triggers_total` ascending so Bill sees the worst-backfilled positions first.

**Test:**
```bash
python manager.py vault thesis-audit
```
Expect a table showing current thesis coverage. Most positions will have 0/N populated until Bill does the backfill work.

### 5d — Backfill priority guidance

**Action:**
- Do NOT attempt to populate any thesis trigger values on Bill's behalf. These require Bill's actual conviction levels.
- Write a standalone note file `vault/THESIS_BACKFILL_GUIDE.md` with:
  - Why quantitative triggers improve agent signal quality
  - Suggested backfill order (by position weight — UNH, GOOG, JPIE, AMZN first)
  - Examples of trigger values for each of the four styles (GARP, FUND, THEME, ETF), showing what "good" looks like
  - A note: "It is better to leave a trigger null than to invent a value. A null trigger is a known-missing data point; an invented trigger is a lie the agent will believe."

**Commit:** `feat: thesis quantitative triggers + screener integration + audit CLI`

---

## Section 6 — Verification run and final review

After all sections complete:

1. Run `python manager.py analyze-all --fresh-bundle` (dry run) and confirm all seven agents succeed (no MAX_TOKENS, no AttributeError, no Pydantic parse failures).
2. Run `python manager.py analyze-all --fresh-bundle --live` on a Sunday test cadence.
3. Open the `Agent_Outputs` tab. Confirm:
   - Proper header row is present
   - `run_date` is compact (no UUID, no ISO timestamps)
   - HOLD_SUMMARY row collapses all Valuation HOLD signals
   - Action rows are at the top of sort order (severity ordering)
   - Data quality flags (if any) are clearly marked, not mixed with findings
   - Action column text is never truncated mid-word
4. Open Decision_View. Confirm per-ticker signal columns are populated for action-severity signals only.
5. Run `python manager.py vault thesis-audit` and screenshot output for Bill's backfill queue.

**Final commit:** `chore: Phase 6 — Agent utility overhaul complete`

---

## Out of scope for this prompt (explicitly deferred)

- **FMP paid tier migration.** If Bill wants full earnings-surprises and income-statement data, that's a separate decision about spending on FMP Starter tier. For now, yfinance fallback + graceful degradation is acceptable.
- **New Idea Screener rejection-budget work.** Covered in a separate prompt file; do not touch `agents/new_idea_screener.py` in this work.
- **Disagreement detection between Thesis and Valuation agents.** Once both agents share verdict vocabulary (Section 4), disagreement detection is a natural next step but lives in its own prompt.
- **Styles.json per-style size ceilings.** Bill will edit `styles.json` directly; no code change needed.
- **FastAPI+HTMX dashboard or Looker Studio.** Still deferred. Agent_Outputs + Decision_View in Sheets is the current surface.

---

## Notes for Bill (read after Claude Code completes)

The five-layer tuning stack from the previous conversation still applies: **styles.json → thesis files → config thresholds → framework routing → agent prompts**. This prompt touches layers 2, 3, and 5. The highest-leverage layer remaining is still layer 1 (`styles.json`) — specifically, adding explicit per-style size ceilings (GARP 9%, FUND 5%, THEME 3%, ETF 8% — use your real numbers). That's a five-minute edit you should do yourself, ideally before the next Sunday run.

The thesis backfill is the work that converts this system from "interesting output" to "actionable output." The agents can only be as good as the thesis files they read. Section 5 gives you the structure; the substantive work is sitting down with your top ten positions and writing specific trigger values. A weekend afternoon of backfill will produce more signal quality improvement than months of prompt tuning.

One caution: when you start writing quantitative triggers, resist the urge to be precise about things you're not actually precise about. If you don't have a strong view on what forward P/E would make you trim UNH, leave it null. Null is honest; a guessed number becomes a trigger the agent treats as your conviction.
