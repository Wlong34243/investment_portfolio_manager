"""Desk cockpit — registry safety, allowlist, chart aggregation."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ui.app import UI_WRITE_ROUTE_ALLOWLIST, app
from ui.charts import ChartMarker, _aggregate_markers_by_week
from ui.routines import (
    UI_APPROVED_LIVE_IDS,
    build_argv,
    routine_by_id,
    validate_routine_args,
)


client = TestClient(app)


def test_allowlist_exact():
    found = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        for m in methods:
            if m in {"POST", "PUT", "PATCH", "DELETE"}:
                found.add((m, path))
    assert found == set(UI_WRITE_ROUTE_ALLOWLIST)


def test_no_shell_true_in_ui():
    ui_dir = Path("ui")
    for py in ui_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "shell=True" not in text


def test_routine_id_injection_rejected():
    r = client.post("/run/judge-rotations%3B%20del%20*", json={"args": {}})
    assert r.status_code in (404, 422, 200)
    data = r.json()
    assert "error" in data or r.status_code == 404


def test_ticker_path_traversal_rejected():
    routine = routine_by_id("judge-lifecycle")
    assert routine is not None
    with pytest.raises(ValueError):
        validate_routine_args(routine, {"ticker": "../../etc"})


def test_shares_out_of_range_rejected():
    routine = routine_by_id("tax-project")
    assert routine is not None
    with pytest.raises(ValueError):
        validate_routine_args(routine, {"ticker": "MU", "shares": "1e9"})


def test_build_argv_dry_reconcile_has_no_live():
    routine = routine_by_id("journal-reconcile")
    assert routine is not None
    argv = build_argv(routine, {})
    assert "--live" not in argv


def test_ui_approved_live_routines_exact_set():
    from ui.routines import ROUTINES

    live_ids = {k for k, v in ROUTINES.items() if "--live" in v.argv}
    assert live_ids == set(UI_APPROVED_LIVE_IDS)


def test_confirm_name_required_for_dashboard_refresh():
    routine = routine_by_id("refresh-dashboard-live")
    assert routine is not None
    assert routine.confirm_name is True


def test_confirm_name_not_required_for_backup():
    routine = routine_by_id("store-backup-live")
    assert routine is not None
    assert routine.confirm_name is False


def test_refresh_dashboard_rejected_without_confirm():
    r = client.post("/run/refresh-dashboard-live", json={"args": {}})
    data = r.json()
    assert data.get("error")


def test_rejected_routines_not_registered():
    from ui.routines import ROUTINES

    assert "morning-live" not in ROUTINES
    assert "journal-promote" not in ROUTINES
    assert "store-sync-sheets" not in ROUTINES


def test_same_week_marker_aggregation():
    dates = ("2026-01-06", "2026-01-07", "2026-01-08")
    markers = (
        ChartMarker(0, 100.0, "buy", 6.0, 0),
        ChartMarker(1, 101.0, "buy", 6.0, 1),
        ChartMarker(2, 102.0, "sell", 6.0, 2),
    )
    agg = _aggregate_markers_by_week(markers, dates)
    buys = [m for m in agg if m.side == "buy"]
    assert len(buys) == 1
    assert buys[0].count == 2


def test_cockpit_route_renders():
    r = client.get("/")
    assert r.status_code == 200
    assert "Morning cockpit" in r.text


def test_runs_route_renders():
    r = client.get("/runs")
    assert r.status_code == 200
    assert "Routine launcher" in r.text
