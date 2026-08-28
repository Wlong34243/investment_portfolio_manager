"""Pre-commitments read-only desk page."""

from __future__ import annotations

from typing import Any


def assemble_precommit() -> dict[str, Any]:
    try:
        from core.journal.precommit import list_pending_firings, list_precommitments

        declarations = list_precommitments(open_only=False)
        pending = list_pending_firings()
    except Exception:
        declarations = []
        pending = []

    dec_rows = []
    for p in declarations:
        dec_rows.append(
            {
                "id": p.get("id"),
                "ticker": p.get("ticker"),
                "type": p.get("type") or p.get("trigger_type"),
                "side": p.get("side") or p.get("band_side"),
                "level": p.get("level") or p.get("band_level"),
                "status": p.get("status"),
                "action": p.get("action") or p.get("intended_action"),
                "thesis_at": str(p.get("thesis_at") or p.get("declared_at") or "")[:10],
            }
        )

    pend_rows = []
    for p in pending:
        pend_rows.append(
            {
                "ticker": p.get("ticker"),
                "declared_at": str(p.get("declared_at", ""))[:10],
                "trigger_type": p.get("trigger_type"),
                "band_side": p.get("band_side"),
                "band_level": p.get("band_level"),
                "event_date": p.get("event_date"),
                "metric_value": p.get("metric_value"),
                "intended_action": p.get("intended_action"),
            }
        )

    return {
        "declarations": dec_rows,
        "pending": pend_rows,
        "sheets_tab": "Precommitments",
    }
