# The Rationale Loop — the morning proposes; you confirm, correct, or reject

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 7 of 10.** **Hard dependency:** prompt 1 (`signal_events`). **Soft:** prompt 2 (corpus, for
weak-match evidence). **Does not need the UI** — this is a CLI morning ritual and can run long before
prompts 4–5 exist.
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 6a.

> Blank-prompt journaling fails. It has already failed here: roughly 16 rows sit in
> `Trade_Log_Staging` marked `promoted` with no `Implicit_Bet`, because composing a rationale from
> nothing is friction and friction wins. A proposal you accept or correct is a different act.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — signal_events accrued; proposal quality is a direct function of this
python manager.py store evidence-status

# 0.2 — the actual backlog. Confirm the ~16 figure against reality; do not take it from the roadmap.
python -c "
from core.store import get_store
s=get_store(); df=s.get_trade_log_staging() if hasattr(s,'get_trade_log_staging') else None
print('staging accessor present:', df is not None)
"
python -c "import sqlite3,config,json;\
rows=[json.loads(r[0]) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute('select payload_json from trade_log_staging')];\
print('staging rows:', len(rows));\
print('promoted w/ blank Implicit_Bet:', sum(1 for r in rows if str(r.get('Status','')).lower()=='promoted' and not str(r.get('Implicit_Bet','')).strip()));\
print('distinct Status values:', sorted({str(r.get('Status','')) for r in rows}))"

# 0.3 — Trade_Log columns as they actually are
python -c "import sqlite3,config,json;\
rows=[json.loads(r[0]) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute('select payload_json from trade_log limit 1')];\
print(list(rows[0].keys()) if rows else 'EMPTY')"
grep -n -A20 "^### Trade_Log$" PORTFOLIO_SHEET_SCHEMA.md

# 0.4 — the promote path this must not duplicate or bypass
grep -n "def promote\|approved\|Promoted_At" manager.py | head -30

# 0.5 — column guard, so a new column does not trip it
grep -n "^def \|^class " utils/column_guard.py

