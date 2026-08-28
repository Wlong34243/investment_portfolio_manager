# The Instrument — Roadmap

**Status:** architecture, not commitment. Phase 1 is specced; everything after is a direction.
**Date:** 2026-08-26
**Amended:** 2026-08-27 — four decisions closed, one dependency corrected. Changes are marked
**[AMENDED 2026-08-27]** in place. **Shipped 2026-08-28:** Phase 3 judgment engine (Units A/B live,
C scaffold). Build prompts live in `prompts/*_2026-08-27.md` and `prompts/surface_delivery_2026-08-28.md`.

> **Why this file is in the repo.** The roadmap governs ten build prompts and every one of them cites
> it. It sits in `docs/architecture/` alongside 01–05 rather than as a root note, per the
> extend-don't-proliferate convention.

---

## What this is trying to become

Not a dashboard. Not an agent showcase. An instrument that does six things no vendor will sell you,
because all six depend on knowing *your* positions, *your* reasoning, and *your* history:

1. **Nothing is forgotten.** Every signal, every price, every fundamental reading, permanently.
2. **Everything is searchable, with citation.** Three years of your own corpus, queryable, sourced.
3. **Every decision is judged — including the ones you didn't make.** Signals ignored are scored
   the same as signals acted on.
4. **The system argues back.** It hunts for evidence against your own theses and puts it in front
   of you.
5. **Pre-commitment is enforced.** You declare the trigger in advance; the system records it firing
   and records what you did.
6. **Tax cost is visible before the trade, not on next April's 1099.**

Six is the one with a measured dollar value. 74% of gross realized gains being short-term is a
holding-period problem, and it persists because the cost is invisible at the moment of decision.

---

## What it will never be

No auto-trading. No price targets, no forecasts, no analyst opinion — excluded by standing rule, and
that exclusion is a feature, not a limitation. No multi-user. No cloud beyond what already exists.
No vendor onboarded before an existing client is extended.

---

## Phase 1 — Memory

*Specced.* **[AMENDED 2026-08-27]** The referenced `prompts/evidence_capture_phase1_2026-08-26.md`
**does not exist in the repo** — verified against the working tree 2026-08-27. The spec is
`prompts/evidence_capture_2026-08-27.md`.

**Delivers:** `signal_events`, `bars_daily`, `fundamentals_snapshot` appending daily. Live `.db`
relocated off the synced tree; `VACUUM INTO` snapshots to Drive with retention. Provenance inventory
naming what Schwab cannot regenerate.

**Add before handoff:** an FTS5 index over the corpus — 236 transcripts, 38 theses, Spotify digests,
doctrine, moment cache, agent outputs. Free, local, ships with SQLite. Backfillable, so no clock on
it, but it belongs in the same `.db` and the same commit discipline.
**[AMENDED 2026-08-27]** Split into its own prompt, `prompts/corpus_fts_index_2026-08-27.md`, because
it has no clock and the evidence half does. Same `.db`, same discipline, second in sequence.

**Gate:** ten trading days of clean accrual before anything reads.

**Why first:** two of the three retrospective questions are computable from data already on disk.
The third bleeds one day of permanent record per day. Nothing else on this page can be built without
this, and this is the only item with a clock.

---

## Phase 2 — The Desk

**Delivers:** `ui/app.py` promoted from debug to product. Served on the Geekom, localhost, read-only.
Sheets stays exactly as-is as the glanceable remote surface — no second remote path is needed.

Two pages carry the phase:

**Position Story.** One ticker, one timeline. Price line with every buy and sell plotted, lot-level
detail beneath, cost-basis curve, holding-period ladder, realized and unrealized, every signal that
ever fired on it, and the thesis state at each point. Scroll it and you see the whole campaign.

**Corpus Search.** Query the FTS index, get dated hits with surrounding context and source file.
Filter by ticker, date, source type. This is the thing you currently do not have in any form.

**Needs:** Phase 1 accrued. Charting is server-rendered or a light JS library; no framework.

