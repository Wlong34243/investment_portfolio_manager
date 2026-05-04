# Phase 5 Prompts — Trade Log Maturation & Decision Review

**Status:** QUEUED. Do not start until Phase 4 is boring.

**Owner:** Bill. **Executor:** Claude Code or Gemini CLI, one prompt at a time.

**Governing rules:**
- Phase 5 does not start until Phase 4 is boring. No exceptions.
- Prompts run in order. Each is a single clean commit.
- DRY RUN → verify → `--live`, as always.

---

## Why this phase exists

You said: *"the trade log has value to me for assessing my prior decisions and tuning my market timing."*

The staging pipeline already exists — `tasks/derive_rotations.py` clusters Schwab buys/sells into rotation candidates and writes them to `Trade_Log_Staging`; `manager.py journal promote` moves approved rotations into `Trade_Log`. That's the capture side.

What's missing is the **review** side. A Trade_Log with entries but no post-hoc attribution is just a list. Phase 5 makes it a feedback loop: when you rotated UNH into VEA on a given date, what happened to that pairing over the next 30, 60, 90, 180 days? What was the RSI on both sides at the moment of decision? Would you make that trade again?

This is the decision-tuning instrument. It turns the Trade_Log from a record-keeping obligation into the thing you check when you're about to do a similar rotation and want to know: *did the last three of these work?*

---

## Scope

In scope:
- Fix the known `Sell_Proceeds`/`Buy_Amount` column mismatch in `derive_rotations.py` (per project memory)
- `Trade_Log` post-hoc attribution: compute and display the P&L performance of each rotation over 30/60/90/180 days
- Decision context capture at the moment of rotation: RSI, MA vs price, trend_label on both sides
- New `Rotation_Review` tab — a deduplicated view of rotations with attribution columns, sortable, filterable
- `manager.py trade review` command that refreshes the attribution
- An export scenario `export rotation-retrospective` that packages the last N rotations for LLM-aided pattern analysis
- User documentation updated

Out of scope for Phase 5:
- Any auto-trading or auto-suggestion based on past performance
- Attribution that accounts for position sizing differences, dividends, or tax drag — this is a simple price-return comparison ("how did the pair move after the decision?"), not a full TWR
- Backtesting of hypothetical rotations that didn't happen
- ML-based pattern recognition across rotations

---

## Pre-flight

Before starting Phase 5:

- [ ] Phase 4 completion gate fully passed.
- [ ] Trade_Log has a meaningful history to review — if you're starting from a near-empty log, the review is meaningless. Before this phase, run `tasks/derive_rotations.py --since 2025-01-01 --days 90` to backfill rotation candidates from 2025 Schwab transactions, review them, and promote the ones that look right.
- [ ] Confirm the known bug state: open `tasks/derive_rotations.py` and note whether `Sell_Proceeds` / `Buy_Amount` columns are still misaligned. If they're fixed, skip Prompt 5.1 and renumber the rest.

---

## Prompt 5.1 — Fix `derive_rotations.py` and harden the capture side

### Context

Project memory flags a known bug: `tasks/derive_rotations.py` has a column mismatch on `Sell_Proceeds` / `Buy_Amount` that has been quietly producing wrong staging data. Before adding any attribution logic, the capture side must be correct.

### Task

1. **Read first:** `tasks/derive_rotations.py`, `config.TRADE_LOG_STAGING_COLUMNS`, `config.TRADE_LOG_COLUMNS`, `manager.py journal promote`.

2. Audit the column ordering and value assignments in `derive_rotations.py`:
   - Confirm that sell-side dollars are written to `Sell_Proceeds` (not `Buy_Amount`)
   - Confirm that buy-side dollars are written to `Buy_Amount`
   - Confirm the fingerprint formula is consistent with what `journal promote` expects

3. Fix any misalignment. Document the fix in `docs/phase5/derive_rotations_fix.md` with before/after column examples from a real rotation in 2025 data.

4. Add a `--dry-run-verify` flag that: runs the rotation clustering, displays the first 5 candidates in a Rich table, and exits without writing. This lets you visually confirm columns line up before committing any more data.

