"""Subprocess runner for desk routines — one at a time, SSE stdout stream."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator

from core.store.models import UiRun, get_engine, get_session
from ui.routines import Routine, build_argv, is_ui_launchable, routine_by_id, validate_routine_args

ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = Path("logs") / "pipeline.lock"
_STALE_LOCK_HOURS = 3
_ARTIFACT_RE = re.compile(r"(agent_outputs[/\\][^\s\]]+\.(?:md|json|txt|html))", re.IGNORECASE)

_lock = threading.Lock()
_active: dict[str, Any] | None = None


@dataclass
class RunState:
    run_id: int
    routine_id: str
    label: str
    lines: list[str] = field(default_factory=list)
    finished: bool = False
    exit_code: int | None = None
    artifact_path: str | None = None


_runs: dict[int, RunState] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def pipeline_lock_held() -> tuple[bool, str]:
    if not LOCK_PATH.is_file():
        return False, ""
    try:
        mtime = datetime.fromtimestamp(LOCK_PATH.stat().st_mtime, tz=timezone.utc)
        age_h = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
        if age_h >= _STALE_LOCK_HOURS:
            return False, ""
        return True, mtime.astimezone().strftime("%Y-%m-%d %H:%M")
    except OSError:
        return False, ""


def active_run() -> RunState | None:
    with _lock:
        if _active is None:
            return None
        rid = _active.get("run_id")
        return _runs.get(rid)


def _parse_artifact(stdout: str) -> str | None:
    for line in stdout.splitlines():
        m = _ARTIFACT_RE.search(line)
        if m:
            return m.group(1).replace("\\", "/")
        if "Wrote" in line and "agent_outputs" in line:
            parts = line.split()
            for p in parts:
                if "agent_outputs" in p:
                    return p.strip("`[]").replace("\\", "/")
    return None


def _insert_run(routine_id: str, args: dict[str, str]) -> int:
    get_engine()
    with get_session() as session:
        row = UiRun(
            routine_id=routine_id,
            args_json=json.dumps(args, sort_keys=True),
            started_at=_utcnow(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id)


def _finish_run(run_id: int, exit_code: int, artifact: str | None) -> None:
    get_engine()
    with get_session() as session:
        row = session.get(UiRun, run_id)
        if row:
            row.finished_at = _utcnow()
            row.exit_code = exit_code
            row.artifact_path = artifact
            session.commit()


def insert_desk_write_run(route_id: str, args: dict[str, Any]) -> int:
    """Insert ui_runs row for inline desk writes (why-cards, etc.)."""
    safe_args = {k: str(v) for k, v in args.items()}
    run_id = _insert_run(route_id, safe_args)
    _finish_run(run_id, 0, None)
    return run_id


def list_ui_runs(limit: int = 50) -> list[dict[str, Any]]:
    get_engine()
    from sqlalchemy import select

    with get_session() as session:
        rows = session.scalars(
            select(UiRun).order_by(UiRun.id.desc()).limit(limit)
        ).all()
        out = []
        for r in rows:
            dur = None
            if r.started_at and r.finished_at:
                dur = (r.finished_at - r.started_at).total_seconds()
            out.append(
                {
                    "id": r.id,
                    "routine_id": r.routine_id,
                    "args_json": r.args_json,
                    "started_at": r.started_at.isoformat() if r.started_at else "",
                    "finished_at": r.finished_at.isoformat() if r.finished_at else "",
                    "exit_code": r.exit_code,
                    "artifact_path": r.artifact_path,
                    "duration_sec": dur,
                }
            )
        return out


def start_run(
    routine_id: str,
    raw_args: dict[str, Any],
    *,
    confirm_name: str | None = None,
) -> tuple[int, str | None]:
    """
    Start a routine. Returns (run_id, error_message).
    error_message is set when refused (lock, busy, validation).
    ui_runs row is inserted before subprocess starts.
    """
    global _active

    routine = routine_by_id(routine_id)
    if routine is None or not is_ui_launchable(routine_id):
        return 0, f"Unknown or disallowed routine: {routine_id!r}"

    if routine.confirm_name and confirm_name != routine_id:
        return 0, f"Type {routine_id!r} exactly to confirm this run"

    held, since = pipeline_lock_held()
    if held:
        return 0, f"Pipeline lock held since {since} — skipped (exit-3 semantics)"

    with _lock:
        if _active is not None:
            other = _active.get("label", _active.get("routine_id", "unknown"))
            return 0, f"Run already in progress: {other}"

    try:
        args = validate_routine_args(routine, raw_args)
    except ValueError as e:
        return 0, str(e)

    argv_tail = build_argv(routine, args)
    cmd = [sys.executable, str(ROOT / argv_tail[0]), *argv_tail[1:]]

    # Record intent before execution (amendment requirement for all launchable runs).
    run_id = _insert_run(routine_id, args)
    state = RunState(run_id=run_id, routine_id=routine_id, label=routine.label)
    _runs[run_id] = state
    if routine.writes_banner:
        state.lines.append(f"[writes] {routine.writes_banner}")

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}

    def _worker() -> None:
        global _active
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        with _lock:
            _active = {"run_id": run_id, "routine_id": routine_id, "label": routine.label, "proc": proc}
        try:
            assert proc.stdout is not None
            import time

            deadline = time.time() + routine.timeout_sec
            stdout_parts: list[str] = []
            while True:
                line = proc.stdout.readline()
                if line:
                    state.lines.append(line.rstrip("\n"))
                    stdout_parts.append(line)
                    continue
                if proc.poll() is not None:
                    state.exit_code = proc.returncode
                    break
                if time.time() > deadline:
                    proc.kill()
                    state.lines.append(f"[timeout after {routine.timeout_sec}s]")
                    state.exit_code = 124
                    break
                time.sleep(0.05)
        except Exception as exc:
            state.lines.append(f"[runner error: {exc}]")
            state.exit_code = 1
        state.finished = True
        full = "".join(stdout_parts)
        state.artifact_path = _parse_artifact(full)
        _finish_run(run_id, state.exit_code or 0, state.artifact_path)
        with _lock:
            if _active and _active.get("run_id") == run_id:
                _active = None

    t = threading.Thread(target=_worker, daemon=True)
    with _lock:
        _active = {"run_id": run_id, "routine_id": routine_id, "label": routine.label}
    t.start()
    return run_id, None


def stream_run(run_id: int) -> Generator[str, None, None]:
    """SSE generator — yields data lines for new stdout."""
    state = _runs.get(run_id)
    if state is None:
        yield "event: error\ndata: run not found\n\n"
        return
    sent = 0
    while True:
        while sent < len(state.lines):
            line = state.lines[sent].replace("\n", " ")
            yield f"data: {line}\n\n"
            sent += 1
        if state.finished:
            payload = json.dumps(
                {
                    "exit_code": state.exit_code,
                    "artifact_path": state.artifact_path,
                }
            )
            yield f"event: done\ndata: {payload}\n\n"
            break
        import time

        time.sleep(0.15)
