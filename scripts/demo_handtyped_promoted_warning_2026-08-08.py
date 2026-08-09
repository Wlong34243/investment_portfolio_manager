"""Demonstrate hand-typed promoted warning, then restore the row."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from utils.sheet_readers import get_gspread_client

ss = get_gspread_client().open_by_key(config.PORTFOLIO_SHEET_ID)
ws = ss.worksheet(config.TAB_TRADE_LOG_STAGING)
rows = ws.get_all_values()
h = rows[0]
si = h.index("Status")
ii = h.index("Stage_ID")
sheet_row = None
rid = None
for i, r in enumerate(rows[1:], start=2):
    p = r + [""] * (len(h) - len(r))
    if p[si] == "needs_rationale":
        rid = p[ii]
        sheet_row = i
        break
if not sheet_row:
    print("No needs_rationale row found")
    sys.exit(1)

print(f"Temporarily setting {rid} row {sheet_row} to promoted (blank Promoted_At)...")
ws.update_cell(sheet_row, si + 1, "promoted")
time.sleep(0.5)

print("--- journal promote dry-run (expect hand-typed warning) ---")
import subprocess

subprocess.check_call(
    [sys.executable, str(Path(__file__).resolve().parent.parent / "manager.py"), "journal", "promote"],
)

print(f"Restoring {rid} to needs_rationale...")
ws.update_cell(sheet_row, si + 1, "needs_rationale")
time.sleep(0.3)
print("Restored.")
