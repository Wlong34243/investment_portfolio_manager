# Retrieval Layer — the seam between "Python gathers" and "LLMs reason"

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 3 of 10.** **Depends on:** prompt 1 (evidence tables), prompt 2 (FTS index).
**Gates:** prompts 4, 5, 6. **Nothing downstream may query SQLite directly once this exists.**
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 4 (The Analyst), architecture paragraph; and the
"worth building the retrieval layer so it serves both the UI and the existing agents" note.

> Built third, ahead of the UI, on purpose. Both Desk pages and the Analyst read through this. If the
> UI ships first it will grow its own ad-hoc queries and this layer arrives as a refactor instead of
> a foundation.

---

## The one architectural rule this file exists to enforce

**The model never authors SQL against the ledger and never fetches.** It names a template id and
supplies parameters. Python executes. This is not a preference — it is `CLAUDE.md` Hard Rule 2 made
mechanical, and the reason is reproducibility: a template-plus-params call is re-runnable and
hash-stampable, so when a number turns out wrong you can tell whether the data changed or the
reasoning did.

Corollary, and this is the part that gets eroded first: **a "template" that takes a WHERE clause as a
parameter is not a template.** Parameters are values. If a future need cannot be expressed as values
against an existing template, the answer is a new template in `queries.py`, reviewed and committed —
never a passthrough.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — prompt 1 landed
python -c "import sqlite3,config;\
[print(r[0]) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute(\
\"select name from sqlite_master where type='table' and name in \
('signal_events','bars_daily','fundamentals_snapshot','corpus_docs','corpus_chunks')\")]"
python manager.py store evidence-status

# 0.2 — prompt 2 landed
python manager.py corpus status
python -c "from core.corpus.search import search; print(search.__doc__)"

# 0.3 — the mirror tables this layer must also read
python -c "import sqlite3,config;\
[print(r[0]) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute(\
\"select name from sqlite_master where type='table' order by name\")]"

# 0.4 — how the blob tables are unpacked today (do not reimplement this)
grep -n "^def " core/store/serialize.py

# 0.5 — the two agents to be rewired in the gated tier
grep -n "open(\|read_text\|glob\|Path(" utils/agents/idea_generator.py | head -30
grep -n "open(\|read_text\|glob\|Path(" utils/agents/valuation_drift.py | head -30

# 0.6 — existing hashing discipline to reuse, not reinvent
grep -n "^def \|sha256\|canonical" core/bundle.py | head -20
grep -n "^def " core/store/ledger_hash.py
```

**Expected at 0.1/0.2:** all five tables present; `evidence-status` prints a GATE line;
`corpus status` prints per-source counts. **If either prompt has not landed, STOP** — this layer
retrieves from tables that must already exist.

### 0.0 — Mirror parity before any template (added 2026-08-27)

Prompt 7 found `trade_log_staging` empty in SQLite while Sheets holds ~149 rows. This layer is
read-only over SQLite; if the mirror is incomplete, a template that returns zero rows because the
mirror is empty looks identical to one that returns zero because there's nothing to find.
`STORE_PRIMARY=sqlite` has been the read path since 2026-08-21.

**Before writing a single template**, paste literal stdout from:

```bash
python manager.py store verify
python manager.py store bundle-parity
```

and a row-count table, SQLite vs Sheets, for every table the twelve templates touch:

| table | sqlite | sheets | notes |
|---|---:|---:|---|
| `trade_log` | | | |
| `trade_log_staging` | | | (not a template target; still count — dual-write canary) |
| `transactions` | | | |
| `realized_gl` | | | |
| `holdings_current` | | | |
| `tax_control_lots` | | | |
| `rotation_review` | | | |
| `decision_view` | | | |

Any non-parity gets **named and explained** before the layer is declared done. Value-level MATCH with
ledger_hash FAIL is still a finding — say so. Do not treat `STORE_PRIMARY=sqlite` as proof the
mirror is complete.

---

## Step 1 — Read-only connection

New package `core/retrieval/`. Module `conn.py`.

Open the ledger through a **read-only URI**: `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.
Not a convention, an enforcement — a bug in a query template physically cannot mutate the ledger.

- Separate from the SQLAlchemy engine in `core/store/models.py`. Do not reuse that engine; it is the
  write path.
- If the DB file is missing, raise a clear error naming `SQLITE_DB_PATH`. Do not create it — a
  read-only path that creates an empty database is how you get a silently empty retrieval layer.
- Set `PRAGMA query_only = ON` as well. Belt and braces; the two mechanisms fail differently.

---

