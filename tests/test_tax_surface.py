"""Prompt 9 — wash window (3a) and LT ladder (3b)."""

from __future__ import annotations

import ast
import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_tax_wash_window_gld_disallow_through():
    """GLD 2026-07-21 wash-disallowed loss → disallow-through 2026-08-20."""
    from core.tax.wash import open_wash_windows

    rows = [
        {
            "Ticker": "GLD",
            "Closed Date": "2026-07-21",
            "Quantity": 1.0,
            "Gain Loss $": 0.0,
            "Wash Sale": "TRUE",
            "Disallowed Loss": 74.43,
        },
        {
            "Ticker": "EMXC",
            "Closed Date": "2026-07-20",
            "Quantity": 25.0,
            "Gain Loss $": 116.32,  # gain — must not open a window
            "Wash Sale": "FALSE",
            "Disallowed Loss": 0.0,
        },
        {
            "Ticker": "XLF",
            "Closed Date": "2026-06-30",
            "Quantity": 100.0,
            "Gain Loss $": -0.63,
            "Wash Sale": "FALSE",
            "Disallowed Loss": 0.0,
        },
    ]
    # Historical: include closed windows
    all_w = open_wash_windows(rows, as_of=date(2026, 7, 22), only_open=False)
    by_t = {w.ticker: w for w in all_w}
    assert "GLD" in by_t
    assert by_t["GLD"].disallow_through == date(2026, 8, 20)
    assert by_t["GLD"].wash_sale_flagged is True
    assert "EMXC" not in by_t  # gain row
    assert by_t["XLF"].disallow_through == date(2026, 7, 30)

    # As of 2026-08-27 all three historical windows are closed
    open_now = open_wash_windows(rows, as_of=date(2026, 8, 27), only_open=True)
    assert open_now == []


def test_tax_lt_ladder_sort_and_leap():
    from core.tax.ladder import days_to_lt_ladder

    lots = [
        {"ticker": "UNH", "open_date": date(2025, 11, 19), "shares": 22},
        {"ticker": "UNH", "open_date": date(2026, 4, 2), "shares": 18},
        {"ticker": "UNH", "open_date": date(2026, 5, 11), "shares": 12},
        # leap-day acquisition
        {"ticker": "UNH", "open_date": date(2024, 2, 29), "shares": 1},
    ]
    ladder = days_to_lt_ladder(lots, as_of=date(2026, 8, 27))
    assert [r.open_date for r in ladder]  # non-empty
    days = [r.days_to_lt for r in ladder]
    assert days == sorted(days)  # sorted by days remaining, not open date
    leap = next(r for r in ladder if r.open_date == date(2024, 2, 29))
    assert leap.already_long_term  # >365 days by Aug 2026
    apr = next(r for r in ladder if r.open_date == date(2026, 4, 2))
    assert apr.crosses_on == date(2027, 4, 3)  # open + 366
    assert apr.days_to_lt == (apr.crosses_on - date(2026, 8, 27)).days


def test_tax_ladder_no_relief_model():
    src = Path("core/tax/ladder.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "lot_relief" not in mod
            assert not any("lot_relief" in (a.name or "") for a in node.names)
        if isinstance(node, ast.Import):
            assert not any("lot_relief" in (a.name or "") for a in node.names)
    # No from/import of the optimizer module (docstring may mention the name)
    assert "import lot_relief" not in src
    assert "from core.tax.lot_relief" not in src
    assert "from core.tax import lot_relief" not in src


def test_open_lots_not_fifo_on_realized_match():
    """Closing a newer lot first (optimizer-like) leaves the older buy open."""
    from core.tax.open_lots import reconstruct_open_lots_from_realized

    txns = [
        {"Ticker": "AAA", "Action": "Buy", "Trade Date": "2026-01-01", "Quantity": 10, "Price": 100},
        {"Ticker": "AAA", "Action": "Buy", "Trade Date": "2026-06-01", "Quantity": 10, "Price": 120},
    ]
    # Realized closed the June lot (optimizer might), not the January lot
    realized = [
        {
            "Ticker": "AAA",
            "Opened Date": "2026-06-01",
            "Quantity": 10,
            "Gain Loss $": 50,
        }
    ]
    open_lots = reconstruct_open_lots_from_realized(txns, realized, ticker="AAA")
    assert len(open_lots) == 1
    assert open_lots[0]["open_date"] == date(2026, 1, 1)
    assert open_lots[0]["shares"] == 10


def test_tax_hold_runner_surface_measurement_not_auto_expand(monkeypatch):
    from core.tax import surface as surf

    class FakeDoc:
        constraints = [
            type(
                "C",
                (),
                {"id": "tax_hold_runners", "tickers": ["UNH", "COF"]},
            )()
        ]

    monkeypatch.setattr(surf, "load_doctrine", lambda: FakeDoc())
    monkeypatch.setattr(surf, "_realized_records", lambda ticker=None: [])
    monkeypatch.setattr(surf, "_txn_records", lambda ticker: [])
    ann_unh = surf.annotate_ticker("UNH", as_of=date(2026, 8, 27))
    ann_meta = surf.annotate_ticker("META", as_of=date(2026, 8, 27))
    assert ann_unh.is_tax_hold_runner is True
    assert ann_meta.is_tax_hold_runner is False
    text = surf.format_project_report(ann_meta)
    assert "ESTIMATE" in text
    assert "Not a tax_hold_runner" in text
