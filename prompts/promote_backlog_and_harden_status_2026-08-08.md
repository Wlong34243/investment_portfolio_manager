# Build: Promote the Rotation Backlog, Then Make the Status Field Honest

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative).

**Context.** Basket-aware attribution shipped 2026-08-08 and works — `Rotation_Review` has one
row (`63.5`, 2026-04-20, 30d Residual +7.36%). It has one row because `Trade_Log` has one row.
Meanwhile `Trade_Log_Staging` holds a large backlog of rows whose `Status` reads `promoted`
but which were **never promoted** — `promoted` is the value `journal promote` *writes* on
success, and it only ever acts on `Status == "approved"`. Hand-typing the terminal state made
every one of those rows invisible to the command.

The goal of this build is to convert that backlog into measured history, and then make the
same mistake impossible.

Standing conventions: archive-before-overwrite; dry run → verify → `--live`; never write to
`Target_Allocation`; extend existing docs rather than creating parallel ones; deliver exactly
what is asked.

---

## Step 0 — Verification gate

Report a PASS/FAIL table with literal output. Stop and report on discrepancy.

| # | Assertion |
|---|---|
| 0.1 | `Trade_Log` row count. Expected: **1** (`63.5`, 2026-04-20). Report the actual number. |
| 0.2 | `Rotation_Review` row count. Expected: **1**, Status `OK`. |
| 0.3 | `Trade_Log_Staging` row count, and a breakdown by `Status` value. **Report the exact count of rows reading `promoted`** — this is the backlog size and it is currently unknown. |
| 0.4 | Confirm no staging row's `Fingerprint` already appears in `Trade_Log` (other than 63.5's, if present). If any do, some rows *were* genuinely promoted and the triage in Step 1 must exclude them. |
| 0.5 | `journal promote` filters on `Status == "approved"` (case-insensitive) and writes `promoted` on success. |
| 0.6 | Earliest and latest staging `Date`. Report the span — this is how much unmeasured history exists. |

---

## Step 1 — Triage staging (read-only analysis first, no writes)

Two problems overlap. Separate them before touching anything.

### 1a. Nested supersets

`derive_rotations` clusters by date window. Re-running it daily against an open window emits a
new, larger superset each time — the 2026-08-03 basket exists as **five** rows, each with a
different fingerprint, so fingerprint dedup does not catch them. The 2026-05-07 / 2026-05-08
pair is the same artifact (identical ticker sets both sides, different proceeds).

- The attribution module already contains superset-group detection built in the 2026-08-08
  build. **Reuse it.** Do not write a second implementation.
- Produce a table of every nested group found: anchor date, member Stage_IDs, which is widest,
  and the ticker-set difference that makes it widest.
- **Report and stop.** Do not set any status yet.

### 1b. Rows with no written rationale

`journal promote` already warns when `Implicit_Bet` is blank. Bill wrote real rationale on some
rows ("sold dry powder to acquire value"; "kre exit was due to interest rate hike concerns")
and left others empty.

- List every candidate row with a blank `Implicit_Bet` or `Thesis_Brief`.
- **Do not invent either field.** `state.md` (2026-07-31) records the precedent: `Implicit_Bet`
  was transcribed from Bill's own words already on record, never fabricated. A blank rationale
  on a promoted row is a permanent gap in the record — better to leave the row unpromoted and
  ask than to fill it.

### 1c. Proposed status assignment

Output a proposed disposition per row — **as a table for Bill's approval, not as writes**:

| Disposition | Meaning |
|---|---|
| `approved` | Widest row of its group, rationale present. Promote it. |
| `superseded` | Narrower member of a nested group. Inert to the command; label is for the human. |
| `needs_rationale` | Would be approved, but `Implicit_Bet` is blank. Bill to fill or waive. |

**Get Bill's sign-off on this table before Step 2.**

---

## Step 2 — Promote

Only after sign-off.

1. Write the agreed `Status` values into `Trade_Log_Staging`. **Back up the tab first** (export
   current contents to `agent_outputs/trade_log_staging/backup_<timestamp>.csv`).
2. `python manager.py journal promote` — dry run. Paste output.
3. `python manager.py journal promote --live`. Paste output including the post-write
   fingerprint verification.
4. Confirm `Trade_Log` row count increased by exactly the number approved, and that every
   approved `Fingerprint` is present.

**Known limitation, expected, not a failure:** staging's plural `Sell_Tickers`/`Buy_Tickers`
land in `Trade_Log`'s singular `Sell_Ticker`/`Buy_Ticker` as comma-joined strings. The
attribution module handles this. Do not "fix" it by splitting rows.

---

## Step 3 — Run attribution across the backlog

1. `python tasks/compute_rotation_attribution.py` — dry run across all promoted rows.
2. Then `--live`.
3. Refresh the markdown at `agent_outputs/rotation_attribution/`.