## Step 2 — Whitelisted query templates

Module `core/retrieval/queries.py`. A frozen registry:

```python
@dataclass(frozen=True)
class QueryTemplate:
    id: str
    sql: str                    # named bind params only, e.g. :ticker, :since
    params: dict[str, type]     # name -> expected python type
    returns: list[str]          # declared column names
    description: str            # one line, shown to the model as its menu
```

Initial set — implement exactly these, no more. Anything a downstream prompt needs beyond this list
comes back here as a reviewed addition:

| id | Params | Returns |
|---|---|---|
| `holdings_current` | — | ticker, market value, weight, style, cost basis |
| `position_transactions` | `ticker`, `since?`, `until?` | trade date, action, shares, price, net amount, account |
| `position_lots` | `ticker` | lot open date, shares, cost basis, unrealized, holding days, term |
| `position_realized_gl` | `ticker`, `since?` | close date, shares, proceeds, basis, G/L, term, holding days |
| `signal_events_for_ticker` | `ticker`, `since?`, `until?` | full evidence row |
| `signal_events_for_date` | `event_date` | the whole day's ranked list |
| `bars_for_ticker` | `ticker`, `since`, `until`, `source?` | OHLCV |
| `fundamentals_series` | `ticker`, `since?` | the snapshot series |
| `rotation_review_for_ticker` | `ticker` | attribution rows |
| `trade_log_for_ticker` | `ticker` | Date, Sell/Buy, Implicit_Bet, Rotation_Type |
| `tax_control_lots` | `ticker?` | lot detail + wash-sale state |
| `thesis_state_for_ticker` | `ticker` | frontmatter: style, trigger_type, bands, ceiling |

**Blob-table templates need care.** `trade_log`, `tax_control_lots`, `rotation_review`,
`holdings_current` and `transactions` store `payload_json`, so a template against them selects the
blob and unpacks it in Python via `core/store/serialize.py` (identified in Step 0.4). **Do not write
`json_extract()` into the SQL.** Sheet headers change; a `json_extract('$.Implicit_Bet')` scattered
across templates is a silent-empty-column bug waiting for the next header rename, and the pandas
≥3.0 string-dtype incident in `CLAUDE.md` is the precedent for how that failure presents: not as an
error, as a zero.

Validate at call time: unknown template id → raise. Unknown param name → raise. Missing required
param → raise. Wrong type → raise. **Never coerce silently.**

---

## Step 3 — `RetrievalSet`, hash-stamped

Module `core/retrieval/api.py`. One entry point:

```python
def retrieve(
    *,
    corpus: list[CorpusQuery] | None = None,
    queries: list[TemplateCall] | None = None,
    label: str = "",
) -> RetrievalSet
```

`RetrievalSet` carries: `label`, `created_at`, `corpus_hits` (list of `CorpusHit` from prompt 2),
`tables` (template id → rows), `sources` (deduped list of every path and table the set touched), and
`retrieval_hash` — SHA-256 over canonical JSON of the whole set.

**Reuse the canonical-JSON serializer already in `core/bundle.py`** (Step 0.6). Do not write a second
one; two hashers that disagree on float formatting is a debugging afternoon nobody needs.

The hash is what makes an answer re-checkable: same hash, same evidence, and any disagreement between
two answers is reasoning, not data. That is the identical argument the bundle layer already makes,
applied one level down.

`RetrievalSet.to_prompt_context()` renders the set as text for a model, with every row and every
snippet carrying a stable citation token: `[thesis:vault/theses/ET_thesis.md:L42 2026-07-14]` for
corpus hits, `[table:signal_events_for_ticker#7]` for rows. **Prompt 4 validates model citations
against exactly these tokens**, so the token format is a contract — put it in the docstring and do
not change it casually.

---

## Step 4 — Query log

Module `core/retrieval/log.py`, table `retrieval_log` in `core/store/models.py`:

`id`, `created_at`, `label`, `caller` (`ui` / `cli` / `agent:<name>`), `template_id` (nullable),
`params_json`, `corpus_query` (nullable), `row_count`, `hit_count`, `retrieval_hash`, `elapsed_ms`.

Every retrieval logs. No flag to turn it off. Two reasons: the roadmap requires "every query logged",
and six months from now the log itself answers *which* questions Bill actually asks, which is the
input to knowing which templates to keep.

The log is a write, so it goes through the write engine, not the read-only connection — those are two
different handles to the same file, and that is fine and intended. Note it in the module docstring so
it doesn't read as a bug.

---

## Step 5 — Gated tier: rewire the two existing agents

