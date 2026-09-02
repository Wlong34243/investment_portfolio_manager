"""Tests for core/decisions/ schema, validate, store — including Amendment A."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.decisions.schema import DecisionRecord
from core.decisions.source_text import assertion_in_source
from core.decisions.store import write_binding, write_proposal
from core.decisions.validate import validate

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

GLD_SAMPLE = {
    "id": "2026-08-14_GLD_size_and_role",
    "decided_on": "2026-08-14",
    "decided_on_status": "known",
    "scope": "position",
    "tickers": ["GLD"],
    "assertion": "do not trim on price up alone",
    "conditions": {"operator": "all", "legs": [{"metric": "price", "comparator": "gte", "value": 400}]},
    "unencodable_conditions": [],
    "overrides": ["price_trim_above"],
    "falsifier": "Exit condition 4.",
    "supersedes": None,
    "provenance": "extracted",
    "source_ref": "vault/theses/GLD_thesis.md#L73",
    "status": "proposed",
    "ratified_on": None,
}


def test_unencodable_conditions_required():
    bad = dict(GLD_SAMPLE)
    del bad["unencodable_conditions"]
    with pytest.raises(KeyError):
        DecisionRecord.from_dict(bad)


def test_decided_on_status_required():
    bad = dict(GLD_SAMPLE)
    del bad["decided_on_status"]
    with pytest.raises(KeyError):
        DecisionRecord.from_dict(bad)


def test_validate_rejects_known_without_date():
    rec = DecisionRecord.from_dict({**GLD_SAMPLE, "decided_on": None, "decided_on_status": "known"})
    errs = validate(rec, target="ingest")
    assert any("decided_on must be set" in e for e in errs)


def test_validate_rejects_unknown_with_date():
    rec = DecisionRecord.from_dict({**XOM_SAMPLE, "decided_on": "2026-08-09", "decided_on_status": "unknown"})
    errs = validate(rec, target="ingest")
    assert any("must be null" in e for e in errs)


def test_validate_rejects_non_substring_assertion():
    rec = DecisionRecord.from_dict({**XOM_SAMPLE, "assertion": "Harvest only if multiple and oil are both rich"})
    errs = validate(rec, target="ingest")
    assert any("not found on line" in e or "not found" in e for e in errs)


def test_validate_rejects_assertion_on_wrong_line():
    rec = DecisionRecord.from_dict({**XOM_SAMPLE, "source_ref": "vault/theses/XOM_thesis.md#L3"})
    errs = validate(rec, target="ingest")
    assert any("line 3" in e for e in errs)


def test_validate_accepts_verbatim_xom_with_proposed_restatement():
    rec = DecisionRecord.from_dict(XOM_SAMPLE)
    assert validate(rec, target="ingest") == []
    assert rec.proposed_restatement


def test_assertion_in_source_line_suffix():
    assert assertion_in_source("harvest if multiple + oil both rich", "vault/theses/XOM_thesis.md#L16")


def test_validate_rejects_ratified_on_ingest():
    rec = DecisionRecord.from_dict({**GLD_SAMPLE, "status": "ratified"})
    errs = validate(rec, target="ingest")
    assert any("ratified" in e for e in errs)


def test_write_binding_requires_ratification():
    rec = DecisionRecord.from_dict({**GLD_SAMPLE, "status": "proposed"})
    out = write_binding(rec, ratification=False, live=False)
    assert not out["ok"]
    assert "ratification" in out["error"]


def test_write_binding_strips_proposed_restatement(tmp_path, monkeypatch):
    monkeypatch.setattr("core.decisions.store.PROPOSALS_DIR", tmp_path / "proposals")
    monkeypatch.setattr("core.decisions.store.BINDING_DIR", tmp_path / "decisions")
    rec = DecisionRecord.from_dict(
        {
            **GLD_SAMPLE,
            "status": "ratified",
            "ratified_on": "2026-08-14",
            "proposed_restatement": "should not appear in binding",
        }
    )
    out = write_binding(rec, ratification=True, live=True)
    assert out["ok"]
    text = Path(out["path"]).read_text(encoding="utf-8")
    assert "proposed_restatement" not in text
    assert "should not appear" not in text


def test_write_binding_includes_restatement_section(tmp_path, monkeypatch):
    monkeypatch.setattr("core.decisions.store.PROPOSALS_DIR", tmp_path / "proposals")
    monkeypatch.setattr("core.decisions.store.BINDING_DIR", tmp_path / "decisions")
    rec = DecisionRecord.from_dict(
        {
            **GLD_SAMPLE,
            "status": "ratified",
            "ratified_on": "2026-08-14",
            "restatement": "Size-and-role governs trimming, not the 400 print alone.",
            "restatement_author": "bill",
        }
    )
    out = write_binding(rec, ratification=True, live=True)
    text = Path(out["path"]).read_text(encoding="utf-8")
    assert "## Restatement (bill)" in text
    assert "Size-and-role governs trimming" in text
    assert "do not trim on price up alone" in text


def test_write_proposal_quarantine(tmp_path, monkeypatch):
    monkeypatch.setattr("core.decisions.store.PROPOSALS_DIR", tmp_path)
    rec = DecisionRecord.from_dict(XOM_SAMPLE)
    out = write_proposal(rec, live=True)
    assert out["ok"]
    data = json.loads((tmp_path / f"{rec.id}.json").read_text(encoding="utf-8"))
    assert data["status"] == "proposed"
    assert data["proposed_restatement"]
