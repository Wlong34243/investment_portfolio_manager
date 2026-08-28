# The Judgment Engine — build the retrospective now, against what already backfills

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 10 of 10.** **Depends on:** prompt 3 (retrieval). **Unit C additionally depends on**
prompts 1 and 8, and only Unit C waits.
**Buildable in parallel with prompts 2, 4, 5, 6.** The "10" is an identifier, not a queue position.
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 3 (Judgment), **with a correction.**

---

## The correction, which is the reason this prompt exists

The roadmap's dependency diagram marks Phase 3 `(needs 6mo)` and the prose says *"Gate: enough
firings to be non-noise. Six months, realistically."* **That gate applies to one of the three units,
not to the phase.** Read the roadmap's own Phase 3 section back:

| Unit | Roadmap's own words | Actually gated? |
|---|---|---|
| **A — Rotation quality** | *"Built. Backfills across the whole trade log."* | **No.** Runnable today. |
| **B — Position lifecycle** | *"Derivable today from `Transactions` + lots + bars."* | **No.** Runnable today. |
| **C — Decision quality including passes** | *"Needs `signal_events` accrued."* | **Yes.** Six months. |

So: **build the engine now against A and B, render the calibration table with its fourth quadrant
visibly empty, and let it fill itself.** That converts a six-month passive wait into a working
retrospective with one blank cell and a counter — which is a different thing entirely from a project
sitting idle, and idle is how solo projects die.

The engine, the surfaces, the caveat language, the artifact format and the tests are all built once,
now, against A and B. When C's data arrives it drops into a structure that already exists and has
already been read.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — Unit A is genuinely built; confirm rather than trust the roadmap
grep -n "^def \|Residual_Pair\|Beta_Explained\|find_superseded_groups" tasks/compute_rotation_attribution.py | head -30
python -c "from core.retrieval.api import retrieve; from core.retrieval.queries import TemplateCall;\
r=retrieve(queries=[TemplateCall('rotation_review_for_ticker',{'ticker':'MU'})],label='probe');\
print(len(r.tables['rotation_review_for_ticker']))"

# 0.2 — the sample this engine is allowed to describe, and its holes
python -c "import sqlite3,config,json;\
rows=[json.loads(r[0]) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute('select payload_json from trade_log')];\
print('trade_log rows:', len(rows))"
python -c "import sqlite3,config,json;\
rows=[json.loads(r[0]) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute('select payload_json from rotation_review')];\
print('rotation_review rows:', len(rows));\
print('Price_Source values:', sorted({str(r.get('Price_Source','')) for r in rows}))"

# 0.3 — the Gate C freeze, which this engine must not disturb
grep -n "frozen_pre_schwab\|Gate C\|FREEZE" state.md | head

# 0.4 — Unit B's inputs
python -c "from core.retrieval.queries import REGISTRY; [print(t.id) for t in REGISTRY]"

