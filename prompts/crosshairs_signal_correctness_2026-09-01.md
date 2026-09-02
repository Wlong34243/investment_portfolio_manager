# Crosshairs Signal Correctness — 2026-09-01

**Handoff target:** Claude Code or Gemini CLI.
**Premise (standing, 2026-09-01):** innovate and automate; correction and discipline
come from scrutinising real signals in use, not from pre-specifying the rubric.
Ship the first values. Do not tune before seeing output.

---

## Why this exists

On 2026-09-01 the Command Center ranked **GLD #1 NEAR_TRIM**. At that moment GLD was:

| fact | value |
|---|---|
| price vs. `price_trim_above: 400` | $402.27 vs 400 — through the level by 0.6% |
| unrealized | **−$119.57 (−1.72%)** — at a loss |
| weight | 1.15% |
| `style_size_ceiling_pct` | 8.0 — position is at **14% of its own ceiling** |
| `GLD_thesis.md` body prose (2026-08-14) | "I will NOT trim GLD based on gold price moving up alone… price_trim_above: 400 is an evaluate-if-momentum flag." |

Three independent defects, fixed here in order. They are coupled because all three
touch `tasks/build_crosshairs.py` — do not split across parallel agents.

1. A written trim instruction has no machine-readable home. `add_triggers_suspended`
   exists for the add side; there is no trim-side equivalent at thesis scope.
   (`vault/doctrine.md` `downgrade_informational` is the *portfolio/Bill-fact* shelf and
   is deliberately NOT the fix here — see Boundary, below.)
2. `_near_candidates()` ranks trim candidates on `abs(dist_trim)` alone. No size term,
   no P&L-direction term. GLD is the instance; the ranker is the class.
3. Nothing detects a directive written into thesis prose below the parser's read-line.

**Boundary rule to preserve (do not blur it):**
> Thesis holds what is true about the position. Doctrine holds what is true about Bill.
> Precedence: `doctrine > thesis frontmatter > thesis prose (unread) > Trade_Log`.

---

## Step 0 — Verification gate

Report literal findings. **If any item differs from the expectation, STOP and report.
Do not adapt silently.**

1. `tasks/build_crosshairs.py` exists. Print the line numbers of `_near_candidates`,
   `_add_triggers_suspended`, `_apply_add_suspensions`, `_apply_doctrine_downgrades`,
   and the `_BUCKET_*` constants. (Expected approx: 337, 544, 613, 563, 67–72.)
2. `utils/thesis_reader.py` exports `load_frontmatter` and `THESES_DIR`. Confirm by import.
3. `grep -l "trim_trigger_role\|trim_triggers_suspended" vault/theses/*_thesis.md`
   → expect **no matches**.
4. `grep -l "add_triggers_suspended" vault/theses/*_thesis.md`
   → expect **exactly one** file (VRT).
5. Count live theses (`vault/theses/*_thesis.md`, excluding `.bak*`) → expect **41**.
6. Count live theses carrying `style_size_ceiling_pct` under `triggers:` → report the
   number and **name any file missing it**. Step 3 depends on this.
7. **Print the exact key names** present on a `held` row dict as `_near_candidates`
   receives it (`_holdings_map` output), specifically the keys carrying **cost basis**
   and **unrealized $ / %**. Do NOT guess or assume `"Cost Basis"`. If no unrealized
   figure is on the row, say so — Step 3's P&L term then needs a source decision
   before it can be written.

---

## Step 1 — `trim_trigger_role` thesis frontmatter

Add a trim-side role key under `triggers:`, symmetric with `add_triggers_suspended`
but **named rather than boolean**, because the reason belongs in the rationale string.

```yaml
triggers:
  trim_trigger_role: informational   # binding (default) | informational
```

- Absent or any unrecognised value → `binding`. Absence must never change today's behaviour.
- `informational` → the NEAR_TRIM row **stays on `Decision_View`**, is re-ranked to
  `_BUCKET_DOCTRINE_HOLD + abs(dist_trim)`, gets `override_tag = "TRIM_INFORMATIONAL"`,
  and appends `| trim_trigger_role: informational` to the rationale.
