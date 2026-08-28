"""
RetrievalSet entry point — templates + corpus → hash-stamped evidence set.

Citation token contract (do not change casually; prompts 4/6 validate against it):
  Corpus hit:  [thesis:<path>:L<line_start> <YYYY-MM-DD|undated>]
               Prefer source_type in the path prefix when not thesis — still use
               the same shape: [<kind>:<path>:L<start> <date>]
               Kind is the corpus source_type (thesis, digest, transcript, …).
  Table row:   [table:<template_id>#<0-based-index>]
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.bundle import _sha256_canonical
from core.corpus.search import CorpusHit, search as corpus_search
from core.retrieval.conn import open_readonly
from core.retrieval.log import log_retrieval
from core.retrieval.queries import TEMPLATES, validate_call
from core.store.canonicalize import normalize_table_rows
from utils.thesis_reader import (
    declared_trigger_type,
    get_style,
    get_triggers,
    read_thesis_text,
    resolve_band_levels,
    thesis_path_for_ticker,
)


@dataclass
class CorpusQuery:
    query: str
    tickers: list[str] | None = None
    source_types: list[str] | None = None
    since: date | None = None
    until: date | None = None
    limit: int = 25


@dataclass
class TemplateCall:
    template_id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalSet:
    label: str
    created_at: datetime
    corpus_hits: list[CorpusHit]
    tables: dict[str, list[dict[str, Any]]]
    sources: list[str]
    retrieval_hash: str
    caller: str = "cli"

    def to_prompt_context(self) -> str:
        """
        Render evidence for a model. Every row/hit carries a citation token.

        Tokens:
          [<source_type>:<path>:L<line_start> <doc_date|undated>]
          [table:<template_id>#<ix>]
        """
        lines: list[str] = [
            f"# RetrievalSet label={self.label!r} hash={self.retrieval_hash}",
            f"created_at={self.created_at.isoformat()}",
            "",
        ]
        if self.corpus_hits:
            lines.append("## Corpus hits")
            for h in self.corpus_hits:
                d = h.doc_date.isoformat() if h.doc_date else "undated"
                token = f"[{h.source_type}:{h.path}:L{h.line_start} {d}]"
                head = f" — {h.heading}" if h.heading else ""
                lines.append(f"- {token} score={h.score:.4f}{head}")
                snippet = (h.snippet or "").replace("\n", " ").strip()
                if snippet:
                    lines.append(f"  {snippet[:400]}")
            lines.append("")
        if self.tables:
            lines.append("## Tables")
            for tid, rows in self.tables.items():
                lines.append(f"### {tid} ({len(rows)} rows)")
                for i, row in enumerate(rows):
                    token = f"[table:{tid}#{i}]"
                    # compact single-line JSON-ish
                    parts = []
                    for k, v in row.items():
                        if k == "payload_json":
                            continue
                        parts.append(f"{k}={v}")
                    lines.append(f"- {token} " + "; ".join(parts[:12]))
                lines.append("")
        if self.sources:
            lines.append("## Sources")
            for s in self.sources:
                lines.append(f"- {s}")
        return "\n".join(lines)

    def citation_tokens(self) -> set[str]:
        """Valid inline citation tokens for analyst validation."""
        tokens: set[str] = set()
        for h in self.corpus_hits:
            d = h.doc_date.isoformat() if h.doc_date else "undated"
            tokens.add(f"[{h.source_type}:{h.path}:L{h.line_start} {d}]")
        for tid, rows in self.tables.items():
            for i in range(len(rows)):
                tokens.add(f"[table:{tid}#{i}]")
        return tokens


def _bind_params(params: dict[str, Any], tmpl_param_names: dict[str, type]) -> dict[str, Any]:
    """Normalize dates to ISO strings; ensure every declared name is present (None ok)."""
    out: dict[str, Any] = {}
    for name in tmpl_param_names:
        val = params.get(name)
        if val is None:
            out[name] = None
        elif isinstance(val, date) and not isinstance(val, datetime):
            out[name] = val.isoformat()
        elif isinstance(val, datetime):
            out[name] = val.date().isoformat()
        else:
            out[name] = val
    # also pass through any extra allowed keys already validated
    for k, v in params.items():
        if k not in out:
            if isinstance(v, date) and not isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
    return out


def _rows_from_sql(conn, tmpl, params: dict[str, Any]) -> list[dict[str, Any]]:
    bind = _bind_params(params, tmpl.params)
    cur = conn.execute(tmpl.sql, bind)
    colnames = [d[0] for d in cur.description] if cur.description else []
    raw = [dict(zip(colnames, row)) for row in cur.fetchall()]
    if tmpl.unpack:
        return tmpl.unpack(raw, params)
    # normalize date-ish / bool for hash stability
    out = []
    for r in raw:
        nr = {}
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                nr[k] = v.isoformat()
            else:
                nr[k] = v
        out.append(nr)
    return out


def _thesis_state(ticker: str) -> list[dict[str, Any]]:
    path = thesis_path_for_ticker(ticker)
    text = read_thesis_text(path)
    if not text:
        return []
    triggers = get_triggers(text=text)
    bands = resolve_band_levels(triggers)
    ceiling = triggers.get("style_size_ceiling_pct")
    try:
        rel = str(path.relative_to(Path.cwd()))
    except ValueError:
        rel = str(path)
    return [
        {
            "ticker": ticker.upper(),
            "style": get_style(text=text),
            "trigger_type": declared_trigger_type(triggers),
            "bands": bands,
            "ceiling": ceiling,
            "path": rel.replace("\\", "/"),
        }
    ]


def _hashable_set(
    label: str,
    created_at: datetime,
    corpus_hits: list[CorpusHit],
    tables: dict[str, list[dict]],
    sources: list[str],
) -> dict:
    hits = []
    for h in corpus_hits:
        d = asdict(h)
        if d.get("doc_date") is not None:
            d["doc_date"] = d["doc_date"].isoformat() if hasattr(d["doc_date"], "isoformat") else str(d["doc_date"])
        hits.append(d)
    # Same cell rules as ledger_fingerprint — do not invent a second money/date list.
    canon_tables = {
        tid: normalize_table_rows(rows) for tid, rows in sorted(tables.items())
    }
    return {
        "label": label,
        "created_at": created_at.isoformat(),
        "corpus_hits": hits,
        "tables": canon_tables,
        "sources": sources,
    }


def retrieve(
    *,
    corpus: list[CorpusQuery] | None = None,
    queries: list[TemplateCall] | None = None,
    label: str = "",
    caller: str = "cli",
) -> RetrievalSet:
    """
    Execute whitelisted templates + optional corpus FTS searches.
    Always logs one retrieval_log row (write engine). Never authors SQL from the model.
    """
    t0 = time.perf_counter()
    created_at = datetime.now(timezone.utc)
    tables: dict[str, list[dict[str, Any]]] = {}
    sources: list[str] = []
    corpus_hits: list[CorpusHit] = []

    conn = None
    try:
        needs_sql = any(
            (q.template_id != "thesis_state_for_ticker") for q in (queries or [])
        )
        if needs_sql:
            conn = open_readonly()

        for call in queries or []:
            tmpl = validate_call(call.template_id, call.params or {})
            if call.template_id == "thesis_state_for_ticker":
                rows = _thesis_state(str(call.params["ticker"]))
                sources.append(f"vault:{rows[0]['path']}" if rows else "vault:missing")
            else:
                rows = _rows_from_sql(conn, tmpl, call.params or {})
                # table name from FROM clause — use template id as source tag
                sources.append(f"table:{call.template_id}")
            tables[call.template_id] = rows

        for cq in corpus or []:
            hits = corpus_search(
                cq.query,
                tickers=cq.tickers,
                source_types=cq.source_types,
                since=cq.since,
                until=cq.until,
                limit=cq.limit,
            )
            from core.corpus.search import apply_doctrine_lift

            hits = apply_doctrine_lift(hits)
            seen_chunks = {h.chunk_id for h in corpus_hits}
            for h in hits:
                if h.chunk_id in seen_chunks:
                    continue
                seen_chunks.add(h.chunk_id)
                corpus_hits.append(h)
                src = f"corpus:{h.path}"
                if src not in sources:
                    sources.append(src)

        # stable source order for hash
        sources = sorted(set(sources))

        payload = _hashable_set(label, created_at, corpus_hits, tables, sources)
        # Exclude created_at from hash so two processes with identical evidence match?
        # Prompt checklist: "same retrieve() twice in two processes | identical hash"
        # created_at will always differ — hash without wall-clock.
        hash_payload = {
            "label": label,
            "corpus_hits": payload["corpus_hits"],
            "tables": payload["tables"],
            "sources": payload["sources"],
        }
        retrieval_hash = _sha256_canonical(hash_payload)

        row_count = sum(len(v) for v in tables.values())
        hit_count = len(corpus_hits)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        template_ids = [c.template_id for c in (queries or [])]
        template_id = template_ids[0] if len(template_ids) == 1 else None
        params_for_log = {
            "queries": [{"template_id": c.template_id, "params": c.params} for c in (queries or [])],
            "corpus": [asdict(c) for c in (corpus or [])],
        }
        # fix date in asdict
        for item in params_for_log["corpus"]:
            for k in ("since", "until"):
                if item.get(k) is not None and hasattr(item[k], "isoformat"):
                    item[k] = item[k].isoformat()

        corpus_q = None
        if corpus:
            corpus_q = " | ".join(c.query for c in corpus)

        log_retrieval(
            label=label,
            caller=caller,
            template_id=template_id,
            params=params_for_log,
            corpus_query=corpus_q,
            row_count=row_count,
            hit_count=hit_count,
            retrieval_hash=retrieval_hash,
            elapsed_ms=elapsed_ms,
        )

        return RetrievalSet(
            label=label,
            created_at=created_at,
            corpus_hits=corpus_hits,
            tables=tables,
            sources=sources,
            retrieval_hash=retrieval_hash,
            caller=caller,
        )
    finally:
        if conn is not None:
            conn.close()


@dataclass
class CorpusSearchParams:
    q: str = ""
    tickers: list[str] | None = None
    source_types: list[str] | None = None
    since: date | None = None
    until: date | None = None
    limit: int = 25
    offset: int = 0


def retrieve_corpus_search(
    params: CorpusSearchParams,
    *,
    caller: str = "ui",
    label: str = "corpus_search",
) -> tuple[list, list, RetrievalSet]:
    """
    Corpus search via retrieval layer — logs one row; UI must not call search() directly.

    Returns (ranked_hits_for_page, full_ranked_hits_for_facets, RetrievalSet).
    """
    from core.corpus.search import search_ranked

    q = (params.q or "").strip()
    ranked_all: list = []
    if q:
        ranked_all = search_ranked(
            q,
            tickers=params.tickers,
            source_types=params.source_types,
            since=params.since,
            until=params.until,
            limit=min(500, max(params.limit + params.offset, params.limit)),
            offset=0,
        )
    page = ranked_all[params.offset : params.offset + params.limit]

    t0 = time.perf_counter()
    created_at = datetime.now(timezone.utc)
    conn = open_readonly()
    try:
        tmpl = validate_call("corpus_source_type_counts", {})
        vocab_rows = _rows_from_sql(conn, tmpl, {})
    finally:
        conn.close()

    sources = sorted({f"corpus:{h.path}" for h in ranked_all})
    sources.append("table:corpus_source_type_counts")
    tables = {"corpus_source_type_counts": vocab_rows}
    hits_serial = []
    for h in ranked_all:
        d = asdict(h)
        if d.get("doc_date") is not None and hasattr(d["doc_date"], "isoformat"):
            d["doc_date"] = d["doc_date"].isoformat()
        hits_serial.append(d)
    hash_payload = {
        "label": label,
        "corpus_hits": hits_serial,
        "tables": {tid: normalize_table_rows(rows) for tid, rows in sorted(tables.items())},
        "sources": sources,
    }
    retrieval_hash = _sha256_canonical(hash_payload)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    log_retrieval(
        label=label,
        caller=caller,
        template_id="corpus_source_type_counts",
        params={
            "q": q,
            "tickers": params.tickers,
            "source_types": params.source_types,
            "since": params.since.isoformat() if params.since else None,
            "until": params.until.isoformat() if params.until else None,
            "limit": params.limit,
            "offset": params.offset,
        },
        corpus_query=q or None,
        row_count=len(page),
        hit_count=len(ranked_all),
        retrieval_hash=retrieval_hash,
        elapsed_ms=elapsed_ms,
    )
    return page, ranked_all, RetrievalSet(
        label=label,
        created_at=created_at,
        corpus_hits=ranked_all,
        tables=tables,
        sources=sources,
        retrieval_hash=retrieval_hash,
        caller=caller,
    )
