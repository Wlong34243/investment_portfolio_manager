"""Campaign freshness registry — upserted by lifecycle writer, read by Position Story."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from core.store.models import JudgmentCampaign, get_engine, get_session


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upsert_campaign(
    *,
    ticker: str,
    computed_at: str,
    artifact_path: str,
    json_path: str,
    legs: int,
    retrieval_hash: str,
) -> None:
    get_engine()
    try:
        ts = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
    except ValueError:
        ts = _utcnow()
    with get_session() as session:
        row = session.get(JudgmentCampaign, ticker.upper())
        if row is None:
            row = JudgmentCampaign(ticker=ticker.upper())
            session.add(row)
        row.computed_at = ts
        row.artifact_path = artifact_path
        row.json_path = json_path
        row.legs = legs
        row.retrieval_hash = retrieval_hash
        row.updated_at = _utcnow()
        session.commit()


def get_campaign_registry(ticker: str) -> Optional[dict[str, Any]]:
    get_engine()
    with get_session() as session:
        row = session.get(JudgmentCampaign, ticker.upper())
        if row is None:
            return None
        return {
            "ticker": row.ticker,
            "computed_at": row.computed_at.isoformat() if row.computed_at else None,
            "artifact_path": row.artifact_path,
            "json_path": row.json_path,
            "legs": row.legs,
            "retrieval_hash": row.retrieval_hash,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


def list_registry_rows() -> list[dict[str, Any]]:
    get_engine()
    with get_session() as session:
        rows = session.scalars(
            select(JudgmentCampaign).order_by(JudgmentCampaign.legs.desc())
        ).all()
        return [
            {
                "ticker": r.ticker,
                "computed_at": r.computed_at.isoformat() if r.computed_at else None,
                "artifact_path": r.artifact_path,
                "json_path": r.json_path,
                "legs": r.legs,
                "retrieval_hash": r.retrieval_hash,
            }
            for r in rows
        ]
