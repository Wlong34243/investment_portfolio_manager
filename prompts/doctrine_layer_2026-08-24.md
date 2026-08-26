# Doctrine Layer — 2026-08-24

**Sequence: 1 of 3.** `prompts/decision_capture_detector_2026-08-24.md` (2 of 3) depends
on the reader built here. `prompts/thesis_pattern_tags_2026-08-24.md` (3 of 3) is
independent and may run any time after.

> ⚠️ **Ordering dependency — `prompts/typed_trigger_crosshairs_2026-08-24.md` must run
> BEFORE this prompt.** Both modify `tasks/build_crosshairs.py::_near_candidates()` and
> the `CrosshairItem` dataclass. That prompt *restructures* `_near_candidates` to branch on
> the declared `trigger_type`; this prompt adds a *post-filter* on top of whatever
> candidates it emits. Composed in that order they layer cleanly. Composed in reverse, the
> typed-trigger rewrite silently discards the doctrine downgrade.
>
> **Consequence to expect:** after the typed-trigger build, UNH fires `NEAR_TRIM` on its
> declared primary (fwd P/E 17.39 vs `fwd_pe_trim_above: 18`) rather than on the $380 price
> band. The downgrade in Step 3 matches on **ticker + reason_code**, never on the metric, so
> it catches UNH either way — but Step 0 assertion (g) and verification item 4 must be read
> against whichever build is actually on disk.

## Why this exists

Bill's standing constraints — the ones that govern every future decision — have no home.
On 2026-08-19 the same paragraph was pasted into three thesis files, and the QQQM copy
says the problem out loud: *"recorded as the standing rationale so it doesn't need
re-litigating file by file."* That is doctrine being written with nowhere to put it.

The live cost, 2026-08-24: UNH sits at the top of Crosshairs as `NEAR_TRIM` (-2.9% from
its $380 trim level) while Bill has stated he will not sell it — realized-gain exposure
on a runner. Nothing in the system knows that, so the signal reprints every morning and
crowds out signals he can act on. Analysis rule 8 already says export-time findings Bill
cannot act on must be grouped separately; this extends the same principle to Crosshairs.

**Non-goals.** No new vendor. No MCP. No auto-trading. No writes to `Target_Allocation`,
`Holdings_Current` or `Trade_Log`. Doctrine does not generate signals — it only reranks
and annotates ones already generated.

---

## STEP 0 — Verification gate

Confirm every assertion below against actual file state before writing any code. If any
fails, STOP and report rather than adapting silently.

- **a)** `vault/doctrine.md` does **not** exist. `vault/` contains exactly:
  `theses/`, `frameworks/`, `research/`, `transcripts/`, `THESIS_BACKFILL_GUIDE.md`.
- **b)** `utils/doctrine_reader.py` does **not** exist.
- **c)** The 2026-08-19 standing rationale appears in three live thesis files:
  `vault/theses/QQQM_thesis.md` (Review Log entry), `vault/theses/VST_thesis.md`
  (Review Log entry), `vault/theses/VRT_thesis.md` (inside `next_step:`). Capture the
  exact line numbers and verbatim text before touching anything — Step 5 needs them.
- **d)** `tasks/build_crosshairs.py` defines exactly four sort buckets:
  `_BUCKET_NEAR = 0`, `_BUCKET_DISLOC_HELD = 100`, `_BUCKET_DISLOC_OTHER = 200`,
  `_BUCKET_MISSING = 300`. No `_BUCKET_DOCTRINE*` exists.
- **e)** `CrosshairItem` is a dataclass with fields: `ticker, reason_code, rank_score, mv,
  wt, price, trim, add, dist_trim, dist_add, rationale`. No doctrine field.
- **f)** `tasks/export_ai_briefing.py::main()` assembles exactly five bundle files:
  `prompt.md`, `portfolio.md`, `podcasts.md`, `theses.md`, `SUBMIT_ME.md`, and
  `SUBMIT_ME.md` is the join of the first four in that order.
- **g)** The most recent Crosshairs output ranks `UNH` as `NEAR_TRIM` in the top 5. Record
  **which metric** fired it — price ($380 band) if `typed_trigger_crosshairs_2026-08-24.md`
  has not yet run, forward P/E (`fwd_pe_trim_above: 18`) if it has. Either is a valid
  starting state; the downgrade must work against both.
- **h)** State which of `prompts/typed_trigger_crosshairs_2026-08-24.md` has landed. If it
  has **not**, STOP and run it first — see the ordering warning at the top of this file.

---

## STEP 1 — Create `vault/doctrine.md` (SIGN-OFF GATE)

