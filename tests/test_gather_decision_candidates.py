"""Tests for tasks/gather_decision_candidates.py — XOM/GOOG/AMZN tripwire."""

from __future__ import annotations

from tasks.gather_decision_candidates import gather_candidates


def test_gatherer_finds_known_positives():
    candidates = gather_candidates()
    tickers = {c["ticker"] for c in candidates}
    assert candidates, "zero candidates means gatherer is broken"
    for required in ("XOM", "GOOG", "AMZN"):
        assert required in tickers, f"missing tripwire ticker {required}"


def test_categories_present():
    candidates = gather_candidates()
    categories = {c["category"] for c in candidates}
    assert "yaml_comment_conjunction" in categories or "frontmatter_revision" in categories
    assert "review_log_directive" in categories or "ceiling_only_temporary" in categories


def test_review_log_line_numbers_are_file_absolute():
    """Review-log categories must cite file lines, not chunk-relative indices."""
    candidates = gather_candidates()
    gld = next(c for c in candidates if c["ticker"] == "GLD" and c["category"] == "review_log_directive")
    amzn = next(c for c in candidates if c["ticker"] == "AMZN" and c["category"] == "ceiling_only_temporary")
    assert gld["line"] == 73, f"GLD directive expected L73, got L{gld['line']}"
    assert amzn["line"] == 49, f"AMZN deferral expected L49, got L{amzn['line']}"
    mu = next(c for c in candidates if c["ticker"] == "MU" and c["category"] == "ceiling_only_temporary")
    assert mu["line"] == 235, f"MU deferral expected L235, got L{mu['line']}"
