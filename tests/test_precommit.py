"""Pre-commitment capture (Instrument prompt 8)."""

from __future__ import annotations

import ast
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def precommit_db(tmp_path, monkeypatch):
    db = tmp_path / "precommit_test.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db))
    import config

    monkeypatch.setattr(config, "SQLITE_DB_PATH", db)
    import core.store.models as models

    models._engine = None
    models._SessionLocal = None
    yield db
    models._engine = None
    models._SessionLocal = None


def test_precommit_declare(precommit_db, monkeypatch):
    from core.journal import precommit as pc

    monkeypatch.setattr(pc, "thesis_band_raw", lambda *a, **k: 28)
    monkeypatch.setattr(pc, "thesis_band_level", lambda *a, **k: 28.0)

    dry = pc.declare(
        ticker="META",
        trigger_type="fwd_pe",
        side="trim",
        level=28,
        action="trim to 2%",
        note="test",
        live=False,
    )
    assert dry.ok
    assert dry.precommitment_id is None

    live = pc.declare(
        ticker="META",
        trigger_type="fwd_pe",
        side="trim",
        level=28,
        action="trim to 2%",
        note="test",
        live=True,
    )
    assert live.ok and live.precommitment_id is not None
    rows = pc.list_precommitments(ticker="META")
    assert len(rows) == 1
    assert rows[0].thesis_band_at_declaration == 28.0

    mismatch = pc.declare(
        ticker="META",
        trigger_type="fwd_pe",
        side="trim",
        level=18,
        action="trim to 2%",
        live=False,
    )
    assert not mismatch.ok and mismatch.requires_force

    forced = pc.declare(
        ticker="META",
        trigger_type="fwd_pe",
        side="trim",
        level=18,
        action="trim to 2%",
        force=True,
        live=True,
    )
    assert forced.ok


def test_precommit_rejects_consensus(precommit_db, monkeypatch):
    from core.journal import precommit as pc

    monkeypatch.setattr(pc, "thesis_band_raw", lambda *a, **k: "consensus_price_target")
    monkeypatch.setattr(pc, "thesis_band_level", lambda *a, **k: None)
    res = pc.declare(
        ticker="VST",
        trigger_type="price",
        side="trim",
        level=140.0,
        action="trim",
        live=False,
    )
    assert not res.ok
    assert "consensus" in res.message.lower() or "sell-side" in res.message.lower()


def test_precommit_crossing():
    from core.journal.precommit import band_crossed

    assert band_crossed(side="trim", metric=18.0, level=18.0)
    assert band_crossed(side="trim", metric=18.4, level=18.0)
    assert not band_crossed(side="trim", metric=17.9, level=18.0)
    assert band_crossed(side="add", metric=12.0, level=12.0)
    assert band_crossed(side="add", metric=11.5, level=12.0)
    assert not band_crossed(side="add", metric=12.1, level=12.0)


def test_precommit_fire_idempotent(precommit_db, monkeypatch):
    from core.journal import precommit as pc
    from core.store.evidence import record_signal_events, _fingerprint
    from core.store.models import PrecommitmentFiring, get_session
    from sqlalchemy import func, select

    monkeypatch.setattr(pc, "thesis_band_raw", lambda *a, **k: 18)
    monkeypatch.setattr(pc, "thesis_band_level", lambda *a, **k: 18.0)
    decl = pc.declare(
        ticker="META",
        trigger_type="fwd_pe",
        side="trim",
        level=18,
        action="trim to 2%",
        live=True,
    )
    d = date(2026, 8, 27)
    row = {
        "event_date": d,
        "ticker": "META",
        "signal_type": "NEAR_TRIM",
        "trigger_type": "fwd_pe",
        "metric_value": 18.4,
        "band_level": 18.0,
        "band_side": "trim",
        "distance_pct": 0.0,
        "rank_bucket": 0,
        "rank": 1,
        "source": "crosshairs",
        "doctrine_downgraded": False,
        "payload_json": "{}",
        "fingerprint": _fingerprint(d.isoformat(), "META", "NEAR_TRIM", "fwd_pe", "crosshairs"),
    }
    record_signal_events([row], event_date=d, live=True)
    r1 = pc.detect_firings(live=True)
    r2 = pc.detect_firings(live=True)
    assert r1["inserted"] == 1
    assert r2["inserted"] == 0
    assert r2["ignored_duplicate"] >= 1
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(PrecommitmentFiring)) == 1
    assert decl.precommitment_id is not None