- Implement as `_trim_trigger_role(ticker) -> str` (mirroring `_add_triggers_suspended`)
  plus `_apply_trim_roles(items)` (mirroring `_apply_add_suspensions`).
- **Never drop a row.** Ranking only. This is policy (b), identical to the add side.
- **Precedence:** if a doctrine `downgrade_informational` rule also matches the ticker,
  doctrine wins — `override_tag` stays `HOLD_TAX` (or the doctrine rule id) and the
  rationale notes both. Run `_apply_doctrine_downgrades` first, then `_apply_trim_roles`,
  and make `_apply_trim_roles` a no-op on rows already at `>= _BUCKET_DOCTRINE_HOLD`.

Do not write the key into any thesis file in this step.

---

## Step 2 — SIGN-OFF GATE (stop and present; write nothing)

Produce one table covering every live thesis that currently has a trim level, columns:

`Ticker | trigger_type | trim level | current metric | dist_trim | weight % | ceiling % | headroom (weight/ceiling) | unrealized % | directive prose found? (quote ≤15 words)`

Sort by `dist_trim` ascending. Present it and **STOP**.

Bill accepts / overrides / rejects **per row**. Write `trim_trigger_role: informational`
only into accepted rows, via `ThesisManager` (frontmatter-safe), archive-before-overwrite,
one file at a time.

**Do not write GLD without sign-off**, even though GLD motivated this prompt.

---

## Step 3 — Ranker terms (trim side only)

In `_near_candidates`, for the **NEAR_TRIM candidate only**, extend the score with two
modifiers. Declare both weights as module constants at the top of the file — not inline,
not configurable, not tuned:

```python
W_CEILING_HEADROOM = 0.05   # first value; correct from observed output
W_UNREALIZED_LOSS  = 0.05   # first value; correct from observed output
```

- **Headroom:** `headroom = min(weight / style_size_ceiling_pct, 1.0)`.
  Penalty `W_CEILING_HEADROOM * (1.0 - headroom)`. A position at 14% of its ceiling
  ranks below one at 95% for the same distance-through-level.
  Missing weight or missing/zero ceiling → contribute **0.0**, never crash, never guess.
- **Unrealized direction:** penalty `W_UNREALIZED_LOSS` when unrealized is negative,
  else 0.0. Source per Step 0 item 7. If unavailable on the row, **stop and report**
  rather than deriving it locally.

Constraints:
- These are **rank modifiers inside `_BUCKET_NEAR` only**. They must never re-bucket,
  never suppress, never drop a row, and never alter `dist_trim` as displayed.
- The number Bill reads on the card must remain the raw distance.
- Add the two contributions to the rationale string so the ranking is legible, e.g.
  `| rank: headroom 0.14, unrealized -1.7%`.
- Do not apply either modifier to NEAR_ADD, DISLOCATION, or MISSING_LEVEL.

**Out of scope, deliberately:** a size-vs-*target* term. No thesis carries a
`target_allocation` field (verified 2026-09-01: 41/41 have `current_allocation`,
0/41 have a target). Populating one is a judgment task for Bill, not a migration.
Do not invent the field, do not infer a target from prose.

---

## Step 4 — `lint_theses.py` check 7: directive prose below the read-line

Extend the existing report (do not create a new script; do not change its exit-0 contract).

New check: body prose — outside frontmatter, outside `<!-- region:* -->` markers —
containing a directive phrase, where the corresponding frontmatter key is absent or
contradicts it.

Phrases (case-insensitive, extend as observed): `will not trim`, `won't trim`,
`do not trim`, `will not add`, `do not add`, `governing rule`, `does not override`,
`stand down`, `not a sale candidate`, `not a trim candidate`.

Emit: file, line number, the matched phrase, the ≤15-word quote, and the frontmatter
key the phrase implies (`trim_trigger_role` / `add_triggers_suspended`) with its
current value or `ABSENT`.