> **[AMENDED 2026-08-27] — charting decided: server-rendered inline SVG.**
> The settling argument is not framework avoidance. Phase 2 serves **two render paths from one
> codebase** — `pm ui serve` on localhost and the static mirror from
> `pm store publish-cockpit --live --publish`. A client library needs JS plus a data fetch, and the
> static mirror has no API to fetch from; you would inline the series as JSON and maintain two
> divergent render paths. Inline SVG is identical in both.
>
> **Cost, named and accepted for v1:** Position Story with three years of daily bars has no zoom and
> no hover readout. Reading a specific close means the table beneath, or a reload with narrowed date
> params. Accepted because the alternative is two render paths.
>
> **Hedge:** a `ChartSpec` in `ui/charts.py` and one Jinja partial. Reversing touches two files.

> **[AMENDED 2026-08-27] — the mutation amendment is DEFERRED to Phase 6a. This is a decision.**
> Phase 2 does not need it: nothing here authors Bill's prose into the record. Deciding it now would
> scope the UI wider than Phase 2 requires and leave the extra surface to be defended for six months
> before anything uses it.
>
> `POST /ask` (Phase 4) writes a markdown artifact to `agent_outputs/analyst/` — a sandbox surface
> already covered by `CLAUDE.md` Hard Rule 5. **That is the existing convention arriving over HTTP
> instead of over the CLI, not a new mutation class.** Hard Rule 5 is transport-agnostic.
>
> **Until 6a, the enforcement is a structural test, provisionally standing in for the rule:** an
> explicit `UI_WRITE_ROUTE_ALLOWLIST` of literal `(method, path)` pairs — empty in Phase 2, exactly
> `{("POST", "/ask")}` after Phase 4 — asserted by set equality. **An allowlist, never a predicate.**
> A predicate like "POSTs that only write markdown" erodes: the second endpoint satisfying it slips
> through without anyone deciding. An allowlist of one forces a diff to change.

**Gate:** you reach for it instead of the Sheet, unprompted, for a week.

---

## Phase 3 — Judgment

**Shipped 2026-08-28:** `core/judgment/` + `pm judge` — see `state.md` and `CHANGELOG.md`.

| Unit | Status | CLI |
|---|---|---|
| **A — Rotation quality** | Live | `pm judge rotations` — read-only aggregates over frozen `Rotation_Review`; date spans in header |
| **B — Position lifecycle** | Live | `pm judge lifecycle --ticker X` / `--all` (~2–3 min/ticker; do not pipe stdout) |
| **C — Calibration** | Scaffold | `pm judge calibration` — blank quadrant + accrual counter until firings accrue |

**Delivers:** the retrospective engine, across all three units at once.

- **Rotation quality.** Built. `Residual_Pair_Nd` is selection net of the beta step-up. Backfills
  across the whole trade log.
- **Position lifecycle.** Every entry, add, trim, exit for one ticker as a single campaign.
  Derivable today from `Transactions` + lots + bars. Answers the question nothing currently
  measures: *does small-step scaling actually work for you, or does it just feel disciplined?*
- **Decision quality including passes.** Needs `signal_events` accrued. Every firing gets an outcome
  computed at 30/90/180 days, whether you acted or not.

**The calibration table is the payoff.** Four cells, per signal type:

|  | You acted | You passed |
|---|---|---|
| **Signal was right** | Rule and judgment agree | Judgment cost you |
| **Signal was wrong** | Rule cost you | Judgment saved you |

That table judges your rules *and* your overrides, in both directions. It tells you which triggers to
tighten, which to retire, and — uncomfortably — whether your in-the-moment overrides beat your
pre-committed criteria. Your own standing principle says they don't. This measures it.

~~**Gate:** enough firings to be non-noise. Six months, realistically.~~

