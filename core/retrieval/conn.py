"""Read-only SQLite connection for retrieval templates."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import config


def open_readonly() -> sqlite3.Connection:
    """
    Open SQLITE_DB_PATH read-only. Does not create the file.
    Raises FileNotFoundError naming the path if missing.
    """
    path = Path(config.SQLITE_DB_PATH)
    if not path.is_file():
        raise FileNotFoundError(
            f"retrieval: ledger missing at SQLITE_DB_PATH={path} — "
            "refusing to create an empty DB on the read path"
        )
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn
