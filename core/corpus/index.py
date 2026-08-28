"""Incremental corpus indexer: sha256 skip / re-chunk / soft-delete."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, func, select, text

from core.corpus.chunker import chunk_text
from core.corpus.sources import (
    REPO_ROOT,
    SOURCES,
    SourceSpec,
    _norm_path,
    iter_source_files,
    sha256_file,
)
from core.store.models import CorpusChunk, CorpusDoc, get_engine, get_session

logger = logging.getLogger(__name__)


@dataclass
class IndexReport:
    live: bool
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    deleted: int = 0
    writes: int = 0
    parse_failures: list[str] = field(default_factory=list)
    by_source: dict = field(default_factory=dict)

    def bump(self, source_type: str, key: str) -> None:
        bucket = self.by_source.setdefault(
            source_type, {"new": 0, "changed": 0, "unchanged": 0, "deleted": 0}
        )
        bucket[key] = bucket.get(key, 0) + 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _delete_doc_chunks(session, doc_id: int) -> None:
    chunk_ids = [
        r[0]
        for r in session.execute(select(CorpusChunk.id).where(CorpusChunk.doc_id == doc_id))
    ]
    if chunk_ids:
        # FTS rows keyed by chunk_id
        for cid in chunk_ids:
            session.execute(
                text("DELETE FROM corpus_fts WHERE chunk_id = :cid"),
                {"cid": str(cid)},
            )
        session.execute(delete(CorpusChunk).where(CorpusChunk.doc_id == doc_id))


def _index_one(session, spec: SourceSpec, path: Path, live: bool, report: IndexReport) -> None:
    rel = _norm_path(path)
    digest = sha256_file(path)
    st = path.stat()
    existing = session.scalar(select(CorpusDoc).where(CorpusDoc.path == rel))

    if existing and existing.sha256 == digest and existing.deleted_at is None:
        report.unchanged += 1
        report.bump(spec.source_type, "unchanged")
        return

    kind = "changed" if existing else "new"
    if not live:
        if kind == "new":
            report.new += 1
            report.bump(spec.source_type, "new")
        else:
            report.changed += 1
            report.bump(spec.source_type, "changed")
        return

    try:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        payload = spec.reader(path)
    except Exception as e:
        report.parse_failures.append(f"{rel}: {e}")
        logger.warning("corpus parse failed %s: %s", rel, e)
        return

    # Chunk the file on disk so line_start matches citation tokens in the reader.
    chunks = chunk_text(raw_text)
    if existing:
        _delete_doc_chunks(session, existing.id)
        existing.sha256 = digest
        existing.mtime = st.st_mtime
        existing.bytes = st.st_size
        existing.title = payload.title
        existing.doc_date = payload.doc_date
        existing.date_is_inferred = payload.date_is_inferred
        existing.tickers = ",".join(payload.tickers) if payload.tickers else None
        existing.chunk_count = len(chunks)
        existing.indexed_at = _utcnow()
        existing.deleted_at = None
        existing.source_type = spec.source_type
        existing.is_bills_writing = spec.is_bills_writing
        existing.is_model_output = spec.is_model_output
        existing.is_authoritative = spec.is_authoritative
        doc = existing
        report.changed += 1
        report.bump(spec.source_type, "changed")
    else:
        doc = CorpusDoc(
            source_type=spec.source_type,
            path=rel,
            doc_date=payload.doc_date,
            date_is_inferred=payload.date_is_inferred,
            title=payload.title,
            tickers=",".join(payload.tickers) if payload.tickers else None,
            sha256=digest,
            mtime=st.st_mtime,
            bytes=st.st_size,
            chunk_count=len(chunks),
            indexed_at=_utcnow(),
            is_bills_writing=spec.is_bills_writing,
            is_model_output=spec.is_model_output,
            is_authoritative=spec.is_authoritative,
        )
        session.add(doc)
        session.flush()
        report.new += 1
        report.bump(spec.source_type, "new")

    for i, ch in enumerate(chunks):
        row = CorpusChunk(
            doc_id=doc.id,
            chunk_ix=i,
            char_start=ch.char_start,
            char_end=ch.char_end,
            line_start=ch.line_start,
            line_end=ch.line_end,
            heading=ch.heading,
        )
        session.add(row)
        session.flush()
        session.execute(
            text(
                "INSERT INTO corpus_fts(body, chunk_id, doc_id, source_type, path, doc_date, tickers) "
                "VALUES (:body, :chunk_id, :doc_id, :source_type, :path, :doc_date, :tickers)"
            ),
            {
                "body": ch.text,
                "chunk_id": str(row.id),
                "doc_id": str(doc.id),
                "source_type": spec.source_type,
                "path": rel,
                "doc_date": payload.doc_date.isoformat() if payload.doc_date else "",
                "tickers": ",".join(payload.tickers) if payload.tickers else "",
            },
        )
    report.writes += 1


def run_index(
    *,
    live: bool = False,
    rebuild: bool = False,
    yes: bool = False,
    source_type: Optional[str] = None,
) -> IndexReport:
    get_engine()
    report = IndexReport(live=live)

    if rebuild:
        if not (live and yes):
            raise RuntimeError(
                "corpus index --rebuild requires both --live and --yes (destructive)."
            )
        with get_session() as session:
            session.execute(text("DELETE FROM corpus_fts"))
            session.execute(delete(CorpusChunk))
            session.execute(delete(CorpusDoc))
            session.commit()

    files = iter_source_files(source_type)
    seen_paths: set[str] = set()

    with get_session() as session:
        for spec, path in files:
            rel = _norm_path(path)
            seen_paths.add(rel)
            # One transaction per file
            try:
                _index_one(session, spec, path, live, report)
                if live:
                    session.commit()
            except Exception as e:
                session.rollback()
                report.parse_failures.append(f"{rel}: {e}")
                logger.exception("corpus index failed for %s", rel)

        # Soft-delete missing files (same source_type scope)
        q = select(CorpusDoc).where(CorpusDoc.deleted_at.is_(None))
        if source_type:
            q = q.where(CorpusDoc.source_type == source_type)
        for doc in session.scalars(q):
            if doc.path in seen_paths:
                continue
            report.deleted += 1
            report.bump(doc.source_type, "deleted")
            if live:
                doc.deleted_at = _utcnow()
        if live:
            session.commit()

    return report


def corpus_status() -> dict:
    get_engine()
    out: dict = {"by_source": {}, "totals": {"docs": 0, "chunks": 0}}
    with get_session() as session:
        for spec in SOURCES:
            st = spec.source_type
            if st in out["by_source"]:
                continue  # duplicate source_type entries share one bucket
            n_docs = session.scalar(
                select(func.count())
                .select_from(CorpusDoc)
                .where(CorpusDoc.source_type == st, CorpusDoc.deleted_at.is_(None))
            ) or 0
            n_chunks = session.scalar(
                select(func.count())
                .select_from(CorpusChunk)
                .join(CorpusDoc, CorpusChunk.doc_id == CorpusDoc.id)
                .where(CorpusDoc.source_type == st, CorpusDoc.deleted_at.is_(None))
            ) or 0
            oldest = session.scalar(
                select(func.min(CorpusDoc.doc_date)).where(
                    CorpusDoc.source_type == st, CorpusDoc.deleted_at.is_(None)
                )
            )
            newest = session.scalar(
                select(func.max(CorpusDoc.doc_date)).where(
                    CorpusDoc.source_type == st, CorpusDoc.deleted_at.is_(None)
                )
            )
            last_ix = session.scalar(
                select(func.max(CorpusDoc.indexed_at)).where(
                    CorpusDoc.source_type == st, CorpusDoc.deleted_at.is_(None)
                )
            )
            out["by_source"][st] = {
                "docs": int(n_docs),
                "chunks": int(n_chunks),
                "oldest": oldest.isoformat() if oldest else None,
                "newest": newest.isoformat() if newest else None,
                "last_indexed": last_ix.isoformat() if last_ix else None,
            }
            out["totals"]["docs"] += int(n_docs)
            out["totals"]["chunks"] += int(n_chunks)
    return out