> **⚠️ Separate commit. Do not fold into Steps 1–4.** This mirrors the tier-8 precedent in
> `prompts/price_history_migration_2026-08-25.md`: build the new path, prove it, *then* move
> consumers onto it, separately, so a regression has one obvious cause.
>
> **Stop after Step 4's verification checklist passes. Present the diff plan for Step 5 and wait.**

`utils/agents/idea_generator.py` and `utils/agents/valuation_drift.py` both read files directly
(Step 0.5). Both get better on an index. Rewire each to call `retrieve()`:

- **5a — `valuation_drift`.** Smaller surface, tighter blast radius, do it first. Its fundamentals
  reads become `fundamentals_series`; its thesis reads become `thesis_state_for_ticker`.
  **Acceptance: output for the same tickers is materially identical to the pre-rewire run.** Diff the
  two `agent_outputs/valuation_drift/` markdown files and paste the diff. A non-empty diff is a
  finding to explain, not a result to accept.
- **5b — `idea_generator`.** Its corpus reads become `corpus` queries. Same acceptance test against
  `agent_outputs/ideas/`.

Neither rewire may change what the agent *says* — only where it got the material. Behavior change and
plumbing change in one commit is how you lose the ability to tell which one broke it.

---

## Tests

- `test_retrieval_readonly.py` — attempting an INSERT through the retrieval connection raises.
- `test_retrieval_template_validation.py` — unknown id, unknown param, missing param, wrong type each
  raise; **and a param containing `; DROP TABLE` is bound as a value, not interpolated.**
- `test_retrieval_hash_stable.py` — same inputs → same `retrieval_hash` across two processes.
- `test_retrieval_hash_sensitive.py` — one changed row → different hash.
- `test_retrieval_citation_tokens.py` — every row and hit in `to_prompt_context()` carries a token
  that round-trips back to its source.
- `test_retrieval_log.py` — a retrieve() call writes exactly one log row with a non-null hash.

---

## Post-build verification checklist (Steps 1–4)

**Literal stdout for every row.**

| # | Check | Expect |
|---|---|---|
| 1 | Read-only enforced | INSERT through retrieval conn | raises; paste the traceback |
| 2 | `query_only` set | `PRAGMA query_only` on that conn | `1` |
| 3 | Every template runs | loop all ids with real params | rows or empty, never an exception |
| 4 | Declared `returns` honest | compare each template's `returns` to actual columns | exact match |
| 5 | Blob unpacking | `trade_log_for_ticker` for a ticker with a known `Implicit_Bet` | value present, not null |
| 6 | No `json_extract` in SQL | `grep -n "json_extract" core/retrieval/` | no matches |
| 7 | Injection bound as value | param `"'; DROP TABLE trade_log; --"` | returns empty, table still exists |
| 8 | Hash reproducible | same retrieve() twice in two processes | identical hash |
| 9 | Hash sensitive | mutate one row, re-retrieve | different hash |
| 10 | Citation tokens resolve | pick 3 at random, open each source | content matches |
| 11 | Log populated | `select count(*), label from retrieval_log group by label` | one row per call |
| 12 | Corpus + tables in one set | a `retrieve()` with both | both present, one hash |
| 13 | Tests | `python -m pytest tests/ -q` |

## Post-build verification checklist (Step 5, separate commit)

| # | Check | Expect |
|---|---|---|
| 14 | valuation-drift parity | diff pre/post `agent_outputs/valuation_drift/` | empty, or every line explained |
| 15 | idea-generator parity | diff pre/post `agent_outputs/ideas/` | empty, or every line explained |
| 16 | No direct file reads left | `grep -n "open(\|read_text" utils/agents/*.py` | only non-corpus reads remain |
| 17 | Agents log | `retrieval_log` shows `caller='agent:...'` rows | present |

---

## Documentation to update on completion

- **`CLAUDE.md`** — `core/retrieval/` in Key Files; a new subsection under Core Architecture
  Principle stating the template-not-SQL rule and the read-only-connection mechanism; add
  **"Do not let any component query the ledger outside `core/retrieval`"** to *What NOT to Do*.
- **`state.md`** — dated entry; note Step 5's tier status separately from Steps 1–4.
- **`CHANGELOG.md`** — two entries if Step 5 lands separately, which it should.

## Out of scope — do not build

- Any LLM call. This layer hands back evidence; prompt 6 narrates over it.
- Any UI route. Prompts 4 and 5.
- Write templates of any kind. This layer is read-only, permanently. Writes stay on the CLI path.
- New templates beyond the twelve listed. Downstream prompts that want more come back here.