def test_precommit_downgraded_still_fires(precommit_db, monkeypatch):
    from core.journal import precommit as pc
    from core.store.evidence import record_signal_events, _fingerprint

    monkeypatch.setattr(pc, "thesis_band_raw", lambda *a, **k: 18)
    monkeypatch.setattr(pc, "thesis_band_level", lambda *a, **k: 18.0)
    pc.declare(
        ticker="UNH",
        trigger_type="fwd_pe",
        side="trim",
        level=18,
        action="trim",
        live=True,
    )
    d = date(2026, 8, 27)
    row = {
        "event_date": d,
        "ticker": "UNH",
        "signal_type": "HOLD_TAX",
        "trigger_type": "fwd_pe",
        "metric_value": 19.0,
        "band_level": 18.0,
        "band_side": "trim",
        "distance_pct": 0.0,
        "rank_bucket": 400,
        "rank": 1,
        "source": "crosshairs",
        "doctrine_downgraded": True,
        "payload_json": "{}",
        "fingerprint": _fingerprint(d.isoformat(), "UNH", "HOLD_TAX", "fwd_pe", "crosshairs"),
    }
    record_signal_events([row], event_date=d, live=True)
    assert pc.detect_firings(live=True)["inserted"] == 1
    pending = pc.list_pending_firings()
    assert len(pending) == 1
    assert pending[0]["doctrine_downgraded"] is True


