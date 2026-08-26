# Build: Commit the Work, Re-test the Exclusions, Then Dashboard

> **STATUS: partially shipped; historical recovery deferred by design (2026-08-26).** Useful parts landed (Command Center rotation-performance block). Pre-2026 / multi-account historical ledger recovery remains an Open Question — never re-sync live `Transactions` unfiltered. Incomplete remainder is not a product gap. Archived under `prompts/archive/`.

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative).

Three jobs, deliberately ordered. **Step 1 first because 71 changed/untracked files with no
commit is the largest risk in the repo right now** — two days of thesis repairs, a central
sanitizer fix, and a new attribution module exist only as working-tree state.

Standing conventions: archive-before-overwrite; dry run → verify → `--live`; never write
`Target_Allocation`; extend existing docs; deliver exactly what is asked.

---

## Step 1 — Commit two days of work in logical chunks

`git status` shows ~71 changed/untracked files; the only recent commit is an unrelated
menu-launcher change. Stage in separable commits, not one blob. Suggested grouping — adjust if
the actual diff argues otherwise, and say so:

1. **`read_gsheet_robust()` pandas 3.0 fix** — the highest-value commit. Isolate it. Its
   message should state the failure mode explicitly: pandas ≥3.0 infers plain-string columns
   as a dedicated string dtype, so a `dtype == object` check silently skipped the `$`/`%`/`,`
   strip and every currency and percent cell collapsed to 0. This one deserves to be findable.
2. **Thesis repairs** — VRT, ET, ES, PWR, KRE archive, plus the new MU / RRC files and their
   `.bak` siblings.
3. **Rotation attribution module** — `tasks/compute_rotation_attribution.py`,
   `config.ROTATION_REVIEW_COLUMNS` additions, `journal promote` changes.
4. **Prompts and agent outputs** — `prompts/*.md`, `agent_outputs/**`, verification sidecars.
5. **Docs** — `state.md`, `CHANGELOG.md`.

Before committing: confirm nothing sensitive is staged — no tokens, no `.env`, no credential
JSON, no full account numbers. `config.py` carries masked suffixes only; verify that is still
true. Report anything that looks like a secret rather than committing it.

---

## Step 2 — Re-test the 69 exclusions BEFORE any recovery work (gate)

**Hypothesis to test:** the 69 `WEIGHTS_UNRECONCILED` rows may be an artifact of the
`read_gsheet_robust()` bug rather than out-of-scope accounts.

The reasoning: that bug collapsed every currency cell read from Sheets to `0`. The attribution
module reconstructs dollar weights from the `Transactions` tab through that same reader. The
reported symptom on the 69 was *"reconstructed totals landing at exactly $0.00."* That is
precisely what a zeroed amount column produces. The out-of-scope explanation is also
consistent — several excluded tickers (FNDX, TCNNF, QXO, STAG, BITW, KBWY, MOS, O) genuinely
do not appear in the current scoped Transactions — but **the two causes are indistinguishable
from the symptom alone**, and they imply completely different amounts of work.

1. Establish whether the attribution run at ~14:16 on 2026-08-08 executed **before or after**
   the sanitizer fix landed in the working tree. Check the file mtime of `utils/sheet_readers.py`
   against the run timestamp and report both.
2. Regardless of that answer, **re-run attribution now**:
   `python tasks/compute_rotation_attribution.py` (dry run), forcing a cache bypass so weights
   are genuinely recomputed rather than served from the ≤7-day cache. If no bypass flag exists,
   say so and clear the cache explicitly.
3. Report the new included/excluded split against the prior **47 / 69**.

**Then branch:**

- **If the exclusion count drops materially** → it was the sanitizer bug. Recompute the
  aggregate summary, report the corrected medians, and **skip Step 3 entirely.** Say so plainly;
  do not do the recovery work "anyway."
- **If it stays at ~69** → the out-of-scope explanation holds. Proceed to Step 3.
- **If it drops partially** → report both populations separately. Some rows are bug artifacts,
  some are genuinely out of scope, and the split matters.

---

## Step 3 — Historical multi-account transaction recovery (ONLY if Step 2 says so)

Context from `config.py`: six Schwab accounts exist. The portfolio is the sum of three —
`...6499`, `...8767`, `...5119`. Three are excluded — `...4151`, `...0217`, `...9753`. The
scoping was introduced 2026-08-03 (`prompts/schwab_account_scope_fix_2026-08-03.md`).
`SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` empty = no filtering, i.e. pre-fix behavior.

2025 rotations predate the fix and span all six accounts, so they cannot reconcile against a
three-account ledger.

