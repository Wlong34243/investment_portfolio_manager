"""
Build rationale proposals from retrieval evidence. No LLM — templated Python only.

Match strength:
  strong — signal_events for a ticker on the correct side within the window
  weak   — corpus / thesis context only
  none   — empty proposal_text (AMZN/ETN precedent)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from core.journal.reconcile import UnreconciledCluster
from core.retrieval.api import CorpusQuery, TemplateCall, retrieve

DEFAULT_WINDOW_CALENDAR_DAYS = 7  # ~±5 trading days
# signal_events first accrual — fills before this cannot be strong from evidence tables
EVIDENCE_ACCRUAL_START = date(2026, 8, 27)


@dataclass
class Proposal:
    cluster_id: str
    fingerprint: str
    fill_date: date
    sell_tickers: list[str]
    buy_tickers: list[str]
    match_strength: str  # strong | weak | none
    proposal_text: str  # empty when none
    evidence_tokens: list[str] = field(default_factory=list)
    evidence_json: dict[str, Any] = field(default_factory=dict)
    retrieval_hash: str = ""
    source: str = ""
    status: str = ""
    superseded_ids: list[str] = field(default_factory=list)
    batch_reason: str = ""
    # declared_before only when an acted precommitment firing matches (prompt 8).
    rationale_provenance: str = "reconstructed_after"


def _window(fill: date, days: int = DEFAULT_WINDOW_CALENDAR_DAYS) -> tuple[date, date]:
    return fill - timedelta(days=days), fill + timedelta(days=days)


def _tickers(cluster: UnreconciledCluster) -> list[str]:
    seen: list[str] = []
    for t in cluster.sell_tickers + cluster.buy_tickers:
        if t and t not in seen:
            seen.append(t)
    return seen


def _strong_signals(
    rows: list[dict],
    *,
    sell_tickers: set[str],
    buy_tickers: set[str],
    since: date,
    until: date,
) -> list[dict]:
    hits = []
    for r in rows:
        ed = r.get("event_date")
        ed_s = str(ed)[:10] if ed is not None else ""
        if ed_s and (ed_s < since.isoformat() or ed_s > until.isoformat()):
            continue
        t = str(r.get("ticker") or "").upper()
        side = str(r.get("band_side") or "").lower()
        stype = str(r.get("signal_type") or "").upper()
        if t in sell_tickers and (side == "trim" or stype in ("NEAR_TRIM", "HOLD_TAX")):
            hits.append(r)
        elif t in buy_tickers and (side == "add" or stype == "NEAR_ADD"):
            hits.append(r)
    return hits


def _format_strong(cluster: UnreconciledCluster, hits: list[dict]) -> str:
    h0 = hits[0]
    action = (
        f"sold {','.join(cluster.sell_tickers[:4])} / bought {','.join(cluster.buy_tickers[:4])}"
        if cluster.sell_tickers and cluster.buy_tickers
        else f"rotated on {cluster.fill_date.isoformat()}"
    )
    return (
        f"You {action} on {cluster.fill_date.isoformat()}. "
        f"{h0.get('signal_type')} on {h0.get('ticker')} "
        f"({h0.get('trigger_type') or 'trigger'}={h0.get('metric_value')} "
        f"vs band {h0.get('band_level')}) within the fill window. "
        f"Proposed: pre-committed trigger fired."
    )


def _format_weak(cluster: UnreconciledCluster, notes: list[str]) -> str:
    action = f"{','.join(cluster.sell_tickers[:3]) or '—'} → {','.join(cluster.buy_tickers[:3]) or '—'}"
    body = "; ".join(notes[:3]) if notes else "nearest evidence only"
    return (
        f"You rotated {action} on {cluster.fill_date.isoformat()}. No trigger fired. "
        f"Nearest evidence: {body}. WEAK — author your own."
    )


def _provenance_for_cluster(
    cluster: UnreconciledCluster,
    *,
    window_days: int,
) -> tuple[str, Optional[dict[str, Any]]]:
    """declared_before iff an acted precommitment firing matches the fill window."""
    from core.journal.precommit import find_acted_firing_for_fill

    hit = find_acted_firing_for_fill(
        tickers=_tickers(cluster),
        fill_date=cluster.fill_date,
        window_days=window_days,
    )
    if hit:
        return "declared_before", hit
    return "reconstructed_after", None


def build_proposal_for_cluster(
    cluster: UnreconciledCluster,
    *,
    window_days: int = DEFAULT_WINDOW_CALENDAR_DAYS,
) -> Proposal:
    since, until = _window(cluster.fill_date, window_days)
    tickers = _tickers(cluster)[:10]
    sell_set, buy_set = set(cluster.sell_tickers), set(cluster.buy_tickers)
    provenance, pre_hit = _provenance_for_cluster(cluster, window_days=window_days)

    all_signals: list[dict] = []
    last_hash = ""

    # Strong path only possible on/after evidence accrual
    if cluster.fill_date >= EVIDENCE_ACCRUAL_START:
        for t in tickers:
            sub = retrieve(
                queries=[
                    TemplateCall(
                        "signal_events_for_ticker",
                        {
                            "ticker": t,
                            "since": since.isoformat(),
                            "until": until.isoformat(),
                        },
                    )
                ],
                label=f"journal:sig:{cluster.cluster_id}:{t}",
                caller="cli:journal",
            )
            last_hash = sub.retrieval_hash
            all_signals.extend(sub.tables.get("signal_events_for_ticker") or [])

    strong_hits = _strong_signals(
        all_signals, sell_tickers=sell_set, buy_tickers=buy_set, since=since, until=until
    )
    tokens: list[str] = []
    evidence: dict[str, Any] = {"signals": [], "corpus": [], "notes": []}

    if strong_hits:
        for i, h in enumerate(strong_hits[:5]):
            tokens.append(f"[table:signal_events_for_ticker#{i}]")
            evidence["signals"].append(
                {
                    "ticker": h.get("ticker"),
                    "signal_type": h.get("signal_type"),
                    "event_date": str(h.get("event_date")),
                    "band_side": h.get("band_side"),
                }
            )
        if pre_hit:
            evidence["precommitment"] = pre_hit
            text = (
                f"Pre-commitment {pre_hit.get('precommitment_id')} acted "
                f"({pre_hit.get('ticker')}: {pre_hit.get('intended_action')}). "
                + _format_strong(cluster, strong_hits)
            )
        else:
            text = _format_strong(cluster, strong_hits)
        return Proposal(
            cluster_id=cluster.cluster_id,
            fingerprint=cluster.fingerprint,
            fill_date=cluster.fill_date,
            sell_tickers=cluster.sell_tickers,
            buy_tickers=cluster.buy_tickers,
            match_strength="strong",
            proposal_text=text,
            evidence_tokens=tokens,
            evidence_json=evidence,
            retrieval_hash=last_hash,
            source=cluster.source,
            status=cluster.status,
            superseded_ids=list(cluster.superseded_ids),
            rationale_provenance=provenance,
        )

    # Weak: corpus in window
    notes: list[str] = []
    if tickers:
        rs = retrieve(
            corpus=[
                CorpusQuery(
                    query=" OR ".join(tickers[:6]),
                    tickers=tickers[:6],
                    since=since,
                    until=until,
                    limit=6,
                )
            ],
            label=f"journal:corp:{cluster.cluster_id}",
            caller="cli:journal",
        )
        last_hash = rs.retrieval_hash
        for h in rs.corpus_hits[:5]:
            d = h.doc_date.isoformat() if h.doc_date else "undated"
            tok = f"[{h.source_type}:{h.path}:L{h.line_start} {d}]"
            tokens.append(tok)
            evidence["corpus"].append({"token": tok, "score": h.score})
            notes.append(f"{h.source_type}:{h.path.split('/')[-1]}({d})")

    if not notes and tickers:
        sub = retrieve(
            queries=[TemplateCall("thesis_state_for_ticker", {"ticker": tickers[0]})],
            label=f"journal:thesis:{tickers[0]}",
            caller="cli:journal",
        )
        last_hash = sub.retrieval_hash
        if sub.tables.get("thesis_state_for_ticker"):
            notes.append(f"thesis {tickers[0]} present")
            tokens.append("[table:thesis_state_for_ticker#0]")

    if pre_hit:
        evidence["precommitment"] = pre_hit
        # Acted firing without a same-window signal still counts as declared_before.
        return Proposal(
            cluster_id=cluster.cluster_id,
            fingerprint=cluster.fingerprint,
            fill_date=cluster.fill_date,
            sell_tickers=cluster.sell_tickers,
            buy_tickers=cluster.buy_tickers,
            match_strength="strong",
            proposal_text=(
                f"Pre-commitment {pre_hit.get('precommitment_id')} acted "
                f"({pre_hit.get('ticker')}: {pre_hit.get('intended_action')}) "
                f"within the fill window. Provenance=declared_before."
            ),
            evidence_tokens=tokens,
            evidence_json=evidence,
            retrieval_hash=last_hash,
            source=cluster.source,
            status=cluster.status,
            superseded_ids=list(cluster.superseded_ids),
            rationale_provenance="declared_before",
        )

    if notes:
        evidence["notes"] = notes
        return Proposal(
            cluster_id=cluster.cluster_id,
            fingerprint=cluster.fingerprint,
            fill_date=cluster.fill_date,
            sell_tickers=cluster.sell_tickers,
            buy_tickers=cluster.buy_tickers,
            match_strength="weak",
            proposal_text=_format_weak(cluster, notes),
            evidence_tokens=tokens,
            evidence_json=evidence,
            retrieval_hash=last_hash,
            source=cluster.source,
            status=cluster.status,
            superseded_ids=list(cluster.superseded_ids),
            rationale_provenance=provenance,
        )

    return Proposal(
        cluster_id=cluster.cluster_id,
        fingerprint=cluster.fingerprint,
        fill_date=cluster.fill_date,
        sell_tickers=cluster.sell_tickers,
        buy_tickers=cluster.buy_tickers,
        match_strength="none",
        proposal_text="",
        evidence_tokens=[],
        evidence_json={"reason": "no_evidence_in_window"},
        retrieval_hash=last_hash,
        source=cluster.source,
        status=cluster.status,
        superseded_ids=list(cluster.superseded_ids),
        batch_reason="predates_evidence_capture",
        rationale_provenance=provenance,
    )


def build_proposals(
    clusters: list[UnreconciledCluster],
    *,
    window_days: int = DEFAULT_WINDOW_CALENDAR_DAYS,
) -> list[Proposal]:
    return [build_proposal_for_cluster(c, window_days=window_days) for c in clusters]


def match_strength_counts(proposals: list[Proposal]) -> dict[str, int]:
    out = {"strong": 0, "weak": 0, "none": 0}
    for p in proposals:
        out[p.match_strength] = out.get(p.match_strength, 0) + 1
    return out


def proposal_to_row(p: Proposal) -> dict[str, Any]:
    return {
        "cluster_id": p.cluster_id,
        "fingerprint": p.fingerprint,
        "fill_date": p.fill_date.isoformat(),
        "sells": ",".join(p.sell_tickers[:6]),
        "buys": ",".join(p.buy_tickers[:6]),
        "match": p.match_strength,
        "source": p.source,
        "status": p.status,
        "superseded_n": len(p.superseded_ids),
        "proposal_text": (p.proposal_text[:120] + "…") if len(p.proposal_text) > 120 else p.proposal_text,
        "batch_reason": p.batch_reason,
    }
