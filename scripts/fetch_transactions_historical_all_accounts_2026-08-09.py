"""
scripts/fetch_transactions_historical_all_accounts_2026-08-09.py

One-off historical fetch for prompts/commit_recover_dashboard_2026-08-09.md Step 3.

Fetches ALL SIX linked Schwab accounts (env override at call time, not a
config.py edit -- gone the moment this process exits) for
2025-01-01 -> 2026-08-03, the window that predates the 2026-08-03 account-scope
fix (prompts/schwab_account_scope_fix_2026-08-03.md). Writes to a NEW tab,
Transactions_Historical_AllAccounts, with an added Account_Suffix column so
in-scope and out-of-scope rows stay distinguishable forever. Never touches the
live Transactions tab. Read-only Schwab endpoints only (fetch_transactions()
issues GET requests; no order/trading endpoint is imported or called).

Usage:
    python scripts/fetch_transactions_historical_all_accounts_2026-08-09.py         (dry run)
    python scripts/fetch_transactions_historical_all_accounts_2026-08-09.py --live  (writes the tab)
"""
import os

# Must happen before `import config` anywhere in this process -- config.py
# reads this env var once, at import time, via os.getenv(..., "6499,8767,5119").
os.environ["SCHWAB_PRIMARY_ACCOUNT_SUFFIXES"] = ""

import argparse
import csv
import sys
from datetime import datetime, timedelta

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils import schwab_client
from utils.sheet_readers import get_gspread_client

HISTORICAL_TAB = "Transactions_Historical_AllAccounts"
HISTORICAL_COLUMNS = config.TRANSACTION_COLUMNS + ["Account_Suffix"]
FETCH_START = datetime(2025, 1, 1)
FETCH_END = datetime(2026, 8, 3)
CHUNK_DAYS = 90  # Schwab's transaction endpoint 400s on the full ~19-month span


def _date_chunks(start: datetime, end: datetime, days: int = CHUNK_DAYS):
    chunks = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=days), end)
        chunks.append((cur, nxt))
        cur = nxt
    return chunks


def main(live: bool) -> None:
    # Confirm the env override actually took -- config.py filters blank
    # entries, so "" correctly yields [] ("Empty = no filtering").
    assert config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES == [], (
        f"Env override did not take effect: "
        f"{config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES!r}"
    )

    client = schwab_client.get_accounts_client()
    if not client:
        print("ERROR: could not initialize Schwab client (token missing/expired). "
              "Run `python manager.py login` first.")
        sys.exit(1)

    chunks = _date_chunks(FETCH_START, FETCH_END)
    print(f"Fetching ALL linked accounts, {FETCH_START.date()} -> {FETCH_END.date()} "
          f"in {len(chunks)} chunks of <= {CHUNK_DAYS}d (read-only, unscoped for this call only)...")

    parts = []
    for i, (c0, c1) in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)}: {c0.date()} -> {c1.date()}")
        part = schwab_client.fetch_transactions(client, start_date=c0, end_date=c1)
        print(f"    -> {len(part)} rows")
        if not part.empty:
            parts.append(part)

    if not parts:
        print("No transactions returned -- stopping before any write.")
        return

    df = pd.concat(parts, ignore_index=True)
    before = len(df)
    df = df.drop_duplicates(subset=["Fingerprint"], keep="first")
    print(f"Fetched {before} rows across chunks, {len(df)} after de-duping "
          f"on Fingerprint (chunk boundaries can double-count same-day activity).")

    df["Account_Suffix"] = df["Account"].str.extract(r"(\d{4})$").fillna("")
    print("Rows by Account_Suffix:")
    for suf, n in df["Account_Suffix"].value_counts().sort_index().items():
        in_scope = suf in ("6499", "8767", "5119")
        print(f"  ...{suf}: {n} rows{'  (in current 3-account scope)' if in_scope else ''}")

    date_min = df["Trade Date"].min()
    date_max = df["Trade Date"].max()
    print(f"Trade Date range actually returned: {date_min} -> {date_max}")

    df = df[HISTORICAL_COLUMNS]

    if not live:
        print(f"\nDRY RUN -- no Sheet writes. Pass --live to write to '{HISTORICAL_TAB}'.")
        return

    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    existing_tabs = {ws.title for ws in ss.worksheets()}

    if HISTORICAL_TAB in existing_tabs:
        ws = ss.worksheet(HISTORICAL_TAB)
        existing_rows = ws.get_all_values()
        if existing_rows:
            os.makedirs("agent_outputs/rotation_attribution", exist_ok=True)
            backup_path = (
                f"agent_outputs/rotation_attribution/"
                f"archive_{HISTORICAL_TAB}_{datetime.now():%Y-%m-%d_%H%M%S}.csv"
            )
            with open(backup_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(existing_rows)
            print(f"Archived existing tab content -> {backup_path}")
        ws.clear()
    else:
        ws = ss.add_worksheet(
            title=HISTORICAL_TAB, rows=max(50, len(df) + 5), cols=len(HISTORICAL_COLUMNS)
        )

    values = [HISTORICAL_COLUMNS] + df.astype(str).values.tolist()
    ws.update(range_name="A1", values=values, value_input_option="RAW")
    print(f"Wrote {len(df)} rows to '{HISTORICAL_TAB}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    main(live=args.live)
