"""Assertion cards UI and ratification — Amendment A."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from ui.app import app

client = TestClient(app)

XOM_SAMPLE = {
    "id": "2026-09-01_XOM_harvest_conjunction",
    "decided_on": None,
    "decided_on_status": "unknown",
    "scope": "position",
    "tickers": ["XOM"],
    "assertion": "harvest if multiple + oil both rich",
    "conditions": {
        "operator": "all",
        "legs": [
            {"metric": "price", "comparator": "gte", "value": 140.0},
            {"metric": "fwd_pe", "comparator": "gte", "value": 14},
        ],
    },
    "unencodable_conditions": ["oil price rich"],
    "overrides": ["price_trim_above"],
    "falsifier": "",
    "supersedes": None,
    "provenance": "extracted",
    "source_ref": "vault/theses/XOM_thesis.md#L16",
    "status": "proposed",
    "proposed_restatement": "Harvest only if multiple and oil are both rich — not on price alone.",
}


def test_cockpit_no_assertion_panel_without_proposals(monkeypatch):
    monkeypatch.setattr("ui.assertion_cards.load_proposed_assertions", lambda: [])
    r = client.get("/")
    assert r.status_code == 200
    assert "Is this what we're saying?" not in r.text


def test_ratify_reject_does_not_write_binding(tmp_path, monkeypatch):
    from core.decisions.store import write_proposal
    from core.decisions.schema import DecisionRecord

    monkeypatch.setattr("core.decisions.store.PROPOSALS_DIR", tmp_path / "proposals")
    monkeypatch.setattr("core.decisions.store.BINDING_DIR", tmp_path / "decisions")
    monkeypatch.setattr("ui.assertion_cards.ROOT", tmp_path)

    rec = DecisionRecord.from_dict(XOM_SAMPLE)
    write_proposal(rec, live=True)

    r = client.post(
        "/decision/ratify",
        json={"decision_id": rec.id, "action": "reject", "text": "no", "live": True},
    )
    data = r.json()
    assert data.get("ok")
    assert not (tmp_path / "decisions").exists() or not list((tmp_path / "decisions").glob("*.md"))


def test_correct_ratify_keeps_verbatim_assertion_and_restatement(tmp_path, monkeypatch):
    from core.decisions.store import write_proposal
    from core.decisions.schema import DecisionRecord

    monkeypatch.setattr("core.decisions.store.PROPOSALS_DIR", tmp_path / "proposals")
    monkeypatch.setattr("core.decisions.store.BINDING_DIR", tmp_path / "decisions")
    monkeypatch.setattr("ui.assertion_cards.ROOT", tmp_path)

    rec = DecisionRecord.from_dict(XOM_SAMPLE)
    write_proposal(rec, live=True)

    bill_text = "Harvest when both multiple and oil are rich — not on fwd_pe alone."
    r = client.post(
        "/decision/ratify",
        json={
            "decision_id": rec.id,
            "action": "correct",
            "text": bill_text,
            "decided_on": "2026-08-15",
            "live": True,
        },
    )
    data = r.json()
    assert data.get("ok"), data

    binding = (tmp_path / "decisions" / f"{rec.id}.md").read_text(encoding="utf-8")
    assert "harvest if multiple + oil both rich" in binding
    assert bill_text in binding
    assert "Harvest only if multiple and oil are both rich" not in binding
    assert "proposed_restatement" not in binding

    quarantine = json.loads((tmp_path / "proposals" / f"{rec.id}.json").read_text(encoding="utf-8"))
    assert quarantine.get("restatement_author") == "bill"
    assert quarantine.get("proposed_restatement") is None