> **[AMENDED 2026-08-27] — Phase 3 is gated on calendar for ONE of its three units, not for the
> phase.** The correction is latent in the section above: rotation quality is *"built, backfills
> across the whole trade log"*; position lifecycle is *"derivable today."* Only decision-quality-
> including-passes needs firings to accrue.
>
> **So build the engine now against the two backfillable units and render the calibration table with
> its fourth quadrant visibly empty, carrying a live accrual counter and both gate dates.** A blank
> quadrant with a counter is the design, not a placeholder — it shows the honest state of the
> evidence every time the table is read, and it fills itself.
>
> That converts a six-month passive wait into a working retrospective. The wait was the real risk:
> a phase that sits idle for two quarters is a phase that quietly never ships.
>
> The original caution still holds for the gated unit and is not softened: a retrospective tuned on
> three weeks of firings is tuned on noise, and the tuning is invisible afterward.
>
> Spec: `prompts/judgment_engine_2026-08-27.md`.

---

## Phase 4 — The Analyst

**Delivers:** natural-language question → cited answer, over your corpus and your numbers.

Architecture, non-negotiable: **question → Python retrieves (FTS hits + parameterized SQL) → Gemini
narrates over the retrieved set, citing back to source.** The model never authors SQL against the
ledger and never fetches. Read-only connection, whitelisted query templates, every query logged.

This is the same pattern the expensive platforms use — grounded generation with snippet-level
citation — and it's the pattern your invariants already describe. It costs you nothing
architecturally.

Worth building the retrieval layer so it serves both the UI and the existing agents. Idea Generator
and Valuation Drift both currently read files directly; both get better on an index.

**[AMENDED 2026-08-27]** Split: the retrieval layer is `prompts/retrieval_layer_2026-08-27.md` and
is built **third**, ahead of the Desk, so the UI reads through it rather than growing its own
queries and arriving as a refactor. Narration is `prompts/analyst_grounded_qa_2026-08-27.md`.

**Gate:** it answers a question you'd otherwise have spent twenty minutes on, correctly, with
citations you can check.

---

## Phase 5 — The Adversary

The phase that makes this different from a research tool. Three capabilities, all reads:

**Thesis falsification hunting.** Each thesis file carries Key Risks and Exit Conditions. Point the
corpus search at them continuously and surface hits that argue *against* the position. Concrete case
already open: `ET_thesis.md` claims export terminal networks; reporting conflicts on whether the Lake
Charles project was suspended. That's been sitting unverified. The system should be finding those,
not you.

**Confirmation-bias counterweight.** A flagged pattern of yours: reading numbers as confirming an
existing doubt. So when you open Position Story on a name you're considering trimming, the page
shows the strongest *contrary* evidence in the corpus first, above the fold, before the supporting
material.

**Zero-exposure surface.** Themes appearing repeatedly across the corpus with no expression in the
book, ranked by frequency × recency × conviction. Moment extraction already proves the mechanism
works — v2 surfaced WMT, FND, IBIT/MSTR, FIS/MFC/PAYX, all names you don't hold. The dream version
runs continuously and tells you what you'd have to buy to express the theme.

**Gate:** it surfaces something that changes a position, and you'd have missed it.

*No build prompt yet — deliberately. The chunk `heading` field in the FTS index is the hook
falsification hunting will use; it is built and left alone.*

---

## Phase 6 — The Loop

The first mutations, narrowly scoped.

### 6a — The rationale loop

**The idea, in one line:** the morning shows you yesterday's fills and asks why — but proposes an
answer first, assembled from evidence the system already holds.

Blank-prompt journaling fails. It fails for everyone, and it has already failed here: roughly 16
rows sit in `Trade_Log_Staging` marked `promoted` with no `Implicit_Bet`, because composing a
rationale from nothing is friction and friction wins every time. A proposal you accept or correct is
a different act entirely. One keystroke on the easy ones is what makes a daily ritual survivable.

**The mechanic.** Diff `Trade_Log_Staging` against `Trade_Log`. For each unreconciled cluster, build
a proposal from what fired near the fill date:

> *You trimmed META 8/25. `NEAR_TRIM` fired 8/24 on fwd_pe 19.1 against your declared band of 18.
> Proposed: pre-committed trigger fired. Confirm / edit / reject.*

> *You bought QXO 8/25. No trigger fired. Nearest evidence: dislocation flag 8/22 (drawdown 16%,
> fwd P/E 14); moment from Invest Like The Best 8/19 mentioning Jacobs. Weak match — author your own.*

