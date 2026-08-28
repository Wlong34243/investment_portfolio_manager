"""Evidence capture: idempotent writes, dry-run, dual-source bars, gate."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def evidence_db(tmp_path, monkeypatch):
    db = tmp_path / "evidence_test.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db))
    # Force config + models engine reset
    import config

    monkeypatch.setattr(config, "SQLITE_DB_PATH", db)
    import core.store.models as models

    models._engine = None
    models._SessionLocal = None
    yield db
    models._engine = None
    models._SessionLocal = None


def _signal_row(ticker: str, event_date: date, signal_type: str = "NEAR_TRIM") -> dict:
    from core.store.evidence import _fingerprint

    source = "crosshairs"
    trigger = "price"
    return {
        "event_date": event_date,
        "ticker": ticker,
        "signal_type": signal_type,
        "trigger_type": trigger,
        "metric_value": 100.0,
        "band_level": 110.0,
        "band_side": "trim",
        "distance_pct": -0.05,
        "rank_bucket": 0,
        "rank": 1,
        "source": source,
        "doctrine_downgraded": False,
        "payload_json": '{"ticker":"%s"}' % ticker,
        "fingerprint": _fingerprint(
            event_date.isoformat(), ticker, signal_type, trigger, source
        ),
    }


def test_evidence_idempotent(evidence_db):
    from sqlalchemy import func, select

    from core.store.evidence import record_signal_events
    from core.store.models import SignalEvent, get_session

    d = date(2026, 8, 27)
    rows = [_signal_row("VST", d), _signal_row("MU", d)]
    r1 = record_signal_events(rows, event_date=d, live=True)
    assert r1.inserted == 2
    assert r1.ignored_duplicate == 0
    r2 = record_signal_events(rows, event_date=d, live=True)
    assert r2.inserted == 0
    assert r2.ignored_duplicate == 2
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(SignalEvent)) == 2


def test_evidence_dry_run(evidence_db):
    from sqlalchemy import func, select

    from core.store.evidence import record_signal_events
    from core.store.models import SignalEvent, get_engine, get_session

    get_engine()
    d = date(2026, 8, 27)
    rows = [_signal_row("VST", d)]
    r = record_signal_events(rows, event_date=d, live=False)
    assert r.attempted == 1
    assert r.inserted == 0
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(SignalEvent)) == 0


def test_evidence_bars_dual_source(evidence_db):
    from sqlalchemy import func, select

    from core.store.evidence import record_bars
    from core.store.models import BarDaily, get_session

    idx = pd.DatetimeIndex([pd.Timestamp("2026-08-26", tz="UTC")])
    df = pd.DataFrame(
        {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100]},
        index=idx,
    )
    r1 = record_bars("MU", df, source="yfinance", live=True)
    r2 = record_bars("MU", df, source="schwab", live=True)
    assert r1.inserted == 1
    assert r2.inserted == 1
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(BarDaily)) == 2


def test_evidence_gate(evidence_db):
    from core.store.evidence import EVIDENCE_GATE_DAYS, evidence_status, record_signal_events

    d0 = date(2026, 8, 1)
    for i in range(3):
        d = d0 + timedelta(days=i)
        record_signal_events(
            [_signal_row("VST", d)],
            event_date=d,
            live=True,
        )
    st = evidence_status()
    assert st["gate_met"] is False
    assert st["clean_trading_days"] == 3
    assert st["gate_remaining"] == EVIDENCE_GATE_DAYS - 3
    assert "NOT MET" in st["gate_line"]
