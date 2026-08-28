# Pre-commitment Capture — declare the trigger before the fact

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 8 of 10.** **Depends on:** prompt 1 (`signal_events`), prompt 7 (shares the resolution loop
and the provenance vocabulary).
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 6b.

> Right now the pre-committed criteria live in thesis frontmatter and **the response lives nowhere.**
> This is the `declared_before` half of the rationale loop, and the thing that makes Phase 3's
> calibration table measure what it claims to.

---

## What is actually missing, precisely

The thesis frontmatter already holds the bands. `build_crosshairs` already evaluates them. Prompt 1
now records the firings. Three of four quadrants exist.

What does not exist is **the dated declaration of what Bill intended to do when it fires**, and
**the record of what he then did.** Without those, the calibration table's "you acted / you passed"
axis is reconstructed after the fact — which is exactly the hindsight contamination prompt 7 exists
to keep out of the other axis.

A thesis band says *18*. It does not say *when Bill decided 18*, or *what he meant to do at 18*, or
*what he did when it hit*. Those three are this prompt.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — dependencies
python manager.py store evidence-status
python -c "import sqlite3,config;\
[print(r[0]) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute(\
\"select name from sqlite_master where type='table' and name in ('signal_events','rationale_proposals')\")]"

# 0.2 — the canonical trigger reader and the six types
grep -n "^def \|trigger_type\|resolve_band_levels" utils/thesis_reader.py | head -30
grep -n "def get_ticker_triggers" core/composite_bundle.py

# 0.3 — one live thesis's triggers block, verbatim
sed -n '1,40p' vault/theses/MU_thesis.md

# 0.4 — coverage as it stands
python manager.py vault thesis-audit 2>&1 | head -20
python -c "from utils.level_coverage import *" 2>&1 | head -3

# 0.5 — doctrine, which is where standing constraints already live
sed -n '1,60p' vault/doctrine.md
```

**Expected at 0.2:** six trigger types (`price`, `fwd_pe`, `trailing_pe`, `discount_from_high`,
`price_to_book`, `ceiling_only`), and `trigger_type` documented as *primary, not exclusive* — a
thesis may carry populated bands for more than one type.

---

## The boundary that keeps this from becoming a second source of truth

**Thesis frontmatter stays authoritative on the bands.** This prompt does not move them, mirror them,
or let a CLI command edit them. `ThesisManager` owns thesis writes.

A pre-commitment record is a **dated declaration referencing** a band: *on 2026-08-27 I declared that
if META's fwd P/E reaches 18 I intend to trim to 2%.* If the band later moves in the thesis file, the
old pre-commitment stays as written, closed with a reason. **That is the point** — a moved band is
itself a decision worth having a record of, and a system that silently updated the declaration to
match would erase exactly the thing being measured.

---

## Step 1 — Schema

### `precommitments`

`id`, `declared_at`, `ticker` (indexed), `trigger_type`, `band_side` (`trim`/`add`), `band_level`,
`intended_action` (free text — "trim to 2%", "add one step", "exit"), `note` (free text, Bill's
reasoning at declaration time), `source` (`cli` / `thesis_sync`), `thesis_band_at_declaration`
(the band as the thesis file read at that moment — a snapshot, for drift detection),
`status` (`open` / `fired` / `closed_band_moved` / `closed_position_exited` / `closed_manual`),
`closed_at`, `close_reason`.

### `precommitment_firings`

`id`, `precommitment_id` (FK), `signal_event_id` (FK), `fired_at`, `response`
(`acted` / `passed` / `pending`), `responded_at`, `response_note`,
`linked_trade_log_id` (nullable — set when a fill reconciles to this firing).
`UNIQUE(precommitment_id, signal_event_id)`.

**`response` starts `pending` and is only ever set by Bill.** No inference, no timeout that assumes
`passed`, no auto-close. A `pending` firing that stays pending for a month is a true and useful
fact — it means the question was never answered — and quietly resolving it to `passed` would
manufacture data for the calibration table's most consequential cell.

---

## Step 2 — Declare

```
pm journal precommit --ticker META --type fwd_pe --side trim --level 18 \
    --action "trim to 2%" --note "multiple re-rate is the whole thesis; 18 is where it stops being GARP"