# 0.5 — Unit C's gate
python manager.py store evidence-status
python -c "import sqlite3,config;\
[print(r) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute(\
\"select name from sqlite_master where type='table' and name in ('precommitments','precommitment_firings')\")]"
```

**Expected at 0.2:** ~116 `Trade_Log` rows, of which **69 fail weight reconciliation** — almost all
2025, because those rotations span accounts descoped on 2026-08-03. And `Rotation_Review` carrying
`Price_Source = yfinance|frozen_pre_schwab_2026-08-25`. **Both are load-bearing constraints, not
trivia.** If either has changed, stop and report — the aggregate's meaning changed with it.

---

## The standing constraint on everything this prompt produces

`CLAUDE.md` **Analysis Rule 9**, in full force:

> The aggregate describes a **documented subset**, not Bill's investing. Excluded rows are
> non-random — they skew old and wide — so medians describe well-reconciled rotations only. The
> sample is one regime with heavily overlapping windows, so **effective N is far below nominal N.**
> Do not build a recommendation on it.

Three build consequences, none optional:

1. **Every aggregate renders with its N, its excluded-N, and the exclusion reason inline.** Not a
   footnote, not an appendix — on the same line as the number. A median with a hidden denominator is
   how a 47-row subset becomes "your rotations return X."
2. **No recommendation, ever.** Not "tighten this trigger," not "scale in less." The engine reports
   what happened. `CLAUDE.md` Hard Rule 4 and Analysis Rule 6: deliver the finding, name the file to
   update, stop.
3. **No moralizing about process.** A finding that small-step scaling underperformed a single entry
   is a measurement, not a verdict on discipline, and it must not be narrated as one. Bill is the
   authoritative source on Bill's decisions.

---

## Step 1 — Unit A: rotation quality (wrap, do not rebuild)

`tasks/compute_rotation_attribution.py` already computes basket-aware attribution with beta
decomposition into `Beta_Explained` and `Residual_Pair`, at 30/90/180 trading days. **Do not touch
it.** `Rotation_Review` is under a deliberate freeze (`Price_Source=...frozen_pre_schwab_2026-08-25`,
Bill 2026-08-25) and recomputation is not this prompt's business.

Build a **read-only aggregator** over what is already there:

- `Residual_Pair_Nd` distribution at each horizon — median, quartiles, N, excluded-N.
- Split by `Rotation_Type` (`upgrade` / `rebalance` / `tax_loss`), each with its own N.
- Split by whether the basket had a documented `Implicit_Bet` at the time — which, once prompt 7 has
  run, also splits by `Rationale_Provenance`.
- **Superseded rows excluded and counted separately.** `find_superseded_groups()` already marks them
  (`SUPERSEDED_BY`); reuse it, do not re-derive.

Where N at a horizon drops below a `config` floor (suggest 12), **render the cell as `N too small`
rather than a number.** A median of four overlapping observations is not a median.

---

## Step 2 — Unit B: position lifecycle (the one nothing currently measures)

New module `core/judgment/lifecycle.py`. For one ticker, assemble every entry, add, trim and exit as
a **single campaign** from `position_transactions` + lots + `bars_for_ticker` — all via
`core/retrieval`, no direct reads.

The roadmap's question, stated exactly: *does small-step scaling actually work for you, or does it
just feel disciplined?*

Per campaign, compute:

- Sequence and timing of each leg; dollar-weighted average entry and exit.
- **Realized + unrealized against two counterfactuals:**
  - **Single entry** — the full eventual position bought at the first buy's price and date.
  - **Benchmark** — the same dollars into SPY / VTI on the same dates (the benchmarks Unit A
    already uses; reuse them, do not introduce a third).
- Time-weighted vs dollar-weighted return, shown separately. They answer different questions and
  conflating them is the standard way this analysis goes wrong.
- Whether adds were made into strength or into weakness, by price relative to the running average.

**The counterfactual is a measurement, not a recommendation.** Render it as *"the same dollars
deployed at first-buy price would have returned X"* — never as *"you should have."* And where the
campaign is still open, say so and mark the unrealized portion; a closed-campaign comparison and an
open one are not the same evidence.

**Small-step scaling is Bill's stated method, not a hypothesis on trial.** If the aggregate says it
underperformed single entry, that is a finding to report plainly with its N — and it is also one
regime, so say that too.

---

## Step 3 — Unit C: scaffold now, data later

Build the structure. Do **not** fake the data, and do not lower the bar to populate it.

For each `signal_events` firing, an outcome computed at 30/90/180 days — **whether Bill acted or
not.** The response comes from prompt 8's `precommitment_firings` (`acted` / `passed` / `pending`);
where no pre-commitment exists, the firing has no response and is excluded from the table rather than
assumed.

`evidence_status()` gates it. While unmet:

- The unit runs and reports `GATE NOT MET — n of 10 trading days accrued; earliest meaningful read
  <date>` for the data-hygiene gate, and separately the six-month non-noise gate with its own date.
- **It never emits a partial calibration table.** Two gates, both named, both with dates.

---

## Step 4 — The calibration table, with a visibly empty quadrant

|  | You acted | You passed |
|---|---|---|
| **Signal was right** | Rule and judgment agree | *Judgment cost you* |
| **Signal was wrong** | *Rule cost you* | Judgment saved you |

Render it now, per signal type, with the two "passed" cells showing:

```
        PENDING — requires pre-commitment firings.
        0 responses recorded. Accrual began <date>. Non-noise gate: <date>.
