"""Persist rationale_proposals. Implicit_Bet is never written here."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from core.journal.propose import Proposal
from core.store.models import RationaleProposal, get_engine, get_session

# Reconcile path may only set reconstructed_after — never declared_before.
PROVENANCE_RECONCILE = "reconstructed_after"

# Closed status vocabulary — amend prompts/rationale_loop + state.md if extended.
PROPOSAL_STATUSES = frozenset(
    {
        "open",
        "confirmed",
        "edited",
        "rejected",
        "deferred",
        "void_scope",  # not dismissed — outside signed-off population / written in error
    }
)


def _require_status(status: str) -> str:
    s = (status or "").strip()
    if s not in PROPOSAL_STATUSES:
        raise ValueError(
            f"unknown rationale_proposals.status {s!r}; "
            f"allowed: {sorted(PROPOSAL_STATUSES)}"
        )
    return s


def persist_proposals(proposals: Iterable[Proposal], *, live: bool) -> int:
    """Insert open proposal rows. Dry-run returns count without writing."""
    items = list(proposals)
    if not live:
        return len(items)
    get_engine()
    n = 0
    with get_session() as session:
        for p in items:
            fp = p.fingerprint or p.cluster_id
            session.add(
                RationaleProposal(
                    cluster_fingerprint=fp,
                    cluster_id=p.cluster_id,
                    proposed_at=datetime.now(timezone.utc),
                    proposal_text=p.proposal_text or "",
                    match_strength=p.match_strength,
                    evidence_json=json.dumps(p.evidence_json, default=str),
                    retrieval_hash=p.retrieval_hash or None,
                    status=_require_status("open"),
                    rationale_provenance=(
                        p.rationale_provenance
                        if p.rationale_provenance == "declared_before"
                        else PROVENANCE_RECONCILE
                    ),
                    batch_reason=p.batch_reason or None,
                    fill_date=p.fill_date,
                    sell_tickers=",".join(p.sell_tickers),
                    buy_tickers=",".join(p.buy_tickers),
                )
            )
            n += 1
        session.commit()
    return n


def batch_reject_none(
    proposals: Iterable[Proposal],
    *,
    live: bool,
    reason: str = "predates_evidence_capture",
) -> int:
    """
    Bulk-resolve match_strength=none: status=rejected, proposal_text stays empty,
    batch_reason set. Does not touch Trade_Log Implicit_Bet or any Sheets tab.
    """
    from datetime import timedelta

    nons = [p for p in proposals if p.match_strength == "none"]
    if not live:
        return len(nons)
    get_engine()
    n = 0
    base = datetime.now(timezone.utc)
    with get_session() as session:
        for i, p in enumerate(nons):
            raw_fp = (p.fingerprint or "").strip()
            fp = (
                raw_fp
                if (len(raw_fp) >= 8 and all(c in "0123456789abcdef" for c in raw_fp.lower()))
                else p.cluster_id
            )
            proposed_at = base + timedelta(microseconds=i)
            session.add(
                RationaleProposal(
                    cluster_fingerprint=fp,
                    cluster_id=p.cluster_id,
                    proposed_at=proposed_at,
                    proposal_text="",
                    match_strength="none",
                    evidence_json=json.dumps(p.evidence_json, default=str),
                    retrieval_hash=p.retrieval_hash or None,
                    status=_require_status("rejected"),
                    resolved_at=proposed_at,
                    resolved_text=None,
                    rationale_provenance=PROVENANCE_RECONCILE,
                    batch_reason=p.batch_reason or reason,
                    fill_date=p.fill_date,
                    sell_tickers=",".join(p.sell_tickers),
                    buy_tickers=",".join(p.buy_tickers),
                )
            )
            n += 1
        session.commit()
    return n