Proposal quality is a direct function of `signal_events`. Without it the system can only propose from
thesis prose and podcast moments, which is generic. With it, it proposes from **your own
pre-committed criteria**. That is the argument for Phase 1 in one sentence.

**Two poisoning risks, both structural, both cheap to prevent:**

1. **Fabricated rationale.** A proposal stays visibly machine-generated until confirmed, and the
   confirmed record retains *what was proposed* alongside *what you said*. Otherwise the
   retrospective reads invented reasoning as stated reasoning. Precedent exists — the `[INFERRED]`
   tags on JPIE and XOM, and the decision to leave AMZN and ETN blank rather than manufacture
   something plausible.
2. **Hindsight.** Rationale recorded 24 hours after a fill is *stated* rationale, not *actual*. It
   beats the nothing you have now, but it is not pre-commitment. Every row carries a flag:
   `declared_before` or `reconstructed_after`. Phase 3's calibration table is only honest if those
   two can be separated — reconstructed rationale will otherwise make your judgment look better than
   it was, systematically and invisibly.

**It does not need the UI.** This is a morning ritual over local files and can run in a Cowork
session long before Phase 2 exists. Its only hard dependency is `signal_events`.

**It also closes the staging backlog** as a side effect, which has been open since July.

> **[AMENDED 2026-08-27]** This is where the mutation amendment comes due, having been deferred
> through Phase 2. A reconcile *UI* would author `Implicit_Bet` into `Trade_Log` — an authoritative
> surface — which is exactly the class the amendment governs. The CLI ritual needs no amendment and
> is what `prompts/rationale_loop_2026-08-27.md` builds. A browser version is a separate prompt whose
> Step 1 is writing the amendment down.

### 6b — Pre-commitment capture

Declare the trigger before the fact, at the moment of thinking. It fires later; the system records
the firing and records your response. Right now the pre-committed criteria live in thesis
frontmatter and the response lives nowhere. This is the `declared_before` half of 6a, and the thing
that makes the calibration table measure what it claims to.

*Spec: `prompts/precommitment_capture_2026-08-27.md`.*

### 6c — Tax-aware decision surface

When a NEAR_TRIM fires: this lot crosses to long-term in 23 days, trimming now costs $X in the ST/LT
differential, and there is an open wash-sale window on this ticker from a loss sale 12 days ago.
Inputs all exist — lots in SQLite, `Tax_Control`, and `doctrine.md` already does this by hand via
`tax_hold_runners` for UNH and COF. This generalizes it and puts a number on the behavior.

**Constraint discovered 2026-08-26:** the account uses Schwab's Tax Lot Optimizer. Lot relief order
is short-term losses (largest first), long-term losses, short-term flat, long-term flat, long-term
gains (smallest first), short-term gains (smallest first). **This is not FIFO.** Consequences:

- The system must never derive lot relief locally. Schwab's Realized_GL import is the sole
  authority on which lot went. Write this into `CLAUDE.md` as a rule.
- Any pre-trade tax projection must model the optimizer's hierarchy, not FIFO, or it shows the wrong
  lot and the wrong number. Deterministic Python over lots already held — tractable, but real work.
- **It reframes the 74% problem.** The optimizer defers short-term gains to last, so if it has been
  on, lot selection is already optimized and the short-term share is coming from decision-level
  holding period instead. Different diagnosis, different fix. Worth establishing when the method was
  set and whether it applies to all three allowlisted accounts.
- Known override case: when carrying realized short-term losses to offset, you want short-term gains
  realized *before* long-term — the opposite of the optimizer. That is a specified-lot call and
  exactly what this surface should flag rather than leaving to memory.

