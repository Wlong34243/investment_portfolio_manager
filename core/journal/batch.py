"""
Batch triage rules for the rationale loop (amended 2026-08-27).

Scope is staging Status, not match_strength:
  - pending: leave untouched (queue, not backlog)
  - promoted + blank Implicit_Bet + fill < evidence accrual → predates_evidence_capture
  - superseded + blank → superseded_cluster (different fact)
  - match_strength weak/none is not the discriminator for pre-accrual fills
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from core.journal.propose import Proposal, EVIDENCE_ACCRUAL_START
from core.journal.reconcile import UnreconciledCluster


@dataclass
class BatchPlan:
    predates: list[UnreconciledCluster]  # promoted-blank, fill < accrual
    superseded: list[UnreconciledCluster]
    pending_skipped: list[UnreconciledCluster]
    post_accrual_promoted: list[UnreconciledCluster]  # wait for real signals
    other: list[UnreconciledCluster]


def _status(c: UnreconciledCluster) -> str:
    return (c.status or "").strip().lower()


def plan_batch(clusters: Iterable[UnreconciledCluster]) -> BatchPlan:
    """
    Split clusters before any write. Only promoted-blank pre-accrual is the
    predates_evidence_capture backlog. pending is never batched.
    """
    already = _already_batch_closed_ids()
    plan = BatchPlan([], [], [], [], [])
    for c in clusters:
        if c.cluster_id in already or (c.fingerprint and c.fingerprint in already):
            continue
        if c.source == "trade_log":
            # Trade_Log blank rows: date-gated only when we treat them as backlog;
            # do not invent staging Status. Pre-accrual → predates; else other.
            if c.fill_date < EVIDENCE_ACCRUAL_START:
                plan.predates.append(c)
            else:
                plan.other.append(c)
            continue

        st = _status(c)
        if st == "pending":
            plan.pending_skipped.append(c)
            continue
        if st == "superseded":
            plan.superseded.append(c)
            continue
        if st == "promoted":
            if c.fill_date < EVIDENCE_ACCRUAL_START:
                plan.predates.append(c)
            else:
                plan.post_accrual_promoted.append(c)
            continue
        plan.other.append(c)
    return plan


def _already_batch_closed_ids() -> set[str]:
    """cluster_id / fingerprint already rejected with a batch_reason — skip re-insert."""
    try:
        from sqlalchemy import select

        from core.store.models import RationaleProposal, get_engine, get_session

        get_engine()
        out: set[str] = set()
        with get_session() as session:
            rows = session.execute(
                select(
                    RationaleProposal.cluster_id,
                    RationaleProposal.cluster_fingerprint,
                ).where(
                    RationaleProposal.status == "rejected",
                    RationaleProposal.batch_reason.is_not(None),
                )
            ).all()
            for cid, fp in rows:
                if cid:
                    out.add(cid)
                if fp:
                    out.add(fp)
        return out
    except Exception:
        return set()


def apply_batch_reasons(clusters: list[UnreconciledCluster]) -> list[Proposal]:
    """
    Build closed-proposal stubs for batch buckets. proposal_text always empty.
    Does not call retrieval — date/status are the discriminator.
    """
    from core.journal.propose import Proposal

    out: list[Proposal] = []
    plan = plan_batch(clusters)
    for c in plan.predates:
        out.append(
            Proposal(
                cluster_id=c.cluster_id,
                fingerprint=c.fingerprint,
                fill_date=c.fill_date,
                sell_tickers=c.sell_tickers,
                buy_tickers=c.buy_tickers,
                match_strength="none",
                proposal_text="",
                evidence_json={"reason": "predates_evidence_capture", "by": "fill_date"},
                source=c.source,
                status=c.status,
                superseded_ids=list(c.superseded_ids),
                batch_reason="predates_evidence_capture",
            )
        )
    for c in plan.superseded:
        out.append(
            Proposal(
                cluster_id=c.cluster_id,
                fingerprint=c.fingerprint,
                fill_date=c.fill_date,
                sell_tickers=c.sell_tickers,
                buy_tickers=c.buy_tickers,
                match_strength="none",
                proposal_text="",
                evidence_json={"reason": "superseded_cluster"},
                source=c.source,
                status=c.status,
                superseded_ids=list(c.superseded_ids),
                batch_reason="superseded_cluster",
            )
        )
    return out


def dollars(c: UnreconciledCluster) -> float:
    """Prefer Sell_Proceeds, else Buy_Amount, from raw row."""
    raw = c.raw or {}
    for key in ("Sell_Proceeds", "Buy_Amount", "Sell Proceeds", "Buy Amount"):
        v = raw.get(key)
        if v is None or v == "":
            continue
        try:
            import pandas as pd
            from utils.sheet_readers import coerce_sheet_numeric_series

            n = float(coerce_sheet_numeric_series(pd.Series([v])).iloc[0])
            if n:
                return abs(n)
        except Exception:
            continue
    return 0.0


def top_by_dollars(
    clusters: Iterable[UnreconciledCluster],
    *,
    n: int = 15,
    status: Optional[str] = "promoted",
) -> list[tuple[UnreconciledCluster, float]]:
    items = []
    for c in clusters:
        if status is not None:
            st = _status(c)
            if status.lower() == "promoted":
                if st != "promoted" and c.source != "trade_log":
                    continue
            elif st != status.lower():
                continue
        items.append((c, dollars(c)))
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:n]
