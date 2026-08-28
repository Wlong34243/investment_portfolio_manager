# Tax-Aware Decision Surface — the cost visible before the trade, not on next April's 1099

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 9 of 10.** **Depends on:** prompt 1 (`signal_events`), prompt 3 (retrieval). Surfaces in
prompt 4's Position Story if that has landed; works from the CLI regardless.
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 6c, including the constraint discovered 2026-08-26.

> **Professional-judgment boundary, stated up front.** This prompt attaches dollar figures to a
> pre-trade tax question. Three of its four signals are pure arithmetic; the fourth **bounds** the
> cost rather than predicting a broker's lot selection (Step 4). Those figures inform a decision;
> they are not tax advice, not a filing position, and not a substitute for the 1099. Every number this
> surface produces must be labelled **ESTIMATE**, and the completion report must state plainly that
> the wash-sale and holding-period determinations are Bill's (or his CPA's) call, not the system's.
> Bill is a CISA/CPA and does not need the disclaimer explained — but the *labelling in the output*
> is a build requirement, not a courtesy.

---

## Step 1 comes before any code — the rule

**Do this first, commit it, then build.**

The account uses **Schwab's Tax Lot Optimizer**. Lot relief order is:

1. Short-term losses, largest first
2. Long-term losses
3. Short-term flat
4. Long-term flat
5. Long-term gains, smallest first
6. Short-term gains, smallest first

**This is not FIFO.** Add to `CLAUDE.md`:

- Under **Hard Rules**: *The system must never derive lot relief locally. Schwab's `Realized_GL`
  import is the sole authority on which lot went. A pre-trade figure is an **estimate**, is expressed
  as a bound rather than a point value, is labelled, and never touches the ledger. The rule governs
  the record, not the estimate — and is what keeps the two from being confused.*
- Under **What NOT to Do**: *Do not assume FIFO anywhere. The account uses Schwab's Tax Lot Optimizer
  (established 2026-08-26); the relief hierarchy is in the Tax section.*
- A new subsection under the tax material recording the six-step hierarchy verbatim.

That commit is worth making even if nothing else in this file is ever built.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — dependencies
python manager.py store evidence-status
python -c "from core.retrieval.api import retrieve; print('ok')"

# 0.2 — the rule is not yet written; confirm before writing it
grep -n "Tax Lot Optimizer\|lot relief\|FIFO" CLAUDE.md

# 0.3 — find every place that ALREADY assumes FIFO. This is the real audit.
grep -rn "fifo\|FIFO\|first.in.first.out\|sort_values('Open Date'\|oldest" \
  --include=*.py tasks/ utils/ core/ scripts/ manager.py

# 0.4 — existing tax machinery to extend, not duplicate
grep -n "^def \|^class " utils/tax.py
grep -n "^def \|wash\|WASH" tasks/build_tax_control.py | head -30
grep -n "^def \|term\|holding_days" utils/gl_parser.py | head -30

# 0.5 — tax rates and doctrine's existing hand-rolled version of this
grep -n "TAX\|RATE" config.py | head -20
grep -n "tax_hold_runners" vault/doctrine.md utils/doctrine_reader.py

