"""
Ingest Precommitments tab → precommitments table.

APPEND-AND-MARK ONLY — never clear-and-rebuild this tab. Bill is the writer;
the pipeline reads blank Ingested_At rows and writes back H/I/J.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import config
from core.journal.precommit import declare_from_sheet
from utils.sheet_readers import get_gspread_client, read_gsheet_robust
from utils.sheet_writers import safe_execute


def _parse_declared_at(raw: Any) -> datetime | None:
    if raw is None or str(raw).strip() == "":
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            d = datetime.strptime(s[:19], fmt)
            return d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        d = date.fromisoformat(s[:10])
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _ensure_tab(ss):
    """Create tab with headers if missing. Never clear existing rows."""
    try:
        return ss.worksheet(config.TAB_PRECOMMITMENTS)
    except Exception:
        ws = ss.add_worksheet(
            title=config.TAB_PRECOMMITMENTS,
            rows=100,
            cols=len(config.PRECOMMITMENTS_COLUMNS),
        )
        safe_execute(
            ws.update,
            range_name="A1",
            values=[config.PRECOMMITMENTS_COLUMNS],
            value_input_option="RAW",
        )
        return ws


def ingest_precommitments_from_sheet(*, live: bool = False) -> dict[str, Any]:
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = _ensure_tab(ss)
    df = read_gsheet_robust(ws)
    if df is None or df.empty:
        return {"ingested": 0, "skipped": 0, "errors": [], "flags": [], "live": live}

    from utils.column_guard import ensure_precommitments_columns

    df = ensure_precommitments_columns(df)

    ingested = skipped = 0
    errors: list[str] = []
    flags: list[str] = []
    mark_updates: list[dict] = []

    for idx, row in df.iterrows():
        sheet_row = int(idx) + 2  # 1-based header + data
        if str(row.get("Ingested_At", "")).strip():
            continue

        declared = _parse_declared_at(row.get("Date_Declared"))
        if declared is None:
            skipped += 1
            errors.append(f"row {sheet_row}: blank/invalid Date_Declared — skipped (no substitution)")
            continue

        ticker = str(row.get("Ticker", "")).strip().upper()
        trigger_type = str(row.get("Trigger_Type", "")).strip()
        side = str(row.get("Side", "")).strip().lower()
        try:
            level = float(row.get("Level"))
        except (TypeError, ValueError):
            skipped += 1
            errors.append(f"row {sheet_row}: invalid Level")
            continue

        action = str(row.get("Intended_Action", "")).strip()
        note = str(row.get("Note", "") or "").strip()

        res = declare_from_sheet(
            declared_at=declared,
            ticker=ticker,
            trigger_type=trigger_type,
            side=side,
            level=level,
            action=action,
            note=note,
            live=live,
        )
        if not res.ok:
            skipped += 1
            errors.append(f"row {sheet_row}: {res.message}")
            continue

        if "FLAG:" in res.message:
            flags.append(f"row {sheet_row}: {res.message.split('FLAG:', 1)[1].strip()}")

        ingested += 1
        if live and res.precommitment_id:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            mark_updates.append({
                "row": sheet_row,
                "ingested_at": now,
                "precommit_id": res.precommitment_id,
                "status": "open",
            })

    if live and mark_updates:
        for mu in mark_updates:
            r = mu["row"]
            safe_execute(
                ws.update,
                range_name=f"H{r}:J{r}",
                values=[[mu["ingested_at"], mu["precommit_id"], mu["status"]]],
                value_input_option="RAW",
            )

    return {
        "ingested": ingested,
        "skipped": skipped,
        "errors": errors,
        "flags": flags,
        "live": live,
    }
