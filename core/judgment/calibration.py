"""Unit C — calibration table scaffold (gates; no partial data)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from core.store.evidence import EVIDENCE_GATE_DAYS, evidence_status

SIX_MONTH_GATE_DAYS = 182  # ~6 calendar months trading-day proxy for display


@dataclass
class CalibrationResult:
    gate_met: bool
    clean_trading_days: int
    remaining_hygiene_days: int
    earliest_hygiene_date: Optional[date]
    six_month_gate_date: Optional[date]
    pending_cell_text: str
    provenance_banner: str
    signal_types: list[str]
    table_rows: list[dict[str, str]]
    firing_response_count: int
    precommitment_count: int


def _six_month_gate_date(first_accrual: Optional[str]) -> Optional[date]:
    if not first_accrual:
        return None
    try:
        start = date.fromisoformat(str(first_accrual)[:10])
    except ValueError:
        return None
    return start + timedelta(days=SIX_MONTH_GATE_DAYS)


def build_calibration() -> CalibrationResult:
    ev = evidence_status()
    clean = int(ev.get("clean_trading_days") or 0)
    remaining = int(ev.get("remaining_trading_days") or max(0, EVIDENCE_GATE_DAYS - clean))
    gate_met = bool(ev.get("gate_met"))
    first = ev.get("evidence_first_accrual_date")
    hygiene_date = None
    if first:
        try:
            d0 = date.fromisoformat(str(first)[:10])
            hygiene_date = d0 + timedelta(days=remaining)
        except ValueError:
            hygiene_date = None
    six_mo = _six_month_gate_date(first)

    from core.journal.precommit import list_pending_firings, list_precommitments

    pending = list_pending_firings()
    pcs = list_precommitments()
    firing_responses = 0
    try:
        import sqlite3
        import config

        conn = sqlite3.connect(f"file:{config.SQLITE_DB_PATH}?mode=ro", uri=True)
        firing_responses = conn.execute(
            "SELECT COUNT(*) FROM precommitment_firings WHERE response != 'pending'"
        ).fetchone()[0]
        conn.close()
    except Exception:
        firing_responses = 0

    accrual_str = str(first) if first else "unknown"
    six_str = six_mo.isoformat() if six_mo else "unknown"
    pending_text = (
        f"PENDING — requires pre-commitment firings.\n"
        f"{firing_responses} responses recorded. Accrual began {accrual_str}. "
        f"Non-noise gate: {six_str}."
    )

    provenance_banner = (
        "**Provenance:** With zero (or insufficient) `declared_before` firings, every rationale row is "
        "`reconstructed_after` by construction. The passed column cannot measure judgment until prompt 8 "
        "firings accrue — do not read this table as a scorecard."
    )

    signal_types = ["NEAR_TRIM", "NEAR_ADD", "HOLD_TAX", "DISLOCATION"]
    table_rows: list[dict[str, str]] = []
    for st in signal_types:
        table_rows.append({
            "signal_type": st,
            "acted_right": pending_text,
            "acted_wrong": pending_text,
            "passed_right": pending_text,
            "passed_wrong": pending_text,
        })

    return CalibrationResult(
        gate_met=gate_met,
        clean_trading_days=clean,
        remaining_hygiene_days=remaining,
        earliest_hygiene_date=hygiene_date,
        six_month_gate_date=six_mo,
        pending_cell_text=pending_text,
        provenance_banner=provenance_banner,
        signal_types=signal_types,
        table_rows=table_rows,
        firing_response_count=firing_responses,
        precommitment_count=len(pcs),
    )


def format_calibration_markdown(result: CalibrationResult) -> str:
    lines = [
        "# Judgment — Calibration (Unit C)",
        "",
        result.provenance_banner,
        "",
    ]

    if not result.gate_met:
        lines.extend([
            f"**GATE NOT MET** — {result.clean_trading_days} of {EVIDENCE_GATE_DAYS} trading days accrued; "
            f"earliest meaningful hygiene read: {result.earliest_hygiene_date or '—'}",
            f"**Six-month non-noise gate:** {result.six_month_gate_date or '—'}",
            "",
            "*No partial calibration table is emitted below the gate.*",
            "",
        ])
    else:
        lines.extend([
            f"**Hygiene gate met** ({result.clean_trading_days} days). "
            f"**Six-month non-noise gate:** {result.six_month_gate_date or '—'}",
            "",
            "*Hygiene gate met does not populate the passed column — firings still required.*",
            "",
        ])

    lines.extend([
        f"**Precommitments on record:** {result.precommitment_count} · "
        f"**Firing responses (non-pending):** {result.firing_response_count}",
        "",
        "## Calibration table",
        "",
        "| Signal | You acted / right | You acted / wrong | You passed / right | You passed / wrong |",
        "|---|---|---|---|---|",
    ])

    for row in result.table_rows:
        cell = "PENDING (see banner)"
        lines.append(
            f"| {row['signal_type']} | {cell} | {cell} | {cell} | {cell} |"
        )

    lines.extend([
        "",
        "### Pending quadrant detail (all cells)",
        "",
        "```",
        result.pending_cell_text,
        "```",
        "",
        "*Visible blank with counter is the design — not a placeholder to hide.*",
    ])
    return "\n".join(lines)