5. Add defensive validation:
   - If `Sell_Proceeds` or `Buy_Amount` is non-numeric, log and skip
   - If a rotation's Sell and Buy totals differ by more than 3× (sanity bound), flag it for review and tag `Rotation_Type` as `anomalous` instead of inferring

6. Add a one-off script `scripts/repair_trade_log.py` (gitignored or clearly marked one-time):
   - Reads existing `Trade_Log` rows
   - If any row has suspicious column content (numeric in text fields, etc.), flags them for manual review
   - Does NOT auto-correct — it just prints a report so Bill can clean the sheet manually
   - This is surgical one-time cleanup, not ongoing pipeline logic

### Constraints

- **Do not modify `Trade_Log` rows programmatically.** Manual cleanup only via the sheet UI, guided by the repair script's report.
- **Do not change the schema.** Column order in `config.TRADE_LOG_COLUMNS` and `config.TRADE_LOG_STAGING_COLUMNS` stays the same. The fix is in the data values, not the schema.
- **Preserve fingerprint compatibility.** Old Trade_Log rows must still be deduplicable against new runs.

### Gate criteria

- [ ] `tasks/derive_rotations.py --since 2025-01-01 --days 120 --dry-run-verify` shows a visual preview with correct column alignment
- [ ] Running against 2025 data produces rotation candidates whose Sell_Proceeds and Buy_Amount values are within 3× of each other (the usual rotation ratio)
- [ ] `scripts/repair_trade_log.py` runs and produces a clean report
- [ ] `docs/phase5/derive_rotations_fix.md` committed
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 5.1: Fix derive_rotations column mismatch + validation`

### What NOT to do

- Do not attempt to auto-repair existing Trade_Log rows
- Do not expand the rotation schema
- Do not add new `Rotation_Type` values beyond adding `anomalous`

---

## Prompt 5.2 — Capture decision context at rotation time

### Context

When you recorded the rotation, you knew what the technicals looked like. Three months later, you won't. To tune market timing, you need the technical state of both the sell and the buy captured at the moment of the decision.

### Task

1. **Read first:** `tasks/derive_rotations.py`, `tasks/enrich_technicals.py`, the composite bundle shape (specifically `calculated_technicals`).

2. Extend `derive_rotations.py` (and the `Trade_Log_Staging` / `Trade_Log` schema) to capture technical snapshots for each rotation:
   - `Sell_RSI_At_Decision`, `Sell_Trend_At_Decision`, `Sell_Price_vs_MA200_At_Decision`
   - `Buy_RSI_At_Decision`, `Buy_Trend_At_Decision`, `Buy_Price_vs_MA200_At_Decision`

3. Source: yfinance for the historical daily OHLCV around the decision date. Compute RSI-14 and MA200 with the same math as `enrich_technicals.py` so the numbers are consistent. If yfinance is unavailable for a ticker, set fields to `null` — do not fail the rotation.

4. Update `config.TRADE_LOG_COLUMNS` and `config.TRADE_LOG_STAGING_COLUMNS` to include the new fields. Update `PORTFOLIO_SHEET_SCHEMA.md`.

5. Existing Trade_Log rows will have blanks for these fields — that's fine. Write a one-time backfill script (`scripts/backfill_trade_log_decision_context.py`, gitignored or clearly marked) that reads existing rows and populates the historical RSI/trend/MA values for already-promoted rotations. Backfill is opt-in — don't run it automatically.

6. Update `journal promote` to pass these fields through from staging to log.

### Constraints

- **Historical fetch is point-in-time.** RSI at decision date uses the 14 days up to and including the decision date — not today's RSI for a historical decision.
- **Defensive.** Missing data is `null`, never 0 (which would mislead).
- **Do not hit yfinance more than once per ticker per rotation.** Cache per ticker if multiple rotations share a ticker in one run.

### Gate criteria

- [ ] `derive_rotations.py` on 2025 data now populates the 6 new decision-context fields for each candidate
- [ ] Spot-check: for a rotation you remember, the captured RSI matches a historical lookup (yfinance or TradingView)
- [ ] Backfill script runs on existing Trade_Log rows and populates historical context correctly
- [ ] `PORTFOLIO_SHEET_SCHEMA.md` updated
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 5.2: Capture decision context (RSI/trend/MA) at rotation time`