**The per-row table is not the deliverable. Add a summary section answering the question this
whole build exists for:**

- Count of rotations with matured horizons at 30d / 90d / 180d.
- **Median and mean `Residual_Pair`** at each matured horizon, plus the count positive vs negative.
- **Median `Vs_Index_Nd`** (VTI) at each horizon — did the buy side beat simply indexing the proceeds.
- **Median `Sell_Vs_Index_Nd`** at each horizon — this isolates the *funding* instinct. Whether
  Bill reliably sells things that go on to underperform is a separate skill from what he buys,
  and it has never been measured.
- Rows where `Coverage_Pct` < 0.90 or status is not `OK`, listed separately and excluded from
  the medians.

### Benchmark-spread caution — carry this into the summary

On the single existing row, `Bench_Spread_30d` was **8.46%** (SPY +7.17, VTI +6.90, QQQ +15.36).
Against VTI that rotation reads +6.50%; against QQQ it reads **−1.96%**. The verdict flips with
the yardstick because the buy side was tech-concentrated.

- Report the **count of rows where the sign of `Vs_Index` flips** between VTI and QQQ.
- Do not resolve it by picking a winner. Surface it: a high flip count means the aggregate
  medians are benchmark-dependent and should be read as a range, not a verdict.

---

## Step 4 — Make the status field non-collidable

The root cause: a hand-typed terminal state is indistinguishable from a real one.

1. Accept **`approve`** (imperative) as the input value alongside `approved`, and document it.
   The distinction matters: the input is an instruction, the output is a record.
2. Add a **`Promoted_At`** column to `TRADE_LOG_STAGING_COLUMNS`, written by `journal promote`
   with a UTC timestamp on success. A row claiming `promoted` with an empty `Promoted_At` is
   provably hand-typed.
3. Add a startup check to `journal promote`: if any row reads `promoted` with a blank
   `Promoted_At`, print a warning naming those rows. **Warn, do not auto-correct** — after this
   build the historical rows will legitimately have blank timestamps, and silently rewriting
   them would destroy the evidence of what happened.
4. Backfill `Promoted_At` for rows promoted *by this build* only.

---

## Step 5 — Small fix, flagged separately on 2026-08-08

`tasks/build_valuation_card.py:349` calls `pd.to_numeric` on raw `"$X,XXX.XX"` strings from
`df_holdings["Market Value"]` with no stripping, so `Position MV` is 0 for every row. Effects:
the card fails to sort by position size (which its own comment says is the point), and a column
of `$0` is written to the Sheet.

**Fix by routing through the existing sanitizer in `utils/sheet_readers.py`** (~line 144),
which already strips `$`, `%`, `,`, handles parenthesized negatives, and carries a comment
describing this exact failure mode. `build_valuation_card.py` currently imports only
`get_gspread_client` from that module, bypassing it.

**Do not add a local `.str.replace()` stripper** — that would be the third copy of this logic
in the repo. If the sanitized reader cannot be used here, report why instead of duplicating.

---

## Step 6 — Verification

Literal output for each. An agent-reported PASS table is not evidence.

- [ ] Step 0 table, including the actual backlog count and date span.
- [ ] Nested-group table from Step 1a, and Bill's sign-off recorded before any write.
- [ ] Staging tab backed up to CSV before any status write; path and row count pasted.
- [ ] `journal promote` dry run, then `--live`, both pasted, with the fingerprint verification.
- [ ] `Trade_Log` row count before and after, and every approved fingerprint confirmed present.
- [ ] Attribution dry run then `--live`; summary section pasted in full.
- [ ] VTI-vs-QQQ sign-flip count reported.
- [ ] `Promoted_At` present, populated for this build's rows, blank for historical ones, and the
      startup warning demonstrated by running against a row with a blank timestamp.
- [ ] `Position MV` non-zero in a fresh valuation card, sorted descending. Paste the top 5 rows.
- [ ] `state.md` and `CHANGELOG.md` each updated with one dated entry.

## Out of scope

- Do not modify `derive_rotations.py` clustering. The superset emission is a real bug; it is a
  separate build and this one reads around it.
- Do not invent `Implicit_Bet` or `Thesis_Brief` content.
- Do not delete any staging row.
- Do not rewrite historical `Promoted_At` values.
- Do not change the beta normalizer. The JEPI/JPIE caveat stands as flagged.
- No price targets, forecasts, or buy/sell language in any output.

## Open question for Bill, surfaced by this build

Once the backlog is measured, the medians will say something about whether these rotations add
value. **Two cautions before that number gets treated as a verdict:** the sample is one market
regime, and the benchmark spread on row 63.5 was wide enough to flip the sign. Report the
result as evidence, not as a scorecard, and let Bill decide what it is worth.
