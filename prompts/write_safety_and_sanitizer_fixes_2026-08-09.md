# Build: Write-Safety and Sanitizer Fixes

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative).
**Source:** the 2026-08-09 data-integrity and dead-code audit.

**Scope discipline — read this first.** The audit has ~40 findings. This prompt takes **eight**,
chosen on one criterion: *code that can write the wrong thing, or write when it was told not to.*
Everything else is deferred, and the deferrals are listed at the bottom with reasons. Do not
pull them forward.

**Do not touch anything in flight for `prompts/trigger_types_2026-08-09.md`** — `level_coverage.py`,
`vault_bundle.py`, and the trigger-type work are mid-build with uncommitted changes.

Standing conventions: archive-before-overwrite; dry run → verify → `--live`; no cell-by-cell
Sheet writes; no price targets or buy/sell language in output.

---

## Step 0 — Verification gate

Report PASS/FAIL with literal output. The audit is dated 2026-08-09 — confirm each finding still
holds before fixing it.

| # | Assertion |
|---|---|
| 0.1 | `tasks/derive_rotations.py` — `--dry-run` is `store_true` (default `False`) and is passed to `write_staging(dry_run=args.dry_run)`, so a bare CLI invocation writes. Confirm, and confirm `manager.py` passes `dry_run=not live` on the morning path. |
| 0.2 | `manager.py` `journal_promote` — the `Promoted_At` schema-ensure calls `update_cell()` **before** the `if not live:` branch. Report both line numbers. |
| 0.3 | `scripts/apply_staging_dispositions_2026-08-08.py` performs `batch_update` on Status with no `--live` gate. |
| 0.4 | `tasks/build_tax_control.py:get_realized_gl_robust()` and `pipeline.py` (`append_daily_snapshot`, `calculate_income_metrics`, `write_risk_metrics`) gate their `$`/`,` strip on `dtype == object`. |
| 0.5 | `utils/sheet_readers.py` exposes `coerce_sheet_numeric_series()` handling both object and string dtypes, and `build_valuation_card.py` already uses it for `Position MV`. **If Position MV is already fixed, do not re-fix it.** |
| 0.6 | `utils/gl_parser.py` sets `is_primary_acct` from an IRA/401k/Roth name test, not from account suffix; `build_tax_control.py` includes all rows when that column is absent. |
| 0.7 | `tasks/create_dashboard.py` and `scripts/create_dashboard.py` have **zero** importers, and at least one performs a clear-and-rebuild of `0_DASHBOARD`. |
| 0.8 | Working tree state: which of the above files have uncommitted changes from the in-flight trigger build. **Report before editing anything.** |

---

## Step 1 — `derive_rotations` CLI must not write by default

The function default is already `dry_run=True`; only the CLI inverts it.

- Change the CLI to require `--live` to write. Keep `--dry-run` accepted as a no-op alias if
  removing it would break a script, and say which you chose.
- The morning path (`dry_run=not live`) must be unchanged.
- **Verification:** run `python tasks/derive_rotations.py` with no flags against the live Sheet
  and prove `Trade_Log_Staging` row count is unchanged before and after. Paste both counts.

---

## Step 2 — `journal promote` schema-ensure behind the gate

Move the `Promoted_At` column creation so it cannot run during a dry run.

- Either gate it under `--live`, or split it into an explicit one-time migrate command.
- Whichever you choose, the dry-run path must perform **zero** Sheet mutations.
- While here: the staging status marking is cell-by-cell in a loop, against hard rule 6. Convert
  to a single batched update. This also removes the partial-write failure mode seen on
  2026-08-08 when Google rate-limited mid-loop.
- **Verification:** dry-run `journal promote` against a staging tab lacking `Promoted_At`;
  prove the header is unchanged afterwards.

---

## Step 3 — One-off script write gate

`scripts/apply_staging_dispositions_2026-08-08.py` writes with no gate, so a re-run silently
overwrites current dispositions.

- Preferred: **delete it.** It was a one-time script and its work is done.
- If you would rather keep it, add a `--live` gate and a loud dry-run default.
- Report which, and check whether other `scripts/*_2026-08-*.py` one-offs have the same shape.
  List any that do; do not fix them in this pass.

---

## Step 4 — Sanitizer residuals

Two files still gate the currency strip on `dtype == object`, so under pandas ≥3 they silently
produce zeros rather than erroring.

- `tasks/build_tax_control.py:get_realized_gl_robust()`
- `pipeline.py`: `append_daily_snapshot`, `calculate_income_metrics`, `write_risk_metrics`

Route all of them through `coerce_sheet_numeric_series()` and **delete the local strippers** —
do not leave a second implementation beside the shared one.