This is the mechanical replacement for a manual 41-file sweep. Run it and paste
literal stdout.

---

## Post-build verification checklist

**Literal stdout/stderr only. An agent-reported "PASS" table is not accepted** — on
2026-08-08 a checklist item was reported PASS while the artifact header contradicted it.

1. `python tasks/lint_theses.py` — full literal stdout, including check 7 findings.
2. `pm refresh dashboard` (**DRY RUN**) — paste the full Crosshairs ordering before and
   after Step 3, side by side. State GLD's rank in each.
3. Show that a thesis with **no** `trim_trigger_role` produces byte-identical rationale
   and rank_score to pre-change, for at least three tickers. Paste both.
4. Show a `trim_trigger_role: informational` ticker still present on `Decision_View`
   and absent from the CC top 5. Paste both lists.
5. Show doctrine precedence: a ticker matching **both** a doctrine downgrade and
   `trim_trigger_role` reports `override_tag = HOLD_TAX` (not `TRIM_INFORMATIONAL`).
   If no such ticker exists live, construct it in a test and paste the test output.
6. `pytest` — full literal summary line.
7. Confirm no writes occurred outside `vault/theses/` sign-off rows and the two
   Python files. `git status --porcelain`, pasted.

---

## Do not

- Do not add GLD (or anything) to `vault/doctrine.md` in this prompt. Wrong shelf.
- Do not drop or hide any Crosshairs row. Ranking only.
- Do not add a `target_allocation` frontmatter field.
- Do not tune `W_CEILING_HEADROOM` / `W_UNREALIZED_LOSS` before Bill has seen output.
- Do not touch `tasks/build_command_center.py`'s grid construction.
- Do not create new root-level markdown. Extend `CHANGELOG.md` and `state.md` only.


---
---

# DEFECT FIX ROUND 1 — 2026-09-01, post-build

Build landed. Gate 1 held correctly (no thesis carries `trim_trigger_role`; vault untouched).
Four defects found in the sign-off output. **None of the trim-role writes may proceed until
D1–D3 are fixed and the table is regenerated.**

## D1 — `Weight` unit mismatch makes the headroom term a silent no-op  [BLOCKING]

`Holdings_Current.Weight` (col Q) arrives as a **fraction**, not percentage points.
Evidence from the live sign-off run:

| ticker | `Weight` as read | actual weight |
|---|---|---|
| GLD  | 0.011 | 1.15% |
| AAPL | 0.016 | 1.59% |
| GOOG | 0.057 | 5.7%  |

`style_size_ceiling_pct` is in percentage points (8.0, 9.0). So in
`_trim_rank_modifiers`:

```
headroom = min(0.011 / 8.0, 1.0) = 0.0014   ->   prints 0.00
```

Every live row computes 0.00–0.01. The penalty collapses to
`W_CEILING_HEADROOM * (1.0 - ~0.0)` ≈ 0.05 **applied uniformly to every trim
candidate**, which changes no relative ordering. GLD still ranks #1. The term is dead.

**Fix — one explicit normalization, no heuristic.**

- Add a helper with the unit contract stated in its docstring, citing
  `PORTFOLIO_SHEET_SCHEMA.md` Holdings_Current col Q: the sheet stores a fraction;
  the ranker works in percentage points.
- **Do not** infer the unit at runtime (`if wt <= 1.0: wt *= 100`). A genuine 0.9pp
  weight and a 0.9 fraction are indistinguishable; a guess here fails silently in the
  same way this defect did.
- Apply the same normalization anywhere `Weight` meets a `*_pct` field. Audit for
  other call sites before assuming this is the only one.