Seed content below is transcribed from Bill's own words, 2026-08-24 and 2026-08-19.
**Transcribe; do not extend, summarise, or infer additional constraints.** Present the
full proposed file at a sign-off gate and STOP. Bill accepts, overrides or rejects per
constraint before anything is written.

```markdown
---
doctrine_version: 1
updated: 2026-08-24
constraints:
  - id: no_withdrawal_need
    established: 2026-08-19
    restated: 2026-08-24
    scope: portfolio
    summary: >
      Real estate cash flow covers living expenses and cost of living has been
      reduced. This portfolio does not fund withdrawals; it exists to grow.
    affects: [ceiling_breach_acceptance, risk_tolerance]
    action: context_only

  - id: accumulation_phase
    established: 2026-08-24
    scope: portfolio
    summary: >
      Accumulation phase. Pushing money into appreciating assets and waiting for
      recent acquisitions to pay off. Not harvesting.
    affects: [rotation_bias]
    action: context_only

  - id: tax_hold_runners
    established: 2026-08-24
    scope: position
    tickers: [UNH, COF]
    summary: >
      Acute awareness of realized-gain exposure. Selling runners is not
      attractive. These are not sale candidates on a valuation trigger alone.
    affects: [NEAR_TRIM]
    action: downgrade_informational
---

# Portfolio Doctrine

Standing constraints that govern decisions across positions. This file is the single
source; thesis files point here rather than restating.

**This file is hand-maintained and manual-only. No agent writes to it** — same rule as
`Target_Allocation`. Changes are Bill's, dated, and additive: supersede an entry by
adding a new one with a later `established` date, do not silently edit history.

## Review Log
- 2026-08-24: File created. `no_withdrawal_need` migrated out of QQQM/VST/VRT thesis
  Review Logs (see prompts/doctrine_layer_2026-08-24.md Step 5). `accumulation_phase`
  and `tax_hold_runners` recorded from Bill's 2026-08-24 statement.
```

**Gate question for Bill, ask explicitly:** `tax_hold_runners` names UNH and COF because
those are the two he named. Are there others that belong on this list, and does the
constraint apply to *trims* as well as full exits? The `action` value assumes it applies
to any `NEAR_TRIM` regardless of size.

---

## STEP 2 — `utils/doctrine_reader.py`

Canonical reader, same role `utils/thesis_reader.py` plays for theses. Build it so every
consumer shares one parse path — do not let `build_crosshairs` and `export_ai_briefing`
each grow their own.

Required surface:

```python
def load_doctrine(path: Path | None = None) -> Doctrine
def constraints_for_ticker(doctrine, ticker: str) -> list[Constraint]
def downgrade_rule(doctrine, ticker: str, reason_code: str) -> Constraint | None
```

Hard requirements:

- **Missing file is not an error.** Return an empty `Doctrine` and let callers proceed.
  This must ship before `vault/doctrine.md` is guaranteed present on every machine.
- **Malformed frontmatter is soft-skip, not raise.** Follow the 2026-08-11 precedent
  (`state.md`, vault sync YAML hardening): collect a `parse_errors` list, omit the broken
  constraint, keep going. Do **not** raise `logs/HEALTH_FAILURE.flag` for a doctrine
  parse failure.
- **Unknown `action` values are ignored with a warning**, not applied as a default.
- Tickers are upper-cased and de-duplicated on read.

---

## STEP 3 — Wire the downgrade into `tasks/build_crosshairs.py`

Bill's decision, 2026-08-24: **downgrade to informational, do not suppress.** The item
stays visible and keeps its distance figure — he wants to see how far past a level a
position has run for tax-year planning — but it stops competing with actionable items.

Implement:

1. Add one bucket constant, below `_BUCKET_MISSING`:
   ```python
   _BUCKET_DOCTRINE_HOLD = 400  # doctrine says Bill won't act — visible, ranked last
   ```
2. Add two fields to `CrosshairItem`: `doctrine_tag: Optional[str] = None` and
   `doctrine_reason: str = ""`. Defaulted, so `asdict()` and every existing consumer stay
   backwards-compatible.
3. In `_near_candidates()`, after a `NEAR_TRIM` candidate is built, consult
   `downgrade_rule()`. On a match: set `rank_score = _BUCKET_DOCTRINE_HOLD + abs(dist)`,
   set `doctrine_tag` (e.g. `HOLD_TAX`), and append the doctrine summary to `rationale`.
   **Leave `reason_code` as `NEAR_TRIM`** — the level really was crossed; only its
   priority changes.
4. `NEAR_ADD` is untouched. `tax_hold_runners` constrains selling only.

Do **not** change `NEAR_BAND_PCT`, the dislocation path, or `MISSING_LEVEL` handling.