def test_precommit_no_auto_response():
    """Structurally: only respond_firing assigns acted/passed to a row."""
    src = Path("core/journal/precommit.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    def _fn_name(node):
        for parent in ast.walk(tree):
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(child is node for child in ast.walk(parent)):
                    # Prefer innermost function containing this node
                    pass
        return None

    # Map each Assign of .response to enclosing function name
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack: list[str] = []
            self.hits: list[tuple[str, str]] = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Assign(self, node):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "response":
                    fn = self.stack[-1] if self.stack else "<module>"
                    self.hits.append((fn, ast.dump(node.value)))
            self.generic_visit(node)

    v = Visitor()
    v.visit(tree)
    # Row mutation to acted/passed only inside respond_firing
    for fn, val in v.hits:
        assert fn == "respond_firing", f".response assigned in {fn}: {val}"
    # Inserts always start pending
    assert 'response="pending"' in src.replace(" ", "").replace("'", '"') or (
        "response='pending'" in src.replace(" ", "")
    )


def test_precommit_declared_before_join(precommit_db, monkeypatch):
    from core.journal import precommit as pc
    from core.journal.reconcile import UnreconciledCluster
    from core.journal.propose import build_proposal_for_cluster
    from core.store.evidence import record_signal_events, _fingerprint

    monkeypatch.setattr(pc, "thesis_band_raw", lambda *a, **k: 18)
    monkeypatch.setattr(pc, "thesis_band_level", lambda *a, **k: 18.0)
    # Avoid retrieve() hitting live DB for signal/corpus
    monkeypatch.setattr(
        "core.journal.propose.retrieve",
        lambda **kwargs: type(
            "RS",
            (),
            {
                "retrieval_hash": "x",
                "tables": {},
                "corpus_hits": [],
            },
        )(),
    )

    pc.declare(
        ticker="META",
        trigger_type="fwd_pe",
        side="trim",
        level=18,
        action="trim to 2%",
        live=True,
    )
    d = date(2026, 8, 28)
    row = {
        "event_date": d,
        "ticker": "META",
        "signal_type": "NEAR_TRIM",
        "trigger_type": "fwd_pe",
        "metric_value": 19.0,
        "band_level": 18.0,
        "band_side": "trim",
        "distance_pct": 0.0,
        "rank_bucket": 0,
        "rank": 1,
        "source": "crosshairs",
        "doctrine_downgraded": False,
        "payload_json": "{}",
        "fingerprint": _fingerprint(d.isoformat(), "META", "NEAR_TRIM", "fwd_pe", "crosshairs"),
    }
    record_signal_events([row], event_date=d, live=True)
    pc.detect_firings(live=True)
    pending = pc.list_pending_firings()
    assert pending
    pc.respond_firing(pending[0]["firing_id"], response="acted", live=True)

    cluster = UnreconciledCluster(
        cluster_id="t1",
        fingerprint="abcdef012345",
        fill_date=d,
        sell_tickers=["META"],
        buy_tickers=["CASH"],
        status="promoted",
        source="trade_log",
        implicit_bet="",
    )
    prop = build_proposal_for_cluster(cluster)
    assert prop.rationale_provenance == "declared_before"

    cluster2 = UnreconciledCluster(
        cluster_id="t2",
        fingerprint="abcdef012346",
        fill_date=d,
        sell_tickers=["AMZN"],
        buy_tickers=["CASH"],
        status="promoted",
        source="trade_log",
        implicit_bet="",
    )
    prop2 = build_proposal_for_cluster(cluster2)
    assert prop2.rationale_provenance == "reconstructed_after"


def test_precommit_band_moves(precommit_db, monkeypatch):
    from core.journal import precommit as pc

    monkeypatch.setattr(pc, "thesis_band_raw", lambda *a, **k: 18)
    monkeypatch.setattr(pc, "thesis_band_level", lambda *a, **k: 18.0)
    live = pc.declare(
        ticker="META",
        trigger_type="fwd_pe",
        side="trim",
        level=18,
        action="trim",
        live=True,
    )
    # Simulate thesis band move — existing row unchanged
    monkeypatch.setattr(pc, "thesis_band_level", lambda *a, **k: 20.0)
    rows = pc.list_precommitments(ticker="META")
    assert rows[0].band_level == 18.0
    assert rows[0].thesis_band_at_declaration == 18.0
    assert live.precommitment_id == rows[0].id


def test_precommit_pass_stays_until_respond(precommit_db, monkeypatch):
    from core.journal import precommit as pc
    from core.store.evidence import record_signal_events, _fingerprint

    monkeypatch.setattr(pc, "thesis_band_raw", lambda *a, **k: 12)
    monkeypatch.setattr(pc, "thesis_band_level", lambda *a, **k: 12.0)
    pc.declare(
        ticker="META",
        trigger_type="fwd_pe",
        side="add",
        level=12,
        action="add one step",
        live=True,
    )
    d = date(2026, 8, 27)
    row = {
        "event_date": d,
        "ticker": "META",
        "signal_type": "NEAR_ADD",
        "trigger_type": "fwd_pe",
        "metric_value": 11.0,
        "band_level": 12.0,
        "band_side": "add",
        "distance_pct": 0.0,
        "rank_bucket": 0,
        "rank": 1,
        "source": "crosshairs",
        "doctrine_downgraded": False,
        "payload_json": "{}",
        "fingerprint": _fingerprint(d.isoformat(), "META", "NEAR_ADD", "fwd_pe", "crosshairs"),
    }
    record_signal_events([row], event_date=d, live=True)
    pc.detect_firings(live=True)
    assert pc.pending_count() == 1
    # defer leaves pending
    fid = pc.list_pending_firings()[0]["firing_id"]
    pc.respond_firing(fid, response="d", live=True)
    assert pc.pending_count() == 1
    pc.respond_firing(fid, response="p", note="wait for RL spend print", live=True)
    assert pc.pending_count() == 0
