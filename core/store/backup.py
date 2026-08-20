"""SQLite ledger backup: VACUUM INTO + SHA-256 + optional Drive copy."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

BACKUP_DIR = Path("data") / "portfolio_store_backups"
DEFAULT_DRIVE_DB_SUBDIR = "db_backups"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_sqlite(
    *,
    live: bool = False,
    dest_drive: Optional[str] = None,
) -> dict:
    """
    Phase 1 acceptance backup.

    1. Ensure source DB exists (create empty schema if needed).
    2. VACUUM INTO a dated file under data/portfolio_store_backups/.
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
    }

    if not live:
        result["ok"] = True
        result["warn"] = "DRY RUN — pass --live to VACUUM INTO + hash + Drive copy"
        return result

    if not src.exists():
        result["warn"] = f"Source DB missing: {src}"
        return result

    # VACUUM INTO requires a new destination path and exclusive access.
    conn = sqlite3.connect(str(src))
    try:
        conn.execute(f"VACUUM INTO '{dest.as_posix()}'")
    finally:
        conn.close()

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
        # daily
        for p in dbs[:keep_daily]:
            keep.add(p)
        # weekly: parse stamp portfolio_store_YYYYMMDDTHHMMSSZ.db
        weeks: dict[str, Path] = {}
        for p in dbs:
            name = p.name
            try:
                stamp = name.replace("portfolio_store_", "").replace(".db", "")
                d = datetime.strptime(stamp[:8], "%Y%m%d").date()
            except ValueError:
                continue
            iso = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
            # keep earliest of each week among remaining (oldest stamp in week =
            # first seen when iterating reverse chrono... use first = newest)
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
