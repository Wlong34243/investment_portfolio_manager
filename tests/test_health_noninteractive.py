"""Health gate non-interactive behavior."""

from __future__ import annotations

from pathlib import Path

from tasks.health import (
    CheckResult,
    CRITICAL,
    FAIL,
    PIPELINE_LOCK_PATH,
    handle_unattended_critical_failure,
    is_noninteractive_health_gate,
)


def test_is_noninteractive_env_and_no_prompt():
    import os

    assert is_noninteractive_health_gate(no_prompt=True)
    os.environ["MORNING_NONINTERACTIVE"] = "1"
    try:
        assert is_noninteractive_health_gate(no_prompt=False)
    finally:
        os.environ.pop("MORNING_NONINTERACTIVE", None)


def test_unattended_critical_failure_releases_lock(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    lock = log_dir / "pipeline.lock"
    lock.write_text("pid=999", encoding="utf-8")
    monkeypatch.setattr("tasks.health.HEALTH_SENTINEL_PATH", log_dir / "HEALTH_FAILURE.flag")
    monkeypatch.setattr("tasks.health.MORNING_AUTO_LOG", log_dir / "morning_auto.log")
    monkeypatch.setattr("tasks.health.PIPELINE_LOCK_PATH", lock)

    results = [
        CheckResult(
            name="schwab_api_positions",
            label="schwab_api_positions",
            level=CRITICAL,
            status=FAIL,
            detail="Schwab API error: unauthorized",
        )
    ]
    handle_unattended_critical_failure(results)
    assert not lock.exists()
    assert (log_dir / "HEALTH_FAILURE.flag").is_file()
    log_text = (log_dir / "morning_auto.log").read_text(encoding="utf-8")
    assert "schwab_emergency_reauth.bat" in log_text
