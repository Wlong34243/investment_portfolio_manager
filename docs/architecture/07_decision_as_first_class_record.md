# 07 — The Decision as a First-Class Record

**Status:** proposed, 2026-09-01. Nothing in this document is built yet.
**Supersedes nothing.** Extends 04 (rotation as unit of analysis) one level up:
the rotation is the unit of *action*; the decision is the unit of *reasoning*.

---

## The diagnosis

Every store in this system holds the **conclusion** of a thought and discards the
thought. A trigger is a threshold — the residue of reasoning about when something
matters. `styles.json` is a taxonomy — the residue of reasoning about how Bill
invests. `vault/doctrine.md` is a constraint set — the residue of reasoning about his
circumstances. Thesis files are largely current-state snapshots.

Three stores of state. None of reasoning.

The reasoning is not missing. It is written down, faithfully, in the only places the
schema left available — YAML comments, Review Log prose, HTML comments, free-text
`Implicit_Bet`. Those are exactly the places nothing parses. The machine-readable
layer captured every number and not one reason.

### Evidence base (all verified 2026-09-01)

| # | Case | What was written | What the system could hold |
|---|---|---|---|
| 1 | **GLD** | A paragraph of conditional reasoning: *"size-and-role, not the 400 print… 400 is an evaluate-if-momentum flag… does not override"* | one enum, `trim_trigger_role: informational` |
| 2 | **XOM** | `# harvest if multiple + oil both rich` — a **conjunction** | two independent scalars; only one evaluated. "oil rich" has no field at all |
| 3 | **AMZN** | `ceiling_only` set for a *data-quality* reason with "revisit with rolling-TTM data" attached | identical to `ceiling_only` set because a position is core. Same behaviour, different rule, indistinguishable until they diverge |
| 4 | **GOOG** | `price_trim_above: 450.00 # raised from $395 — thesis intact` | the new scalar. The decision to raise rather than trim was never an event |
| 5 | **Review Log parser** | Bill's reasons, in prose | parsed as his transactions — `_review_log_dates` bled into `region:transaction_log` in 39/41 files |

### The shape of the loss

Bill's reasoning has five recurring shapes. The schema degrades every one to a scalar:

| how the thought is formed | what the schema forces |
|---|---|
| conditional — "if A **and** B", "unless" | one threshold |
| substitutional — sell-to-buy, the rotation | two unlinked rows |
| regime-scoped — "peak-AI-mania", "evaluate-if-momentum" | a number with no regime |
| precedence — "size-and-role **wins over** the 400 print" | nothing; prose only |
| revisable — "raised from 395", "lowered from 20" | overwrite, no event |

### Second-order consequence: detectors that cannot fire

A system that stores conclusions without events cannot audit itself. Two dead
detectors found on the same day, same species:

- **`MATERIAL_RESIZE_NO_REVIEW`** — unreachable in both branches, because
  `_review_log_dates` returned the transaction dates it was comparing against.
- **`lint_theses` check 5 (stale review > 90 days)** — can never fire, because the
  morning sync stamps `last_reviewed` on all 41 theses daily. Measured 2026-09-01:
  41/41 read `'2026-09-01'`.

`last_reviewed` is misnamed. It records **last synced**, not last reviewed, and
therefore certifies a review that never happened.

---

## The primitive

A **decision**: dated, attributable, carrying its own conditions, scope, precedence,
and falsifier.

Not the trade — that is the effect. Not the thesis — that is current state. Not the
trigger — that is a threshold. GLD 2026-08-14 was a decision. XOM 2026-08-09 was a
decision. GOOG 395→450 was a decision. All three exist today as prose fragments in
three different formats, none linked to the trigger it produced.

### Schema

```yaml
id: 2026-08-14_GLD_size_and_role      # date_ticker_slug, stable, never reused
decided_on: 2026-08-14                # when Bill decided, NOT when recorded
scope: position                        # position | portfolio
tickers: [GLD]
assertion: >                           # Bill's words, verbatim where extracted
  Size-and-role governs, not the 400 print. I will not trim on gold price
  moving up alone; the hedge value comes from holding through equity stress.
conditions:                            # machine-evaluable legs
  operator: all                        # all | any   <- the conjunction gap
  legs:
    - metric: price
      comparator: gte
      value: 400
unencodable_conditions:                # named, not silently dropped
  - "oil rich"                         # no field exists for this
overrides: [price_trim_above]          # precedence, explicit
falsifier: >                           # what would change his mind
  Exit condition 4 — extreme real rates.
supersedes: null
provenance: extracted                  # extracted | authored_at_desk
source_ref: vault/theses/GLD_thesis.md#L71
status: proposed                       # proposed | ratified | rejected | superseded
ratified_on: null
```

