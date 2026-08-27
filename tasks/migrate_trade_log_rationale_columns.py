"""
Trade_Log Q/R/S column migration (Instrument prompt 7 Step 1).

Appends Proposed_Bet, Rationale_Provenance, Rationale_Evidence after Fingerprint.
Archive-before-overwrite: full tab CSV before any header mutation; pre-edit
proven by grep (Hard Rule 7).

Dry-run by default; pass live=True to write.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config

NEW_COLS = ("Proposed_Bet", "Rationale_Provenance", "Rationale_Evidence")


def migrate_trade_log_rationale_columns(*, live: bool = False) -> dict:
    from utils.sheet_readers import get_gspread_client

    client = get_gspread_client()
    ws = client.open_by_key(config.PORTFOLIO_SHEET_ID).worksheet(config.TAB_TRADE_LOG)
    values = ws.get_all_values()
    if not values:
        return {"ok": False, "error": "Trade_Log empty"}

    header = list(values[0])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = Path("data") / f"Trade_Log_bak_{stamp}.csv"
    bak.parent.mkdir(parents=True, exist_ok=True)

    # Archive BEFORE any mutation
    with bak.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(values)

    # Prove pre-edit content by grep (Hard Rule 7)
    bak_text = bak.read_text(encoding="utf-8")
    header_line = bak_text.splitlines()[0] if bak_text else ""
    proof = {
        "bak_path": str(bak),
        "bak_bytes": bak.stat().st_size,
        "pre_edit_has_Fingerprint": "Fingerprint" in header_line,
        "pre_edit_has_Proposed_Bet": "Proposed_Bet" in header_line,
        "pre_edit_header": header,
    }
    if not proof["pre_edit_has_Fingerprint"]:
        return {"ok": False, "error": "pre-edit archive missing Fingerprint", **proof}
    if proof["pre_edit_has_Proposed_Bet"]:
        return {
            "ok": True,
            "skipped": True,
            "reason": "Proposed_Bet already present — no write",
            "live": live,
            **proof,
        }

    missing = [c for c in NEW_COLS if c not in header]
    new_header = header + missing
    result = {
        "ok": True,
        "live": live,
        "skipped": False,
        "appended": missing,
        "new_header": new_header,
        **proof,
    }

    if not live:
        result["warn"] = "DRY RUN — pass live=True to append header cells"
        return result

    # Append only the new header cells; do not rewrite body
    start_col = len(header) + 1  # 1-based
    end_col_letter = _col_letter(len(new_header))
    start_letter = _col_letter(start_col)
    ws.update(
        f"{start_letter}1:{end_col_letter}1",
        [missing],
        value_input_option="RAW",
    )
    result["wrote"] = f"{start_letter}1:{end_col_letter}1"
    return result


def _col_letter(n: int) -> str:
    """1-based column index → Excel letter (supports >26)."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


if __name__ == "__main__":
    import sys

    live = "--live" in sys.argv
    out = migrate_trade_log_rationale_columns(live=live)
    print(out)
    if not out.get("ok"):
        sys.exit(1)
