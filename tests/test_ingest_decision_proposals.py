"""Tests for tasks/ingest_decision_proposals.py — including Amendment A --file path."""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest

from core.decisions.schema import DecisionRecord
from tasks.ingest_decision_proposals import _validate_file_records, ingest_file

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
    "status": "ratified",
    "proposed_restatement": "Harvest only if multiple and oil are both rich — not on price alone.",
}


def test_whole_file_rejected_on_invalid_record():
    bad = dict(XOM_SAMPLE)
    bad["id"] = "not-valid-id"
    records, errors = _validate_file_records([XOM_SAMPLE, bad])
    assert records == []
    assert errors


def test_forces_proposed_and_extracted():
    records, errors = _validate_file_records([XOM_SAMPLE])
    assert not errors
    assert len(records) == 1
    assert records[0].status == "proposed"
    assert records[0].provenance == "extracted"


def test_ingest_dry_then_live_then_skip(tmp_path, monkeypatch):
    monkeypatch.setattr("tasks.ingest_decision_proposals.PROPOSALS_DIR", tmp_path)
    monkeypatch.setattr("tasks.ingest_decision_proposals.LEDGER_PATH", tmp_path / ".ingested.json")
    monkeypatch.setattr("core.decisions.store.PROPOSALS_DIR", tmp_path)
    drop = tmp_path / "decision-proposals-2026-09-01.json"
    drop.write_text(json.dumps([XOM_SAMPLE]), encoding="utf-8")

    dry = ingest_file(drop, live=False)
    assert dry.get("dry_run")
    assert not (tmp_path / "2026-09-01_XOM_harvest_conjunction.json").exists()

    live = ingest_file(drop, live=True)
    assert live.get("ok")
    assert (tmp_path / "2026-09-01_XOM_harvest_conjunction.json").is_file()

    skip = ingest_file(drop, live=True)
    assert skip.get("skipped")


def test_fixture_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("tasks.ingest_decision_proposals.PROPOSALS_DIR", tmp_path)
    monkeypatch.setattr("tasks.ingest_decision_proposals.LEDGER_PATH", tmp_path / ".ingested.json")
    monkeypatch.setattr("core.decisions.store.PROPOSALS_DIR", tmp_path)
    fixture = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "decision-proposals-sample.json"
    out = ingest_file(fixture, live=True)
    assert out.get("ok")
    data = json.loads((tmp_path / "2026-09-01_XOM_harvest_conjunction.json").read_text(encoding="utf-8"))
    assert data["decided_on_status"] == "unknown"
    assert data["proposed_restatement"]


def test_ingest_module_cannot_write_binding():
    mod = importlib.import_module("tasks.ingest_decision_proposals")
    src = inspect.getsource(mod)
    assert "write_binding" not in src
    assert "vault/decisions" not in src
