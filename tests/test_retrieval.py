"""Retrieval layer unit tests (prompt 3 Steps 1–4)."""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def retrieval_db(tmp_path, monkeypatch):
    db = tmp_path / "retrieval_test.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db))
    import config

    monkeypatch.setattr(config, "SQLITE_DB_PATH", db)
    import core.store.models as models

    models._engine = None
    models._SessionLocal = None
    from core.store.models import get_engine

    get_engine()  # create tables
    # Seed minimal mirror + evidence rows
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO holdings_current (ticker, payload_json) VALUES (?, ?)",
        (
            "VST",
            '{"Ticker":"VST","Market Value":1000,"Weight":0.02,"Asset Strategy":"GARP","Cost Basis":800}',
        ),
    )
    conn.execute(
        "INSERT INTO trade_log (payload_json) VALUES (?)",
        (
            '{"Date":"2026-01-15","Sell_Ticker":"JEPI","Buy_Ticker":"VST",'
            '"Implicit_Bet":"power demand","Rotation_Type":"theme",'
            '"Proposed_Bet":"","Rationale_Provenance":""}',
        ),
    )
    conn.execute(
        "INSERT INTO transactions (payload_json) VALUES (?)",
        ('{"Ticker":"VST","Trade Date":"2026-01-15","Action":"Buy","Quantity":10,"Price":50,"Net Amount":-500,"Account":"...5119"}',),
    )
    conn.execute(
        "INSERT INTO tax_control_lots (payload_json) VALUES (?)",
        ('{"Ticker":"VST","Open Date":"2026-01-15","Quantity":10,"Cost Basis":500,"Gain/Loss":100,"Holding Days":200,"Term":"Short Term"}',),
    )
    conn.execute(
        "INSERT INTO realized_gl (payload_json) VALUES (?)",
        ('{"Ticker":"VST","Close Date":"2025-06-01","Quantity":5,"Proceeds":400,"Cost Basis":300,"Gain/Loss":100,"Term":"Short Term","Holding Days":100}',),
    )
    conn.execute(
        "INSERT INTO rotation_review (payload_json) VALUES (?)",
        ('{"Sell_Ticker":"JEPI","Buy_Ticker":"VST","Residual_Pair":0.01}',),
    )
    d = date(2026, 8, 27)
    conn.execute(
        """INSERT INTO signal_events
        (event_date, captured_at, ticker, signal_type, trigger_type, metric_value, band_level, band_side,
         distance_pct, rank_bucket, rank, source, doctrine_downgraded, payload_json, fingerprint)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            d.isoformat(),
            "2026-08-27T12:00:00+00:00",
            "VST",
            "NEAR_TRIM",
            "price",
            100.0,
            110.0,
            "trim",
            -0.05,
            0,
            1,
            "crosshairs",
            0,
            '{"ticker":"VST"}',
            "fp-vst-1",
        ),
    )
    conn.execute(
        """INSERT INTO bars_daily
        (ticker, bar_date, open, high, low, close, volume, source, captured_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        ("VST", d.isoformat(), 1, 2, 0.5, 1.5, 1000, "schwab", "2026-08-27T12:00:00+00:00"),
    )
    conn.execute(
        """INSERT INTO fundamentals_snapshot
        (ticker, as_of_date, fwd_pe, trailing_pe, price_to_book, market_cap, dividend_yield,
         week52_high, week52_low, eps, source, captured_at, payload_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "VST",
            d.isoformat(),
            20.0,
            25.0,
            3.0,
            1e9,
            0.01,
            120,
            80,
            5.0,
            "fmp",
            "2026-08-27T12:00:00+00:00",
            "{}",
        ),
    )
    conn.commit()
    conn.close()
    yield db
    models._engine = None
    models._SessionLocal = None


def test_retrieval_readonly(retrieval_db):
    from core.retrieval.conn import open_readonly

    conn = open_readonly()
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO trade_log (payload_json) VALUES ('{}')")
    conn.close()


def test_query_only_pragma(retrieval_db):
    from core.retrieval.conn import open_readonly

    conn = open_readonly()
    row = conn.execute("PRAGMA query_only").fetchone()
    assert int(row[0]) == 1
    conn.close()


def test_retrieval_template_validation(retrieval_db):
    from core.retrieval.queries import validate_call

    with pytest.raises(KeyError):
        validate_call("no_such_template", {})
    with pytest.raises(KeyError):
        validate_call("position_lots", {"ticker": "VST", "bogus": 1})
    with pytest.raises(KeyError):
        validate_call("position_lots", {})
    with pytest.raises(TypeError):
        validate_call("bars_for_ticker", {"ticker": "VST", "since": 123, "until": "2026-01-01"})

    # Injection string is a *value*, not interpolated — validation accepts it as ticker str
    tmpl = validate_call(
        "position_lots",
        {"ticker": "'; DROP TABLE trade_log; --"},
    )
    assert tmpl.id == "position_lots"


def test_injection_bound_as_value(retrieval_db):
    from core.retrieval.api import TemplateCall, retrieve

    evil = "; DROP TABLE trade_log; --"
    rs = retrieve(
        queries=[TemplateCall("trade_log_for_ticker", {"ticker": evil})],
        label="injection",
        caller="test",
    )
    assert rs.tables["trade_log_for_ticker"] == []
    conn = sqlite3.connect(str(retrieval_db))
    n = conn.execute("SELECT COUNT(*) FROM trade_log").fetchone()[0]
    conn.close()
    assert n == 1


def test_retrieval_hash_stable(retrieval_db):
    from core.retrieval.api import TemplateCall, retrieve

    a = retrieve(
        queries=[TemplateCall("holdings_current", {})],
        label="hash-stable",
        caller="test",
    )
    b = retrieve(
        queries=[TemplateCall("holdings_current", {})],
        label="hash-stable",
        caller="test",
    )
    assert a.retrieval_hash == b.retrieval_hash
    assert len(a.retrieval_hash) == 64


def test_retrieval_hash_sensitive(retrieval_db):
    from core.retrieval.api import TemplateCall, retrieve

    a = retrieve(
        queries=[TemplateCall("holdings_current", {})],
        label="hash-sens",
        caller="test",
    )
    conn = sqlite3.connect(str(retrieval_db))
    conn.execute(
        "INSERT INTO holdings_current (ticker, payload_json) VALUES (?, ?)",
        (
            "MU",
            '{"Ticker":"MU","Market Value":1,"Weight":0.01,"Asset Strategy":"GARP","Cost Basis":1}',
        ),
    )
    conn.commit()
    conn.close()
    b = retrieve(
        queries=[TemplateCall("holdings_current", {})],
        label="hash-sens",
        caller="test",
    )
    assert a.retrieval_hash != b.retrieval_hash


def test_retrieval_citation_tokens(retrieval_db):
    from core.retrieval.api import TemplateCall, retrieve

    rs = retrieve(
        queries=[
            TemplateCall("signal_events_for_ticker", {"ticker": "VST"}),
            TemplateCall("thesis_state_for_ticker", {"ticker": "VST"}),
        ],
        label="cite",
        caller="test",
    )
    ctx = rs.to_prompt_context()
    assert "[table:signal_events_for_ticker#0]" in ctx
    assert "[table:thesis_state_for_ticker#0]" in ctx
    # round-trip: token index resolves to a row
    m = re.search(r"\[table:(signal_events_for_ticker)#(\d+)\]", ctx)
    assert m
    tid, ix = m.group(1), int(m.group(2))
    assert rs.tables[tid][ix]["ticker"] == "VST"


def test_retrieval_log(retrieval_db):
    from sqlalchemy import func, select

    from core.retrieval.api import TemplateCall, retrieve
    from core.store.models import RetrievalLog, get_session

    before = 0
    with get_session() as s:
        before = s.scalar(select(func.count()).select_from(RetrievalLog)) or 0
    rs = retrieve(
        queries=[TemplateCall("bars_for_ticker", {"ticker": "VST", "since": "2026-08-01", "until": "2026-08-28"})],
        label="log-one",
        caller="test",
    )
    assert rs.retrieval_hash
    with get_session() as s:
        after = s.scalar(select(func.count()).select_from(RetrievalLog)) or 0
        row = s.execute(
            select(RetrievalLog).where(RetrievalLog.label == "log-one")
        ).scalars().first()
    assert after == before + 1
    assert row is not None
    assert row.retrieval_hash == rs.retrieval_hash
    assert row.caller == "test"


def test_all_templates_run(retrieval_db):
    from core.retrieval.api import TemplateCall, retrieve
    from core.retrieval.queries import TEMPLATES

    d0 = date(2026, 8, 1)
    d1 = date(2026, 8, 28)
    params = {
        "holdings_current": {},
        "position_transactions": {"ticker": "VST", "since": d0, "until": d1},
        "position_lots": {"ticker": "VST"},
        "position_realized_gl": {"ticker": "VST", "since": d0},
        "signal_events_for_ticker": {"ticker": "VST"},
        "signal_events_for_date": {"event_date": date(2026, 8, 27)},
        "bars_for_ticker": {"ticker": "VST", "since": d0, "until": d1},
        "fundamentals_series": {"ticker": "VST"},
        "rotation_review_for_ticker": {"ticker": "VST"},
        "trade_log_for_ticker": {"ticker": "VST"},
        "tax_control_lots": {},
        "thesis_state_for_ticker": {"ticker": "VST"},
        "corpus_source_type_counts": {},
        "corpus_doc_by_id": {"doc_id": 1},
        "corpus_chunks_for_doc": {"doc_id": 1},
        "decision_view": {},
    }
    for tid in TEMPLATES:
        rs = retrieve(
            queries=[TemplateCall(tid, params[tid])],
            label=f"all-{tid}",
            caller="test",
        )
        assert tid in rs.tables
        rows = rs.tables[tid]
        declared = TEMPLATES[tid].returns
        if declared:
            for row in rows:
                assert set(declared) <= set(row.keys()), (tid, set(declared) - set(row.keys()))


def test_blob_implicit_bet(retrieval_db):
    from core.retrieval.api import TemplateCall, retrieve

    rs = retrieve(
        queries=[TemplateCall("trade_log_for_ticker", {"ticker": "VST"})],
        label="bet",
        caller="test",
    )
    rows = rs.tables["trade_log_for_ticker"]
    assert rows
    assert rows[0]["Implicit_Bet"] == "power demand"
