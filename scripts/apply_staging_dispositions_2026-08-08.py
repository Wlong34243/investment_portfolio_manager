"""Apply Bill-signed dispositions to Trade_Log_Staging (option 2, 2026-08-08).

1. Backup staging to CSV
2. Ensure Promoted_At header exists
3. Write Status: approved / superseded / needs_rationale per sign-off
"""
from __future__ import annotations

import csv
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import config
from tasks.compute_rotation_attribution import find_superseded_groups, load_staging, _row_get
from utils.sheet_readers import get_gspread_client

OUT = _ROOT / "agent_outputs" / "trade_log_staging"
OUT.mkdir(parents=True, exist_ok=True)

# Option 2 sign-off: 3 clean + Aug 3 widest
APPROVED_IDS = {
    "ae34e9ca-8846-4a66-92f1-afd891c4e9bb",  # NOW+IGV clean
    "f0662cc8-c081-4dd1-9d0c-8a49d6ca0b10",  # EMXC->BBJP clean
    "f5b02584-6fe4-40ed-8fb2-9bdbf1740e4f",  # IGV/VEU/JEPI->IBM clean
    "ca3bedba-25e7-4f82-a548-82773af02d8f",  # Aug 3 widest (Thesis_Brief rationale)
}

# Messy bundles Bill already marked superseded (keep even though widest)
FORCE_SUPERSEDED = {
    "c70504cb-d039-46b9-bf03-e605fb8f1a59",
    "25e85f9b-b6f8-4540-9af0-238106d181f4",
}


def main() -> None:
    ss = get_gspread_client().open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_TRADE_LOG_STAGING)
    raw = ws.get_all_values()
    header = list(raw[0])
    data = raw[1:]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = OUT / f"backup_{ts}.csv"
    with backup.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerows(raw)
    print(f"BACKUP: {backup} ({len(data)} data rows)")

    if "Promoted_At" not in header:
        header.append("Promoted_At")
        ws.update_cell(1, len(header), "Promoted_At")
        time.sleep(0.5)
        print("Added Promoted_At header column")

    status_idx = header.index("Status")
    id_idx = header.index("Stage_ID")

    # Nested supersets from attribution detector
    rows = load_staging(ss)
    superseded_map, groups = find_superseded_groups(rows)
    print(f"Nested groups: {len(groups)}; detector superseded: {len(superseded_map)}")

    # Build disposition per Stage_ID
    dispositions: dict[str, str] = {}
    for r in rows:
        rid = str(_row_get(r, "Trade_Log_ID", "Stage_ID"))
        if rid in APPROVED_IDS:
            dispositions[rid] = "approved"
        elif rid in FORCE_SUPERSEDED or rid in superseded_map:
            # Don't supersede an approved clean subset
            if rid in APPROVED_IDS:
                dispositions[rid] = "approved"
            else:
                dispositions[rid] = "superseded"
        else:
            dispositions[rid] = "needs_rationale"

    # Override: approved wins over superseded_map
    for rid in APPROVED_IDS:
        dispositions[rid] = "approved"

    from gspread.utils import rowcol_to_a1

    counts = {"approved": 0, "superseded": 0, "needs_rationale": 0}
    updates = []
    for i, row in enumerate(data):
        padded = row + [""] * (len(header) - len(row))
        rid = padded[id_idx].strip() if id_idx < len(padded) else ""
        disp = dispositions.get(rid, "needs_rationale")
        counts[disp] = counts.get(disp, 0) + 1
        sheet_row = i + 2
        updates.append({
            "range": rowcol_to_a1(sheet_row, status_idx + 1),
            "values": [[disp]],
        })

    print(f"Disposition counts: {counts}")
    print(f"Approved IDs: {sorted(APPROVED_IDS)}")

    # Batch in chunks to avoid API limits
    chunk = 50
    for start in range(0, len(updates), chunk):
        batch = updates[start : start + chunk]
        ws.batch_update(batch, value_input_option="USER_ENTERED")
        time.sleep(1.0)
        print(f"  wrote status rows {start + 1}-{min(start + chunk, len(updates))}")

    print("DONE: statuses written. Next: journal promote dry-run / --live.")


if __name__ == "__main__":
    main()
