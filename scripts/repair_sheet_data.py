"""
scripts/repair_sheet_data.py — One-shot sheet data repair.

Uses clear + single-batch rewrite (never row-by-row delete) to avoid
Google Sheets 429 quota limits.

Fixes:
  1. Daily_Snapshots rows where Blended Yield > 0.5 (>50%) — the 100x
     inflation artifact from when dividend_yield was stored as a percentage
     rather than a raw decimal.
  2. Transactions rows where both Amount AND Net Amount are empty/zero —
     legacy rows written before the Schwab API fingerprint was corrected.

Usage:
    python scripts/repair_sheet_data.py           # dry run — shows counts only
    python scripts/repair_sheet_data.py --live     # clears bad rows
"""

import sys
import os
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from utils.sheet_readers import get_gspread_client


def _find_col(headers: list[str], *candidates: str) -> int | None:
    """Case-insensitive column search. Returns 0-based index or None."""
    lower_headers = [h.strip().lower() for h in headers]
    for name in candidates:
        try:
            return lower_headers.index(name.strip().lower())
        except ValueError:
            continue
    return None


def _is_blank(val) -> bool:
    return str(val).strip() in ("", "0", "0.0", "0.00", "none", "null")


def repair_daily_snapshots(ws, live: bool) -> int:
    """
    Remove rows where Blended Yield > 0.5 (impossible real yield —
    leftover from when the value was stored as a percentage like 1.54
    instead of 0.0154).

    Strategy: read all → filter → clear → rewrite in one batch.
    """
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        print("  Daily_Snapshots: no data rows — nothing to repair.")
        return 0

    headers = all_values[0]
    data_rows = all_values[1:]

    yield_idx = _find_col(headers, "Blended Yield", "Blended Yield %", "blended_yield")
    if yield_idx is None:
        print(f"  Daily_Snapshots: could not find Blended Yield column.")
        print(f"  Actual headers: {headers}")
        return 0

    good_rows, bad_count = [], 0
    for row in data_rows:
        raw = row[yield_idx] if len(row) > yield_idx else ""
        try:
            val = float(str(raw).replace("%", "").strip())
            if val > 0.5:
                bad_count += 1
                print(f"    BAD — Blended Yield = {val:.4f}  row: {row[:3]}")
                continue
        except (ValueError, TypeError):
            pass
        good_rows.append(row)

    if bad_count == 0:
        print("  Daily_Snapshots: no inflated yield rows found. ✅")
        return 0

    print(f"  Daily_Snapshots: {bad_count} inflated row(s) flagged, {len(good_rows)} good row(s) kept.")
    if not live:
        print("  DRY RUN — use --live to commit.")
        return 0

    ws.clear()
    time.sleep(1.0)
    ws.update(range_name="A1",
              values=[headers] + good_rows,
              value_input_option="USER_ENTERED")
    time.sleep(1.5)
    print(f"  ✅ Rewrote Daily_Snapshots: removed {bad_count} bad row(s).")
    return bad_count


def repair_transactions(ws, live: bool) -> int:
    """
    Remove transaction rows where both Amount and Net Amount are blank/zero.
    These are legacy rows written before the Schwab fingerprint fix.

    Strategy: read all → filter → clear → rewrite in one batch.
    No row-by-row deletes — avoids 429 quota errors entirely.
    """
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        print("  Transactions: no data rows — nothing to repair.")
        return 0

    headers = all_values[0]
    data_rows = all_values[1:]

    amount_idx  = _find_col(headers, "Amount")
    net_amt_idx = _find_col(headers, "Net Amount")

    if amount_idx is None and net_amt_idx is None:
        print("  Transactions: Amount/Net Amount columns not found — skipping.")
        print(f"  Actual headers: {headers}")
        return 0

    good_rows, bad_count = [], 0
    for row in data_rows:
        amt_blank = _is_blank(row[amount_idx]) if amount_idx is not None and amount_idx < len(row) else True
        net_blank = _is_blank(row[net_amt_idx]) if net_amt_idx is not None and net_amt_idx < len(row) else True
        if amt_blank and net_blank:
            bad_count += 1
        else:
            good_rows.append(row)

    if bad_count == 0:
        print("  Transactions: no empty-amount rows found. ✅")
        return 0

    print(f"  Transactions: {bad_count} empty-amount row(s) flagged, {len(good_rows)} good row(s) kept.")
    if not live:
        print("  DRY RUN — use --live to commit.")
        return 0

    # Single clear + single write — avoids all quota issues
    print(f"  Clearing {config.TAB_TRANSACTIONS} and rewriting {len(good_rows)} clean rows...")
    ws.clear()
    time.sleep(1.5)
    ws.update(range_name="A1",
              values=[headers] + good_rows,
              value_input_option="USER_ENTERED")
    time.sleep(1.5)
    print(f"  ✅ Rewrote Transactions: removed {bad_count} empty-amount row(s).")
    return bad_count


def main(live: bool = False):
    print(f"=== Sheet Data Repair ({'LIVE' if live else 'DRY RUN'}) ===\n")

    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)

    # --- Daily_Snapshots ---
    print("[1/2] Checking Daily_Snapshots for inflated Blended Yield rows...")
    try:
        ws_snap = ss.worksheet(config.TAB_DAILY_SNAPSHOTS)
        n_snap = repair_daily_snapshots(ws_snap, live=live)
    except Exception as e:
        print(f"  ERROR: {e}")
        n_snap = 0

    time.sleep(1.0)

    # --- Transactions ---
    print("\n[2/2] Checking Transactions for empty Amount rows...")
    try:
        ws_tx = ss.worksheet(config.TAB_TRANSACTIONS)
        n_tx = repair_transactions(ws_tx, live=live)
    except Exception as e:
        print(f"  ERROR: {e}")
        n_tx = 0

    print(f"\n=== Repair {'Complete' if live else 'Preview'} ===")
    print(f"  Snapshot rows {'removed' if live else 'to remove'}: {n_snap}")
    print(f"  Transaction rows {'removed' if live else 'to remove'}: {n_tx}")

    if not live:
        print("\nRe-run with --live to apply:")
        print("  python scripts/repair_sheet_data.py --live")
    else:
        print("\nNext steps:")
        print("  1. Backfill transaction history (1 year):")
        print("     python manager.py sync transactions --days 365 --live")
        print("  2. Refresh positions + new snapshot:")
        print("     python manager.py dashboard refresh --update --live")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair corrupt sheet data (batch rewrite — no quota issues)")
    parser.add_argument("--live", action="store_true",
                        help="Commit changes (default is dry run)")
    args = parser.parse_args()
    main(live=args.live)
