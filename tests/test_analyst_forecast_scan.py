from core.analyst.validate import validate_answer
from core.retrieval.api import RetrievalSet
from datetime import datetime, timezone


def test_forecast_language_flagged():
    rs = RetrievalSet(
        label="t",
        created_at=datetime.now(timezone.utc),
        corpus_hits=[],
        tables={},
        sources=[],
        retrieval_hash="x",
    )
    v = validate_answer("The price target of $140 is noted.", rs)
    assert "price target" in [f.lower() for f in v.forecast_flags]