**`unencodable_conditions` is load-bearing.** Naming the leg the system cannot
evaluate is worth more than pretending the rule is fully captured. XOM's signal is
honest only when the record says out loud that "oil rich" is unmeasured.

---

## Two surfaces, one loop

Neither surface works alone, and they fail in opposite directions.

|  | **Cowork scheduled task** | **Desk cockpit** |
|---|---|---|
| Sees | the whole bundle + language | the live signal |
| Can | read prose and *propose* structure; notice a rule with no machine-readable home | ratify against consequence, deterministically |
| Cannot | be trusted to write anything binding | notice that a rule is **missing** |
| Role | **proposes** | **ratifies** |

> **The model drafts. Bill ratifies. The model never writes a binding record.**

This is not a new rule. It is "all AI output is sandboxed" and "every write needs an
explicit `--live` flag" applied to reasoning instead of to numbers. A decision
proposal is the highest-stakes model output in the system, so it gets the strictest
gate, not the loosest.

### Two card types

- **Assertion card** — *"This is what we're saying as of today. Correct?"* A
  restatement. Catches drift **before** it produces a bad signal. Build this first:
  GLD would have surfaced in August as *"we're saying 400 is a binding trim on a 1.15%
  hedge you're building toward 3–5% — correct?"* three weeks before it reached #1.
- **Why-card** — *"Why did you do this?"* A reconstruction, after the fact. Already
  specified in `prompts/why_cards_decision_capture_2026-09-01.md`. Strictly lower
  evidence grade; provenance `reconstructed_after`.

### Inbound path — reuse, do not invent

`tasks/ingest_ai_dispatch.py` is already the sanctioned channel from an AI surface into
this repo: file drop → sha256 dedup ledger → dry-run default → `--live` gate →
quarantine into `data/ai_briefs/`, never `vault/`. Its header already argues the right
anxiety — that routing content through the wrong path *fabricates* structure.

A decision proposal is a third dispatch kind alongside the Spotify digest and the AI
dispatch, and inherits all of it.

```
Cowork task  ->  decision-proposals-YYYY-MM-DD.json   (drop file)
             ->  ingest_decision_proposals.py --live
             ->  data/decision_proposals/             (QUARANTINE — model may write)
             ->  desk assertion card                  (Bill ratifies)
             ->  vault/decisions/                     (BINDING — ratification only)
```

`vault/decisions/` is written by exactly one code path: desk ratification. No
pipeline, no agent, no sync ever writes it.

---

## `last_ratified`

Ratification needs somewhere honest to land. Add `last_ratified` to thesis
frontmatter, written **only** by a ratification event, and point `lint_theses` check 5
at it. Leave `last_reviewed` to the sync — it means "last synced" and renaming it
across 41 files is not in scope. Document the misnomer; do not perpetuate it.

This is the first metric in the system that will mean what its name says.

---

## Sequence

1. **Record + quarantine store.** Schema, validator, `vault/decisions/` writer.
   Nothing derives from it yet. Fully reversible.
2. **Extractor.** Cowork task drafts candidates from prose already written. Starts
   full, not empty — ~41 theses of real reasoning to work from.
3. **Assertion card.** Cockpit, signal-implicated rows only. A periodic sweep of all
   41 invites queue fatigue; the failure mode of a capture surface is abandonment.
4. **Derivation.** Triggers generated *from* decisions rather than authored beside
   them. **Last, and out of scope until 1–3 have run for a month** — it is the only
   irreversible step, and it makes drift between rule and trigger structurally
   impossible by removing the second copy.

## Non-goals

- No LLM writes to `vault/`, `Trade_Log`, `Target_Allocation`, or doctrine.
- No decision record confers a trade recommendation. It records a rule, not a call.
- Not a replacement for precommit. Precommit remains the only source of
  `declared_before`; extraction and ratification are lower grades and stay labelled.
- Not a new markdown file at repo root.