# 0.6 — lot data as actually shaped
python -c "from core.retrieval.api import retrieve; from core.retrieval.queries import TemplateCall;\
r=retrieve(queries=[TemplateCall('tax_control_lots',{})],label='probe');\
rows=r.tables['tax_control_lots']; print(len(rows)); print(rows[0] if rows else 'EMPTY')"
```

**Step 0.3 is the one that matters.** If any existing code sorts lots by open date to reason about
what a sale would consume, it is producing wrong numbers today and that is a finding to report
immediately — not something to quietly fix inside this build.

---

## Step 2 — Human input gate: establish the facts

> **⚠️ STOP. This cannot be answered by code and must not be guessed.**

The roadmap: *"Worth establishing when the method was set and whether it applies to all three
allowlisted accounts."*

Ask Bill, and do not proceed past this gate without answers:

1. What is the cost-basis method **currently** set on each of the three allowlisted accounts?
2. **When** was it set? Anything realised before that date used a different method, and applying
   today's hierarchy to older lots produces confident wrong answers about history.
3. Is it uniform across all three, or per-account?

**These belong in `vault/doctrine.md`** — Bill's own file, manual-only, authoritative on standing
constraints, already parsed by `utils/doctrine_reader.py`. Give Bill the text to paste. **Do not write
to `doctrine.md` from code.** Then have `doctrine_reader` expose the method and effective date so the
projector can refuse to project across a boundary it does not know about.

---

## Step 3 — Four signals, and only one of them needs the optimizer

The reviewer's maintenance objection — "you are replicating a broker's proprietary algorithm and it
will drift out from under you" — has teeth, but **only against one of the four things 6c delivers.**
Sorting them by what they actually cost is the whole design of this prompt.

| Signal | What it needs | Optimizer dependency |
|---|---|---|
| **3a** Open wash-sale window on this ticker | date arithmetic over `Realized_GL` | **none** |
| **3b** Days-to-long-term ladder | every open lot's crossing date | **none** |
| **3c** `tax_hold_runners` generalization | rule application, already done by hand for UNH/COF | **none** |
| **3d** "Trimming now costs $X" | the six-tier relief hierarchy | **total** |

Three of four are free of it. **Build 3a, 3b and 3c first, ship them, and treat 3d as a separate
increment** — they carry most of the behavioral payoff on their own, and they keep working unchanged
if Schwab ever revises the algorithm.

### 3a — Wash-sale window

Pure date arithmetic over `Realized_GL`: any loss sale on this ticker within the trailing 30 days
opens a window; report the disallow-through date. Extend `utils/tax.py` and whatever
`build_tax_control.py` already computes (Step 0.4) — **do not write a second wash-sale implementation.**
Three windows are already live and unpriced per `state.md` (EMXC, GLD, XLF); those are the test cases.

### 3b — Days-to-long-term ladder

Every open lot, its crossing date, sorted by days remaining. **You do not need to know which lot
Schwab will pick to see that three lots cross inside 30 days.** That is the entire insight, and it
requires no model of the optimizer at all. This is the single highest value-to-effort item in the
file.

### 3c — `tax_hold_runners` generalization

`vault/doctrine.md` already encodes the behavior by hand for UNH and COF, and
`utils/doctrine_reader.downgrade_rule` already applies it. Generalize the *measurement* — surface
days-to-LT and window state on every ticker, not just the two — while the *decision* to downgrade
stays in doctrine where Bill controls it. **Do not auto-expand `tax_hold_runners` from computed
figures.** That would move a standing constraint out of Bill's file and into code.

---

## Step 4 — 3d: produce a bound, never a point estimate

> **⚠️ This is the load-bearing design decision in this file. Read it before writing
> `core/tax/lot_relief.py`.**

The rule from Step 1 — *never derive lot relief locally* — governs **the record of what was sold**:
post-trade, authoritative, Schwab's. A **pre-trade estimate**, labelled as an estimate and never
written to the ledger, is a different object and the two coexist without tension. The rule is
precisely what stops the estimate from ever being mistaken for the record.

But a *point* estimate — "trimming 40 shares costs $142.66" — claims a precision that depends on
replicating a proprietary algorithm exactly, forever. When it is right, it is right by luck; when it
drifts, it is quietly wrong and nothing announces it. **So do not produce one.**

### Produce a range instead

```python
def bound_relief_cost(lots, shares_to_sell, *, as_of) -> ReliefBound
```

Two deterministic endpoints, each trivially computable and neither requiring the tier order to be
exactly right:

- **Best case** — relief starts at the short-term-loss end. Sort lots most-favourable-first
  (ST losses largest, then LT losses, then flat), consume, compute the tax.
- **Worst case** — relief lands on short-term gains. Sort least-favourable-first (ST gains largest,
  then LT gains), consume, compute the tax.

`ReliefBound` returns `best_case_tax`, `worst_case_tax`, `best_case_lots`, `worst_case_lots`,
the ST/LT split at each endpoint, `is_estimate=True`, and `basis` naming the method and effective
date from doctrine.

**Why this is better than the precise number, stated so it survives review:** the payoff was never
precision. It was making the cost visible *at all*, at the moment of decision, instead of on next
April's 1099. A range that is directionally right delivers that. And it **degrades honestly** — if
Schwab revises the hierarchy tomorrow, the true cost is still inside the bound, whereas a point
estimate would simply be wrong with no signal that it had become so.

Where the bound is tight (best and worst within a few percent), say so — that is the common case for
a position with homogeneous lots, and it means the range is as good as a point estimate anyway.
Where it is wide, the width *is* the finding: it means lot selection materially matters here, which
is itself a reason to look before trading.

**Optionally**, and only after 3a–3c have shipped and been used: implement the full six-tier
hierarchy as an *indication inside the bound* — "likely relief, per the documented hierarchy" —
rendered subordinate to the range, never replacing it. Its tier sorting is easy to get backwards
(**largest** ST loss first; **smallest** LT gain first), so it carries its own tests. Treat it as a
nice-to-have that the surface works fine without.

### Guards, unchanged and not optional

- **Refuse to estimate** when any lot's open date precedes the method's effective date from Step 2.
  Return `UNKNOWN_METHOD_PERIOD` naming the lots.
- **Refuse to estimate** across accounts. Relief is per-account; a blended figure is meaningless.
- **Never write to `Realized_GL`.** The Schwab import is the sole authority on what actually went.
- `pm tax reconcile-estimate` compares a stored bound against the realised lots after the fact and
  reports whether the actual landed **inside the bound**. An actual outside the bound is a real
  finding — the model of the account is wrong — and is far more informative than a point estimate
  being off by $30.

---

## Step 4b — The decision surface

```
pm tax project --ticker UNH --shares 40
pm tax project --ticker UNH --shares 40 --as-of 2026-09-15
```

```
UNH — 40-share sale, 2026-08-27              *** ESTIMATE — not a tax determination ***
Method: Schwab Tax Lot Optimizer (effective 2025-03-14, per doctrine.md)

  COST OF TRIMMING NOW               [3d]
    Best case  (relief from ST losses):   $   0.00
    Worst case (relief hits ST gains):    $ 1,038.40
    Range is wide — lot selection materially matters on this position.

  HOLDING PERIOD                     [3b]   -- no optimizer model required
    2026-04-02   18 sh   crosses to long-term in 23 days (2026-09-19)
    2026-05-11   12 sh   crosses in 62 days
    2025-11-19   22 sh   already long-term
    Three lots cross inside 90 days.

  WASH SALE                          [3a]   -- no optimizer model required
    OPEN WINDOW — loss sale 2026-08-15 (12 days ago). A repurchase before 2026-09-14
    disallows. This estimate assumes no repurchase.

  DOCTRINE                           [3c]
    UNH is a tax_hold_runner. Crosshairs will downgrade NEAR_TRIM to HOLD_TAX.

  OVERRIDE CASE
    You are carrying 4,210.00 of realized short-term losses YTD. Against that carry you may
    want short-term gains realized BEFORE long-term — the opposite of the optimizer's order.
    That is a specified-lot call and cannot be expressed by leaving the optimizer on.
