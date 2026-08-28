"""
Corpus Search page assembly — reads via core.retrieval only (never core.corpus.search).
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

from core.corpus.search import provenance_badge, snippet_html
from core.retrieval.api import CorpusSearchParams, RetrievalSet, TemplateCall, retrieve, retrieve_corpus_search

DATE_PRESETS = {
    "30d": 30,
    "90d": 90,
    "1y": 365,
}


def _parse_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _facet_counts(hits: list) -> dict[str, Any]:
    st_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    for h in hits:
        st_counts[h.source_type] += 1
        if h.tickers:
            for t in str(h.tickers).split(","):
                t = t.strip().upper()
                if t:
                    ticker_counts[t] += 1
    top_tickers = ticker_counts.most_common(15)
    return {
        "source_type": dict(st_counts),
        "ticker": top_tickers,
        "total": len(hits),
    }


def _search_url(
    *,
    q: str,
    tickers: list[str],
    source_types: list[str],
    since: Optional[date],
    until: Optional[date],
    limit: int,
    offset: int,
    preset: Optional[str] = None,
) -> str:
    params: list[tuple[str, str]] = []
    if q:
        params.append(("q", q))
    for t in tickers:
        params.append(("ticker", t))
    for st in source_types:
        params.append(("source_type", st))
    if preset:
        params.append(("preset", preset))
    if since:
        params.append(("since", since.isoformat()))
    if until:
        params.append(("until", until.isoformat()))
    if limit != 25:
        params.append(("limit", str(limit)))
    if offset:
        params.append(("offset", str(offset)))
    return "/search?" + urlencode(params)


def assemble_search(
    *,
    q: Optional[str] = None,
    tickers: Optional[list[str]] = None,
    source_types: Optional[list[str]] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    preset: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    tickers = [t.upper() for t in (tickers or []) if t]
    source_types = list(source_types or [])
    since_d = _parse_date(since)
    until_d = _parse_date(until)
    if preset in DATE_PRESETS and not since_d:
        since_d = date.today() - timedelta(days=DATE_PRESETS[preset])

    params = CorpusSearchParams(
        q=q or "",
        tickers=tickers or None,
        source_types=source_types or None,
        since=since_d,
        until=until_d,
        limit=limit,
        offset=offset,
    )
    page_hits, all_hits, rs = retrieve_corpus_search(params, caller="ui", label="corpus_search")
    vocab = rs.tables.get("corpus_source_type_counts", [])

    facets = _facet_counts(all_hits) if all_hits else {
        "source_type": {},
        "ticker": [],
        "total": 0,
    }

    hit_rows = []
    for h in page_hits:
        badge = provenance_badge(h)
        hit_rows.append(
            {
                "hit": h,
                "badge": badge,
                "snippet_html": snippet_html(h.snippet),
                "doc_url": f"/doc/{h.doc_id}?chunk={h.chunk_id}",
            }
        )

    return {
        "q": q or "",
        "tickers": tickers,
        "source_types": source_types,
        "since": since_d.isoformat() if since_d else "",
        "until": until_d.isoformat() if until_d else "",
        "preset": preset or "",
        "limit": limit,
        "offset": offset,
        "hits": hit_rows,
        "hit_count": len(all_hits),
        "page_count": len(page_hits),
        "facets": facets,
        "vocab": vocab,
        "retrieval_hash": rs.retrieval_hash,
        "search_url": _search_url,
        "page": "search",
    }


def assemble_doc(doc_id: int, *, chunk_id: Optional[int] = None) -> Optional[dict[str, Any]]:
    rs = retrieve(
        queries=[
            TemplateCall("corpus_doc_by_id", {"doc_id": int(doc_id)}),
            TemplateCall("corpus_chunks_for_doc", {"doc_id": int(doc_id)}),
        ],
        label=f"corpus_doc:{doc_id}",
        caller="ui",
    )
    docs = rs.tables.get("corpus_doc_by_id", [])
    if not docs:
        return None
    doc = docs[0]
    path = Path(doc["path"])
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = f"(Could not read file: {doc['path']})"

    chunks = rs.tables.get("corpus_chunks_for_doc", [])
    anchor_chunk = None
    if chunk_id is not None:
        anchor_chunk = next((c for c in chunks if int(c["id"]) == int(chunk_id)), None)
    elif chunks:
        anchor_chunk = chunks[0]

    lines = text.splitlines()
    rendered_lines = []
    anchor_line = int(anchor_chunk["line_start"]) if anchor_chunk else 1
    for i, line in enumerate(lines, start=1):
        cls = "line"
        if anchor_chunk and anchor_chunk["line_start"] <= i <= anchor_chunk["line_end"]:
            cls = "line highlight"
        rendered_lines.append({"n": i, "text": line, "class": cls})

    return {
        "doc": doc,
        "lines": rendered_lines,
        "anchor_line": anchor_line,
        "anchor_chunk": anchor_chunk,
        "chunks": chunks,
        "retrieval_hash": rs.retrieval_hash,
        "page": "search",
    }
