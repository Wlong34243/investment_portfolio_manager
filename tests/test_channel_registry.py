"""Tests for utils/channel_registry.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils import channel_registry as cr


def test_load_channels_counts():
    all_ch = cr.load_channels()
    finance = cr.load_channels("finance")
    ai = cr.load_channels("ai")
    assert len(all_ch) == 23
    assert len(finance) == 14
    assert len(ai) == 9


def test_legacy_dict_on_investing_title_filter():
    d = cr.channels_as_legacy_dict("finance")
    assert d["On Investing"]["title_filter"] == "On Investing"
    assert len(d) == 14


def test_dedup_track_defaults_finance():
    assert cr.dedup_track({}) == "finance"
    assert cr.dedup_track({"track": "ai"}) == "ai"


def test_bad_track_raises(tmp_path: Path, monkeypatch):
    bad = {
        "schema_version": 1,
        "channels": [
            {
                "name": "Bad Track",
                "channel_id": "UCkrwgzhIBKccuDsi_SvZtnQ",
                "track": "macro",
                "enabled": True,
            }
        ],
    }
    p = tmp_path / "podcast_channels.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(cr, "REGISTRY_PATH", p)
    with pytest.raises(ValueError, match="invalid track"):
        cr.load_channels()


def test_duplicate_id_raises(tmp_path: Path, monkeypatch):
    dup = {
        "schema_version": 1,
        "channels": [
            {
                "name": "A",
                "channel_id": "UCkrwgzhIBKccuDsi_SvZtnQ",
                "track": "finance",
                "enabled": True,
            },
            {
                "name": "B",
                "channel_id": "UCkrwgzhIBKccuDsi_SvZtnQ",
                "track": "finance",
                "enabled": True,
            },
        ],
    }
    p = tmp_path / "podcast_channels.json"
    p.write_text(json.dumps(dup), encoding="utf-8")
    monkeypatch.setattr(cr, "REGISTRY_PATH", p)
    with pytest.raises(ValueError, match="Duplicate channel_id"):
        cr.load_channels()
