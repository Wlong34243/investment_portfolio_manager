"""
Pre-commitment capture — the only path that produces Rationale_Provenance=declared_before.

Crossing condition (hold constant — changing later rewrites every historical firing):
  - trim band at L fires when metric_value >= L
  - add  band at L fires when metric_value <= L
A reading strictly inside the band (trim metric < L, add metric > L) does not fire.

Doctrine-downgraded signal_events still create firings; the downgrade is recorded on
the firing row. A tax override is a response, not a non-event.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from core.store.models import (
    Precommitment,
    PrecommitmentFiring,
    SignalEvent,
    get_engine,
    get_session,
)
from utils.level_coverage import TRIGGER_TYPE_FIELDS
from utils.thesis_reader import _safe_float, get_triggers, thesis_path_for_ticker

# Sell-side / consensus targets ratchet — refuse as declaration levels (CLAUDE.md).
_CONSENSUS_RE = re.compile(
    r"consensus|price[_\s-]?target|analyst[_\s-]?target|sell[_\s-]?side",
    re.IGNORECASE,
)

PRECOMMIT_STATUSES = frozenset(
    {
        "open",
        "fired",
        "closed_band_moved",
        "closed_position_exited",
        "closed_manual",
    }
)
FIRING_RESPONSES = frozenset({"pending", "acted", "passed"})
BAND_SIDES = frozenset({"trim", "add"})


@dataclass
class DeclareResult:
    ok: bool
    message: str
    precommitment_id: Optional[int] = None
    requires_force: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_consensus_ref(raw: Any) -> bool:
    if raw is None:
        return False
    s = str(raw).strip()
    if not s:
        return False
    return bool(_CONSENSUS_RE.search(s))


def band_crossed(*, side: str, metric: float | None, level: float | None) -> bool:
    """True iff the reading has crossed (or landed on) the declared band."""
    if metric is None or level is None:
        return False
    side = (side or "").lower()
    if side == "trim":
        return float(metric) >= float(level)
    if side == "add":
        return float(metric) <= float(level)
    return False


def thesis_band_raw(ticker: str, trigger_type: str, side: str) -> Any:
    """Raw thesis field value for (type, side) — may be numeric or consensus text."""
    path = thesis_path_for_ticker(ticker)
    trigs = get_triggers(path=path)
    fields = TRIGGER_TYPE_FIELDS.get(trigger_type)
    if not fields:
        return None
    trim_field, add_field = fields
    key = trim_field if side == "trim" else add_field
    if not key:
        return None
    return trigs.get(key)


def thesis_band_level(ticker: str, trigger_type: str, side: str) -> float | None:
    return _safe_float(thesis_band_raw(ticker, trigger_type, side))


def declare(
    *,
    ticker: str,
    trigger_type: str,
    side: str,
    level: float,
    action: str,
    note: str = "",
    source: str = "cli",
    force: bool = False,
    live: bool = False,
) -> DeclareResult:
    """
    Write a precommitment. Dry-run (live=False) validates only.
    Band mismatch vs thesis requires --force. Consensus refs are always refused.
    """
    ticker = (ticker or "").strip().upper()
    trigger_type = (trigger_type or "").strip()
    side = (side or "").strip().lower()
    action = (action or "").strip()
    source = (source or "cli").strip() or "cli"

    if not ticker:
        return DeclareResult(False, "ticker required")
    if trigger_type not in TRIGGER_TYPE_FIELDS:
        return DeclareResult(
            False,
            f"unknown trigger_type {trigger_type!r}; allowed: {sorted(TRIGGER_TYPE_FIELDS)}",
        )
    if side not in BAND_SIDES:
        return DeclareResult(False, "side must be trim or add")
    if TRIGGER_TYPE_FIELDS[trigger_type] == (None, None):
        return DeclareResult(
            False,
            f"{trigger_type} has no valuation band (ceiling_only) — nothing to pre-commit",
        )
    if not action:
        return DeclareResult(False, "--action required (e.g. 'trim to 2%')")
    if source == "thesis_sync":
        return DeclareResult(
            False,
            "thesis_sync seeding is disabled — declare explicitly via cli "
            "(false-precision bootstrap refused)",
        )

    raw = thesis_band_raw(ticker, trigger_type, side)
    if is_consensus_ref(raw) or is_consensus_ref(level):
        return DeclareResult(
            False,
            "refused: level references a sell-side / consensus price target "
            "(targets ratchet; trim pegged to consensus structurally cannot fire — "
            "see VST_thesis.md / CLAUDE.md)",
        )

    thesis_level = thesis_band_level(ticker, trigger_type, side)
    mismatch = (
        thesis_level is not None
        and abs(float(thesis_level) - float(level)) > 1e-9
    )
    if mismatch and not force:
        return DeclareResult(
            False,
            f"declared level {level} disagrees with thesis band {thesis_level} "
            f"({ticker} {trigger_type} {side}). Pass --force to proceed anyway.",
            requires_force=True,
        )

    msg = (
        f"would declare {ticker} {trigger_type} {side}@{level} "
        f"action={action!r} thesis_band={thesis_level}"
    )
    if not live:
        return DeclareResult(True, f"DRY RUN — {msg}", requires_force=mismatch)

    get_engine()
    with get_session() as session:
        row = Precommitment(
            declared_at=_utcnow(),
            ticker=ticker,
            trigger_type=trigger_type,
            band_side=side,
            band_level=float(level),
            intended_action=action,
            note=note or None,
            source=source,
            thesis_band_at_declaration=thesis_level,
            status="open",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return DeclareResult(True, f"declared id={row.id} — {msg}", precommitment_id=row.id)


def declare_from_sheet(
    *,
    declared_at: datetime,
    ticker: str,
    trigger_type: str,
    side: str,
    level: float,
    action: str,
    note: str = "",
    live: bool = False,
) -> DeclareResult:
    """
    Ingest a Precommitments tab row. Band mismatch is ingested anyway (flagged).
    declared_at comes from Bill's Date_Declared column, not ingest time.
    """
    ticker = (ticker or "").strip().upper()
    trigger_type = (trigger_type or "").strip()
    side = (side or "").strip().lower()
    action = (action or "").strip()

    if trigger_type not in TRIGGER_TYPE_FIELDS:
        return DeclareResult(
            False,
            f"unknown trigger_type {trigger_type!r}; allowed: {sorted(TRIGGER_TYPE_FIELDS)}",
        )
    if side not in BAND_SIDES:
        return DeclareResult(False, "side must be trim or add")
    if TRIGGER_TYPE_FIELDS[trigger_type] == (None, None):
        return DeclareResult(False, f"{trigger_type} has no valuation band — nothing to pre-commit")

    raw = thesis_band_raw(ticker, trigger_type, side)
    if is_consensus_ref(raw) or is_consensus_ref(level):
        return DeclareResult(
            False,
            "refused: level references a sell-side / consensus price target",
        )

    thesis_level = thesis_band_level(ticker, trigger_type, side)
    mismatch = (
        thesis_level is not None
        and abs(float(thesis_level) - float(level)) > 1e-9
    )
    mismatch_note = ""
    if mismatch:
        mismatch_note = (
            f" FLAG: declared {level} disagrees with thesis band {thesis_level}"
        )

    if not action:
        return DeclareResult(False, "Intended_Action required")

    msg = (
        f"would declare {ticker} {trigger_type} {side}@{level} "
        f"declared_at={declared_at.date().isoformat()} action={action!r}"
        f"{mismatch_note}"
    )
    if not live:
        return DeclareResult(True, f"DRY RUN — {msg}")

    get_engine()
    with get_session() as session:
        row = Precommitment(
            declared_at=declared_at,
            ticker=ticker,
            trigger_type=trigger_type,
            band_side=side,
            band_level=float(level),
            intended_action=action,
            note=(note or None),
            source="sheet",
            thesis_band_at_declaration=thesis_level,
            status="open",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return DeclareResult(
            True,
            f"declared id={row.id} — {msg}",
            precommitment_id=row.id,
        )


def list_precommitments(
    *,
    ticker: str | None = None,
    open_only: bool = False,
) -> list[Precommitment]:
    get_engine()
    with get_session() as session:
        q = select(Precommitment).order_by(Precommitment.id.desc())
        if ticker:
            q = q.where(Precommitment.ticker == ticker.strip().upper())
        if open_only:
            q = q.where(Precommitment.status.in_(("open", "fired")))
        return list(session.scalars(q).all())


def close_precommitment(
    precommitment_id: int,
    *,
    reason: str,
    status: str = "closed_manual",
    live: bool = False,
) -> DeclareResult:
    reason = (reason or "").strip()
    if not reason:
        return DeclareResult(False, "--reason required")
    if status not in PRECOMMIT_STATUSES or not status.startswith("closed_"):
        return DeclareResult(
            False,
            f"close status must be closed_*; got {status!r}",
        )
    if not live:
        return DeclareResult(
            True,
            f"DRY RUN — would close id={precommitment_id} status={status} reason={reason!r}",
        )
    get_engine()
    with get_session() as session:
        row = session.get(Precommitment, precommitment_id)
        if row is None:
            return DeclareResult(False, f"no precommitment id={precommitment_id}")
        row.status = status
        row.closed_at = _utcnow()
        row.close_reason = reason
        session.commit()
        return DeclareResult(True, f"closed id={precommitment_id} ({status})")


def detect_firings(*, live: bool = False, as_of: date | None = None) -> dict[str, int]:
    """
    For each open/fired precommitment, insert firings for matching signal_events
    whose metric crossed the declared level. Idempotent on UNIQUE(pc, signal).
    """
    get_engine()
    attempted = inserted = ignored = 0
    with get_session() as session:
        pcs = list(
            session.scalars(
                select(Precommitment).where(
                    Precommitment.status.in_(("open", "fired"))
                )
            ).all()
        )
        for pc in pcs:
            q = select(SignalEvent).where(
                SignalEvent.ticker == pc.ticker,
                SignalEvent.trigger_type == pc.trigger_type,
                SignalEvent.band_side == pc.band_side,
            )
            if as_of is not None:
                q = q.where(SignalEvent.event_date <= as_of)
            # Only events on/after declaration calendar day
            decl_day = pc.declared_at.date() if pc.declared_at else None
            if decl_day is not None:
                q = q.where(SignalEvent.event_date >= decl_day)

            for sig in session.scalars(q).all():
                if not band_crossed(
                    side=pc.band_side,
                    metric=sig.metric_value,
                    level=pc.band_level,
                ):
                    continue
                attempted += 1
                if not live:
                    continue
                stmt = (
                    sqlite_insert(PrecommitmentFiring)
                    .values(
                        precommitment_id=pc.id,
                        signal_event_id=sig.id,
                        fired_at=_utcnow(),
                        response="pending",
                        doctrine_downgraded=bool(sig.doctrine_downgraded),
                    )
                    .on_conflict_do_nothing(
                        index_elements=["precommitment_id", "signal_event_id"]
                    )
                )
                result = session.execute(stmt)
                # SQLite: rowcount 1 insert, 0 ignore
                if result.rowcount and result.rowcount > 0:
                    inserted += 1
                    if pc.status == "open":
                        pc.status = "fired"
                else:
                    ignored += 1
        if live:
            session.commit()
    return {
        "attempted": attempted,
        "inserted": inserted if live else 0,
        "would_insert": attempted if not live else inserted,
        "ignored_duplicate": ignored,
        "live": live,
    }


def list_pending_firings() -> list[dict[str, Any]]:
    get_engine()
    with get_session() as session:
        rows = session.execute(
            select(PrecommitmentFiring, Precommitment, SignalEvent)
            .join(Precommitment, Precommitment.id == PrecommitmentFiring.precommitment_id)
            .join(SignalEvent, SignalEvent.id == PrecommitmentFiring.signal_event_id)
            .where(PrecommitmentFiring.response == "pending")
            .order_by(PrecommitmentFiring.id)
        ).all()
        out: list[dict[str, Any]] = []
        for firing, pc, sig in rows:
            out.append(
                {
                    "firing_id": firing.id,
                    "precommitment_id": pc.id,
                    "ticker": pc.ticker,
                    "trigger_type": pc.trigger_type,
                    "band_side": pc.band_side,
                    "band_level": pc.band_level,
                    "intended_action": pc.intended_action,
                    "declared_at": pc.declared_at,
                    "note": pc.note,
                    "fired_at": firing.fired_at,
                    "signal_event_id": sig.id,
                    "metric_value": sig.metric_value,
                    "event_date": sig.event_date,
                    "doctrine_downgraded": bool(firing.doctrine_downgraded),
                    "signal_type": sig.signal_type,
                }
            )
        return out


def respond_firing(
    firing_id: int,
    *,
    response: str,
    note: str = "",
    live: bool = False,
) -> DeclareResult:
    """Set response on a pending firing. Only path that leaves pending."""
    response = (response or "").strip().lower()
    if response in ("a", "acted"):
        response = "acted"
    elif response in ("p", "passed"):
        response = "passed"
    elif response in ("d", "defer", "deferred"):
        return DeclareResult(True, f"deferred firing id={firing_id} (still pending)")
    else:
        return DeclareResult(False, "response must be acted|passed|defer (a|p|d)")

    if not live:
        return DeclareResult(
            True,
            f"DRY RUN — would set firing id={firing_id} → {response}",
        )
    get_engine()
    with get_session() as session:
        row = session.get(PrecommitmentFiring, firing_id)
        if row is None:
            return DeclareResult(False, f"no firing id={firing_id}")
        if row.response != "pending":
            return DeclareResult(
                False,
                f"firing id={firing_id} already {row.response!r} — not overwriting",
            )
        row.response = response
        row.responded_at = _utcnow()
        row.response_note = note or None
        session.commit()
        return DeclareResult(True, f"firing id={firing_id} → {response}")


def find_acted_firing_for_fill(
    *,
    tickers: list[str],
    fill_date: date,
    window_days: int = 7,
) -> Optional[dict[str, Any]]:
    """
    Match an acted precommitment firing to a fill for declared_before provenance.
    Window is calendar days around fill_date; any ticker on the rotation qualifies.
    """
    from datetime import timedelta

    if not tickers:
        return None
    ticker_set = {t.strip().upper() for t in tickers if t}
    since = fill_date - timedelta(days=window_days)
    until = fill_date + timedelta(days=window_days)
    get_engine()
    with get_session() as session:
        rows = session.execute(
            select(PrecommitmentFiring, Precommitment, SignalEvent)
            .join(Precommitment, Precommitment.id == PrecommitmentFiring.precommitment_id)
            .join(SignalEvent, SignalEvent.id == PrecommitmentFiring.signal_event_id)
            .where(PrecommitmentFiring.response == "acted")
            .where(Precommitment.ticker.in_(ticker_set))
            .where(SignalEvent.event_date >= since)
            .where(SignalEvent.event_date <= until)
            .order_by(PrecommitmentFiring.responded_at.desc())
        ).all()
        if not rows:
            return None
        firing, pc, sig = rows[0]
        return {
            "firing_id": firing.id,
            "precommitment_id": pc.id,
            "ticker": pc.ticker,
            "intended_action": pc.intended_action,
            "signal_event_id": sig.id,
            "event_date": sig.event_date,
        }


def link_firing_to_trade_log(
    firing_id: int,
    trade_log_id: str,
    *,
    live: bool = False,
) -> DeclareResult:
    if not live:
        return DeclareResult(
            True,
            f"DRY RUN — would link firing {firing_id} → trade_log {trade_log_id}",
        )
    get_engine()
    with get_session() as session:
        row = session.get(PrecommitmentFiring, firing_id)
        if row is None:
            return DeclareResult(False, f"no firing id={firing_id}")
        row.linked_trade_log_id = trade_log_id
        session.commit()
        return DeclareResult(True, f"linked firing {firing_id} → {trade_log_id}")


def pending_count() -> int:
    get_engine()
    with get_session() as session:
        from sqlalchemy import func

        return int(
            session.scalar(
                select(func.count())
                .select_from(PrecommitmentFiring)
                .where(PrecommitmentFiring.response == "pending")
            )
            or 0
        )
