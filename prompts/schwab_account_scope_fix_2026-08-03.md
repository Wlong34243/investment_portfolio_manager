# Build Prompt: Schwab Multi-Account Aggregation Fix

**Author:** Chief Architect (Claude, 2026-08-03)
**Executor:** Claude Code / Gemini CLI
**Prompt version:** 1.0.0
**Severity:** High — every downstream dollar figure, weight %, and style-ceiling
calculation is currently unreliable.

## Objective

Two compounding bugs in `utils/schwab_client.py`, confirmed by Bill and independently
verified against the live repo on 2026-08-03, are merging a second Schwab-linked
account (most likely the 401(k), `Individual_401(k)_XXX499`) into what should be a
single-account (`Individual_XXX119`) portfolio view. Fix both. Do not touch anything
else.

## Background — what's already confirmed (do not re-derive, just verify still true)

1. **No account-level filtering anywhere in the codebase.** `fetch_positions()`
   (`utils/schwab_client.py:79`), `fetch_transactions()` (`:422`), and
   `fetch_tax_lots()` (`:559`) all call `client.get_accounts()` /
   `client.get_account_numbers()` and aggregate every account the token can see —
   the function's own docstring says "ALL linked Schwab accounts." A repo-wide grep
   found exactly one account-scoping check, in `build_tax_control.py`, and it only
   filters tax-report output, not position/value aggregation.
2. **`config.SCHWAB_ACCOUNT_HASH` is dead for this purpose.** It's read in
   `core/bundle.py:281-283`, but only to build a fingerprint hash — it is never
   passed into `fetch_positions()`/`fetch_transactions()`/`fetch_tax_lots()` to
   scope the account query.
3. **`state.md` line 165 is wrong and should be corrected as part of this work:**
   it claims "workaround in place via account filtering." No such workaround exists
   in code. Fix the doc once the real fix lands — don't leave two contradictory
   claims about the same bug in the repo.
4. **The tax-treatment classifier can't recognize a 401(k).**
   `utils/schwab_client.py:126-132` only checks for `'ROTH'` or `'IRA'` substrings
   in Schwab's account `type` field; everything else — including a 401(k)/QRP
   account — falls through to `tax_treatment = 'taxable'`. This is why the
   existing cross-account safety net (designed to flag `'mixed'` when the same
   ticker appears under different tax treatments) never fired: the 401(k)'s
   holdings get tagged identically to the real taxable account and silently merge.
5. **Confirmed live, not historical**, from three bundle snapshots:

   | Bundle | JEPI qty | JPIE qty | total_value | position_count |
   |---|---|---|---|---|
   | 2026-08-01T141909Z | 881 | 460 | $598,037.24 | 38 |
   | 2026-08-02T232710Z | 5131 | 1460 | $897,748.49 | 38 |
   | 2026-08-03T132843Z | 5131 | 1460 | $899,332.32 | 38 |

   JEPI gained exactly +4,250 shares and JPIE exactly +1,000 shares between the
   08-01 and 08-02 bundles, with position_count unchanged (38) and every other
   ticker essentially flat. That is an aggregation-scope change, not a trade —
   confirmed against `Trade_Log`, which shows net *selling* of JEPI/JPIE in the
   primary account over the same window.
6. **Downstream, confirmed-corrupted:** `build_ceiling_check()`
   (`tasks/export_ai_briefing.py:484-495`) reads `weight_pct` straight from the
   bundle position dict — the same field whose denominator (`total_value`) is
   inflated. Every BREACH/near-ceiling flag computed against the current bundle is
   unreliable until this is fixed.