**Verification is the point here, because the failure is silent.** For `build_tax_control`,
paste YTD short-term, YTD long-term, wash-sale and estimated-tax figures **before and after**
the change. If they were zeroing, those numbers will move — and that difference is a real
correction to Bill's tax picture, not a cosmetic fix. Say so explicitly if it happens.

---

## Step 5 — Tax_Control account scope

`utils/gl_parser.py` decides "primary" by testing the account *name* for IRA/401k/Roth, while
positions, transactions and lots gate on account *suffix* (`SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` =
`6499,8767,5119`). These are different questions, and `build_tax_control.py` includes every row
when the column is missing.

- Tag lots by account suffix and filter to `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`.
- **If the suffix is unavailable in the Realized_GL source, do not guess.** Fail loudly with a
  message naming what is missing, and report back rather than falling back to "include all."
  Silently including out-of-scope taxable lots is the bug being fixed; a fallback that does the
  same thing is not a fix.
- Report the row count and dollar impact of the filter — how much of Tax_Control was
  out-of-scope. That number is the finding.

---

## Step 6 — Archive the dead dashboard builders

`tasks/create_dashboard.py` and `scripts/create_dashboard.py` have no importers and at least one
clear-rebuilds `0_DASHBOARD` — the tab `build_command_center.py` owns.

- Move both to `archive/`. Do not delete; they may hold reference logic.
- Confirm zero importers before moving, and confirm `pm morning` runs clean afterwards.
- This is the only dead-code item in this pass. It is here because it can overwrite a live
  surface, not because it is untidy.

---

## Step 7 — Documentation reconciliation

The audit found docs asserting bugs that are fixed and omitting bugs that are open.

- `CLAUDE.md` Known Issues was updated 2026-08-09 with the audit findings. **Verify it matches
  reality after this build** and correct anything this pass changes.
- `state.md` "What's Next" still lists Position MV as open. **It is fixed.** Remove it.
- `sync_transactions.py` docstring claims "archive-before-overwrite"; the live path **appends**
  fingerprint-new rows. Correct the docstring — the real hazards are `clean_junk_tickers`
  (clear+rewrite) and an empty `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`, and the docstring currently
  points attention at the wrong thing.
- Add to `state.md`: `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` empty means unscoped. A guard refusing to
  sync unless `--force-unscoped` is passed is worth building later; record it, do not build it here.

---

## Step 8 — Verification

Literal output for each. An agent-reported PASS table is not evidence.

- [ ] Step 0 table, including the uncommitted-files report from 0.8.
- [ ] `derive_rotations` with no flags: staging row count before and after, identical.
- [ ] `journal promote` dry run against a tab missing `Promoted_At`: header unchanged.
- [ ] Staging status marking is a single batched call. Paste the diff.
- [ ] Tax_Control figures before and after the sanitizer fix — **all four**, with a plain
      statement of whether they moved.
- [ ] Tax_Control account filter: rows and dollars excluded.
- [ ] Both `create_dashboard` files in `archive/`; zero importers proven; `pm morning` dry run clean.
- [ ] `git log --oneline` — **one commit per step**, not one blob. These are independently
      revertible fixes and should stay that way.
- [ ] `CLAUDE.md` and `state.md` reconciled; `sync_transactions.py` docstring corrected.

---

## Deferred — do NOT do these here

Each has a reason. Raise them separately when their turn comes.

| Finding | Why deferred |
|---|---|
| **Nested-superset deriver fix** (A5) | Needs a design decision on stable cluster identity — widen-in-place vs. re-fingerprint. Attribution already reads around it. Design first, then build. |
| **Typed triggers not surfaced on Valuation_Card** (A10) | Already Step 5 of `prompts/trigger_types_2026-08-09.md`, currently in flight. Duplicating it would collide. |
| **Podcast `allocation_view: none`** (A6) | Real, and already recorded in `CLAUDE.md`. Belongs with the next `batch_podcast_sync.py` change, not here. |
| **Dead-code sweep** — Streamlit leftovers, unused config keys, hidden Typer aliases, `fetch_balances`, `risk.py` trim | Large, low urgency, and none of it can write to a live surface. Its own pass. |
| **Dry-run morning still writes to disk** (A8) | Behavioural change to the main pipeline. Decide first whether the fix is gating disk writes or documenting "Sheets-dry / disk-live"; do not guess. |
| **Dashboard cash KPI labelling** (A9), **Signal staleness** (A14) | Display decisions, and both need Bill's input on what should show. |
| **Dual Schwab token helpers** (A15) | Cosmetic inconsistency; no wrong numbers result. |
| **Strategy 1 fenced-YAML parsing** | Interacts with the in-flight trigger build. Decide after it lands. |
