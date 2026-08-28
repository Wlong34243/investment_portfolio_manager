"""Desk CSS contract — sticky column stacking for multi-pin tables."""

from pathlib import Path


def test_decision_second_sticky_col_offset():
    css = Path("ui/static/desk.css").read_text(encoding="utf-8")
    assert ".data-table .sticky-col + .sticky-col" in css
    assert "left: 2.5rem" in css
