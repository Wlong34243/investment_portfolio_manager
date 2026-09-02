"""Tests for utils/build_ai_index.py matching logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils import build_ai_index as bai


def test_no_prose_matching(monkeypatch, tmp_path: Path):
    brief_dir = tmp_path / "ai_briefs"
    brief_dir.mkdir()
    monkeypatch.setattr(bai, "BRIEFS_DIR", brief_dir)
    monkeypatch.setattr(bai, "ENTITY_ALIASES_PATH", tmp_path / "empty_aliases.json")
    (tmp_path / "empty_aliases.json").write_text('{"tickers": {}, "unlisted": []}')
    monkeypatch.setattr(bai, "_held_tickers", lambda: set())

    payload = {
        "headline": "Test",
        "summary": "Apple Inc dominates phones",
        "named_orgs": [],
        "named_systems": [],
        "claims": [],
        "novelty": "explainer",
        "source_quality": "Medium",
    }
    p = brief_dir / "2026-08-31_Test_x_vid1.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    (brief_dir / "2026-08-31_Test_x_vid1.md").write_text("summary only Apple", encoding="utf-8")

    idx = bai.build_index()
    assert idx["rollup"]["brief_count"] == 1
    assert not idx["entries"][0]["exposed"]
    assert not idx["entries"][0]["listed_unheld"]


def test_unlisted_bucket(monkeypatch, tmp_path: Path):
    brief_dir = tmp_path / "ai_briefs"
    brief_dir.mkdir()
    aliases = tmp_path / "ai_entity_aliases.json"
    aliases.write_text(json.dumps({"tickers": {}, "unlisted": ["OpenAI"]}), encoding="utf-8")
    monkeypatch.setattr(bai, "BRIEFS_DIR", brief_dir)
    monkeypatch.setattr(bai, "ENTITY_ALIASES_PATH", aliases)
    monkeypatch.setattr(bai, "_held_tickers", lambda: set())

    payload = {
        "headline": "T",
        "named_orgs": ["OpenAI"],
        "named_systems": [],
        "claims": [{"claim": "x", "claim_type": "release", "specificity": "qualitative", "attributed_to": ""}],
        "novelty": "incremental",
        "source_quality": "High",
    }
    p = brief_dir / "2026-08-31_OAI_x_ab.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    entry = bai.build_index()["entries"][0]
    assert "OpenAI" in entry["unlisted"]


def test_write_index_dry_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bai, "INDEX_PATH", tmp_path / "ai_thematic_index.json")
    assert bai.write_index({"generated_at": "x", "entries": [], "rollup": {}}, live=False) is None
    assert not (tmp_path / "ai_thematic_index.json").exists()
