"""
Corpus search API — contract for prompt 3 retrieval and prompts 5/6/9.

Ranking is BM25 from FTS5, descending, with an explicit doctrine-first lift.
There is no relevance feedback, click-through learning, or personalization:
a search index that reorders itself from what Bill clicked would amplify
confirmation bias — the opposite of Phase 5's contrary-evidence goal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Literal, Optional

from markupsafe import Markup
from sqlalchemy import text

from core.store.models import get_engine, get_session

_MARK_OPEN = "<mark>"
_MARK_CLOSE = "</mark>"
_MARK_SPLIT = re.compile(r"(<mark>|</mark>)")


@dataclass
class CorpusHit:
    chunk_id: int
    doc_id: int
    source_type: str
    path: str
    doc_date: Optional[date]
    date_is_inferred: bool
    heading: Optional[str]
    line_start: int
    line_end: int
    snippet: str
    score: float  # negated bm25 — larger is better
    is_bills_writing: bool
    is_model_output: bool
    tickers: Optional[str] = None


def _prepare_fts_query(query: str) -> str:
    """Strip FTS5 metacharacters; word-tokenize or return empty."""
    q = (query or "").strip()
    if not q:
        return ""
    tokens = re.findall(r"[\w-]+", q, flags=re.UNICODE)
    if tokens:
        return " ".join(tokens)
    return ""


def search(
    query: str,
    *,
    tickers: list[str] | None = None,
    source_types: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 25,
    offset: int = 0,
) -> list[CorpusHit]:
    """
    FTS5 search over corpus_fts joined to chunk/doc metadata.

    score is -bm25(corpus_fts): SQLite's bm25() is smaller-is-better; we negate
    so callers can sort descending and treat larger as better.
    """
    if not (query or "").strip():
        return []
    fts_q = _prepare_fts_query(query)
    if not fts_q:
        return []
    get_engine()
    clauses = ["corpus_fts MATCH :q"]
    params: dict = {"q": fts_q, "limit": int(limit), "offset": int(offset)}

    if source_types:
        placeholders = []
        for i, st in enumerate(source_types):
            key = f"st{i}"
            placeholders.append(f":{key}")
            params[key] = st
        clauses.append(f"corpus_fts.source_type IN ({', '.join(placeholders)})")

    if since:
        clauses.append("(corpus_fts.doc_date = '' OR corpus_fts.doc_date >= :since)")
        params["since"] = since.isoformat()
    if until:
        clauses.append("(corpus_fts.doc_date = '' OR corpus_fts.doc_date <= :until)")
        params["until"] = until.isoformat()

    ticker_clause = ""
    if tickers:
        # Filter on comma-joined tickers column (contains)
        parts = []
        for i, t in enumerate(tickers):
            key = f"tk{i}"
            parts.append(f"instr(',' || upper(corpus_fts.tickers) || ',', ',' || :{key} || ',') > 0")
            params[key] = t.upper()
        ticker_clause = " AND (" + " OR ".join(parts) + ")"

    where = " AND ".join(clauses) + ticker_clause
    sql = f"""
    SELECT
      corpus_fts.chunk_id,
      corpus_fts.doc_id,
      corpus_fts.source_type,
      corpus_fts.path,
      corpus_fts.doc_date,
      snippet(corpus_fts, 0, '<mark>', '</mark>', '…', 32) AS snip,
      bm25(corpus_fts) AS raw_bm25,
      c.line_start,
      c.line_end,
      c.heading,
      d.date_is_inferred,
      d.is_bills_writing,
      d.is_model_output,
      d.tickers,
      d.deleted_at
    FROM corpus_fts
    JOIN corpus_chunks c ON c.id = CAST(corpus_fts.chunk_id AS INTEGER)
    JOIN corpus_docs d ON d.id = CAST(corpus_fts.doc_id AS INTEGER)
    WHERE {where}
      AND d.deleted_at IS NULL
    ORDER BY bm25(corpus_fts)
    LIMIT :limit OFFSET :offset
    """

    hits: list[CorpusHit] = []
    with get_session() as session:
        rows = session.execute(text(sql), params).mappings().all()
        for r in rows:
            dd = r["doc_date"] or None
            parsed: Optional[date] = None
            if dd:
                try:
                    parsed = date.fromisoformat(str(dd)[:10])
                except ValueError:
                    parsed = None
            hits.append(
                CorpusHit(
                    chunk_id=int(r["chunk_id"]),
                    doc_id=int(r["doc_id"]),
                    source_type=r["source_type"],
                    path=r["path"],
                    doc_date=parsed,
                    date_is_inferred=bool(r["date_is_inferred"]),
                    heading=r["heading"],
                    line_start=int(r["line_start"] or 1),
                    line_end=int(r["line_end"] or 1),
                    snippet=r["snip"] or "",
                    score=-float(r["raw_bm25"] or 0.0),
                    is_bills_writing=bool(r["is_bills_writing"]),
                    is_model_output=bool(r["is_model_output"]),
                    tickers=r["tickers"],
                )
            )
    return hits


def apply_doctrine_lift(hits: list[CorpusHit]) -> list[CorpusHit]:
    """Doctrine sorts above equal-scored non-doctrine hits; BM25 order preserved within groups."""
    return sorted(
        hits,
        key=lambda h: (0 if h.source_type == "doctrine" else 1, -h.score, h.path, h.line_start),
    )


def search_ranked(
    query: str,
    *,
    tickers: list[str] | None = None,
    source_types: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 25,
    offset: int = 0,
    fetch_cap: int = 500,
) -> list[CorpusHit]:
    """
    Ranked corpus search — single code path for CLI and UI.

    Fetches up to fetch_cap BM25 hits, applies doctrine lift, then paginates.
    """
    if not (query or "").strip():
        return []
    cap = min(fetch_cap, max(limit + offset, limit))
    raw = search(
        query,
        tickers=tickers,
        source_types=source_types,
        since=since,
        until=until,
        limit=cap,
        offset=0,
    )
    ranked = apply_doctrine_lift(raw)
    return ranked[offset : offset + limit]


def provenance_badge(hit: CorpusHit) -> Literal["your_writing", "model_output", "third_party"]:
    if hit.is_model_output or hit.source_type in ("podcast_summary", "agent_output", "ai_brief"):
        return "model_output"
    if hit.is_bills_writing or hit.source_type in (
        "thesis",
        "thesis_archive",
        "doctrine",
    ):
        return "your_writing"
    return "third_party"


def snippet_html(snippet: str) -> Markup:
    """Escape snippet text; preserve FTS <mark> highlight tags."""
    if not snippet:
        return Markup("")
    parts = _MARK_SPLIT.split(snippet)
    out: list[str] = []
    in_mark = False
    for part in parts:
        if part == _MARK_OPEN:
            in_mark = True
            out.append(_MARK_OPEN)
        elif part == _MARK_CLOSE:
            in_mark = False
            out.append(_MARK_CLOSE)
        elif part:
            out.append(escape(part))
    return Markup("".join(out))


def format_hit(hit: CorpusHit) -> str:
    flags = []
    if hit.is_model_output:
        flags.append("MODEL_OUTPUT")
    if hit.is_bills_writing:
        flags.append("BILLS_WRITING")
    if hit.date_is_inferred:
        flags.append("date_inferred")
    flag_s = f"  [{', '.join(flags)}]" if flags else ""
    dd = hit.doc_date.isoformat() if hit.doc_date else "—"
    head = f"  #{hit.heading}" if hit.heading else ""
    badge = provenance_badge(hit)
    return (
        f"[{hit.source_type}] {hit.path}:{hit.line_start}  ({dd})  score={hit.score:.4f}  [{badge}]{head}\n"
        f"    {hit.snippet}"
    )
