# Thesis Pattern Tags — 2026-08-24

**Sequence: 3 of 3.** Independent of prompts 1 and 2; may run any time after either.
Small on purpose.

## Why this exists

On 2026-08-24 Bill described the QXO entry as *"I like the turnaround story like I did with
UNH at $300."* That is not a one-off rationale — it is a **named, repeatable setup with a
worked comparable**, stated unprompted.

`tasks/dislocation_scan.py` currently screens on generic thresholds: market cap >= $10B,
drawdown >= 15%, 5d return <= -10%, forward P/E <= 18, gross margin >= 30%. Those are
reasonable defaults and they are not Bill's actual pattern. His pattern has a shape the
thresholds do not capture — a broken-then-mending operator story, bought during the repair,
sized up as evidence arrives.

**This prompt only starts capturing the tag. It does not build a screener.** Tag first,
accumulate real examples, then decide whether the scanner should read them. Building the
screener now would be spec-ahead-of-evidence, which `CLAUDE.md`'s development philosophy
explicitly warns against: *do NOT over-spec scoring rubrics before seeing actual output.*

**Non-goals, stated so a later session does not quietly expand scope.** No change to
`dislocation_scan.py`. No change to trigger types. No change to Crosshairs. No new screen.
No backfill of tags onto positions whose entry rationale is not already on record in
Bill's own words.

---

## STEP 0 — Verification gate

- **a)** All 39 live thesis files parse via the nested-frontmatter strategy in
  `core/vault_bundle.py::_parse_thesis_fields()`. Only archived `KTOS_thesis.md` uses the
  fenced ```yaml block. Confirm — a new field must not resurrect the dead strategy.
- **b)** `utils/thesis_reader.py` is the canonical reader (style taxonomy, `#` strip, typed
  trigger bands) and is shared by briefing / vault / dislocation / lint paths.
- **c)** No `pattern` key exists in any thesis frontmatter today.
  `grep -l "^ *pattern:" vault/theses/*.md` returns nothing.
- **d)** `vault/theses/QXO_thesis.md` exists, `trigger_type: ceiling_only`,
  `style_size_ceiling_pct: 9.0`. Note: an earlier `trigger_type: event` defect
  (2026-08-12 brief) is already resolved — confirm it has not regressed.
- **e)** `vault/theses/UNH_thesis.md` contains entry history around the $300 level to
  support the comparable. If it does not, the `comp` value below is unsupported and must be
  left blank rather than asserted.

---

## STEP 1 — Define the field

Add an **optional** `pattern` block to thesis frontmatter:

```yaml
pattern:
  name: turnaround_reversion
  comp: UNH@300
  established: 2026-08-24
  note: >
    Broken-then-mending operator bought during the repair, not after it.
```

Rules:

- **Optional everywhere.** A thesis without `pattern` is valid and must stay valid. No
  coverage metric, no `MISSING_PATTERN` finding, nothing in Crosshairs. This is descriptive
  metadata, not a trigger — the moment it generates a signal it needs a band, and it has
  none.
- `name` comes from a **closed vocabulary** (Step 2). `comp` is free text.
- Parsed by `utils/thesis_reader.py` and carried through `core/vault_bundle.py`'s
  `_parse_thesis_fields()` into the vault bundle. Follow the 2026-08-09 precedent: the
  `triggers` dict was widened to carry whatever keys a file declares — do the same rather
  than hardcoding a fixed shape.
- Surfaces in `theses.md` at `detail: standard`, one line. Not in `portfolio.md`.

---

## STEP 2 — Seed vocabulary (SIGN-OFF GATE)

Do **not** invent categories. Propose only patterns already evidenced by Bill's own
recorded words in thesis files or the 2026-08-24 conversation, present the table, and STOP.

| `name` | Evidence on record | Candidate tickers |
|---|---|---|
| `turnaround_reversion` | "I like the turnaround story like I did with UNH at $300" (2026-08-24) | QXO, UNH |
| `debasement_hedge` | "monetary policies driving down the value of the dollar... world moving off USD as a core store of value and into more gold" (2026-08-24) | GLD |
| `accumulate_on_decline` | "VRT was accumulated because I like the company and the price was dropping — it got big, same as COF" (`VRT_thesis.md`, 2026-08-19) | VRT, COF |

**Gate questions:**

1. Is `turnaround_reversion` the same pattern as `accumulate_on_decline`, or genuinely
   distinct? Both buy into weakness. The proposed distinction: turnaround requires a
   *broken operator with a repair underway*; accumulate-on-decline is a good company at a
   falling price with nothing broken. If Bill does not recognise that split, collapse to one
   name — two names for one pattern is worse than a coarse one.
2. Do COWZ, LLY, WSM, XBI and RRC (the 2026-08-24 "prizes" and energy entries) belong to a
   pattern, or are they thesis-specific? Do **not** assign a tag to make the table look
   complete.

Only tag what Bill confirms. An unconfirmed tag is invented data wearing a schema.

---

## STEP 3 — Write the confirmed tags

- Archive-before-overwrite. Prove pre-edit content by grep before writing.
- Frontmatter edits go through `ThesisManager` (strict ruamel), not hand-editing —
  the 2026-08-11 duplicate-`triggers:` incident came from bypassing it.
- Add a dated `## Review Log` line to each tagged file recording the tag and its source
  quote.
- Run `lint_theses.py` after. Known subject-scoping false positives are expected; triage,
  do not auto-fix.

---

## Verification checklist

**Literal stdout for every item.**

1. `python -c "from utils.thesis_reader import ...; ..."` on a tagged file — paste parsed
   `pattern` block.
2. Same on an **untagged** file — paste output. Returns `None`/absent, raises nothing.
3. File with malformed `pattern` block — paste output. Soft-skip per the 2026-08-11 pattern,
   no `HEALTH_FAILURE.flag`.
4. `python manager.py morning --dry-run` — confirm bundle builds, paste `manifest.json`
   `level_coverage` block and confirm **`trigger_type_by_ticker` is byte-identical** to the
   2026-08-24 bundle. Pattern tags must not perturb trigger typing.
5. Paste the `theses.md` section for QXO showing the pattern line.
6. Paste the Crosshairs list from the same run and confirm it is **unchanged** versus the
   pre-change run — same tickers, same reason codes, same rank scores. Any delta means the
   tag leaked into signal generation.
7. `git diff --stat` — confirm only thesis files, `thesis_reader.py`, `vault_bundle.py` and
   `export_ai_briefing.py` changed. **`dislocation_scan.py` must be untouched.**

## Update on completion

`state.md` (one line, including the explicit "screener deliberately not built" note),
`CHANGELOG.md`. Do not add a Key Files row — no new file is created.
