"""Shared canonicalize + Wash Sale blank/FALSE parity (ledger_hash root cause)."""

from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.store.canonicalize import bool_cell, normalize_records, GL_MONEY
from core.store.ledger_hash import ledger_fingerprint


def test_bool_cell_blank_equals_false():
    assert bool_cell("", blank_means_false=True) is False
    assert bool_cell(None, blank_means_false=True) is False
    assert bool_cell("", blank_means_false=False) is None
    assert bool_cell("FALSE") is False
    assert bool_cell("TRUE") is True


def test_wash_sale_blank_vs_false_same_fingerprint():
    """The 2026-08-27 bisect: one realized_gl row Sheets '' vs SQLite 'FALSE'."""
    from core.store.canonicalize import BOOL_BLANK_MEANS_FALSE

    assert "Wash Sale" in BOOL_BLANK_MEANS_FALSE
    assert "Is Primary Acct" not in BOOL_BLANK_MEANS_FALSE
    base = {
        "Ticker": "ZZZ",
        "Closed Date": "2026-04-13",
        "Opened Date": "2025-01-01",
        "Quantity": 1,
        "Proceeds": 100,
        "Cost Basis": 90,
        "Gain Loss $": 10,
        "ST Gain Loss": 10,
        "LT Gain Loss": 0,
        "Disallowed Loss": 0,
        "Fingerprint": "test-fp-wash",
    }
    sheets = pd.DataFrame([{**base, "Wash Sale": ""}])
    sqlite = pd.DataFrame([{**base, "Wash Sale": "FALSE"}])
    a = normalize_records(sheets, GL_MONEY)
    b = normalize_records(sqlite, GL_MONEY)
    assert a == b
    empty = pd.DataFrame()
    hs = ledger_fingerprint(
        transactions=empty, realized_gl=sheets, tax_metrics={}, tax_lots=empty
    )
    hq = ledger_fingerprint(
        transactions=empty, realized_gl=sqlite, tax_metrics={}, tax_lots=empty
    )
    assert hs == hq


def test_is_primary_acct_blank_stays_unknown():
    """Is Primary Acct is BOOL but not BOOL_BLANK_MEANS_FALSE."""
    from core.store.canonicalize import normalize_value

    assert normalize_value("Is Primary Acct", "") is None
    assert normalize_value("Is Primary Acct", "FALSE") is False
    assert normalize_value("Wash Sale", "") is False
