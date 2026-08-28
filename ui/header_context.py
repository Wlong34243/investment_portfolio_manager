"""Header strip context — freshness contract for every desk page."""

from __future__ import annotations

import copy
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import config
from core.retrieval.api import TemplateCall, retrieve
from core.store.evidence import EVIDENCE_GATE_DAYS, evidence_status

LOCK_PATH = Path("logs") / "pipeline.lock"
LAST_RUN_PATH = Path("logs") / "last_run.json"
_STALE_LOCK_HOURS = 3
_TOKEN_CACHE: tuple[float, str] | None = None
_TOKEN_TTL_SEC = 60.0
_HEADER_CACHE: tuple[float, dict[str, Any], float | None, float | None] | None = None
_HEADER_TTL_SEC = 60.0


def _latest_manifest_path() -> Path | None:
    exports = sorted(Path("exports").glob("ai_briefing_*/manifest.json"))
    return exports[-1] if exports else None


def _file_mtime(path: Path | None) -> float | None:
    if path is None or not path.is_file():
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _latest_manifest() -> dict[str, Any]:
    path = _latest_manifest_path()
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _verify_streak() -> str:
    path = Path(getattr(config, "STORE_VERIFY_STREAK_PATH", "logs/store_verify_streak.jsonl"))
    if not path.is_file():
        return "n/a"
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return "0"
        streak = 0
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                break
            if row.get("ok"):
                streak += 1
            else:
                break
        return str(streak)
    except OSError:
        return "n/a"


def _pipeline_lock_state() -> dict[str, str]:
    if not LOCK_PATH.is_file():
        return {"state": "idle", "detail": "idle"}
    try:
        mtime = datetime.fromtimestamp(LOCK_PATH.stat().st_mtime, tz=timezone.utc)
        age_h = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
        if age_h >= _STALE_LOCK_HOURS:
            return {"state": "idle", "detail": "idle (stale lock ignored)"}
        local = mtime.astimezone().strftime("%H:%M")
        return {"state": "running", "detail": f"running since {local}"}
    except OSError:
        return {"state": "idle", "detail": "idle"}


def _schwab_token_status() -> str:
    global _TOKEN_CACHE
    now = time.monotonic()
    if _TOKEN_CACHE is not None and now - _TOKEN_CACHE[0] < _TOKEN_TTL_SEC:
        return _TOKEN_CACHE[1]
    from tasks.health import desk_schwab_token_summary

    val = desk_schwab_token_summary()
    _TOKEN_CACHE = (now, val)
    return val


def _build_header_body() -> tuple[dict[str, Any], float | None, float | None]:
    rs = retrieve(
        label="header",
        caller="ui",
        queries=[TemplateCall("holdings_current", {})],
    )
    manifest = _latest_manifest()
    composite = manifest.get("composite_hash") or ""
    generated_at = manifest.get("generated_at") or manifest.get("created_at") or ""
    bundle_stale = False
    if generated_at:
        try:
            gen_day = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00")).date()
            bundle_stale = gen_day < date.today()
        except ValueError:
            pass

    ev = evidence_status()
    accrual_day = ev.get("clean_trading_days", 0)
    first_accrual = ev.get("evidence_first_accrual_date")
    gate_clear_date = None
    if first_accrual and accrual_day < EVIDENCE_GATE_DAYS:
        try:
            from datetime import timedelta

            start = date.fromisoformat(str(first_accrual)[:10])
            gate_clear_date = (start + timedelta(days=EVIDENCE_GATE_DAYS * 2)).isoformat()
        except ValueError:
            pass

    verify_streak = _verify_streak()
    streak_hint = ""
    if verify_streak.isdigit() and int(verify_streak) < 5:
        streak_hint = "expected green by 2026-08-31"

    body = {
        "bundle_hash_short": (composite[:12] + "…") if composite else "n/a",
        "composite_hash": composite,
        "generated_at": generated_at,
        "bundle_stale": bundle_stale,
        "schwab_token": _schwab_token_status(),
        "accrual_day": accrual_day,
        "accrual_total": EVIDENCE_GATE_DAYS,
        "accrual_first": first_accrual,
        "gate_clear_date": gate_clear_date,
        "verify_streak": verify_streak,
        "verify_streak_hint": streak_hint,
        "retrieval_hash": rs.retrieval_hash[:12] if rs.retrieval_hash else "",
        "position_count": len(rs.tables.get("holdings_current", [])),
    }
    last_run_mtime = _file_mtime(LAST_RUN_PATH)
    manifest_mtime = _file_mtime(_latest_manifest_path())
    return body, last_run_mtime, manifest_mtime


def assemble_header() -> dict[str, Any]:
    global _HEADER_CACHE
    now = time.monotonic()
    last_run_mtime = _file_mtime(LAST_RUN_PATH)
    manifest_mtime = _file_mtime(_latest_manifest_path())

    if _HEADER_CACHE is not None:
        cached_at, cached_body, cached_lr, cached_mf = _HEADER_CACHE
        if now - cached_at < _HEADER_TTL_SEC:
            if last_run_mtime == cached_lr and manifest_mtime == cached_mf:
                lock = _pipeline_lock_state()
                out = copy.copy(cached_body)
                out["lock_state"] = lock["state"]
                out["lock_detail"] = lock["detail"]
                return out

    body, lr, mf = _build_header_body()
    lock = _pipeline_lock_state()
    body["lock_state"] = lock["state"]
    body["lock_detail"] = lock["detail"]
    _HEADER_CACHE = (now, copy.copy(body), lr, mf)
    return copy.copy(body)