### What NOT to do

- Do not capture fundamentals at decision time — those don't move enough to be actionable in rotation timing review
- Do not capture volume or volatility — RSI and trend cover the timing signal adequately

---

## Prompt 5.3 — Post-hoc P&L attribution

### Context

The core of the review loop: for each rotation, compute how the sell-side and buy-side performed over 30/60/90/180 days from the decision date. Then compute the **pair return** — the relative performance that captures whether the rotation actually improved the book.

### Task

1. Create `tasks/compute_rotation_attribution.py`:
   - Reads `Trade_Log`
   - For each row, fetches closing prices for sell-side and buy-side at: +30, +60, +90, +180 trading days from `Date`
   - Computes:
     - `Sell_Return_30d`, `Sell_Return_60d`, etc. — what the sell-side would have done if you hadn't sold
     - `Buy_Return_30d`, `Buy_Return_60d`, etc. — what the buy-side did after you bought it
     - `Pair_Return_Nd` = `Buy_Return_Nd - Sell_Return_Nd` — positive means the rotation was additive, negative means you'd have been better off not rotating
   - Writes results to a new tab: `Rotation_Review`

2. `Rotation_Review` tab schema:
   - Key columns: `Trade_Log_ID`, `Date`, `Sell_Ticker`, `Buy_Ticker`, `Rotation_Type`, `Implicit_Bet`
   - Decision context: `Sell_RSI_At_Decision`, `Buy_RSI_At_Decision`, plus trend labels for both
   - Attribution: `Sell_Return_30d`, `Sell_Return_90d`, `Sell_Return_180d`, `Buy_Return_30d`, `Buy_Return_90d`, `Buy_Return_180d`, `Pair_Return_30d`, `Pair_Return_90d`, `Pair_Return_180d`
   - Status: `Attribution_As_Of` (the date the attribution was computed; rotations < 180 days old will have nulls for 180d)
   - Fingerprint: `{Trade_Log_ID}|{Attribution_As_Of}`

3. The tab is a **clear-and-rebuild** view, not append-only. Each `trade review` run regenerates the full table. This keeps attribution fresh and avoids duplicate rows.

4. Add a `CASH` special case: if `Buy_Ticker == CASH`, the buy-side return is the cash yield from `Config.cash_yield_pct`, pro-rated. If `Sell_Ticker` sold into cash (no real buy), the sell-side return is still computed (what did the thing you sold do?), and `Pair_Return` = `Cash_Return - Sell_Return` (which is negative when the sell went up, positive when it went down — consistent with the interpretation).

5. Add `manager.py trade review`:
   ```python
   trade_app = typer.Typer(help="Trade log review and decision tuning.")
   app.add_typer(trade_app, name="trade")

   @trade_app.command("review")
   def trade_review(live: bool = typer.Option(False, "--live")):
       """Refresh Rotation_Review with fresh attribution for all Trade_Log rows."""
   ```

6. Add conditional formatting to `Rotation_Review` (via `format_sheets_dashboard_v2.py` or a new dedicated function):
   - `Pair_Return_90d` column: green if > +2%, red if < -2%, neutral otherwise
   - `Rotation_Type == 'tax_loss'`: slight grey background (different evaluation criteria)
   - Rows where `Attribution_As_Of - Date < 30 days`: muted text (not enough time to judge)

### Constraints

- **Price-return only.** No dividend reinvestment, no tax drag, no slippage model. This is a "how did the pair move?" review, not a TWR.
- **Cache the yfinance calls.** If you've already computed 30/60/90/180 for a rotation, don't re-fetch unless `Attribution_As_Of` is > 7 days stale AND any of the horizons are still null.
- **Do not recompute attribution in dry run.** Dry run shows the table as-is; `--live` refreshes.
- **No attribution for rotations < 30 days old.** Those cells stay null.

### Gate criteria

