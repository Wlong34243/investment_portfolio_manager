# The Analyst — grounded question answering with checkable citation

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 6 of 10.** **Depends on:** prompts 1, 2, 3. Optionally surfaces in prompt 4/5's UI.
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 4 (The Analyst).

> **Architecture, non-negotiable, quoted from the roadmap:**
> question → Python retrieves (FTS hits + parameterized SQL) → Gemini narrates over the retrieved
> set, citing back to source. The model never authors SQL against the ledger and never fetches.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — retrieval layer, with its citation-token contract
python -c "from core.retrieval.api import retrieve, RetrievalSet; print(RetrievalSet.to_prompt_context.__doc__)"
python -c "from core.retrieval.queries import REGISTRY; [print(t.id, '|', t.description) for t in REGISTRY]"

# 0.2 — the Gemini client, and the preamble that must NOT be duplicated
grep -n "^def \|SAFETY_PREAMBLE" utils/gemini_client.py | head -30
python -c "import utils.gemini_client as g; print(g.SAFETY_PREAMBLE[:600])"

# 0.3 — model config
python -c "import config; print(config.GEMINI_MODEL)"

# 0.4 — existing agent output convention to follow, not reinvent
ls agent_outputs/
sed -n '1,60p' utils/agents/valuation_drift.py

