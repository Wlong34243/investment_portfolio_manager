"""
Archive live Agent_Outputs → Agent_Outputs_Archive, then clear the live tab
(header only). One-shot for Crosshairs Fresh Feed (2026-08-10): drops the
stale April 2026 cbc10a99 run from the feed surface.

Handles the live layout seen 2026-08-10: row 0 = summary banner, row 1 = real
column headers (run_date, run_id_short, ...), data from row 2.

Usage:
  python scripts/archive_agent_outputs_2026-08-10.py          # dry-run
  python scripts/archive_agent_outputs_2026-08-10.py --live   # archive + clear
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import safe_execute


def _find_header_idx(rows: list[list]) -> int:
    for i, row in enumerate(rows[:10]):
        lowered = [str(h).strip().lower() for h in row]
        if "agent" in lowered and ("ticker" in lowered or "signal" in lowered):
            return i
    return -1


def main(live: bool = False) -> int:
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    try:
        ws = ss.worksheet(config.TAB_AGENT_OUTPUTS)
    except Exception as e:
        print(f"FAIL: cannot open {config.TAB_AGENT_OUTPUTS}: {e}")
        return 1

    rows = safe_execute(ws.get_all_values)
    if not rows:
        print(f"{config.TAB_AGENT_OUTPUTS} is empty — nothing to archive.")
        return 0

    header_idx = _find_header_idx(rows)
    if header_idx < 0:
        print("FAIL: could not find Agent_Outputs header row (need agent + ticker/signal).")
        for i, r in enumerate(rows[:5]):
            print(f"  row {i}: {r[:6]}")
        return 1

    headers = rows[header_idx]
    preamble = rows[:header_idx]
    data = rows[header_idx + 1:]

    run_col = None
    for name in ("run_id_short", "run_id"):
        if name in [h.strip().lower() for h in headers]:
            run_col = [h.strip().lower() for h in headers].index(name)
            break
    run_ids = sorted({
        r[run_col] for r in data
        if run_col is not None and len(r) > run_col and r[run_col]
    })

    print(f"Live tab: {len(rows)} total rows; header at row {header_idx}; {len(data)} data row(s).")
    print(f"Preamble rows: {len(preamble)}")
    print(f"run_id values: {run_ids or '(none)'}")
    if preamble:
        print(f"  preamble[0]: {preamble[0][:1]}")

    if not live:
        print("DRY RUN — would archive preamble + data to Agent_Outputs_Archive,")
        print("then rewrite Agent_Outputs with header only. Re-run with --live.")
        return 0

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing_tabs = {w.title for w in ss.worksheets()}

    if config.TAB_AGENT_OUTPUTS_ARCHIVE not in existing_tabs:
        ws_arc = safe_execute(
            ss.add_worksheet,
            title=config.TAB_AGENT_OUTPUTS_ARCHIVE,
            rows=10000,
            cols=len(headers) + 2,
        )
        time.sleep(1.0)
        arc_headers = ["archived_at", "row_kind"] + headers
        safe_execute(ws_arc.update, range_name="A1", values=[arc_headers], value_input_option="USER_ENTERED")
        time.sleep(0.5)
    else:
        ws_arc = safe_execute(ss.worksheet, config.TAB_AGENT_OUTPUTS_ARCHIVE)

    archive_rows = []
    for prow in preamble:
        padded = (prow + [""] * len(headers))[:len(headers)]
        archive_rows.append([run_ts, "preamble"] + padded)
    for drow in data:
        padded = (drow + [""] * len(headers))[:len(headers)]
        archive_rows.append([run_ts, "data"] + padded)

    if archive_rows:
        safe_execute(ws_arc.append_rows, archive_rows, value_input_option="USER_ENTERED")
        time.sleep(1.0)
        print(f"Archived {len(archive_rows)} row(s) to {config.TAB_AGENT_OUTPUTS_ARCHIVE}.")

    safe_execute(ws.clear)
    time.sleep(0.5)
    # Live tab historically had a merged summary banner on row 1 (A1:E1 / F1:K1)
    # and a basicFilter — both make a plain header write look "empty" in B–E.
    try:
        sid = ws.id
        safe_execute(ss.batch_update, {
            "requests": [
                {"unmergeCells": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 12}}},
                {"clearBasicFilter": {"sheetId": sid}},
                {"updateSheetProperties": {
                    "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 0}},
                    "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
                }},
            ]
        })
        time.sleep(0.5)
    except Exception as e:
        print(f"  ! unmerge/filter clear skipped: {e}")

    safe_execute(ws.update, range_name="A1", values=[headers], value_input_option="RAW")
    time.sleep(0.5)

    after = safe_execute(ws.get_all_values)
    print(f"LIVE — archived_at={run_ts}; live tab now {len(after)} row(s) (expect 1 = header).")
    print(f"  header: {after[0][:6] if after else '(empty)'}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    raise SystemExit(main(live=args.live))