- [ ] `python manager.py trade review --live` creates/refreshes `Rotation_Review` with attribution for all historical rotations
- [ ] Pair_Return values manually verifiable against a price chart for at least 3 rotations
- [ ] Conditional formatting renders correctly
- [ ] Re-running is idempotent (second run has near-identical results; only rows where attribution horizons recently matured change)
- [ ] CASH buy-side handled correctly
- [ ] `PORTFOLIO_SHEET_SCHEMA.md` updated with `Rotation_Review`
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 5.3: Rotation attribution and Rotation_Review tab`

### What NOT to do

- Do not try to be precise about tax impact
- Do not try to model dividends reinvested
- Do not rank or recommend based on attribution — that's the LLM's job in 5.4

---

## Prompt 5.4 — Rotation retrospective export scenario

### Context

With `Rotation_Review` populated, you can now ask a frontier LLM: *"Look at my last 20 rotations and the attribution. What patterns do you see? Am I consistently good at one type and bad at another?"* This is the decision-tuning payoff.

### Task

1. **Read first:** `tasks/templates/` (from Phase 4), the new `Rotation_Review` shape.

2. Add `export rotation-retrospective` to the export command group:
   ```python
   @export_app.command("rotation-retrospective")
   def export_rotation_retrospective(
       last_n: int = typer.Option(20, "--last-n", help="Number of most recent rotations to include."),
       by_type: str = typer.Option("", "--type", help="Filter to one rotation type."),
   ):
       """Package the last N rotations with attribution for frontier LLM pattern analysis."""
   ```

3. The command:
   - Reads `Rotation_Review`, filters to last N rows (or by type)
   - Includes rotation details, decision context (RSI etc.), and attribution (30/60/90/180 where available)
   - Packages per the Phase 4 format: `README.md`, `prompt.md`, `context.json`, manifest

4. Template `rotation_retrospective_v1.md`:
   ```markdown
   # Rotation Retrospective — Last {N} Rotations

   This is a review of a disciplined CPA investor's rotation history.
   He trades in small-step rotations across four styles (GARP, Thematic,
   Boring-Fundamentals, Sector/Thematic-ETFs). The table below shows
   each rotation's decision context and post-hoc attribution.

   ## Rotation Table

   (markdown table with all columns: Date, Sell, Buy, Type, Sell RSI,
   Buy RSI, Pair_30d, Pair_90d, Pair_180d, Implicit Bet)

   ## Summary Stats (pre-computed by the CLI)

   - Total rotations in scope: {N}
   - By type: {TYPE_BREAKDOWN}
   - Median Pair_Return_90d: {MEDIAN}
   - % positive at 90d: {POSITIVE_PCT}
   - % positive at 180d (rotations ≥180 days old only): {POSITIVE_180D_PCT}

   ## What I Want From You

   1. **Pattern recognition.** Are there rotation types (dry_powder,
      upgrade, rebalance, tax_loss) where I'm consistently better or worse?
   2. **Timing signal.** Is there an RSI pattern on the sell-side or
      buy-side that correlates with successful vs unsuccessful rotations?
      (e.g., "rotations where sell-side RSI was > 70 tend to be negative")
   3. **Style discipline.** Am I rotating within styles or across styles?
      Is the "implicit bet" field consistent with my four styles or is
      there evidence of drift?
   4. **Honest assessment.** Without flattery, what are my two biggest
      rotation mistakes in this window, and what's the common thread?

   Be direct. This is for my own tuning, not to make me feel good.
   No price predictions. No "you should have sold X instead." Focus on
   the pattern, not the hypothetical.
   ```

5. The CLI also pre-computes the summary stats and injects them into the prompt (don't make the LLM do arithmetic on the table — feed it the numbers).

6. Decide: do we include the `Implicit_Bet` field in the retrospective? **Yes.** It's the most valuable signal for style-discipline review.

### Constraints

- **No price predictions.** Hard rule, stated in the prompt.
- **"Be direct" language.** The whole point of this retrospective is honest feedback.
- **Pre-compute stats.** Don't make the LLM count rows and calculate medians — give it the numbers.

### Gate criteria

- [ ] `python manager.py export rotation-retrospective --last-n 20` creates a package
- [ ] `python manager.py export rotation-retrospective --last-n 30 --type upgrade` filters correctly
- [ ] Manual paste test to Claude + Gemini + Perplexity produces insightful pattern responses
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 5.4: Rotation retrospective export scenario`

### What NOT to do

