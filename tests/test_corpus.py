"""Corpus chunker + incremental index smoke tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_chunker_respects_headings_and_lines():
    from core.corpus.chunker import chunk_text

    text = "# Key Risks\n\nAlpha risk paragraph one.\n\n## Exit Conditions\n\nExit when X.\n"
    chunks = chunk_text(text, target=80, overlap=10)
    assert chunks
    # Round-trip: slice equals chunk text
    for ch in chunks:
        assert text[ch.char_start : ch.char_end] == ch.text
        assert ch.line_start >= 1
        assert ch.line_end >= ch.line_start
    headings = {c.heading for c in chunks if c.heading}
    assert "Key Risks" in headings or "Exit Conditions" in headings


@pytest.fixture()
def corpus_db(tmp_path, monkeypatch):
    db = tmp_path / "corpus_test.db"
    monkeypatch.setattr("config.SQLITE_DB_PATH", db)
    import core.store.models as models

    models._engine = None
    models._SessionLocal = None
    yield tmp_path
    models._engine = None
    models._SessionLocal = None


def test_corpus_incremental(corpus_db, monkeypatch):
    from core.corpus import index as index_mod
    from core.corpus.sources import SourceSpec, _read_markdown
    from core.store.models import CorpusChunk, get_session
    from sqlalchemy import func, select

    vault = corpus_db / "vault" / "theses"
    vault.mkdir(parents=True)
    f = vault / "ET_thesis.md"
    f.write_text("# Thesis\n\nLake Charles facility expansion.\n", encoding="utf-8")

    spec = SourceSpec("thesis", "vault/theses/*.md", _read_markdown, True, False)

    def _fake_iter(source_type=None):
        return [(spec, f)]

    monkeypatch.setattr(index_mod, "iter_source_files", _fake_iter)
    monkeypatch.setattr(index_mod, "REPO_ROOT", corpus_db)

    # Patch _norm_path via sources used inside index
    import core.corpus.sources as sources_mod

    monkeypatch.setattr(sources_mod, "REPO_ROOT", corpus_db)

    r1 = index_mod.run_index(live=True)
    assert r1.new == 1 and r1.writes == 1
    r2 = index_mod.run_index(live=True)
    assert r2.unchanged == 1 and r2.writes == 0

    f.write_text("# Thesis\n\nLake Charles facility expansion. Updated.\n", encoding="utf-8")
    r3 = index_mod.run_index(live=True)
    assert r3.changed == 1 and r3.writes == 1

    with get_session() as s:
        n = s.scalar(select(func.count()).select_from(CorpusChunk))
        assert n and n >= 1


def test_corpus_ticker_tokens(corpus_db):
    """Tokenizer must leave ET / $ET findable in FTS body."""
    from core.store.models import get_engine, get_session
    from sqlalchemy import text

    get_engine()
    with get_session() as s:
        s.execute(
            text(
                "INSERT INTO corpus_fts(body, chunk_id, doc_id, source_type, path, doc_date, tickers) "
                "VALUES ('Bought $ET near Lake Charles and IBIT/MSTR pair plus 000660.KS', "
                "'1','1','thesis','vault/theses/ET_thesis.md','2026-01-01','ET')"
            )
        )
        s.commit()
        for q in ("ET", "IBIT", "000660"):
            rows = s.execute(
                text("SELECT body FROM corpus_fts WHERE corpus_fts MATCH :q"),
                {"q": q},
            ).fetchall()
            assert rows, f"expected hit for {q!r}"