```

**A visible blank with a counter is the design, not a placeholder.** It shows what the retrospective
will be, shows the honest state of the evidence, and makes the accrual legible every time Bill reads
it — which is worth more than hiding the column until it fills.

**One honesty constraint that must be built in from the start:** the table is only meaningful if
`declared_before` and `reconstructed_after` rationale can be separated (prompt 7's second poisoning
risk). Until prompt 8 has firings, **every row is `reconstructed_after` by construction** and the
table must say so at the top. Reconstructed rationale otherwise makes judgment look better than it
was, systematically and invisibly.

---

## Step 5 — Surfaces

```
pm judge rotations                       # Unit A aggregates, N and excluded-N inline
pm judge lifecycle --ticker MU           # one campaign
pm judge lifecycle --all                 # every ticker, summary table
pm judge calibration                     # the table, blank quadrant and all
```

Markdown to `agent_outputs/judgment/`, following the `valuation_drift` convention. Header carries
`retrieval_hash`, N, excluded-N, the freeze stamp, and both gate states.
**Non-authoritative** — no Sheets write, no promotion path.

**No LLM anywhere in this prompt.** These are deterministic computations over the ledger. If
narration is ever wanted, it comes through prompt 6 with citation validation.

If prompt 4 has landed, surface the campaign summary on Position Story. Read-only; no new entry in
`UI_WRITE_ROUTE_ALLOWLIST`.

---

## Tests

- `test_judge_n_disclosure.py` — every rendered aggregate carries N and excluded-N. Assert over the
  output text, so a new metric cannot ship without its denominator.
- `test_judge_small_n_suppressed.py` — below the floor, `N too small` instead of a number.
- `test_judge_superseded_excluded.py` — superseded rows are excluded and counted separately.
- `test_judge_lifecycle_counterfactual.py` — single-entry and benchmark counterfactuals on a
  hand-built campaign match a worked example.
- `test_judge_lifecycle_open_campaign.py` — an open campaign is marked, and its unrealized portion
  reported separately.
- `test_judge_calibration_blank.py` — the passed column renders PENDING with a real counter, and the
  table is never emitted partially populated.
- `test_judge_provenance_banner.py` — with zero firings, the table states that every row is
  `reconstructed_after`.
- `test_judge_no_recommendation.py` — the output contains no imperative recommendation language
  (`should`, `consider trimming`, `tighten`, `retire this trigger`). Crude, and the right backstop.
- `test_judge_no_llm.py` — structural: `core/judgment/` does not import the Gemini client.
- `test_judge_does_not_write_rotation_review.py` — structural; the freeze is not disturbed.

---

## Post-build verification checklist

**Literal stdout for every row.**

| # | Check | Expect |
|---|---|---|
| 1 | Unit A runs | `pm judge rotations` | aggregates render |
| 2 | N disclosed | row 1's output | every number carries N and excluded-N inline |
| 3 | Excluded count matches | excluded-N vs the 69 known reconciliation failures | reconciles, or the delta is explained |
| 4 | Freeze intact | `Price_Source` values before/after | unchanged; `Rotation_Review` not rewritten |
| 5 | Small N suppressed | a horizon with few rows | `N too small` |
| 6 | Unit B runs | `pm judge lifecycle --ticker MU` | full campaign |
| 7 | Counterfactual worked | hand-check one campaign against a spreadsheet | matches; paste both |
| 8 | TWR vs DWR separate | row 6's output | both present, labelled, not conflated |
| 9 | Open campaign marked | a ticker still held | marked; unrealized separated |
| 10 | Unit C gated | `pm judge calibration` | GATE NOT MET with **both** gate dates |
| 11 | Blank quadrant visible | row 10's output | PENDING cells with a real counter |
| 12 | Provenance banner | row 10's output | states all rows are `reconstructed_after` |
| 13 | No partial table | force a few firings, re-run | still refuses until the gate clears |
| 14 | No recommendations | `test_judge_no_recommendation` + read the output | clean |
| 15 | No moralizing | read Unit B's output on a campaign that underperformed | measurement framing only |
| 16 | No LLM | `grep -rn "gemini" core/judgment/` | no matches |
| 17 | Non-authoritative | check Sheets before/after | unchanged |
| 18 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — `core/judgment/` in Key Files; extend **Analysis Rule 9** to state that the same
  caveat governs Unit B's lifecycle aggregates, not only rotation attribution; `agent_outputs/judgment/`
  added to the outputs list.
- **`state.md`** — dated entry recording that **Phase 3 was not wholly calendar-gated**: A and B
  shipped now, C scaffolded with a live counter and its two gate dates. This is the entry that stops
  a future session re-reading the roadmap's diagram and concluding the whole phase is still waiting.
- **`docs/architecture/06_the_instrument_roadmap.md`** — the corrected dependency diagram.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Recomputing or refreshing `Rotation_Review`. It is frozen by decision.
- Fixing `derive_rotations`' nested-superset defect. Open design decision in `state.md`.
- Recovering pre-2026 rotation history. `CLAUDE.md` Open Questions: the path is a parallel historical
  fetch, **never** a re-sync of the live `Transactions` tab.
- Any recommendation, trigger tuning, or "which triggers to retire" output. The roadmap names that as
  the eventual payoff of the *full* table — which requires the quadrant that is still empty.
- Populating Unit C from anything other than real firings.
- Any LLM call.
