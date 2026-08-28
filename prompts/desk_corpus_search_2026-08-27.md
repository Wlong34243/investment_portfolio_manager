# The Desk II — Corpus Search

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 5 of 10.** **Depends on:** prompts 2, 3, and prompt 4 (shares `base.html` nav and the
read-only posture established there).
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 2 (The Desk), Corpus Search:
*"This is the thing you currently do not have in any form."*

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — dependencies
python manager.py corpus status
python -c "from core.corpus.search import search; h=search('lake charles', limit=3);\
print(len(h)); [print(x.source_type, x.path, x.line_start, x.doc_date) for x in h]"
python -c "from core.retrieval.api import retrieve; print('retrieval OK')"

# 0.2 — prompt 4 landed; nav and posture exist
grep -n "@app.get" ui/app.py
grep -n "position" ui/templates/base.html

# 0.3 — the facet vocabulary, from data not from this file
python -c "import sqlite3,config;\
[print(r) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute(\
'select source_type, count(*) from corpus_docs group by source_type order by 2 desc')]"

# 0.4 — HTMX availability (facets degrade to a plain form GET without it; see Step 3)
grep -rn "htmx" ui/templates/
```

---

## Step 1 — Route

`GET /search` in `ui/app.py`, assembly in `ui/corpus_search.py`.

Query params: `q`, `ticker` (repeatable), `source_type` (repeatable), `since`, `until`, `limit`,
`offset`. All optional; empty `q` renders the form with facet counts and no results — **not an error,
and not the whole corpus.**

Every read through `core/retrieval` with `caller="ui"`, `label="corpus_search"`. The retrieval layer
is the only path to the index; the UI does not import `core.corpus.search` directly. That seems
pedantic given they're both local, and it is the reason the query log is complete.

---

## Step 2 — Results

Each hit renders as:

```
[transcript]  data/podcast_transcripts/2026-07-14_invest-like-the-best.md : L412      2026-07-14
              …the Lake Charles project has been <mark>suspended</mark> pending a capital
              reallocation toward pipelines serving data campuses…
              ET  ·  third-party source
```

Requirements:

- **`source_type`, path, line number and date on every hit.** A hit Bill cannot open and check is not
  a citation, and this page's only reason to exist is citation.
- `<mark>` from FTS5's `snippet()`. Escape the surrounding text; do not escape the marks.
- **Provenance badge on every hit**, driven by the `is_bills_writing` / `is_model_output` flags from
  prompt 2. Three states: *your writing* (thesis, doctrine, archived thesis), *third-party*
  (transcript, digest, research), *model output* (podcast_summary, agent_output). This is not
  decoration — a `podcast_summary` hit is a claim, not a datum (`CLAUDE.md`, Bundle Architecture),
  and the badge is what stops a fabricated capex figure being read as sourced.
- **`doctrine` hits render distinctly and sort to the top** of an otherwise equal-scored set.
  Doctrine is authoritative on standing constraints and outranks inference; the ordering should say so.
- Where `date_is_inferred`, show the date greyed with a title attribute explaining it came from file
  mtime. A date filter that silently relies on an mtime a file copy changed is worse than no filter.
- A `/doc/{doc_id}` reader route: the full document, plain, with the matched chunk anchored and
  highlighted. Read-only, no editing. This is the "open it and check" step made one click instead of
  a file-manager expedition.

---

## Step 3 — Facets

Left rail, counts from the current result set, not the whole corpus:

- **Source type** — from Step 0.3's actual vocabulary, never a hardcoded list.
- **Ticker** — top 15 by hit count in the current results, plus a free-text field.
- **Date** — presets (30d / 90d / 1y / all) plus explicit from/to.

Clicking a facet re-runs the search. With HTMX present, swap the results div; without it, a plain
form GET is entirely acceptable and the page still works with JavaScript off. **Do not add a JS
dependency for facets** — the URL carries the state, which also makes a search bookmarkable, which is
worth more than the swap animation.

---

## Step 4 — Ranking, stated plainly

BM25 from FTS5, descending, with the doctrine lift from Step 2. **Show the score.** Not because Bill
will tune it, but because an unexplained order invites the assumption that the ranking means
something about importance. It means term frequency.

One deliberate omission: **no relevance feedback, no click-through learning, no personalization.**
A search index that reorders itself based on what Bill clicked is a confirmation-bias amplifier
pointed directly at a person whose flagged pattern is reading evidence as confirming an existing
doubt. Phase 5 addresses that bias by surfacing *contrary* evidence; a learning ranker would work in
exactly the opposite direction. Do not build one, and write the reason into the module docstring so
it does not get proposed as an improvement later.

---

## Step 5 — CLI parity

`pm corpus search` already exists from prompt 2. Confirm the UI and CLI return **identical hits in
identical order** for the same query and filters — one code path, two renderers. Verification row 8.

---

## Tests

- `test_ui_search_route.py` — empty `q` renders the form, not an error and not all results.
- `test_ui_search_filters.py` — each facet narrows the set; combined facets AND, not OR.
- `test_ui_search_badges.py` — a `podcast_summary` hit renders the model-output badge.
- `test_ui_search_doc_route.py` — `/doc/{id}` renders and anchors the chunk.
- `test_ui_search_parity.py` — UI results == `core.corpus.search` results for the same args.
- `test_ui_search_escaping.py` — a query containing `<script>` renders escaped; `<mark>` survives.

---

## Post-build verification checklist

**Literal stdout, plus screenshots for the visual rows.**

| # | Check | Expect |
|---|---|---|
| 1 | Page renders | `/search` with no query | form + facet counts |
| 2 | Real query | `/search?q=lake+charles` | ET thesis **and** the conflicting source(s) |
| 3 | Citation opens | click through `/doc/{id}` on a hit | matched text anchored and highlighted |
| 4 | Line numbers true | open the file at `line_start` outside the app | text matches verbatim |
| 5 | Badges correct | a query hitting all three provenance classes | three distinct badges |
| 6 | Doctrine lift | a query matching doctrine and a transcript equally | doctrine first |
| 7 | Inferred dates marked | a source with no frontmatter date | greyed date with tooltip |
| 8 | CLI parity | same query both ways, diff the ordered paths | identical |
| 9 | Facet counts | sum of a facet's counts vs total hits | consistent |
| 10 | XSS | `q=<script>alert(1)</script>` | rendered as text |
| 11 | Works with JS off | disable JS, run a search | works |
| 12 | No write routes | prompt 4's readonly test still passes | passes; `UI_WRITE_ROUTE_ALLOWLIST` still **empty** |
| 13 | Query logged | `select count(*) from retrieval_log where label='corpus_search'` | increments per search |
| 14 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — Key Files row for `ui/corpus_search.py`; one line under Podcast & Third-Party
  Source Ingestion noting that corpus search surfaces digests and summaries with provenance badges,
  and that the badge is the trust signal.
- **`state.md`** — dated entry.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- **Thesis falsification hunting** (pointing search at Key Risks / Exit Conditions continuously).
  Phase 5. The chunk `heading` field from prompt 2 is the hook it will use; leave the hook alone.
- **Confirmation-bias counterweight** (contrary evidence above the fold). Phase 5.
- **Zero-exposure surface.** Phase 5.
- Saved searches, alerts, or any scheduled query. No.
- Any write path. This prompt adds **no** entry to `UI_WRITE_ROUTE_ALLOWLIST` (prompt 4, Step 4.3).
  The allowlist is still empty when this prompt completes; prompt 6 adds the only entry it will ever
  have. If a facet or a reader route seems to want a POST, it wants a GET with query params instead —
  which also makes the search bookmarkable, so take the trade.
