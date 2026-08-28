# Corpus FTS5 Index — three years of your own writing, searchable with citation

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 2 of 10.** **Depends on:** prompt 1 only for the relocated `SQLITE_DB_PATH` (Step 4 there).
The index itself has no data dependency and **no clock — it is fully backfillable.**
**Gates:** prompt 3 (retrieval layer), and through it prompts 5, 6 and 9.
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 1 (Memory), "Add before handoff".

> Build this second, not first. It is free, local, ships with SQLite, and can be rebuilt from disk at
> any time — which is exactly why it does not get to jump the queue ahead of evidence capture, which
> cannot.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — SQLite has FTS5 compiled in (it is not universal)
python -c "import sqlite3; c=sqlite3.connect(':memory:');\
c.execute('create virtual table t using fts5(body)'); print('FTS5 OK')"

# 0.2 — corpus inventory, actual counts
ls vault/theses/*.md | wc -l
ls vault/theses/archive/*.md 2>/dev/null | wc -l
ls vault/research/ | wc -l
ls vault/frameworks/ | wc -l
ls vault/doctrine.md
ls data/podcast_transcripts/ | wc -l
ls data/podcast_summaries/ | wc -l
ls data/spotify_digests/ | wc -l
ls data/moments/*.moments.json | wc -l
find agent_outputs -name '*.md' | wc -l

# 0.3 — existing alias machinery to REUSE, not reinvent
python -c "import json;d=json.load(open('data/ticker_aliases.json'));print(type(d),len(d))"
grep -n "ISSUER_ALIASES" config.py
grep -n "^def \|^class " utils/moment_windows.py

# 0.4 — one moments file's actual shape, so the extractor is written against reality
python -c "import json,glob;p=sorted(glob.glob('data/moments/*.moments.json'))[0];\
d=json.load(open(p,encoding='utf-8'));print(p);print(json.dumps(d,indent=2)[:1500])"

# 0.5 — one spotify digest's shape and its PROVENANCE stamp
ls data/spotify_digests/ | head -5
head -40 "$(ls data/spotify_digests/*.md 2>/dev/null | head -1)"

# 0.6 — DB path (post-relocation)
python -c "import config; print(config.SQLITE_DB_PATH)"
```

**Expected at 0.2 (verified 2026-08-27, re-verify — these drift daily):** 38 live theses,
236 transcripts, 209 summaries, 17 digests, 236 moments files. **If transcripts and moments no longer
match 1:1, report the gap — do not silently index the shorter list.**

**If 0.1 fails, STOP.** A Python build without FTS5 changes the whole approach and is Bill's decision,
not the executor's.

---

## Design decisions, already made — do not relitigate

**Same `.db` as the evidence tables.** Not a second file. The roadmap is explicit: same database,
same commit discipline. It is already gitignored (`data/portfolio_store.db*`), which is correct — the
index is regenerable from disk, so it is not a permanent-record obligation the way `signal_events` is.

**Plain FTS5, not external-content FTS5.** External-content tables save space by not duplicating the
body text, at the cost of a triggers-and-rebuild dance whenever the content table changes. The corpus
is a few hundred megabytes of text at most and the source of truth is the filesystem, not a content
table. Take the duplication; keep the simplicity.

**Chunk, don't index whole files.** A 90-minute transcript indexed as one row returns "this file
matched" — useless. Chunks return a citable passage, which is the entire point of the phrase
"searchable, with citation."

**`unicode61` tokenizer with `remove_diacritics 2`, plus `porter` stemming.** Ticker symbols must
survive tokenization — verify `$ET`, `ET`, `IBIT/MSTR` and `000660.KS` all remain findable, and adjust
the `tokenchars` argument rather than accepting a tokenizer that shreds them.

**Source registry, not hardcoded paths.** Define sources as a list of declarative entries
(`source_type`, glob, reader, date extractor). Adding earnings transcripts or SEC filings later —
open decision 2 in the roadmap, *not in scope here* — must be a registry entry plus a reader function,
never a change to the indexer's control flow. Build the seam; do not build through it.

---

## Step 1 — Schema

Two tables in `core/store/models.py` plus one virtual table created by raw DDL (SQLAlchemy does not
model FTS5 virtual tables — create it with `text()` DDL guarded by `CREATE VIRTUAL TABLE IF NOT EXISTS`).

### `corpus_docs` — typed, one row per source file

`id`, `source_type`, `path` (repo-relative, **forward slashes, normalized** — this is Windows and a
backslash path will not match a glob written on any other machine), `doc_date` (Date, nullable),
`title`, `tickers` (comma-joined, nullable), `sha256`, `mtime`, `bytes`, `chunk_count`,
`indexed_at`. `UNIQUE(path)`.

`sha256` is what makes re-indexing incremental: unchanged file → skip, changed → delete its chunks and
re-chunk, missing from disk → mark `deleted_at` rather than dropping the row (a transcript deleted
from disk was still real evidence at the time, and prompt 6 may cite a search hit that predates the
deletion).

### `corpus_chunks` — typed, one row per chunk

`id`, `doc_id` (FK), `chunk_ix`, `char_start`, `char_end`, `line_start`, `line_end`, `heading`
(nearest preceding markdown heading, nullable). **`line_start`/`line_end` are not decoration** —
they are what lets a search hit link to a location a human can open and check.

### `corpus_fts` — FTS5 virtual table

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS corpus_fts USING fts5(
  body,
  chunk_id UNINDEXED,
  doc_id UNINDEXED,
  source_type UNINDEXED,
  path UNINDEXED,
  doc_date UNINDEXED,
  tickers UNINDEXED,
  tokenize = "unicode61 remove_diacritics 2"
);
```

Only `body` is indexed; everything else rides along so a hit is self-describing without a join.
Filtering by `source_type` / `doc_date` happens as a `WHERE` on the FTS table, which SQLite handles
fine at this corpus size.

---

## Step 2 — Source registry

New module `core/corpus/sources.py`. Each entry declares `source_type`, a glob, a reader returning
`(title, body_text, doc_date, tickers)`, and whether the source is Bill's own writing (this flag
matters downstream — prompt 6's adversary logic weights Bill's own prose differently from a podcast
digest, and prompt 7 must never propose a rationale sourced from model output alone).

| `source_type` | Glob | Notes |
|---|---|---|
| `thesis` | `vault/theses/*.md` | Bill's writing. Extract frontmatter separately from prose; index the prose, store `tickers` from the filename stem and frontmatter. |
| `thesis_archive` | `vault/theses/archive/*.md` | Bill's writing. Index — an archived thesis is history, and history is the product. |
| `doctrine` | `vault/doctrine.md` | Bill's writing. **Authoritative on standing constraints** — flag it as such. |
| `research` | `vault/research/**/*.md` | mixed |
| `framework` | `vault/frameworks/**/*.md` | mixed |
| `transcript` | `data/podcast_transcripts/*` | third-party. Check the actual extension in Step 0. |
| `podcast_summary` | `data/podcast_summaries/*` | **model output.** Flag it. Every figure is a claim, not a datum (`CLAUDE.md`, Bundle Architecture). |
| `spotify_digest` | `data/spotify_digests/*.md` | third-party aggregate. Preserve the PROVENANCE stamp and VERIFICATION footer as indexed text — **do not strip them, and do not decompose a digest into constituent episodes.** Decomposition once made one digest look like three agreeing sources. |
| `moment` | `data/moments/*.moments.json` | derived. Index the fragment text plus its cue and source-transcript reference. |
| `agent_output` | `agent_outputs/**/*.md` | model output. Flag it. |

**Do not index:** `.venv/`, `__pycache__/`, `*.bak*`, `desktop.ini`, `bundles/`, `exports/`,
`data/fmp_cache/`, `data/schwab_price_cache/`, `data/etf_holdings_cache/`, `archive/`,
`docs/archive/deprecated/`. Every one of those is either machine noise or a deliberately-archived
artifact, and indexing them poisons search results with content Bill has already declined.

**Date extraction** in priority order: frontmatter `date:` / `as_of:` → a `YYYY-MM-DD` or `YYYYMMDD`
in the filename → file mtime, **flagged as inferred** in `corpus_docs` (add an `date_is_inferred`
boolean). Search results filtered by date must not silently rely on an mtime that a file copy changed.

**Ticker tagging:** reuse `data/ticker_aliases.json` and `config.ISSUER_ALIASES` through whatever
function `utils/moment_windows.py` already uses (identify it in Step 0.3). Do not write a second alias
matcher. If the existing one is not importable in isolation, extract it — refactor once, don't fork.

---

## Step 3 — Chunker

New module `core/corpus/chunker.py`.

- Target ~1,200 characters, ~200 character overlap. Tune only if verification shows bad snippets.
- **Split on structure first, length second:** markdown headings, then blank-line paragraphs, then
  hard length. A chunk that straddles two headings is a chunk that produces a confusing citation.
- Carry the nearest preceding heading into `corpus_chunks.heading`. For a thesis file this yields
  "Key Risks" or "Exit Conditions" as the heading on the chunk — **which is precisely the hook prompt
  6's falsification hunting needs.** Get it right here and that prompt becomes much cheaper.
- Track `char_start`/`char_end` and derive `line_start`/`line_end`. Never approximate these.

---

## Step 4 — Indexer

New module `core/corpus/index.py`, and CLI as a new `corpus_app` Typer group (this is a genuinely new
noun, not a variant of `store` — `pm store` is the ledger, `pm corpus` is the text):

```
pm corpus index                 # dry run: per source_type, files new / changed / unchanged / to delete
pm corpus index --live          # do it
pm corpus index --live --rebuild        # drop and rebuild everything; require --yes to proceed
pm corpus index --live --source thesis  # one source_type
pm corpus status                # per source_type: docs, chunks, oldest/newest doc_date, last indexed
```

- Incremental by `sha256`. A full re-index of an unchanged corpus must report **zero** changes and
  write nothing. This is verification row 5.
- `--rebuild` is destructive and therefore needs `--yes` on top of `--live`. Per `CLAUDE.md`, never
  overwrite without an explicit word from Bill.
- Wrap each file's chunk-write in one transaction. A crash mid-corpus must leave the index consistent,
  with that file simply un-indexed and picked up next run.
- Report parse failures at the end as a **list of paths**, never as a swallowed count. A silently
  skipped file is a silently missing search result, six months later, with no way to know.

---

## Step 5 — Search API and CLI

New module `core/corpus/search.py`. **This is the function prompt 3 wraps and prompts 5, 6 and 9
consume — its signature is a contract, not an implementation detail.**

```python
def search(
    query: str, *,
    tickers: list[str] | None = None,
    source_types: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 25,
) -> list[CorpusHit]
```

`CorpusHit`: `chunk_id`, `doc_id`, `source_type`, `path`, `doc_date`, `date_is_inferred`, `heading`,
`line_start`, `line_end`, `snippet` (via FTS5 `snippet()` with `<mark>` delimiters), `score` (negated
`bm25()`, so larger is better — and say so in the docstring, because `bm25()` returns *smaller is
better* and that sign error is the classic way to ship a ranker that returns the worst hits first),
`is_bills_writing`, `is_model_output`.

CLI:

```
pm corpus search "lake charles" --ticker ET --since 2026-01-01 --source-type transcript --limit 10
```

Render each hit as: `[source_type] path:line_start  (doc_date)` then the snippet, indented. A hit
that cannot be opened and checked is not a citation.

---

## Step 6 — Backfill

Run `pm corpus index --live` over the whole corpus once. Expect it to take minutes, not hours.
Report actual wall time, total docs, total chunks, and the resulting `.db` size delta — **prompt 1's
`VACUUM INTO` snapshot now carries this index too**, and if the index turns out to be large enough to
make daily snapshots painful, that is a finding to surface now, not after two weeks of snapshots.

---

## Tests

- `test_corpus_chunker.py` — chunk boundaries respect headings; `line_start`/`line_end` round-trip
  back to the source text exactly.
- `test_corpus_incremental.py` — index, re-index unchanged (zero writes), touch one file, re-index
  (only that file's chunks change).
- `test_corpus_ticker_tokens.py` — `ET`, `$ET`, `000660.KS`, `IBIT/MSTR` are all findable.
- `test_corpus_search_filters.py` — `source_types` and date filters actually narrow results.
- `test_corpus_deleted_doc.py` — a file removed from disk is marked `deleted_at`, not dropped.

---

## Post-build verification checklist

**Literal stdout for every row.**

| # | Check | Expect |
|---|---|---|
| 1 | `pm corpus status` after backfill | per-source counts match Step 0.2's filesystem counts, exactly |
| 2 | Any mismatch in row 1 | explained per source with the specific paths, not written off as rounding |
| 3 | Known-phrase search | `pm corpus search "lake charles"` returns `ET_thesis.md` **and** the conflicting transcript/digest hits |
| 4 | Citation opens | pick one hit, open `path` at `line_start`, confirm the snippet is there verbatim |
| 5 | Re-index is a no-op | `pm corpus index --live` twice; second reports 0 new, 0 changed, 0 writes |
| 6 | Dry run writes nothing | `pm corpus index` then chunk count | unchanged |
| 7 | Rebuild needs `--yes` | `pm corpus index --live --rebuild` without `--yes` | refuses |
| 8 | Ticker filter | `--ticker ET` excludes hits with no ET tag |
| 9 | Date filter honest | a hit with `date_is_inferred` is visibly marked in output |
| 10 | Model-output flag | a `podcast_summary` hit renders flagged as model output |
| 11 | Digest integrity | a `spotify_digest` hit still shows its PROVENANCE stamp; no digest split into episodes |
| 12 | Exclusions honored | `select count(*) from corpus_docs where path like '%archive%' or path like '%.venv%'` → 0 |
| 13 | Parse failures listed | run with one deliberately corrupted file; path is named in output |
| 14 | Index size | `.db` size before/after; snapshot still completes in reasonable time |
| 15 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — `core/corpus/` in Key Files; a short subsection under Bundle Architecture stating
  that `corpus_fts` is a *retrieval* surface and carries the same trust asymmetry as the bundle:
  a `podcast_summary` hit is a claim, a `doctrine` hit is authoritative.
- **`state.md`** — dated entry with the real backfill numbers.
- **`PORTFOLIO_SHEET_SCHEMA.md`** — extend the *Local ledger* paragraph; corpus tables are neither
  Sheet mirrors nor evidence tables, they are a third class.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Any UI. That is prompt 5.
- Any LLM call. This prompt produces hits, not narration.
- Falsification hunting, confirmation-bias counterweight, zero-exposure ranking. That is Phase 5 and
  is not in this build set at all.
- **Earnings transcripts and SEC filings via FMP.** Open decision 2 in the roadmap, undecided, and
  gated on an FMP tier-cost check (`/ratios` and `/sp500-constituent` have already returned 402 at
  the current tier). The registry seam is in scope; the source is not.
