from core.analyst.validate import validate_answer
from core.corpus.search import CorpusHit
from core.retrieval.api import RetrievalSet
from datetime import datetime, timezone


def _minimal_retrieval() -> RetrievalSet:
    hit = CorpusHit(
        chunk_id=1,
        doc_id=1,
        source_type="thesis",
        path="vault/theses/MU_thesis.md",
        doc_date=None,
        date_is_inferred=False,
        heading=None,
        line_start=10,
        line_end=12,
        snippet="test",
        score=1.0,
        is_bills_writing=True,
        is_model_output=False,
    )
    rs = RetrievalSet(
        label="test",
        created_at=datetime.now(timezone.utc),
        corpus_hits=[hit],
        tables={},
        sources=[],
        retrieval_hash="abc",
    )
    return rs


def test_combined_table_citations_split():
    rs = RetrievalSet(
        label="test",
        created_at=datetime.now(timezone.utc),
        corpus_hits=[],
        tables={"position_transactions": [{"trade_date": "2026-08-07"}, {"trade_date": "2026-08-07"}]},
        sources=[],
        retrieval_hash="abc",
    )
    answer = "Both [table:position_transactions#0, table:position_transactions#1] cited."
    v = validate_answer(answer, rs)
    assert v.status == "VALIDATION_PASSED"


def test_fabricated_token_fails():
    rs = _minimal_retrieval()
    token = "[thesis:vault/theses/MU_thesis.md:L10 undated]"
    answer = f"MU is great {token} and also [table:fake#99]."
    v = validate_answer(answer, rs)
    assert v.status == "VALIDATION_FAILED"
    assert "[table:fake#99]" in v.fabricated_tokens


def test_coverage_computed():
    rs = _minimal_retrieval()
    token = "[thesis:vault/theses/MU_thesis.md:L10 undated]"
    answer = f"Paragraph one {token}\n\nParagraph two no cite."
    v = validate_answer(answer, rs)
    assert v.coverage_pct == 50.0