> **[AMENDED 2026-08-27] — descope the point estimate, not the phase.**
>
> "Never derive lot relief locally" governs **the record of what was sold**: post-trade,
> authoritative, Schwab's. A **pre-trade estimate**, labelled and never written to the ledger, is a
> different object. They coexist; the rule is what stops the estimate being mistaken for the record.
>
> The maintenance objection — you are replicating a proprietary algorithm that will drift — has teeth
> against **one of the four signals here.** Three need no lot prediction at all:
>
> - **Open wash-sale window.** Date arithmetic over `Realized_GL`. Zero optimizer dependency.
> - **Days-to-long-term ladder.** Show every lot's crossing date. You do not need to know which lot
>   Schwab picks to see that three lots cross inside 30 days.
> - **`tax_hold_runners` generalization.** Pure rule application, already implemented by hand.
>
> Only *"trimming now costs $X"* requires the hierarchy. **So produce a bound, not a point estimate:**
> best case if relief starts at the ST-loss end, worst case if it lands on ST gains. A range that is
> directionally right beats a precise number that is quietly wrong, and it **degrades honestly** when
> Schwab changes the algorithm — the true cost stays inside the bound.
>
> That is a fraction of the engineering and most of the behavioral payoff, because **the payoff was
> never precision. It was making the cost visible at all, at the moment of decision.**
>
> Spec: `prompts/tax_lot_optimizer_surface_2026-08-27.md`.

### The rule amendment all of this requires

"CLI owns broker-derived mutations; the UI may author Bill's own commentary." Broker access stays
read-only, forever. Your judgment call, and it should be written into `CLAUDE.md` explicitly rather
than arrived at by drift.
**[AMENDED 2026-08-27]** Deferred to 6a by decision — see Phase 2 above. Not needed before then, and
scoping it early would widen the UI ahead of any use for the width.

---

## Dependency order

**[AMENDED 2026-08-27]** — Phase 3 no longer waits as a whole; retrieval precedes the Desk.

```
Phase 1  Memory ─────────┬──────────────────────────────┐
  (evidence)             │                              │
        │                ▼                              ▼
        │        Phase 1b  FTS index            Phase 6a/6b  Loop
        │        (backfillable, no clock)       (needs signal_events only)
        │                │
        └────────────────┴──► Phase 4a  Retrieval layer
                                        │
                     ┌──────────────────┼──────────────────┐
                     ▼                  ▼                  ▼
              Phase 2  Desk      Phase 4b  Analyst   Phase 3  Judgment
                                                     ├─ A rotation  (backfills, now)
                                                     ├─ B lifecycle (backfills, now)
                                                     └─ C passes    (6mo gate only)
                     └──────────────────┬──────────────────┘
                                        ▼
                                 Phase 5  Adversary
```

Phase 1 gates everything and is the only thing losing value while it isn't built. Phase 3's *third
unit* is gated on calendar; its first two are not, and the engine ships against them. Phases 2 and 4
run in parallel with that wait.

---

## Content gap, decided separately

Earnings call transcripts and SEC filings are the one real content hole. FMP has both, and
`utils/fmp_client.py` already exists — an extension, not a new vendor. Indexing them into the same
FTS table would let one query span what management said and what podcast managers said about them.

Caveat: FMP has already returned 402 on `/ratios` and `/sp500-constituent` at your current tier. Cost
of the tier that carries transcripts needs checking before this is scoped. Not a blocker for
anything above.
**[AMENDED 2026-08-27]** The FTS index is built with a declarative source registry, so adding this
later is a registry entry plus a reader function, not a change to the indexer. Seam built; source not.

---

## Open decisions

1. ~~**The mutation amendment** (Phase 6). Yes or no, and written down either way.~~
   **CLOSED 2026-08-27 — deferred to 6a**, with the route allowlist as the provisional rule. Written
   down as a decision, per the original instruction that it be written down either way.
2. **Filings and earnings transcripts** — in scope or corpus-only. Roughly triples Phase 4. **Open.**
3. ~~**Charting approach** — server-rendered images versus a light client library.~~
   **CLOSED 2026-08-27 — server-rendered inline SVG**, on the two-render-path argument. Zoom and
   hover accepted as the v1 cost.
4. **When Phase 3 starts.** ~~Calendar decision.~~ **PARTLY CLOSED 2026-08-27** — units A and B start
   now; only the pass-quality quadrant is a calendar decision, and six months remains the honest
   answer for it.

---

## The one-line version

Build the memory now because it's the only thing with a clock. Everything else on this page is
waiting patiently on disk.
**[AMENDED 2026-08-27]** — except two-thirds of Phase 3, which was never waiting on anything.
