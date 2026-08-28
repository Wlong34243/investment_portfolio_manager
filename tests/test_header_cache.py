"""Header cache — TTL + manifest/last_run mtime invalidation; lock always live."""

from unittest.mock import MagicMock

import ui.header_context as hc


def _fake_retrieve(calls: dict):
    def fake_retrieve(**kwargs):
        calls["n"] += 1
        rs = MagicMock()
        rs.retrieval_hash = "abc123"
        rs.tables = {"holdings_current": [{}]}
        return rs

    return fake_retrieve


def test_header_cache_hits_within_ttl(monkeypatch, tmp_path):
    calls = {"n": 0}
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    stable_mtime = 100.0

    monkeypatch.setattr(hc, "retrieve", _fake_retrieve(calls))
    monkeypatch.setattr(hc, "_latest_manifest_path", lambda: manifest)
    monkeypatch.setattr(hc, "_latest_manifest", lambda: {})
    monkeypatch.setattr(hc, "_verify_streak", lambda: "1")
    monkeypatch.setattr(hc, "_schwab_token_status", lambda: "OK")
    monkeypatch.setattr(hc, "_pipeline_lock_state", lambda: {"state": "idle", "detail": "idle"})
    monkeypatch.setattr(hc, "_file_mtime", lambda p: stable_mtime if p == manifest else None)
    hc._HEADER_CACHE = None

    hc.assemble_header()
    hc.assemble_header()
    assert calls["n"] == 1


def test_header_cache_invalidates_on_manifest_mtime_bump(monkeypatch, tmp_path):
    calls = {"n": 0}
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    mtimes = {"manifest": 100.0}

    def file_mtime(path):
        if path == manifest:
            return mtimes["manifest"]
        return None

    monkeypatch.setattr(hc, "retrieve", _fake_retrieve(calls))
    monkeypatch.setattr(hc, "_latest_manifest_path", lambda: manifest)
    monkeypatch.setattr(hc, "_latest_manifest", lambda: {})
    monkeypatch.setattr(hc, "_verify_streak", lambda: "1")
    monkeypatch.setattr(hc, "_schwab_token_status", lambda: "OK")
    monkeypatch.setattr(hc, "_pipeline_lock_state", lambda: {"state": "idle", "detail": "idle"})
    monkeypatch.setattr(hc, "_file_mtime", file_mtime)
    hc._HEADER_CACHE = None

    hc.assemble_header()
    mtimes["manifest"] = 200.0
    hc.assemble_header()
    assert calls["n"] == 2


def test_header_cache_invalidates_on_last_run_mtime_bump(monkeypatch, tmp_path):
    calls = {"n": 0}
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    last_run = tmp_path / "last_run.json"
    mtimes = {"manifest": 100.0, "last_run": None}

    def file_mtime(path):
        if path == manifest:
            return mtimes["manifest"]
        if path == last_run:
            return mtimes["last_run"]
        return None

    monkeypatch.setattr(hc, "LOCK_PATH", tmp_path / "no.lock")
    monkeypatch.setattr(hc, "LAST_RUN_PATH", last_run)
    monkeypatch.setattr(hc, "retrieve", _fake_retrieve(calls))
    monkeypatch.setattr(hc, "_latest_manifest_path", lambda: manifest)
    monkeypatch.setattr(hc, "_latest_manifest", lambda: {})
    monkeypatch.setattr(hc, "_verify_streak", lambda: "1")
    monkeypatch.setattr(hc, "_schwab_token_status", lambda: "OK")
    monkeypatch.setattr(hc, "_pipeline_lock_state", lambda: {"state": "idle", "detail": "idle"})
    monkeypatch.setattr(hc, "_file_mtime", file_mtime)
    hc._HEADER_CACHE = None

    hc.assemble_header()
    last_run.write_text("{}", encoding="utf-8")
    mtimes["last_run"] = 200.0
    hc.assemble_header()
    assert calls["n"] == 2


def test_lock_state_live_on_cache_hit(monkeypatch, tmp_path):
    calls = {"n": 0}
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    lock = tmp_path / "pipeline.lock"

    monkeypatch.setattr(hc, "LOCK_PATH", lock)
    monkeypatch.setattr(hc, "retrieve", _fake_retrieve(calls))
    monkeypatch.setattr(hc, "_latest_manifest_path", lambda: manifest)
    monkeypatch.setattr(hc, "_latest_manifest", lambda: {})
    monkeypatch.setattr(hc, "_verify_streak", lambda: "0")
    monkeypatch.setattr(hc, "_schwab_token_status", lambda: "OK")
    monkeypatch.setattr(hc, "_file_mtime", lambda p: 100.0 if p == manifest else None)
    hc._HEADER_CACHE = None

    h1 = hc.assemble_header()
    assert h1["lock_state"] == "idle"
    assert calls["n"] == 1

    lock.write_text("pid=123", encoding="utf-8")
    h2 = hc.assemble_header()
    assert calls["n"] == 1
    assert h2["lock_state"] == "running"
    assert "running since" in h2["lock_detail"]
    assert h1["position_count"] == h2["position_count"]