```

Every section is tagged with which signal produced it, so a reader can see at a glance that three of
the four need no model of Schwab's algorithm. The override case is in the roadmap explicitly and is
the highest-value line on the page: *"exactly what this surface should flag rather than leaving to
memory."* Trigger it whenever YTD realized ST losses exceed a `config` threshold and the sale would
realize LT gains.

---

## Step 5 — Annotate Crosshairs

When a `NEAR_TRIM` fires, attach to the row: `days_to_lt` for the nearest-crossing lot (3b —
free), `wash_window_open` (3a — free), `override_case_active`, and **`est_tax_cost_low` /
`est_tax_cost_high`** for a nominal trim size (3d — the bound, never a single field).

**Two fields, not one, and named so.** A single `projected_tax_cost` column would collapse the bound
back into a point estimate at exactly the surface where it gets read fastest, and would be believed
precisely because a dashboard cell looks authoritative. If only one number will fit, show the **high**
end and label it as such.

**Feed the doctrine downgrade; do not duplicate it.** `utils/doctrine_reader.downgrade_rule` already
re-ranks a `NEAR_TRIM` to `HOLD_TAX` (bucket ≥400) for `tax_hold_runners` — currently UNH and COF, by
hand. This prompt **generalises the measurement and puts a number on it**; the downgrade decision stays
in doctrine, where Bill controls it. Do not add a second downgrade path, and do not auto-expand
`tax_hold_runners` from computed figures — that would move a standing constraint out of Bill's file
and into code.

Persist the annotation onto the `signal_events` row (extend `payload_json`; do not add columns to the
append-only table after the fact — see prompt 1's no-Alembic note).

---

## Step 6 — Reframe the 74% problem

The roadmap's sharpest observation, and the thing with a measured dollar value:

> The optimizer defers short-term gains to **last**. So if it has been on, lot selection is already
> optimized, and the short-term share is coming from **decision-level holding period** instead.
> Different diagnosis, different fix.

Build `pm tax diagnose-holding-period`:

1. From `Realized_GL`, all realized gains for the period, split ST/LT, with `holding_days` per lot.
2. **Only for periods after the method's effective date from Step 2.** Say so in the header, and
   report separately for any earlier period as `METHOD UNKNOWN`.
3. Distribution of `holding_days` on ST gains. The diagnostic question: are they clustered just under
   365 (near-misses — a holding-period problem, fixable by waiting) or spread across 30–200 days
   (genuinely short-horizon decisions — a different problem entirely, and not one a tax surface fixes)?
4. Report the counterfactual: **ST gains realized within N days of crossing to LT, and the dollar
   differential at `config` rates.** That is the number the roadmap says is invisible at the moment of
   decision, and it is the justification for the whole phase.
5. **Report it as a measurement, not a verdict.** `CLAUDE.md` Analysis Rule 6: deliver the finding,
   name the file to update, stop. Do not moralize about process — and specifically, do not narrate a
   74% short-term share as a discipline failure. It may be an artifact of a deliberate strategy, and
   the governing principle is that Bill is authoritative on Bill's decisions.

---

## Tests

**3a–3c (no optimizer dependency):**

- `test_tax_wash_window.py` — the three live windows in `state.md` (EMXC, GLD, XLF) are detected with
  correct disallow-through dates.
- `test_tax_lt_ladder.py` — crossing dates correct across a year boundary and a leap day; sorted by
  days remaining, not by open date.
- `test_tax_ladder_no_relief_model.py` — **structural:** the ladder module does not import
  `lot_relief`. The point of 3b is that it needs no model of the optimizer; assert it has none.
- `test_tax_hold_runner_surface.py` — days-to-LT and window state surface for every ticker, while the
  downgrade still fires only for doctrine's `tax_hold_runners`.

**3d (the bound):**

- `test_relief_bound_ordering.py` — `best_case_tax <= worst_case_tax`, always, on randomized lot sets.
- `test_relief_bound_contains_fifo.py` — the FIFO outcome falls **inside** the bound. So does the
  six-tier outcome. **This is the test that proves the bound is doing its job:** any plausible relief
  order lands within it.
- `test_relief_bound_partial.py` — a sale consuming part of a lot splits correctly at both endpoints.
- `test_relief_bound_tight_case.py` — homogeneous lots produce a narrow range; the output says so.
- `test_relief_refuses_unknown_period.py` — lots predating the effective date → `UNKNOWN_METHOD_PERIOD`.
- `test_relief_refuses_cross_account.py` — mixed accounts → refusal.
- `test_relief_never_writes_realized.py` — structural assertion that no path writes `Realized_GL`.
- `test_tax_no_point_estimate.py` — **structural:** no public function returns a single scalar tax
  cost. The API surface offers a bound or nothing.
- `test_tax_override_case.py` — ST loss carry + LT gains in range → override flagged.
- `test_tax_estimate_labelled.py` — every rendered output carries the ESTIMATE label.

*Only if the optional six-tier indication from Step 4 is built:* `test_relief_tier_sorting.py` —
**largest** ST loss first, **smallest** LT gain first. Assert both directions; it is the easiest
thing in the file to get backwards, which is itself a reason it is optional.

---

## Post-build verification checklist

**Literal stdout for every row.**

| # | Check | Expect |
|---|---|---|
| 1 | Rule committed | `grep -n "Tax Lot Optimizer" CLAUDE.md` | present in Hard Rules and What NOT to Do |
| 2 | FIFO audit | Step 0.3 output | every hit triaged and reported; none left assuming FIFO |
| 3 | Doctrine facts | `grep -n "cost basis method" vault/doctrine.md` | method + effective date, written by Bill |
| 4 | **3a wash window** | the three known windows (EMXC/GLD/XLF per `state.md`) | detected, disallow-through dates correct |
| 5 | **3b ladder** | `pm tax project` on a multi-lot ticker | every lot's crossing date, sorted by days remaining |
| 6 | 3b needs no model | `test_tax_ladder_no_relief_model` | passes — the ladder does not import `lot_relief` |
| 7 | **3c doctrine surface** | UNH/COF still downgrade; other tickers show days-to-LT | both true; no auto-expansion of `tax_hold_runners` |
| 8 | **3d is a bound** | `pm tax project --ticker UNH --shares 40` | best/worst range; never a single figure |
| 9 | Bound ordering | randomized lot sets | `best <= worst`, always |
| 10 | Bound contains FIFO **and** the six-tier answer | `test_relief_bound_contains_fifo` | both inside the range — paste all three numbers |
| 11 | No point estimate anywhere | `test_tax_no_point_estimate` + read the rendered output | no scalar cost in the API or the render |
| 12 | Wide vs tight narrated | one homogeneous and one heterogeneous position | output states which, and why it matters |
| 12b | Unknown period refused | lots predating the effective date | refusal naming the lots |
| 12c | Cross-account refused | mixed-account lot set | refusal |
| 12d | Never writes `Realized_GL` | grep + the structural test | no write path |
| 12e | ESTIMATE label | every rendered output | banner present |
| 12f | Override case | ST loss carry + LT gains inside the range | flagged with the specified-lot note |
| 13 | Crosshairs annotated | run morning, inspect a `NEAR_TRIM` row | tax fields present |
| 14 | Doctrine downgrade unchanged | UNH / COF still downgrade via doctrine | unchanged; no second path |
| 15 | Holding-period diagnostic | `pm tax diagnose-holding-period` | distribution + counterfactual dollars + method-period header |
| 16 | Diagnostic is not a verdict | read the output text | measurement framing, no process moralizing |
| 17 | Reconcile the bound | after the next real sale, `pm tax reconcile-estimate` | reports whether the actual landed **inside** the bound |
| 17b | Out-of-bound is loud | construct a case where it would not | reported as a finding about the model, not a rounding note |
| 18 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — Step 1's rule and hierarchy (this is the load-bearing edit); `core/tax/` in Key
  Files; the ESTIMATE-labelling requirement; and one line recording **why the cost signal is a bound
  and not a figure**, so nobody "improves" it into a point estimate in six months.
- **`vault/doctrine.md`** — **text handed to Bill to paste. Do not write it from code.**
- **`state.md`** — dated entry; the Step 0.3 FIFO audit result; the Step 6 diagnostic's actual finding,
  which may reframe the standing "74% short-term" item.
- **`PORTFOLIO_SHEET_SCHEMA.md`** — if `Tax_Control` gains any annotation column.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Any recommendation to sell, hold, or harvest. Facts and dollar ranges only. Bill decides.
- Any automated specified-lot instruction to Schwab. **Read-only on the brokerage, forever.**
- Changing the cost-basis method. That is Bill's action in Schwab's interface, not the system's.
- Estimated-tax planning, quarterly projections, or anything resembling a filing position.
- Auto-expanding `tax_hold_runners`. Doctrine is manual-only.
- Backfilling estimates over pre-effective-date history.
- **A point estimate of the cost of trimming.** Not as an option, not behind a flag, not "for
  reference alongside the range." The bound is the deliverable. A precise figure claims precision the
  inputs do not support, and it fails silently rather than loudly when Schwab changes anything.
- The full six-tier hierarchy, **unless** 3a–3c have already shipped and been used — and then only as
  an indication rendered subordinate to the bound, never replacing it.