# 0.6 — the [INFERRED] precedent
grep -rn "INFERRED" vault/theses/*.md scripts/backfill_trade_log_decision_context.py 2>/dev/null | head
```

**Expected at 0.2:** a `promoted`-with-blank-`Implicit_Bet` count near 16, and a `Status` vocabulary
that includes at least `approve`/`approved`/`promoted`. **If the count is materially different,
report the real number** — the roadmap's figure is from 2026-08-26 and this file does not get to
assume it held.

---

## The two poisoning risks — read before writing any code

Both are structural. Both are cheap to prevent *now* and impossible to repair later, because the
damage is invisible in the data it corrupts.

### 1. Fabricated rationale

A proposal stays **visibly machine-generated until confirmed**, and the confirmed record retains
**what was proposed** alongside **what Bill said**. Otherwise the Phase 3 retrospective reads invented
reasoning as stated reasoning, and there is no way afterwards to tell them apart.

Precedent already exists in this repo and should be honoured, not reinvented: the `[INFERRED]` tags
on JPIE and XOM, and the decision to **leave AMZN and ETN blank rather than manufacture something
plausible** (Step 0.6). Blank is a valid outcome. Build for it.

### 2. Hindsight

Rationale recorded 24 hours after a fill is **stated** rationale, not **actual**. It beats the nothing
that exists now, but it is not pre-commitment. Every row carries a flag: `declared_before` or
`reconstructed_after`. Phase 3's calibration table is only honest if those can be separated —
reconstructed rationale will otherwise make judgment look better than it was, **systematically and
invisibly**, which is the worst kind of measurement error because it never announces itself.

---

## Step 1 — Schema

### New typed table `rationale_proposals` (in `core/store/models.py`)

`id`, `cluster_fingerprint` (indexed), `proposed_at`, `proposal_text`, `match_strength`
(`strong` / `weak` / `none`), `evidence_json` (the citation tokens the proposal was built from),
`retrieval_hash`, `status` (`open` / `confirmed` / `edited` / `rejected` / `deferred` / `void_scope`),
`resolved_at`, `resolved_text` (what Bill actually said), `rationale_provenance`
(`declared_before` / `reconstructed_after`). `UNIQUE(cluster_fingerprint, proposed_at)`.

**Status vocabulary (closed set — do not invent a seventh without amending this list):**

| status | Meaning |
|---|---|
| `open` | Proposal awaiting Bill |
| `confirmed` | Accepted as-is → Implicit_Bet written |
| `edited` | Bill rewrote; both proposal and resolved text retained |
| `rejected` | Considered and dismissed (prompt 10 calibration input) |
| `deferred` | Skip until next run |
| `void_scope` | Written in error / outside signed-off population — **not** dismissed. Prompt 10 and any enumerator must treat this as distinct from `rejected`. |

Appended 2026-08-27 after a scope-corrected batch left 16 Trade_Log twins that must not read as "considered and dismissed."

**Append-only on proposal; the resolution updates the row in place.** That is the one permitted
update in the evidence family, and it is permitted because `proposal_text` is never overwritten —
`resolved_text` is a separate column. Verification row 6 proves it.

### `Trade_Log` gains three columns

`Proposed_Bet`, `Rationale_Provenance`, `Rationale_Evidence`.

`Implicit_Bet` keeps its meaning: **Bill's words, always.** It is never written by a machine. If Bill
confirms a proposal unedited, `Implicit_Bet` gets the proposal text *and* `Proposed_Bet` gets the same
text with `Rationale_Provenance = reconstructed_after` — so the record shows a one-keystroke
confirmation, not an independent authorship.

> **⚠️ Sign-off gate.** Adding Sheet columns touches `PORTFOLIO_SHEET_SCHEMA.md`,
> `utils/column_guard.py`, `tasks/format_sheets_dashboard_v2.py` and every reader that positions by
> index. **Present the full list of affected files and the migration plan. Stop. Wait for Bill.**
> Then apply it as its own commit, before any proposal logic.

---

## Step 2 — Reconcile and cluster

New module `core/journal/reconcile.py`.

Diff `Trade_Log_Staging` against `Trade_Log` to find unreconciled clusters: rows with no
`Implicit_Bet`, whatever their `Status`. **Include the `promoted`-with-blank rows** — those are the
existing backlog and they are the reason this exists.

**Reuse `derive_rotations.py`'s clustering. Do not write a second clusterer.** And inherit its known
defect knowingly: it emits nested supersets when re-run against an open window (five rows existed for
the single 2026-08-03 basket). `compute_rotation_attribution.find_superseded_groups()` already reads
around this — **reuse that same logic here** so the widest row wins and the narrower ones are marked,
rather than generating five proposals for one decision. Do not attempt to fix the deriver; that is an
open design decision in `state.md` about stable cluster identity and is not this prompt's scope.

---

## Step 3 — Build proposals

Module `core/journal/propose.py`. For each unreconciled cluster, gather evidence in a window around
the fill date (default ±5 trading days, configurable) **through `core/retrieval` only**:

1. `signal_events_for_ticker` — did a pre-committed trigger fire?
2. `fundamentals_series` — what was the reading?
3. `thesis_state_for_ticker` — what was the declared band?
4. Corpus hits for the ticker in the window — moments, digests, thesis edits.
5. `position_lots` / `tax_control_lots` — was there a tax reason?

### Match strength — the rule that determines everything

| Strength | Condition | Proposal |
|---|---|---|
| `strong` | a `signal_events` row for this ticker, correct side, within the window | **Built from Bill's own pre-committed criteria.** |
| `weak` | no signal; only dislocation flags, moments, or thesis prose | Presented as weak, with the evidence named. |
| `none` | nothing in the window | **No proposal text. Blank, with "author your own."** |

`none` produces **no sentence at all.** Not a hedged one, not a generic one. This is the AMZN/ETN
precedent and it is the single most important line in this file: a plausible-sounding manufactured
rationale is worse than an empty field, because the empty field is honest and the sentence is not.

Rendering, per the roadmap:

```
You trimmed META 8/25. NEAR_TRIM fired 8/24 on fwd_pe 19.1 against your declared band of 18.
Proposed: pre-committed trigger fired.
  [table:signal_events_for_ticker#3]  [thesis:vault/theses/META_thesis.md:L28]
  STRONG match.                                    Confirm / edit / reject
```

```
You bought QXO 8/25. No trigger fired.
Nearest evidence: dislocation flag 8/22 (drawdown 16%, fwd P/E 14); moment from
Invest Like The Best 8/19 mentioning Jacobs.
  [table:signal_events_for_date#12]  [moment:data/moments/2026-08-19_ilptb.moments.json:L4]
  WEAK match — author your own.                    Confirm / edit / reject
```

**Proposal text is templated Python, not an LLM call.** Deterministic, reproducible, and it cannot
hallucinate a reason. The evidence is the argument; prose generation would only add risk. If
narration is ever wanted here, it comes through prompt 6 with citation validation — not from a
free-text model call inside the journal path.

---

## Step 4 — The ritual

**Amended 2026-08-27 (backlog is 112 promoted-blank, not ~16):**

1. **Batch triage first.** Run the proposer over the full backlog; print counts by
   `strong` / `weak` / `none`. Bulk-resolve the entire `none` bucket in one action with
   reason `predates_evidence_capture` (almost all predate `signal_events`). A half-done
   interactive pass is worse than none — you cannot later tell "considered and rejected"
   from "never reached."
2. **Interactive loop second** — only the survivors with real evidence near the fill.

```
pm journal reconcile                 # dry run: the proposal table. Writes nothing.
pm journal reconcile --live          # interactive: per cluster, confirm / edit / reject / defer
pm journal reconcile --live --backlog-only    # batch-triage then interactive on survivors
```

Interactive loop, one cluster at a time:

- **`c` confirm** — `Implicit_Bet` = proposal text, `Proposed_Bet` = same, provenance
  `reconstructed_after`. One keystroke. **This is what makes a daily ritual survivable** — if the
  easy case is not one keystroke, the ritual dies again.
- **`e` edit** — opens `$EDITOR` with the proposal pre-filled. `Implicit_Bet` = Bill's text,
  `Proposed_Bet` = the original proposal, both retained.
- **`r` reject** — proposal discarded, `Implicit_Bet` left blank, status `rejected`. The proposal row
  survives, so a pattern of rejections is measurable and tells you the proposer is miscalibrated.
- **`d` defer** — next run.
- **`q` quit** — everything resolved so far is already written; no all-or-nothing batch.

**Mid-prompt sign-off gate, per `CLAUDE.md` working patterns:** before the first `--live` run against
the backlog, print the full proposal table and stop. Bill accepts, overrides or rejects per row. The
2026-08-08 rotation promotion caught a nested-superset problem at exactly such a gate — and this
prompt is walking straight back into the same clusterer.

> **⚠️ Identity change invalidates sign-off.** If anything that defines cluster identity changes
> after the table is presented — fingerprint canonicalization, Stage_ID handling, Status filter,
> fill-date cutoff, or the collapse/superset rules — the approval does **not** carry. Re-run the
> dry-run, re-present the table, stop again. Observed 2026-08-27: a `63.5` unique-key fix between
> a failed live attempt and the retry changed Trade_Log twin inclusion (5 → 16) and closed 128
> against a signed-off 112. The interactive path will hit the same class of bug if this line is
> missing.

**Provenance is set by the system, never by the operator.** A row resolved through `pm journal
reconcile` is `reconstructed_after` by construction, because it is being written after the fill.
`declared_before` can only be set by prompt 8's pre-commitment path. **Do not add a flag that lets
someone mark a reconstructed rationale as declared** — that flag would destroy the only thing making
the calibration table honest.

---

## Step 5 — Close the backlog

`--backlog-only` against the rows found in Step 0.2. Expect many to come back `none` — they are weeks
old, they predate `signal_events` entirely, and there is nothing to propose from. **That is the
correct outcome.** Leave them blank, mark them `rejected`, and report the count. Do not lower the
match-strength bar to make the backlog look resolved.

---

## Tests

- `test_journal_cluster_supersets.py` — five nested staging rows for one basket produce **one**
  proposal.
- `test_journal_match_strength.py` — a signal in window → `strong`; only a moment → `weak`; nothing
  → `none`.
- `test_journal_none_is_blank.py` — a `none` proposal has empty `proposal_text`. Assert it is empty,
  not merely short.
- `test_journal_retains_proposal.py` — after an `edit`, both `proposal_text` and `resolved_text`
  persist and differ.
- `test_journal_provenance_forced.py` — no code path sets `declared_before` from the reconcile flow.
- `test_journal_dry_run.py` — dry run writes nothing to `Trade_Log`, staging, or the proposals table.
- `test_journal_implicit_bet_never_machine.py` — `Implicit_Bet` is only ever written from a confirmed
  or edited resolution, never from proposal generation.

---

## Post-build verification checklist

**Literal stdout for every row.**

| # | Check | Expect |
|---|---|---|
| 1 | Column migration | `PRAGMA`/header check on `Trade_Log` | three new columns; existing data intact |
| 2 | Column guard passes | `pm store verify` | no column-drift failure |
| 3 | Dry run writes nothing | `pm journal reconcile`, then row counts | unchanged |
| 4 | Superset collapse | the 2026-08-03 basket | one proposal, not five |
| 5 | Strong match | a fill with a known signal | proposal cites the `signal_events` row |
| 6 | Proposal retained | confirm one, then read the row | `Proposed_Bet` and `Implicit_Bet` both present |
| 7 | Edit retained | edit one | `Proposed_Bet` = original, `Implicit_Bet` = Bill's words, both stored |
| 8 | `none` stays blank | a fill with no evidence | no proposal sentence anywhere in output |
| 9 | Provenance forced | every resolved row | `reconstructed_after`; zero `declared_before` |
| 10 | Backlog run | `--backlog-only` | count resolved / left blank, both reported |
| 11 | Quit is safe | resolve two, quit | those two persisted, rest untouched |
| 12 | No LLM in the path | `grep -rn "gemini\|ask_gemini" core/journal/` | no matches |
| 13 | Promote unaffected | `pm journal promote` on an approved row | works exactly as before |
| 14 | Retrieval logged | `retrieval_log` rows labelled `journal:%` | present |
| 15 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — `core/journal/` in Key Files; a subsection stating the two poisoning risks and
  their mechanical prevention; **an explicit line that `Implicit_Bet` is never machine-written.**
- **`PORTFOLIO_SHEET_SCHEMA.md`** — the three new `Trade_Log` columns, with the provenance vocabulary.
- **`state.md`** — dated entry; replace the standing "trim / promote staging as clusters appear"
  item with the real post-backlog state.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Pre-commitment capture. Prompt 8. It is the `declared_before` half and it is genuinely separate.
- Any scoring of whether the rationale was *right*. Phase 3, gated on six months.
- A UI for this. It is a CLI ritual by design.

  > **This prompt is where roadmap open decision 1 — the mutation amendment — finally comes due.**
  > It was deliberately deferred through Phase 2 (see prompt 4, Step 4.3), because nothing before
  > this point authors Bill's prose into the record and deciding early would have scoped the UI
  > wider than Phase 2 needed. A reconcile UI would author `Implicit_Bet` into `Trade_Log` — an
  > authoritative surface — which is exactly the mutation class the amendment governs.
  >
  > **So: build the CLI ritual. Do not build a UI for it, and do not decide the amendment inside
  > this prompt.** If Bill wants the ritual in the browser, that is a separate prompt whose Step 1 is
  > writing the amendment into `CLAUDE.md` ("CLI owns broker-derived mutations; the UI may author
  > Bill's own commentary") and whose Step 2 is adding the route to
  > `UI_WRITE_ROUTE_ALLOWLIST`. Arrived at explicitly, not by drift.
- Fixing `derive_rotations`' nested-superset defect. Open design decision in `state.md`.
- Any LLM call anywhere in this path.