# 0.5 — accrual gate state
python manager.py store evidence-status
```

**Read `SAFETY_PREAMBLE` in full before writing any prompt text.** It is auto-prepended by
`ask_gemini()`. Duplicating it is explicitly listed in `CLAUDE.md` *What NOT to Do*.

---

## Step 1 — Question → retrieval plan (Python, deterministic)

New package `core/analyst/`. Module `plan.py`.

A `QuestionPlan` maps a natural-language question to: a set of `TemplateCall`s, a set of corpus
queries, and a `label`. **This step contains no LLM call.** It is regex/keyword extraction plus a
small rule table:

- **Ticker extraction** — reuse the alias machinery from prompt 2 (`data/ticker_aliases.json`,
  `config.ISSUER_ALIASES`). Do not write a third matcher.
- **Date extraction** — "last quarter", "since July", "in 2025", explicit dates → a range.
- **Intent keywords** → template selection:

| Question shape | Templates |
|---|---|
| position / holding / weight | `holdings_current`, `thesis_state_for_ticker` |
| bought / sold / when did I | `position_transactions`, `trade_log_for_ticker` |
| cost basis / lots / long-term | `position_lots`, `tax_control_lots` |
| realized / gain / tax | `position_realized_gl`, `tax_control_lots` |
| signal / trigger / fired | `signal_events_for_ticker` |
| valuation / multiple / P/E | `fundamentals_series` |
| rotation / swapped | `rotation_review_for_ticker`, `trade_log_for_ticker` |
| said / mentioned / thesis / why | corpus query only |

**Always include a corpus query** alongside table calls when a ticker is present. The differentiating
capability is spanning both, and the roadmap's example — "what management said and what podcast
managers said about them" — is exactly a cross-source question.

**Ambiguity is answered by over-retrieving, not by asking a model to choose.** Retrieval is cheap;
letting an LLM decide what evidence it gets to see is the failure mode this architecture exists to
prevent.

Where the plan resolves to nothing (no ticker, no matched intent), **say so and stop.** Do not fall
back to sending the question to Gemini bare. A model answering from its own weights about Bill's
portfolio is precisely the thing this whole design forbids, and it will sound completely plausible.

---

## Step 2 — Retrieve

`retrieve(queries=..., corpus=..., label=f"analyst:{slug}")`. One `RetrievalSet`, one
`retrieval_hash`. Log it.

**Gate check:** if the plan includes `signal_events_for_ticker` and prompt 1's ten-day accrual gate is
unmet, prepend an explicit caveat to the retrieved set and carry it into the answer. Do not silently
answer from four days of signals as though it were a record.

---

## Step 3 — Narrate

Module `core/analyst/narrate.py`. One `ask_gemini()` call, over `RetrievalSet.to_prompt_context()`.

The instruction block (do **not** restate `SAFETY_PREAMBLE`):

- You are narrating over a fixed evidence set. **Everything you assert must be traceable to a
  citation token in that set.**
- Cite inline with the exact tokens provided: `[thesis:vault/theses/ET_thesis.md:L42 2026-07-14]`,
  `[table:signal_events_for_ticker#7]`.
- **If the evidence does not answer the question, say so and name what is missing.** An honest "the
  retrieved set does not contain X" is the correct answer and is worth more than a fluent one.
- **No price targets. No forecasts. No buy/sell recommendations. No "the market expects."** Facts,
  valuation data, the narrative versus the counter-facts, and how something maps to the four styles.
  Bill decides.
- Where sources conflict, **present the conflict**; do not resolve it silently by preferring one.
- Source trust is not uniform, and the set tells you which is which: `doctrine` is authoritative on
  standing constraints. `thesis` is authoritative on intent and may be stale on figures.
  `podcast_summary` and `agent_output` are **model output — every figure in them is a claim, not a
  datum.** Never let a `podcast_summary` figure override a `table:` figure.
- Where a file and an observed trade disagree, **the default inference is "the file is stale," not
  "the behavior is incoherent."** Report it as a documentation task naming the file and section.
  Do not narrate it as a discipline problem.

---

## Step 4 — Citation validation (Python, after the model)

Module `core/analyst/validate.py`. This is the step that makes the citation mean something.

1. Extract every `[...]` token from the answer.
2. Every token must exist in the `RetrievalSet`. **Any token that does not is a fabricated citation.**
3. On fabrication: do not silently strip it and do not quietly retry. Mark the answer
   `VALIDATION_FAILED`, list the offending tokens, and write both the answer and the failure to
   `agent_outputs/analyst/`. A fabricated citation is a finding about the model, and hiding it means
   the next one is invisible too.
4. Report a coverage figure: paragraphs containing at least one valid citation / total paragraphs.
   Show it in the output header. An uncited paragraph is where unsupported claims live.
5. Scan the answer for forecast language (`price target`, `fair value`, `we expect`, `should reach`,
   `will likely`, `is poised to`, `undervalued at`) and flag hits for review. A crude regex, and it
   will produce false positives — that is the right trade for a Hard Rule 4 backstop.

---

## Step 5 — Surfaces

**CLI (primary):**

```
pm ask "when did I first buy MU and what was the reasoning"
pm ask "what has been said about ET's Lake Charles project" --since 2026-01-01
pm ask "..." --dry-run     # print the retrieval plan and the retrieved set; make no model call
```

`--dry-run` is not a courtesy. It is how Bill checks that the *retrieval* is right before spending a
call on narration, and it is how a wrong answer gets diagnosed as a retrieval problem rather than a
reasoning one.

Output: markdown to `agent_outputs/analyst/YYYY-MM-DD_HHMM_<slug>.md`, following the
`valuation_drift` convention from Step 0.4. Header carries `retrieval_hash`, model, template ids,
citation coverage, validation status. **Non-authoritative** — same class as every other
`agent_outputs/` artifact, and no promotion path to Sheets.

**UI (optional, only if prompts 4–5 have landed):** `GET /ask` renders the form, `POST /ask` runs it.

> **`POST /ask` does not require the mutation amendment, and does not open it.** It writes a markdown
> artifact to `agent_outputs/analyst/` — a sandbox surface already named in `CLAUDE.md` Hard Rule 5.
> That is the existing convention arriving over HTTP instead of over the CLI, not a new mutation
> class. The amendment (roadmap open decision 1) is **deferred to Phase 6a**, where the UI would
> begin authoring Bill's own prose into `Trade_Log`. Nothing here does that.

**Mechanism.** Add exactly one entry to the constant defined in prompt 4, Step 4.3:

```python
UI_WRITE_ROUTE_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({("POST", "/ask")})
```

**Update `test_ui_position_readonly.py`'s expected set in the same commit as the route.** The test
asserts set equality, so adding the route without the constant fails, and adding the constant without
the route fails. That coupling is the point — it forces a deliberate two-line diff rather than a
predicate that silently admits the next endpoint.

Do **not** replace the allowlist with a rule like "POSTs that only write markdown." A predicate
erodes; an allowlist of one does not.

---

## Tests

- `test_analyst_plan.py` — known questions produce the expected template sets; an unmatched question
  produces an empty plan, not a default one.
- `test_analyst_no_bare_llm.py` — an empty plan never reaches `ask_gemini`. Assert with a mock that
  raises if called.
- `test_analyst_validation.py` — an answer with a fabricated token yields `VALIDATION_FAILED` and
  names the token.
- `test_analyst_coverage.py` — coverage is computed correctly on a hand-built answer.
- `test_analyst_forecast_scan.py` — "price target of $140" is flagged.
- `test_analyst_no_sql_from_model.py` — grep the module for any path where model output reaches a
  cursor. There must be none; assert structurally, not by grep alone.

---

## Post-build verification checklist

**Literal stdout for every row. `--dry-run` output pasted in full for rows 1–3.**

| # | Check | Expect |
|---|---|---|
| 1 | Plan is deterministic | `pm ask "..." --dry-run` twice | identical plan and hash |
| 2 | Retrieval spans both | a thesis+numbers question | corpus hits **and** table rows in the set |
| 3 | No model call on dry run | network off, `--dry-run` | succeeds |
| 4 | Real answer | a question Bill would otherwise spend 20 minutes on | correct, cited |
| 5 | **Citations check out** | open every citation in row 4's answer | each resolves to the claimed content |
| 6 | Fabrication caught | inject a fake token into a canned answer | `VALIDATION_FAILED`, token named |
| 7 | Coverage reported | row 4's header | a real percentage |
| 8 | Missing-evidence honesty | ask something the corpus cannot answer | says so, names what is missing |
| 9 | No forecast language | row 4 + the regex scan | clean, or flagged and explained |
| 10 | Conflict presented | ask about ET / Lake Charles | conflict surfaced, not resolved |
| 11 | Trust asymmetry | a question where a digest figure contradicts a table figure | table wins, digest flagged as a claim |
| 12 | Stale-file framing | a question where thesis and trade log disagree | framed as documentation task, not incoherence |
| 13 | Empty plan stops | `pm ask "what's the weather"` | refuses, no model call |
| 14 | Gate caveat | while accrual < 10 days, a signal question | caveat present in the answer |
| 15 | Logged | `select label, retrieval_hash from retrieval_log where label like 'analyst:%'` | one row per non-dry run |
| 16 | Output non-authoritative | check `agent_outputs/analyst/` and Sheets | markdown only; no Sheet write |
| 17 | Preamble not duplicated | `grep -n "SAFETY_PREAMBLE" core/analyst/` | no matches |
| 18 | Tests | `python -m pytest tests/ -q` |

**The real gate, from the roadmap:** it answers a question you'd otherwise have spent twenty minutes
on, correctly, with citations you can check. Rows 4 and 5 are that gate. **Do not mark this prompt
complete on the strength of the other sixteen rows if 4 and 5 are shaky.**

---

## Documentation to update on completion

- **`CLAUDE.md`** — `core/analyst/` in Key Files; a subsection under Core Architecture Principle
  stating the grounded-generation contract and the citation-validation backstop; add
  `agent_outputs/analyst/` to the agent outputs list; extend Hard Rule 5's list of non-authoritative
  surfaces. **State that Hard Rule 5 is transport-agnostic** — a sandbox write is a sandbox write
  whether it arrives via CLI or HTTP — and that this is why `POST /ask` needed no amendment.
- **`state.md`** — dated entry with the row-4 question and whether it passed.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Any write to an authoritative surface. Ever. `agent_outputs/analyst/` is a sandbox surface and has
  no promotion path to Sheets.
- Any second entry in `UI_WRITE_ROUTE_ALLOWLIST`. One route, permanently, until the Phase 6a
  amendment is actually decided.
- Multi-turn conversation, memory across questions, or a chat UI. One question, one evidence set, one
  hash, one artifact. Conversation breaks the hash-to-answer correspondence that makes this checkable.
- Letting the model request additional retrieval mid-answer (tool use / agentic loop). That is the
  model authoring queries with extra steps.
- Web search or fetch of any kind. `CLAUDE.md` Hard Rule 2.
- Adding query templates. Those come from prompt 3, reviewed.