- Do not build an "auto-retrospective" that runs weekly and emails you. This is on-demand.
- Do not persist the LLM's retrospective in the sheet — if an insight is worth keeping, you write it into `Decision_Journal` yourself.

---

## Prompt 5.5 — User documentation and integration into weekly workflow

### Task

1. **Read first:** `portfolio_manager_user_docs.html` (Version 2.2 after Phase 4).

2. Update `portfolio_manager_user_docs.html`:
   - Bump version to 2.3 (Decision Review Added).
   - Add new section "Decision Review & Market Timing" explaining:
     - The full rotation lifecycle: derive → review → promote → attribution
     - How to read `Rotation_Review`
     - The retrospective export workflow
   - Add commands to the CLI reference:
     - `manager.py trade review`
     - `manager.py export rotation-retrospective`
   - Update the weekly workflow: add a **monthly** section for rotation retrospective ("First Saturday of every month").

3. Update `tasks/templates/WEEKLY_WORKFLOW.md` with the monthly cadence.

4. Add a "what this phase unlocked" note to `CHANGELOG.md`:
   > Phase 5 closes the loop on rotation-based investing. The Trade_Log is now
   > a tuning instrument, not just a record. Decision context captured at the
   > moment of decision means attribution is never guesswork. The monthly
   > retrospective is where market timing actually improves.

### Constraints

- **Honest language in the docs.** This isn't a backtest. It's a price-return comparison with useful but limited framing.
- **Keep the CPA caveat.** Tax drag and dividends are not in the attribution — note this clearly.

### Gate criteria

- [ ] Docs updated to Version 2.3
- [ ] Weekly workflow file has monthly rotation retrospective section
- [ ] Fresh observer can run the full capture → attribution → retrospective loop from docs alone
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 5.5: Decision review user docs and workflow integration`

### What NOT to do

- Do not claim the attribution is a backtest
- Do not claim any predictive power from the retrospective

---

## Phase 5 Completion Gate

Phase 5 is complete when all five prompts have been executed, gated, and committed, **and** the following test passes:

```bash
# Standard morning
python manager.py health
python manager.py snapshot --live
python manager.py sync transactions --live
python manager.py dashboard refresh --live

# Trade log maintenance
python tasks/derive_rotations.py --since 2025-01-01 --days 365
python manager.py journal promote --live     # review staging, approve, promote
python manager.py trade review --live        # refresh attribution

# Monthly retrospective
python manager.py export rotation-retrospective --last-n 20
→ paste to Claude / Gemini / Perplexity
→ note patterns in Decision_Journal manually if any are actionable

# Verify
# 1. Rotation_Review tab exists with attribution for all promoted rotations
# 2. Pair_Return_90d values match price charts for at least 3 spot-check rotations
# 3. RSI-at-decision captured for new rotations; backfilled for historical ones
# 4. Retrospective export produces a useful LLM response across multiple LLMs
```

All of the following must be true:

- [ ] `derive_rotations.py` column alignment fixed and verified
- [ ] Decision-context fields (RSI etc.) captured at rotation time
- [ ] `Rotation_Review` tab shows attribution correctly
- [ ] Retrospective export produces useful pattern analysis
- [ ] User docs at Version 2.3
- [ ] `CHANGELOG.md` has five Phase 5 entries
- [ ] No regressions in Phases 1–4

---

## Notes for Bill

- **This is the phase that changes your behavior.** Phases 1–4 give you better tools. Phase 5 gives you evidence. Over 12 months of retrospectives, you'll see your real timing skill, not your remembered one.
- **Don't expect the attribution to be kind to every rotation.** Rotations meant for tax harvesting aren't supposed to beat the sell-side on return. Rotations meant for "upgrade" are — and if they don't consistently, that's a signal.
- **The first retrospective will be the hardest and most valuable.** You'll see your blind spots in one conversation.
- **The Implicit_Bet field is the thesis-drift detector.** If your bets cluster around "rotating into tech because AI" for six consecutive rotations, that's a concentration signal your dashboard weights can't show you.
- **After Phase 5, Phase 6 is user documentation consolidation** — a single authoritative user manual that replaces the accumulated HTML with a clean, current guide.
