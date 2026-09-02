"""Tests for tasks/detect_undocumented_changes.py — review log bounding."""

from __future__ import annotations

from tasks.detect_undocumented_changes import _review_log_dates


FIXTURE_THESIS = """---
ticker: TST
---
# TST

## Review Log

- 2026-08-01: Bill documented the resize rationale here.

<!-- region:transaction_log -->
- 2026-08-21: Buy 1.0 @ $420.56
- 2026-08-22: Buy 2.0 @ $100.00
<!-- endregion:transaction_log -->
"""


def test_review_log_dates_stops_at_region_not_transaction_log():
    dates = _review_log_dates(FIXTURE_THESIS)
    assert dates == ["2026-08-01"]
    assert "2026-08-21" not in dates
    assert "2026-08-22" not in dates


def test_review_log_dates_stops_at_next_h2():
    text = """## Review Log

- 2026-07-01: noted

## Other Section

- 2026-08-01: must not match
"""
    assert _review_log_dates(text) == ["2026-07-01"]
