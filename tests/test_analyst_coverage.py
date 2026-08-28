from core.analyst.validate import validate_answer
from core.corpus.search import CorpusHit
from core.retrieval.api import RetrievalSet
from datetime import datetime, timezone

import pytest


def _rs_with_hit() -> RetrievalSet:
    hit = CorpusHit(
        chunk_id=1,
        doc_id=1,
        source_type="thesis",
        path="vault/theses/ET_thesis.md",
        doc_date=None,
        date_is_inferred=False,
        heading=None,
        line_start=42,
        line_end=44,
        snippet="export terminals",
        score=1.0,
        is_bills_writing=True,
        is_model_output=False,
    )
    return RetrievalSet(
        label="t",
        created_at=datetime.now(timezone.utc),
        corpus_hits=[hit],
        tables={},
        sources=[],
        retrieval_hash="x",
    )


def test_coverage_three_paragraphs_one_cited():
    rs = _rs_with_hit()
    token = "[thesis:vault/theses/ET_thesis.md:L42 undated]"
    answer = f"First {token}\n\nSecond uncited.\n\nThird also uncited."
    v = validate_answer(answer, rs)
    assert v.coverage_pct == pytest.approx(33.333, rel=1e-3)
