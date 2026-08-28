"""SQLite ledger backup + Drive-synced snapshots.

Live ledger may sit outside the repo (SQLITE_DB_PATH absolute, off Drive).
Snapshots deliberately stay under the repo's data/portfolio_store_backups/ so
Drive sync carries the offsite copy after the ledger leaves the synced tree.
BACKUP_DIR is anchored to the repo root — never to cwd — so `pm store backup`
from another working directory cannot silently write to <cwd>/data/...
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = REPO_ROOT / "data" / "portfolio_store_backups"
DEFAULT_DRIVE_DB_SUBDIR = "db_backups"

# Snapshot retention (prompt 1 Step 5)
SNAPSHOT_KEEP_DAILY = 14
SNAPSHOT_KEEP_WEEKLY = 8  # Monday's
SNAPSHOT_KEEP_MONTHLY = 12  # the 1st
SNAPSHOT_STALE_HOURS = 48


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_stamp(name: str) -> Optional[datetime]:
    """Parse portfolio_store_YYYYMMDD.db or portfolio_store_YYYYMMDDTHHMMSSZ.db."""
    stem = name.replace("portfolio_store_", "").replace(".db", "")
    try:
        if "T" in stem:
            return datetime.strptime(stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return datetime.strptime(stem[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def backup_sqlite(
    *,
    live: bool = False,
    dest_drive: Optional[str] = None,
) -> dict:
    """
    Phase 1 acceptance backup.

    1. Ensure source DB exists (create empty schema if needed).
    2. VACUUM INTO a dated file under repo data/portfolio_store_backups/.
    3. Write .sha256 sidecar.
    4. If live and Drive root is mounted, copy both into
       {PORTFOLIO_ANALYSIS_DRIVE_DIR}/db_backups/.

    Dry-run reports intended paths without writing.
    """
    from core.store.models import get_engine

    get_engine()  # ensure schema exists
    src = Path(config.SQLITE_DB_PATH)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"portfolio_store_{stamp}.db"
    sha_path = Path(str(dest) + ".sha256")

    drive_root = Path(
        dest_drive
        or os.getenv(
            "PORTFOLIO_ANALYSIS_DRIVE_DIR",
            r"G:\My Drive\Portfolio_Analysis",
        )
    )
    drive_db = drive_root / DEFAULT_DRIVE_DB_SUBDIR

    result = {
        "live": live,
        "source": str(src),
        "backup": str(dest),
        "sha256": None,
        "drive_copy": None,
        "warn": None,
        "ok": False,
        "pruned": {
            "keep_daily": config.STORE_BACKUP_KEEP_DAILY,
            "keep_weekly": config.STORE_BACKUP_KEEP_WEEKLY,
            "deleted": [],
            "dry_run": True,
        },
    }

    if not live:
        result["ok"] = True
        result["warn"] = "DRY RUN — pass --live to VACUUM INTO + hash + Drive copy"
        return result

    if not src.exists():
        result["warn"] = f"Source DB missing: {src}"
        return result

    lock_path = Path(str(src) + ".backup.lock")
    lock_fd: Optional[int] = None
    try:
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, f"{os.getpid()}\n".encode("utf-8"))
        except FileExistsError:
            result["warn"] = (
                f"SKIPPED — backup lock held ({lock_path}). Concurrent write/backup; retry later."
            )
            result["ok"] = True
            result["pruned"]["dry_run"] = False
            result["pruned"]["skipped"] = True
            return result

        conn = sqlite3.connect(str(src), timeout=0.25)
        try:
            conn.execute(f"VACUUM INTO '{dest.as_posix()}'")
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "locked" in msg or "busy" in msg:
                result["warn"] = (
                    f"SKIPPED — database locked during VACUUM INTO: {e}. Retry later."
                )
                result["ok"] = True
                result["pruned"]["dry_run"] = False
                result["pruned"]["skipped"] = True
                return result
            raise
        finally:
            conn.close()
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
            lock_path.unlink(missing_ok=True)

    digest = _sha256_file(dest)
    sha_path.write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
    result["sha256"] = digest

    if not drive_root.parent.exists():
        result["warn"] = f"Drive parent not mounted: {drive_root.parent} — local backup kept"
        result["ok"] = True
        return result

    drive_db.mkdir(parents=True, exist_ok=True)
    drive_dest = drive_db / dest.name
    drive_sha = drive_db / sha_path.name
    shutil.copy2(dest, drive_dest)
    shutil.copy2(sha_path, drive_sha)
    result["drive_copy"] = str(drive_dest)
    result["ok"] = True
    logger.info("sqlite backup %s sha256=%s drive=%s", dest, digest[:12], drive_dest)

    pruned = prune_backups(
        local_dir=BACKUP_DIR,
        drive_dir=drive_db if drive_db.exists() else None,
        keep_daily=config.STORE_BACKUP_KEEP_DAILY,
        keep_weekly=config.STORE_BACKUP_KEEP_WEEKLY,
    )
    result["pruned"] = pruned
    return result


def snapshot_sqlite(*, live: bool = False) -> dict:
    """
    Daily VACUUM INTO snapshot under repo data/portfolio_store_backups/.

    Destination stays inside the Drive-synced tree on purpose: after the live
    ledger relocates off Drive, these snapshots are the offsite copy. Do not
    "fix" by moving BACKUP_DIR next to SQLITE_DB_PATH.
    """
    from core.store.models import get_engine

    get_engine()
    src = Path(config.SQLITE_DB_PATH)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"portfolio_store_{day}.db"

    result = {
        "live": live,
        "source": str(src),
        "source_bytes": src.stat().st_size if src.exists() else None,
        "snapshot": str(dest),
        "ok": False,
        "warn": None,
        "pruned": None,
    }

    if not live:
        result["ok"] = True
        result["warn"] = "DRY RUN — pass --live to VACUUM INTO snapshot"
        return result

    if not src.exists():
        result["warn"] = f"Source DB missing: {src}"
        return result

    # Overwrite same-calendar-day snapshot via temp then replace
    tmp = BACKUP_DIR / f"portfolio_store_{day}.db.tmp"
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(src))
    try:
        conn.execute(f"VACUUM INTO '{tmp.as_posix()}'")
    finally:
        conn.close()
    if dest.exists():
        dest.unlink()
    tmp.rename(dest)
    result["ok"] = True
    result["snapshot_bytes"] = dest.stat().st_size

    pruned = prune_snapshots(BACKUP_DIR, live=True)
    result["pruned"] = pruned
    return result


def prune_snapshots(local_dir: Path, *, live: bool = False) -> dict:
    """
    Keep 14 daily, 8 weekly (Monday), 12 monthly (1st).
    Refuse if newest snapshot is older than 48h.
    Print every filename before deleting (caller should print deleted list).
    """
    out = {
        "deleted": [],
        "refused": None,
        "keep_daily": SNAPSHOT_KEEP_DAILY,
        "keep_weekly": SNAPSHOT_KEEP_WEEKLY,
        "keep_monthly": SNAPSHOT_KEEP_MONTHLY,
    }
    if not local_dir.exists():
        return out

    dbs = sorted(local_dir.glob("portfolio_store_*.db"), reverse=True)
    if not dbs:
        return out

    newest_ts = None
    for p in dbs:
        ts = _parse_stamp(p.name)
        if ts and (newest_ts is None or ts > newest_ts):
            newest_ts = ts
    if newest_ts is None:
        out["refused"] = "could not parse newest snapshot stamp"
        return out
    age = datetime.now(timezone.utc) - newest_ts
    if age > timedelta(hours=SNAPSHOT_STALE_HOURS):
        out["refused"] = (
            f"newest snapshot {newest_ts.isoformat()} is older than "
            f"{SNAPSHOT_STALE_HOURS}h — prune refused"
        )
        return out

    if not live:
        return out

    keep: set[Path] = set()
    # daily: newest N
    for p in dbs[:SNAPSHOT_KEEP_DAILY]:
        keep.add(p)

    mondays: dict[str, Path] = {}
    firsts: dict[str, Path] = {}
    for p in dbs:
        ts = _parse_stamp(p.name)
        if ts is None:
            continue
        d = ts.date()
        if d.weekday() == 0:  # Monday
            iso = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
            if iso not in mondays:
                mondays[iso] = p
        if d.day == 1:
            ym = f"{d.year:04d}-{d.month:02d}"
            if ym not in firsts:
                firsts[ym] = p

    for i, (_k, p) in enumerate(sorted(mondays.items(), reverse=True)):
        if i < SNAPSHOT_KEEP_WEEKLY:
            keep.add(p)
    for i, (_k, p) in enumerate(sorted(firsts.items(), reverse=True)):
        if i < SNAPSHOT_KEEP_MONTHLY:
            keep.add(p)

    for p in dbs:
        if p in keep:
            continue
        print(f"prune snapshot: {p}")
        sha = Path(str(p) + ".sha256")
        p.unlink(missing_ok=True)
        sha.unlink(missing_ok=True)
        out["deleted"].append(str(p))
    return out


def prune_backups(
    *,
    local_dir: Path,
    drive_dir: Optional[Path],
    keep_daily: int = 14,
    keep_weekly: int = 8,
) -> dict:
    """
    Keep last `keep_daily` dated backups; additionally keep one per ISO week
    for `keep_weekly` weeks. Deletes older .db and matching .sha256.
    """
    deleted: list[str] = []

    def _prune(folder: Path) -> None:
        if not folder or not folder.exists():
            return
        dbs = sorted(folder.glob("portfolio_store_*.db"), reverse=True)
        keep: set[Path] = set()
        for p in dbs[:keep_daily]:
            keep.add(p)
        weeks: dict[str, Path] = {}
        for p in dbs:
            name = p.name
            try:
                stamp = name.replace("portfolio_store_", "").replace(".db", "")
                d = datetime.strptime(stamp[:8], "%Y%m%d").date()
            except ValueError:
                continue
            iso = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
            if iso not in weeks:
                weeks[iso] = p
        for i, (_iso, p) in enumerate(sorted(weeks.items(), reverse=True)):
            if i < keep_weekly:
                keep.add(p)
        for p in dbs:
            if p in keep:
                continue
            sha = Path(str(p) + ".sha256")
            p.unlink(missing_ok=True)
            sha.unlink(missing_ok=True)
            deleted.append(str(p))

    _prune(local_dir)
    if drive_dir is not None:
        _prune(drive_dir)
    return {
        "keep_daily": keep_daily,
        "keep_weekly": keep_weekly,
        "deleted": deleted,
    }


def provenance_table() -> str:
    """Markdown table: if the local ledger were lost, what could Schwab not give back?"""
    rows = [
        ("transactions", "SQLite + Sheets", "Schwab API (broker retention ~10y typical; confirm in account docs)", "REGENERABLE (bounded)"),
        ("realized_gl", "SQLite + Sheets", "Schwab Lot Details / Chase export", "REGENERABLE (bounded)"),
        ("holdings_current", "SQLite + Sheets", "Schwab positions fetch", "REGENERABLE"),
        ("tax_control_lots", "SQLite + Sheets", "Schwab tax lots", "REGENERABLE (bounded)"),
        ("Trade_Log Implicit_Bet / Thesis_Brief", "Sheets Trade_Log", "Bill's writing only", "NOT REGENERABLE"),
        ("vault/theses/", "git", "Bill's writing (in git)", "IN GIT"),
        ("vault/doctrine.md", "git", "Bill's writing (in git)", "IN GIT"),
        ("data/podcast_transcripts/", "disk (gitignored)", "YouTube while URL lives", "EFFECTIVELY NOT REGENERABLE"),
        ("data/podcast_summaries/", "disk (gitignored)", "model output; not re-runnable to same text", "NOT REGENERABLE"),
        ("data/spotify_digests/", "disk (gitignored)", "Studio artifacts while present", "EFFECTIVELY NOT REGENERABLE"),
        ("data/moments/", "disk (gitignored)", "derived from transcripts", "EFFECTIVELY NOT REGENERABLE"),
        ("agent_outputs/", "disk (gitignored)", "model output; not reproducible", "NOT REGENERABLE"),
        ("signal_events", "SQLite evidence", "permanent Crosshairs record", "NOT REGENERABLE"),
        ("bars_daily", "SQLite evidence", "permanent bar record (source-keyed)", "NOT REGENERABLE"),
        ("fundamentals_snapshot", "SQLite evidence", "permanent fundamentals record", "NOT REGENERABLE"),
        ("corpus_fts / corpus_docs", "SQLite", "rebuild from filesystem via pm corpus index", "REGENERABLE"),
    ]
    lines = [
        "| Data class | Location | Regenerable from | Verdict |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    return "\n".join(lines)