7. **Separately confirmed, real regardless of the scope bug — third bug, same area:**
   `tasks/export_ai_briefing.py:491`
   (`ceiling = (styles.get(style) or {}).get("size_ceiling_pct")`) and
   `core/thesis_sync_data.py:105`
   (`size_ceiling = styles_config.get(style, {}).get("size_ceiling_pct", 0.0)`)
   both compute the ceiling **only** from the style default in `data/styles.json`.
   Neither reads a thesis file's own `style_size_ceiling_pct` frontmatter override.
   Worse: `tasks/write_thesis_updates.py:126`
   (`"style_size_ceiling_pct": p.size_ceiling_pct`) writes this recomputed default
   back into the thesis frontmatter on every sync — so a manually-set override
   (e.g. META's `4.0`) is not just misread for display, it gets **silently
   overwritten back to the style default (9.0 for GARP)** the next time STEP 6
   (`write_thesis_updates.py`) runs. This is destructive, not cosmetic.

## Step 0 — Verification gate (do this before writing any code)

STOP and report instead of building if any of these fail.

1. Confirm the four points above still match current `main` — line numbers may
   have drifted since 2026-08-03; re-grep, don't assume.
2. Identify the primary account. Cross-reference the three transaction CSVs in the
   repo root (`Individual_XXX119_Transactions_*.csv`,
   `Individual_401(k)_XXX499_Transactions_*.csv`,
   `Contributory_XXX767_Transactions_*.csv`) against `config.py`'s
   `'Is Primary Acct'` field (used today only for CSV-import parsing, per
   `config.py:290,461`) to determine how "primary" is currently encoded anywhere in
   this repo, and whether that concept can be reused for the live API path or needs
   a new config constant.
3. Confirm whether `client.get_accounts()` / `client.get_account_numbers()`
   responses include enough info (masked account number, `hashValue`, account
   `type`) to reliably distinguish the three accounts without a live reauth. If the
   current (revoked/expired) refresh token blocks a live test call, note that and
   proceed on static code inspection — do not attempt a live Schwab call without
   Bill present.
4. Confirm no other caller of `fetch_positions()` / `fetch_transactions()` /
   `fetch_tax_lots()` depends on the current multi-account behavior (grep the
   whole repo, not just `core/bundle.py`).

## Deliverable 1 — Account-scope fix (`utils/schwab_client.py`)

Add an explicit primary-account filter to `fetch_positions()`, `fetch_transactions()`,
and `fetch_tax_lots()`. Concretely:

- Add a config constant (e.g. `config.PRIMARY_SCHWAB_ACCOUNT_NUMBER` or reuse/rename
  `SCHWAB_ACCOUNT_HASH` if it already holds the right value — confirm which in Step
  0) identifying the one account (`Individual_XXX119`) this system is supposed to
  represent.
- In all three functions, skip any `securitiesAccount` whose masked account number /
  hash doesn't match the configured primary account, rather than aggregating every
  account the token can see.
- Log (at the existing debug level, masked to last 4 digits — the pattern already
  used at `schwab_client.py:117-118`) any account that gets *skipped*, so a future
  silent-scope-change is visible in logs instead of just in dollar totals.
- Do not remove the ability to query other accounts outright if any other part of
  the system needs it (Step 0.4) — scope the default, don't delete the capability.

## Deliverable 2 — Tax-treatment classifier fix (`utils/schwab_client.py:126-132`)

Extend the `acct_type` check to recognize 401(k)/QRP account types (check Schwab's
actual `type` field values via Step 0.3, don't guess the string) and map them to a
distinct `tax_treatment` (e.g. `'tax_deferred_401k'` or reuse `'tax_deferred'` if
that's semantically correct — confirm with Bill if ambiguous, this is a tax-judgment
call, not a pure engineering one per the repo's own guardrail on professional
judgment). This is what should have caused the existing `'mixed'`-tax-treatment
safety net to fire in the first place; verify it does, post-fix, with a real mixed
holding if one exists in test data.

## Deliverable 3 — Style-ceiling override fix (two files)

- `core/thesis_sync_data.py:~105`: before falling back to
  `styles_config.get(style, {}).get("size_ceiling_pct", 0.0)`, check whether the
  thesis file being synced already has a `style_size_ceiling_pct` value in its
  existing frontmatter, and preserve it if present. Only use the style default when
  no override exists yet.
- `tasks/export_ai_briefing.py:491`: same fix on the read side — check the position's
  thesis-file override before falling back to `styles.get(style)`.
- Add a regression note (comment or test) referencing META as the known case:
  `style_size_ceiling_pct: 4.0` must survive a `write_thesis_updates` sync cycle and
  must be what `build_ceiling_check()` uses for META's drift math, not the GARP
  default.

## Explicitly out of scope for this prompt

- **Do not recompute or re-report any weight%/drift% figures** as part of this fix.
  Every existing BREACH/near-ceiling number in current briefings is unverifiable
  until Deliverable 1 ships and a fresh bundle is generated — that recomputation
  happens naturally on the next `manager.py morning --live` run, not as a manual
  step here.
- **Do not touch `Trade_Log` / `Trade_Log_Staging`.** If any `sync_transactions.py
  --live` run happened 2026-08-02 or later (after the scope apparently expanded),
  the 90-day transaction fetch may have pulled 401(k)/Contributory transactions
  into the same sheet. Flag this as a **separate manual review item** for Bill —
  check Sheet write/version history for `Transactions` and `Trade_Log` tabs since
  2026-08-02 — do not attempt to identify or remove contaminated rows
  automatically.
- **Do not correct `state.md` line 165's specific wording** beyond removing the
  false "workaround in place" claim — Bill may want to word the corrected entry
  himself.

## Post-build verification checklist

Demand literal stdout/stderr for each — do not accept a self-reported PASS table.

1. `python manager.py bundle composite` (dry run, no `--live`) against the current
   token. If the token is still revoked/expired, report that plainly — do not fake
   or skip this step.
2. Once a live token is available: run the bundle build and confirm `total_value`
   lands near Bill's known ballpark (~$591-596K per the Command Center Sheet), not
   ~$897-899K. Show the before/after `total_value`, JEPI qty, and JPIE qty explicitly.
3. Confirm `fetch_positions()` output no longer contains the 401(k)/Contributory
   account's positions unless Bill explicitly re-requests multi-account scope.
4. Confirm a position with a known `style_size_ceiling_pct` override (META, 4.0)
   survives one full `write_thesis_updates` dry-run cycle unchanged, and that
   `build_ceiling_check()` uses 4.0, not 9.0, for META's ceiling in the resulting
   briefing.
5. Confirm no other `--live` write path was touched (`Target_Allocation`,
   `Trade_Log`, anything outside `Agent_Outputs`/local markdown).

## Promotion sequence

DRY RUN → verify against the checklist above → flip `--live` only after Bill
reviews the diff. Standard.