**Hard constraint: do NOT re-sync the live `Transactions` tab unfiltered.** That would undo the
08-03 scope fix and corrupt every current weight, ceiling and bundle figure. This is a
*parallel historical fetch*, landing somewhere else.

1. Fetch transactions for the full 2025-01-01 → 2026-08-03 window with
   `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES=""` **set only for the duration of this fetch** — via
   environment override at call time, not by editing `config.py`. Read-only endpoints only.
2. Write to a **new tab**, `Transactions_Historical_AllAccounts`, with an added
   `Account_Suffix` column so in-scope and out-of-scope rows stay distinguishable forever.
   Do not merge into `Transactions`.
3. Add an opt-in flag to the attribution module — e.g. `--historical-ledger` — that reads the
   union of both tabs when reconstructing weights for rotations dated before 2026-08-03.
   **Default off.** Current-scope behavior must be unchanged when the flag is absent.
4. Re-run attribution with the flag and report the new included/excluded split, plus the
   aggregate summary broken out by ledger source so the two eras are comparable.

---

## Step 4 — Rotation performance on `0_DASHBOARD`

`TAB_DASHBOARD = "0_DASHBOARD"` — index-0, described in config as hard-value KPIs, no
formulas. Add a rotation-performance block reading from `Rotation_Review`. **No new
computation** — surface what the attribution module already produced.

Cells to surface, per matured horizon (30/90/180):

- `N` included, and the **sample window** (earliest → latest included rotation date). The window
  is not decoration: a reader must be able to see at a glance that this covers months, not years.
- **Residual median** — the headline.
- **Hit rate** — share with positive residual.
- **Vs_Index (VTI) median** and **Sell_Vs_Index median**, labelled as two distinct questions:
  *did the buy beat indexing the proceeds*, and *did the funding side go on to lag*.
- **Excluded count and percentage**, adjacent to N, never in a footnote. A reader seeing
  "47 included" without "69 excluded" beside it is being misled.
- **VTI/QQQ sign-flip count** as a fragility indicator.

Label the block so it cannot be read as a scorecard — something like *"Rotation attribution —
evidence, one regime, overlapping windows."* Do not add a rank, grade, or trend arrow.

Also fix, while in this file: **`format_rotation_review()` in
`tasks/format_sheets_dashboard_v2.py` dies on a Unicode console-encoding error** (a `⚠`
character) after a successful data write, so conditional formatting never applies. Data was
never at risk. Fix the encoding, don't remove the warning.

---

## Step 5 — Record two known issues, do not fix

Append to `state.md` Known Issues. Both were diagnosed in this window and should not be
rediscovered:

1. **The `DailyWake` scheduled task has never successfully fired.** This is why STEP 4b missed
   four consecutive Spotify digests and why `logs/morning_auto.log` has not been written since
   2026-07-27. The morning pipeline is effectively manual-only. Record the diagnosis; the fix is
   a Windows Task Scheduler change and is Bill's to make.
2. **`derive_rotations` emits nested supersets** when re-run against an open cluster window —
   five rows for the single 2026-08-03 basket, each fingerprinting differently so dedup cannot
   catch them. Attribution reads around it; the deriver itself is unfixed.

---

## Step 6 — Verification

Literal output for each.

- [ ] `git log --oneline` showing the new commits; `git status` clean or with only
      deliberately-ignored files remaining. State what was intentionally left uncommitted.
- [ ] Confirmation that no credential, token or `.env` file was staged.
- [ ] `utils/sheet_readers.py` mtime vs the 2026-08-08 14:16 attribution run — which came first.
- [ ] Re-run included/excluded split against the prior 47 / 69, and the branch taken.
- [ ] If Step 3 ran: `Transactions_Historical_AllAccounts` row count by `Account_Suffix`, and
      proof that the live `Transactions` tab is byte-unchanged.
- [ ] If Step 3 ran: attribution output with and without `--historical-ledger`, showing default
      behavior is unchanged.
- [ ] `0_DASHBOARD` block rendered — paste the cell values, including excluded count.
- [ ] `format_rotation_review()` completes without the Unicode error; formatting visible.
- [ ] `state.md` Known Issues updated with both items.

## Out of scope

- Do not edit `config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` persistently.
- Do not merge historical transactions into the live `Transactions` tab.
- Do not modify `derive_rotations.py` clustering.
- Do not change the beta normalizer; the JEPI/JPIE caveat stands.
- Do not fix the Task Scheduler entry — record it only.
- No price targets, forecasts, or buy/sell language in any output.
