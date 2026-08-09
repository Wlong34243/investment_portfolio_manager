# Build: Surface Rotation Attribution in the Brief and the Bundle

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative).

**Run this AFTER** `prompts/trigger_types_2026-08-09.md` completes. It touches the morning-brief
skill file and `tasks/export_ai_briefing.py` — different files from the trigger build, but the
`0_DASHBOARD` grid is shared, so sequencing avoids a collision.

**Problem.** `Rotation_Review` holds 116 rows of benchmarked attribution and **nothing reads
it.** Two greps confirm: the morning-brief skill never references it, and
`export_ai_briefing.py` never surfaces it, so it is absent from the composite bundle too. The
measurement exists and reaches no surface Bill actually looks at.

Standing conventions apply. No price targets, forecasts, or buy/sell language in any output.

---

## Step 0 — Verification gate

| # | Assertion |
|---|---|
| 0.1 | `Rotation_Review` row count and how many have a matured horizon at 30/90/180. |
| 0.2 | The morning-brief skill file contains **no** reference to `Rotation_Review` or attribution. Confirm. |
| 0.3 | `tasks/export_ai_briefing.py` contains **no** reference to `Rotation_Review`, `Residual`, or attribution. Confirm. |
| 0.4 | `build_command_center.py` computes `vs SPY YTD` via `_spy_ytd_pct()`, as `ytd_pct − spy_ytd/100`, returning `None` when `headline["ytd_pct"]` is None. Confirm, and report whether that cell is **currently populating** on the live Sheet. It was blank on 2026-08-07, before the `read_gsheet_robust()` pandas fix. |
| 0.5 | Whether the rotation-attribution dashboard block from `prompts/commit_recover_dashboard_2026-08-09.md` was built, and if so whether it lives **inside** `build_command_center.py`'s grid construction. Anything written to `0_DASHBOARD` by another path is erased on the next `pm morning`. |

---

## Step 1 — Portfolio-level benchmarks: extend SPY to VTI and QQQ

`_spy_ytd_pct()` already exists. Generalize it rather than copying it twice.

- Add `vs VTI YTD` and `vs QQQ YTD` alongside the existing `vs SPY YTD` in the Command Center
  headline block.
- Preserve the existing None-handling — a missing `ytd_pct` must still yield a blank cell, not
  a zero. **A zero here is indistinguishable from "flat versus the market" and would be a lie.**
- If 0.4 found `vs SPY YTD` still blank after the pandas fix, diagnose that **first**. Adding
  two more blank cells to a broken row is not progress.

---

## Step 2 — The daily brief: one conditional line, not a table

**Design constraint, deliberate:** horizons mature roughly monthly. A table in a daily brief
would show identical numbers ~29 days out of 30, and would be skimmed past within a week — the
same fate as the verification sidecars. **Silence when nothing changed is the feature.**

Add to the morning-brief skill file a step that emits a line **only when something matured
since the last brief**:

> `3 rotations matured a 30d horizon since 2026-08-05 — median residual +2.1%, 2 of 3 positive.`

Rules:
- Emit **nothing** when no horizon matured. No "no changes" line.
- Never emit the aggregate track record daily. That belongs in the periodic review below.
- Include the count of newly-excluded rows if any appeared, since a rising exclusion rate is a
  data-quality signal, not a performance one.
- Place it near the housekeeping section, not near the dislocation section. It is a
  system-state finding, not a market finding.

**Determining "since the last brief"** needs a watermark. Use `Attribution_As_Of` on
`Rotation_Review` rows, or a small local state file — **not** a hardcoded lookback. Say which
was chosen and why.

---

## Step 3 — The bundle: make attribution available to reasoning

`export_ai_briefing.py` assembles the composite briefing. Add attribution so an agent reasoning
over the bundle can see the track record rather than inferring it.

- Add a compact section to the briefing — aggregate only, not 116 rows: N by horizon, sample
  window, residual median, hit rate, `Vs_Index` median, `Sell_Vs_Index` median, excluded count.
- **Carry the caveats with the numbers, not in a footnote.** Specifically: sample is one regime;
  observations overlap heavily so effective N is far below nominal N; benchmark choice flipped
  the sign on 18 of 47 rows at last run; the JEPI/JPIE beta caveat.
- Add a line to `PROMPT_PAYLOAD`'s analysis rules instructing any agent reading it: **the
  attribution aggregate is evidence about a documented subset, not a verdict on Bill's
  investing.** Excluded rows are non-random — they skew old and wide — so the medians describe
  well-reconciled rotations, not all rotations.

That last point matters more than the numbers. Without it, an agent will read "+3.14% median
residual" as a performance verdict and start building recommendations on a 6-month,
overlapping, one-regime sample.

---

## Step 4 — Periodic review, not daily

The full table belongs somewhere, just not in the morning brief.

- Write a monthly rotation review to `agent_outputs/rotation_attribution/` — the existing
  per-run markdown is already close; make it explicitly monthly-dated and add the
  dispersion stats that were requested and not delivered: **IQR and standard deviation of
  `Residual_Pair` per horizon, plus the best and worst five rows.**
- A median without dispersion is not interpretable. At last run, individual 30d residuals
  ranged roughly −18.6% to +38.4% against a +3.14% median — that spread is the finding, and
  it is currently invisible in the summary.
- Do **not** schedule this. Bill runs it. Note the command in `state.md`.

---

## Step 5 — Verification

- [ ] Step 0 table, including whether `vs SPY YTD` is now populating post-pandas-fix.
- [ ] `0_DASHBOARD` renders `vs SPY / VTI / QQQ YTD`; blanks stay blank, no zeros substituted.
- [ ] Brief step emits the line when a horizon matured, and **emits nothing** when none did.
      Demonstrate both cases.
- [ ] Watermark mechanism stated and justified.
- [ ] Bundle briefing contains the aggregate section with caveats inline, and the new
      `PROMPT_PAYLOAD` rule. Paste both.
- [ ] Monthly review file with IQR, standard deviation, and best/worst five.
- [ ] Composite hash changes noted as expected.
- [ ] `state.md` and `CHANGELOG.md` updated.

## Out of scope

- Do not schedule the monthly review.
- Do not put the aggregate table in the daily brief.
- Do not write to `0_DASHBOARD` outside `build_command_center.py`'s grid construction.
- Do not recompute attribution; this build only surfaces what exists.
- Do not substitute zero for a missing benchmark value.
