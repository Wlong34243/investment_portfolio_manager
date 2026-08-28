"""Bounded morning campaign refresh — yesterday's fills only."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _parse_txn_date(val: Any) -> date | None:
    if val is None:
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def tickers_with_fill_on(target: date) -> list[str]:
    from core.retrieval.api import TemplateCall, retrieve

    rs = retrieve(
        label="morning_fill_tickers",
        caller="cli",
        queries=[TemplateCall("holdings_current", {})],
    )
    tickers = {
        str(r.get("ticker") or "").upper()
        for r in rs.tables.get("holdings_current", [])
        if r.get("ticker")
    }
    found: set[str] = set()
    for t in tickers:
        if not t or t == "CASH_MANUAL":
            continue
        tx_rs = retrieve(
            label=f"fills:{t}",
            caller="cli",
            queries=[
                TemplateCall(
                    "position_transactions",
                    {"ticker": t, "since": target - timedelta(days=3), "until": target + timedelta(days=1)},
                )
            ],
        )
        for row in tx_rs.tables.get("position_transactions", []):
            d = _parse_txn_date(row.get("trade_date"))
            if d == target:
                found.add(t)
                break
    return sorted(found)


def recompute_campaigns_for_yesterday(*, live: bool = True) -> dict[str, Any]:
    """Recompute lifecycle artifacts for tickers that filled yesterday. CLI-only."""
    if not live:
        return {"live": False, "tickers": [], "skipped": "dry-run"}

    yesterday = date.today() - timedelta(days=1)
    tickers = tickers_with_fill_on(yesterday)
    if not tickers:
        return {"live": True, "tickers": [], "date": yesterday.isoformat()}

    from core.judgment.lifecycle import format_campaign_markdown, retrieve_campaign
    from core.judgment.run import write_judgment_report

    updated: list[str] = []
    for t in tickers:
        try:
            camp, rs = retrieve_campaign(t)
            if camp is None:
                continue
            body = format_campaign_markdown(camp, retrieval_hash=rs.retrieval_hash)
            meta = {"unit": "B", "ticker": camp.ticker, "retrieval_hash": rs.retrieval_hash}
            write_judgment_report(body, meta, slug=f"lifecycle_{t.lower()}", campaign=camp)
            updated.append(t)
        except Exception as exc:
            logger.warning("morning increment failed for %s: %s", t, exc)
    return {"live": True, "tickers": updated, "date": yesterday.isoformat()}
