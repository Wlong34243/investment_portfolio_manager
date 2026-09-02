"""Validate decision records before quarantine or binding writes."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from core.decisions.schema import DecisionRecord
from core.decisions.source_text import assertion_on_source_line

_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_[A-Z0-9]+_[a-z0-9_]+$")
_SCOPES = frozenset({"position", "portfolio"})
_STATUSES = frozenset({"proposed", "ratified", "rejected", "superseded"})
_PROVENANCE = frozenset({"extracted", "authored_at_desk"})
_OPERATORS = frozenset({"all", "any"})
_DECIDED_STATUS = frozenset({"known", "unknown"})


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def validate(record: DecisionRecord | dict[str, Any], *, target: str = "proposal") -> list[str]:
    """
    Return human-readable errors. Empty list = valid.

    target: proposal | ingest | binding
    """
    try:
        rec = record if isinstance(record, DecisionRecord) else DecisionRecord.from_dict(record)
    except (KeyError, TypeError, ValueError) as e:
        return [f"record parse error: {e}"]

    errors: list[str] = []

    if not _ID_RE.match(rec.id):
        errors.append(f"id {rec.id!r} must match YYYY-MM-DD_TICKER_slug")

    if rec.decided_on_status not in _DECIDED_STATUS:
        errors.append(f"decided_on_status {rec.decided_on_status!r} must be known or unknown")

    if rec.decided_on_status == "known":
        if not rec.decided_on:
            errors.append("decided_on must be set when decided_on_status is known")
        else:
            decided = _parse_date(rec.decided_on)
            if decided is None:
                errors.append(f"decided_on {rec.decided_on!r} is not a valid date")
            elif decided > date.today():
                errors.append(f"decided_on {rec.decided_on!r} is in the future")
    elif rec.decided_on_status == "unknown" and rec.decided_on:
        errors.append("decided_on must be null when decided_on_status is unknown")

    if target == "binding" and rec.decided_on_status == "unknown":
        errors.append("binding requires decided_on_status known — supply date at ratification")

    if rec.scope not in _SCOPES:
        errors.append(f"scope {rec.scope!r} must be one of {sorted(_SCOPES)}")

    if rec.scope == "position" and not rec.tickers:
        errors.append("tickers must be non-empty when scope is position")

    if rec.conditions.operator not in _OPERATORS:
        errors.append(f"conditions.operator {rec.conditions.operator!r} must be all or any")

    for i, leg in enumerate(rec.conditions.legs):
        if not leg.metric or not leg.comparator or leg.value is None:
            errors.append(f"conditions.legs[{i}] missing metric/comparator/value")

    if rec.status not in _STATUSES:
        errors.append(f"status {rec.status!r} not in allowed set")

    if rec.provenance not in _PROVENANCE:
        errors.append(f"provenance {rec.provenance!r} not in allowed set")

    if not isinstance(rec.unencodable_conditions, list):
        errors.append("unencodable_conditions must be a list")

    if target == "ingest" and rec.status == "ratified":
        errors.append("status ratified is not allowed on ingest")

    if target == "binding" and rec.status != "ratified":
        errors.append(f"binding path requires status ratified, got {rec.status!r}")

    if not rec.assertion.strip():
        errors.append("assertion must be non-empty")
    elif rec.source_ref.strip():
        ok, hint = assertion_on_source_line(rec.assertion, rec.source_ref)
        if not ok:
            errors.append(hint or f"assertion is not a verbatim substring on {rec.source_ref!r}")

    return errors