- `export_ai_briefing.py:536` (`weight > ceiling`) uses a **different** weight source
  (the briefing's computed `weight_pct`, already in percentage points). Do not
  "harmonise" it — confirm which source each call site reads and leave correct ones alone.

## D2 — The unit drift was invisible because the test fixture used the other unit  [BLOCKING]

`tests/test_build_crosshairs.py`'s headroom test **passed** while the production term
was dead. That means the fixture supplies percentage-point weights where production
supplies fractions. A test that cannot fail when the feature is broken is worse than
no test.

**Fix:**
- Rebuild the headroom fixture from a **real** `Holdings_Current` row shape, units included.
- Pin the known case: **GLD headroom must assert to 0.14** (1.15 / 8.0).
- Add a guard test that fails if fixture units diverge from the sheet contract — e.g.
  assert the fixture's weight for a ~1% position is < 1.0 before normalization and
  ~1.15 after.
- Then re-run and state plainly whether the headroom ordering test still passes. If it
  passes unchanged after D1, it is still not testing anything — say so.

## D3 — The sign-off table reconstructs the ranker instead of calling it  [BLOCKING]

`scripts/generate_trim_signoff_table.py` prints `dist_trim` blank on every row because
it looks for `"Dist Trim" / "dist_trim" / "Trim Distance"` on the **Valuation_Card**
row. Those keys do not exist there. The real value is computed by
`resolve_typed_metric(trigger_type, hrow, vdata)["dist_trim"]`.

The wrong key is the surface problem. The real one: the script independently
re-implements level selection (`_trim_level`) and trigger-type resolution, so **the
table shows numbers the ranker does not use.** Approving rows from it means approving
against a parallel implementation that will drift.

**Fix — derive the table from `produce_crosshairs()`, do not reconstruct it.**

- Call `produce_crosshairs(read_sheets_if_needed=True)` and read `dist_trim`,
  `rank_score`, `reason_code`, `override_tag` and the rationale off the returned items.
- Join thesis-side columns (trim level, ceiling, directive quote, current role) by ticker.
- Delete `_trim_level()`. Trigger type comes from `resolve_trigger_type`, the same
  function the ranker uses — never from frontmatter directly.
- A thesis with a trim level that produces **no** crosshair item must still appear,
  with `dist_trim` shown as `not in band` rather than blank — blank reads as an error.
- Sort by `rank_score`, and print it. Bill is approving a ranking; show him the ranking.

## D4 — Unrealized display string carries the same scale error

`_trim_rank_modifiers` builds `f"unrealized {unreal_pct:.1f}%"`. `Unrealized G/L %`
is also a fraction (GLD `-0.017`), so the rationale prints `-0.0%` where it should
read `-1.7%`. The **penalty itself is correct** — sign is scale-invariant, so
`W_UNREALIZED_LOSS` is the one term currently working. Fix the display only; do not
change the comparison.

Also fix the sign-off table's `unrealized%` and `weight%` columns — the headers claim
percent and the values are fractions.

## D5 — Unexplained ninth pytest failure  [BLOCKING for the vault writes]

Baseline `8 failed, 196 passed` (204 collected) → post-build `9 failed, 206 passed`
(215 collected). That is +11 collected, +10 passed, **+1 failed** — not accounted for
by "10 new tests, no new failure class."

**Required before any `trim_trigger_role` write:** paste the literal `pytest -q`
failure lines for both runs and name the ninth failure. Given D2, a new failure is
more likely to be real signal than noise. If it is a new pre-existing-class failure
(`vault_bundle_smoke`), say so with the node id.

## Verification for this round (literal stdout only)

1. `python scripts/generate_trim_signoff_table.py` — full table, `dist_trim` populated,
   headroom in 0.00–1.00 with **GLD showing 0.14**, sorted by `rank_score`.
2. Crosshairs top 5 before and after D1, side by side. State GLD's rank in each. If
   GLD does not move, D1 is not fixed.
3. `pytest -q` failure lines, both runs, with the ninth named.
4. `git status --porcelain` — confirm `vault/theses/` still contains **zero**
   `trim_trigger_role` keys.

## Do not

- Do not write `trim_trigger_role` to any thesis in this round. Gate 1 stays closed.
- Do not runtime-infer the weight unit.
- Do not tune `W_CEILING_HEADROOM` / `W_UNREALIZED_LOSS` — they have never actually run.
- Do not touch `export_ai_briefing.py`'s ceiling-breach comparison.
