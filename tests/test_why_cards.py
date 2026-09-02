"""Tests for ui/why_cards.py — disk reads and dry-run writes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tasks.detect_undocumented_changes import _review_log_dates
from ui.why_cards import (
    load_position_findings,
    newest_briefing_manifest,
    write_position_answer,
)


def test_newest_briefing_manifest_picks_newest(tmp_path: Path):
    old = tmp_path / "ai_briefing_2026-01-01_000000"
    new = tmp_path / "ai_briefing_2026-02-01_000000"
    old.mkdir()
    new.mkdir()
    (old / "manifest.json").write_text("{}", encoding="utf-8")
    mf = new / "manifest.json"
    mf.write_text(json.dumps({"undocumented_changes": {"findings": []}}), encoding="utf-8")
    assert newest_briefing_manifest(tmp_path) == mf


def test_load_position_findings_from_manifest(tmp_path: Path):
    d = tmp_path / "ai_briefing_2026-02-01_000000"
    d.mkdir()
    finding = {
        "code": "NEW_POSITION_NO_THESIS",
        "ticker": "TST",
        "detail": "detail",
        "question": "Why?",
    }
    (d / "manifest.json").write_text(
        json.dumps({"undocumented_changes": {"findings": [finding]}}),
        encoding="utf-8",
    )
    rows = load_position_findings(tmp_path)
    assert len(rows) == 1
    assert rows[0]["question"] == "Why?"


def test_write_position_answer_dry_run(monkeypatch, tmp_path: Path):
    vault = tmp_path / "vault" / "theses"
    vault.mkdir(parents=True)
    target = vault / "ZZZ_thesis.md"
    target.write_text(
        """---
ticker: ZZZ
---
# ZZZ

## Review Log

- 2026-01-01: prior
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("ui.why_cards.ROOT", tmp_path)
    out = write_position_answer("ZZZ", "test rationale", live=False)
    assert out["ok"] is True
    assert out.get("dry_run") is True


def test_review_log_fixture_isolated():
    text = """## Review Log

- 2026-08-01: ok

<!-- region:transaction_log -->
- 2026-08-21: Buy 1.0
<!-- endregion:transaction_log -->
"""
    assert _review_log_dates(text) == ["2026-08-01"]