**Renderer note:** `0_DASHBOARD` shows top 5 and `Decision_View` shows all
(`build_command_center` / `build_decision_view`). A downgraded item will normally fall off
the dashboard and remain on Decision_View — that is the intent. Verify both renderers read
`rank_score` and do not re-sort on `reason_code`; if either does, fix the renderer rather
than working around it here. Remember `0_DASHBOARD` is clear-and-rebuild — nothing outside
`build_command_center.py`'s grid construction may write to it.

---

## STEP 4 — Add `doctrine.md` to the bundle

In `tasks/export_ai_briefing.py::main()`, add `doctrine.md` as a **sixth** bundle file and
include it in the `SUBMIT_ME.md` join, positioned **after `prompt.md` and before
`portfolio.md`** — constraints should be read before the positions they govern.

- Hash it into `file_sha256` alongside the others. The composite hash will change; that is
  expected and unpinned (confirmed 2026-08-09: tests recompute, nothing asserts a literal
  digest).
- If `vault/doctrine.md` is absent, emit **no** `doctrine.md` file and add a
  `preflight_issues` entry. Do not ship an empty placeholder into the bundle.
- Add one paragraph to `PROMPT_PAYLOAD` telling the reasoning model that `doctrine.md` is
  **authoritative on Bill's constraints and outranks inference from the trade log**. It is
  Bill's own writing, so it sits in the same trust tier as `theses.md` on the
  Bundle Architecture table in `CLAUDE.md` — update that table in the same pass.

---

## STEP 5 — Migrate the three thesis copies (SIGN-OFF GATE)

`vault/theses/QQQM_thesis.md`, `VST_thesis.md`, `VRT_thesis.md` each restate the
`no_withdrawal_need` rationale. Replace each with a dated pointer, e.g.:

```
- 2026-08-24: Standing rationale for this breach acceptance moved to `vault/doctrine.md`
  (`no_withdrawal_need`, established 2026-08-19). Text unchanged; single-sourced.
```

Rules:

- **Archive-before-overwrite.** A `.bak` taken *after* an edit is not a backup — prove
  pre-edit content by grep and capture it in the run log before writing.
- VRT's copy is embedded inside `next_step:` frontmatter, not a Review Log bullet. Preserve
  the rest of that `next_step` value verbatim — it also carries the separate
  *"accumulated because I like the company and the price was dropping"* rationale, which is
  position-specific and **stays in the thesis file**.
- Present a three-row before/after table at a sign-off gate and STOP before writing.
- Run `lint_theses.py` after. Expect known subject-scoping false positives (`state.md`,
  2026-08-07) — triage, do not auto-fix.

---

## Verification checklist

**Demand literal stdout/stderr for every item. Do not accept an agent-reported PASS
table** — on 2026-08-08 a checklist item was reported PASS while the artifact header
contradicted it.

1. `python -c "from utils.doctrine_reader import load_doctrine; print(load_doctrine())"` —
   paste output. Three constraints parsed.
2. Same call with `vault/doctrine.md` temporarily renamed — paste output. Returns empty,
   raises nothing, no `HEALTH_FAILURE.flag` written.
3. Same call with deliberately malformed frontmatter — paste output. Soft-skips, populates
   `parse_errors`, no raise.
4. `python manager.py refresh dashboard` (DRY RUN, no `--live`) — paste the full Crosshairs
   list. **UNH must appear with `reason_code=NEAR_TRIM`, `doctrine_tag=HOLD_TAX`, and a
   `rank_score` >= 400.** Paste the row.
5. From the same output: confirm UNH is **absent** from the top 5 and **present** in the
   full list. Paste both.
6. Confirm `GILD`, `ET` and `GLD` NEAR_TRIM rows are **unchanged** — `rank_score` < 100,
   no doctrine tag. Paste the rows. A regression here means the ticker match is too broad.
7. `python manager.py morning --dry-run` (or the briefing export alone) — paste the
   `manifest.json` `files` and `file_sha256` blocks showing six entries including
   `doctrine.md`.
8. Confirm `SUBMIT_ME.md` contains `doctrine.md` content between the prompt and portfolio
   sections — paste the section boundary lines.
9. `grep -c "real estate cash flow" vault/theses/*.md` — paste output. Must be 0 for
   QQQM/VST/VRT live files (`.bak` files will still match; that is correct).
10. Confirm no writes occurred to `Target_Allocation`, `Holdings_Current`, `Trade_Log` or
    `0_DASHBOARD` during any dry run — paste the write log.

Then, and only then: `--live`.

## Update on completion

- `state.md` Recent Decisions Log — one dated entry.
- `CLAUDE.md` — add `vault/doctrine.md` to Key Files, add the doctrine row to the Bundle
  Architecture trust table, and note the Crosshairs downgrade under Trim/Add Triggers.
- `CHANGELOG.md` — dated entry.
