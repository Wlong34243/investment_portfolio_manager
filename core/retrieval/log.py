"""
Retrieval query log — every retrieve() writes one row.

This is a *write* against the same ledger file the read-only URI opens.
It intentionally uses the SQLAlchemy write engine (core.store.models.get_engine),
not core.retrieval.conn.open_readonly(). Two handles to one file is fine and intended.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from core.store.models import RetrievalLog, get_engine, get_session


def log_retrieval(
    *,
    label: str,
    caller: str,
    template_id: Optional[str],
    params: Any,
    corpus_query: Optional[str],
    row_count: int,
    hit_count: int,
    retrieval_hash: str,
    elapsed_ms: int,
) -> None:
    get_engine()  # ensure table exists
    params_json = json.dumps(params, default=str, sort_keys=True) if params is not None else None
    with get_session() as session:
        session.add(
            RetrievalLog(
                created_at=datetime.now(timezone.utc),
                label=label or "",
                caller=caller or "cli",
                template_id=template_id,
                params_json=params_json,
                corpus_query=corpus_query,
                row_count=int(row_count),
                hit_count=int(hit_count),
                retrieval_hash=retrieval_hash,
                elapsed_ms=int(elapsed_ms),
            )
        )
        session.commit()