pm journal precommit --list [--ticker X] [--open-only]
pm journal precommit --close <id> --reason "band moved to 20 in thesis 2026-09-14"
```

- `--live` required to write, per the standing convention.
- On declaration, **read the current thesis band and compare.** If the declared level disagrees with
  the thesis file, print both and require `--force` to proceed. Two different numbers for the same
  trigger is a defect, not a feature, and it should cost a keystroke to create one.
- Store `thesis_band_at_declaration` regardless. Later drift is then detectable.
- **Reject any declaration whose level references a sell-side price target.** `CLAUDE.md`: consensus
  targets ratchet upward after price rises, so a trim pegged to consensus structurally cannot fire.
  `VST_thesis.md`'s `price_trim_above: consensus_price_target` is the live proof and has never been
  actionable. Refuse the declaration and say why.

**Optional, and only if Step 0.4 shows it is safe:** a `thesis_sync` source that seeds a
pre-commitment from an existing thesis band on first sight. Attractive, because it bootstraps 38
positions at once. **Dangerous, because a seeded pre-commitment was never actually declared** — it
would enter the record with a `declared_at` that is a file-scan date, not a decision date. If it is
built at all: `source='thesis_sync'` must be visible everywhere, and Phase 3 must be able to exclude
seeded rows from the calibration table entirely. **Recommendation: do not build it.** Let Bill declare
the ones he means, when he means them. Thirty-eight bootstrapped rows of false precision are worth
less than five real ones.

---

## Step 3 — Detect firings

New module `core/journal/precommit.py`, wired into `pm morning` **immediately after** evidence
capture (prompt 1, Step 3) — the firing detector reads `signal_events`, so it must run after that
day's rows are written.

For each open pre-commitment, find `signal_events` rows for the same ticker, same `trigger_type`,
same side, where the reading crossed the declared level. Insert `precommitment_firings` with
`response='pending'`. Idempotent on `UNIQUE(precommitment_id, signal_event_id)`.

**Bands are crossed, not touched.** Define the crossing condition explicitly in the module docstring
and hold it constant — a trim band at 18 fires when the reading is at or above 18, an add band at 12
fires at or below 12. Getting this wrong in either direction, and then changing it later, silently
rewrites the meaning of every historical firing.

**A doctrine-downgraded signal still fires the pre-commitment**, with the downgrade recorded. Doctrine
(`tax_hold_runners`) may re-rank a `NEAR_TRIM` to `HOLD_TAX` — that is a *response*, and a
system-mediated one, but the trigger did fire. Recording only undowngraded firings would hide every
case where the tax rule overrode a pre-committed criterion, which is precisely a thing worth measuring.

---

## Step 4 — Respond

The morning surfaces pending firings, and this is where the loop closes:

```
pm journal precommit --pending
```

```
META  fwd_pe trim @ 18   declared 2026-08-27 ("trim to 2%")
  FIRED 2026-09-14 — reading 18.4  [table:signal_events_for_ticker#41]
  Doctrine: not downgraded.
  Response?  [a]cted  [p]assed  [d]efer     note:
```

- **`a` acted** — records `acted`. If prompt 7's reconcile later matches a fill on this ticker within
  the window, it links `linked_trade_log_id` and sets that row's `Rationale_Provenance` to
  **`declared_before`**. **This is the only path in the entire system that produces `declared_before`.**
- **`p` passed** — records `passed` with an optional note. **The pass is the valuable data point.**
  The calibration table's two most interesting cells — "judgment cost you" and "judgment saved you" —
  are both passes, and they only exist if passing is as easy to record as acting. Make it one keystroke.
- **`d` defer** — stays pending.

Surface the pending count in `pm morning`'s output and on the `0_DASHBOARD` health block if there is
room — but **do not build a new Sheet tab for it.** `0_DASHBOARD` is clear-and-rebuild and owned by
`build_command_center._build_position_table()`; anything written outside that grid construction is
erased on the next run.

---

## Step 5 — Integration with prompt 7

When `pm journal reconcile` builds a proposal for a fill, it must first check for a matching
`acted` firing:

- **Match found** → the proposal is not a reconstruction. It cites the pre-commitment, and the
  resulting `Trade_Log` row gets `Rationale_Provenance = declared_before`.
- **No match** → `reconstructed_after`, exactly as prompt 7 specifies.

**This is the whole point of both prompts.** Phase 3's calibration table separates rules from
overrides, and it can only do that if declared and reconstructed rationale are distinguishable. Get
this join right or the table measures nothing, convincingly.

---

## Tests

- `test_precommit_declare.py` — declaration writes; band mismatch requires `--force`.
- `test_precommit_rejects_consensus.py` — a level referencing a sell-side target is refused.
- `test_precommit_fire_idempotent.py` — same signal event twice → one firing row.
- `test_precommit_crossing.py` — trim fires at/above, add fires at/below; a reading inside the band
  does not fire.
- `test_precommit_no_auto_response.py` — no code path sets `response` to anything but `pending`
  without an explicit operator action. Assert structurally.
- `test_precommit_downgraded_still_fires.py` — a doctrine-downgraded signal produces a firing with the
  downgrade recorded.
- `test_precommit_declared_before_join.py` — an `acted` firing plus a matching fill yields
  `declared_before`; without the firing, `reconstructed_after`.
- `test_precommit_band_moves.py` — moving the thesis band does not mutate an existing declaration.

---

## Post-build verification checklist

**Literal stdout for every row.**

| # | Check | Expect |
|---|---|---|
| 1 | Declare | `pm journal precommit ... --live` | row written; `thesis_band_at_declaration` populated |
| 2 | Mismatch guard | declare a level differing from the thesis | refused without `--force` |
| 3 | Consensus refused | declare against a sell-side target | refused, reason printed |
| 4 | Fire detection | run morning on a day the band is crossed | firing row, `response='pending'` |
| 5 | Idempotent | re-run the same morning | no second firing row |
| 6 | No auto-response | wait a week without responding | still `pending` |
| 7 | Downgraded fires | a `HOLD_TAX`-downgraded NEAR_TRIM on a pre-committed ticker | firing recorded with the flag |
| 8 | Pass recorded | `--pending`, choose `p` | `passed` with timestamp |
| 9 | `declared_before` join | act, then reconcile the fill | `Trade_Log.Rationale_Provenance = declared_before` |
| 10 | No false `declared_before` | reconcile a fill with no firing | `reconstructed_after` |
| 11 | Band move | edit the thesis band, list precommitments | old declaration unchanged; drift visible |
| 12 | Close | `--close` with a reason | status and reason recorded |
| 13 | No new Sheet tab | Sheets before/after | unchanged tab list |
| 14 | Morning surfaces pending | `pm morning` output | pending count shown |
| 15 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — `core/journal/precommit.py` in Key Files; a Trim/Add Triggers subsection stating
  that thesis frontmatter remains authoritative on bands while `precommitments` records the dated
  declaration and the response; restate that `declared_before` originates **only** here.
- **`vault/doctrine.md`** — **Bill's own file, manual-only. Do not write to it.** If a standing
  pre-commitment pattern emerges that belongs in doctrine, name it in the completion report and let
  Bill write it.
- **`state.md`**, **`CHANGELOG.md`** — dated entries.

## Out of scope — do not build

- The calibration table itself. Phase 3, gated on six months of firings. This prompt builds the
  substrate; **reading it early is how you tune on noise, invisibly.**
- Any automatic response inference, including "no fill within N days therefore passed."
- Editing thesis frontmatter from the CLI. `ThesisManager` owns that path.
- Bootstrapping pre-commitments from existing thesis bands, unless Bill overrides the recommendation
  in Step 2.
- Any notification, alert, or email. The morning output is the surface.
