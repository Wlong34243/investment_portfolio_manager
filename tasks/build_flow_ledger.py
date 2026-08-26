"""
tasks/build_flow_ledger.py — Cash_Flows ledger (external deposits/withdrawals).

Append-only with fingerprint dedup. --live required. No TWR/IRR.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import typer

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from utils.schwab_client import get_accounts_client, fetch_transactions, _is_primary_account
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)
app = typer.Typer()

FLOW_TYPES = {
    "ACH_RECEIPT", "ACH_DISBURSEMENT", "WIRE_IN", "WIRE_OUT",
    "JOURNAL", "CASH_RECEIPT", "CASH_DISBURSEMENT", "ELECTRONIC_FUND",
    "CASH_IN_OR_CASH_OUT",
}

DESCOPED_SUFFIXES = {"4151", "0217", "9753"}


def _fp(row: dict) -> str:
    raw = "|".join(str(row.get(k, "")) for k in (
        "Date", "Account", "Type", "Amount", "Transaction ID"
    ))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_ledger(days: int = 90) -> pd.DataFrame:
    client = get_accounts_client()
    if client is None:
        raise RuntimeError("accounts client unavailable")
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        tt = [getattr(client.Transaction.TransactionType, t, t) for t in FLOW_TYPES]
    except Exception:
        tt = list(FLOW_TYPES)

    # Fetch without type filter if enum fails — filter in Python
    tx = fetch_transactions(client, start_date=start, end_date=end, transaction_types=None)
    rows = []
    if tx is None or tx.empty:
        return pd.DataFrame()

    cols = {c.lower(): c for c in tx.columns}
    for _, r in tx.iterrows():
        t_type = str(r.get(cols.get("type", "type"), "") or r.get("Type", "") or "")
        action = str(r.get(cols.get("action", "action"), "") or r.get("Action", "") or "")
        # Raw type may be in a different column depending on parser
        raw_type = t_type.upper() if t_type else action.upper()
        if raw_type not in FLOW_TYPES and action.upper() not in {"TRANSFER", "JOURNAL"}:
            # Keep journals and transfers from action map
            if "TRANSFER" not in action.upper() and "JOURNAL" not in action.upper():
                continue

        acct = str(r.get(cols.get("account", "account"), "") or r.get("Account", ""))
        amount = float(r.get(cols.get("net_amount", "net_amount"), 0) or r.get("Net Amount", 0) or 0)
        # Sign: + into portfolio. Schwab netAmount often positive for receipts.
        pay = str(r.get(cols.get("trade_date", "trade_date"), "") or r.get("Trade Date", ""))[:10]
        tid = str(r.get(cols.get("activity_id", "activity_id"), "") or r.get("Activity Id", "") or "")
        desc = str(r.get(cols.get("description", "description"), "") or r.get("Description", ""))

        classification = "external"
        # Journal between allowlisted accounts → internal
        if "JOURNAL" in raw_type or action.upper() == "JOURNAL":
            # Without counterparty hash we mark unclassified when we cannot prove both legs
            suffix = acct[-4:] if len(acct) >= 4 else ""
            if suffix in DESCOPED_SUFFIXES:
                classification = "external"  # to/from descoped = external from this system's POV
            else:
                classification = "unclassified"  # need both legs to prove internal

        row = {
            "Date": pay,
            "Account": acct,
            "Type": raw_type or action,
            "Amount": amount,
            "Description": desc,
            "Transaction ID": tid,
            "Classification": classification,
        }
        row["Fingerprint"] = _fp(row)
        rows.append(row)

    return pd.DataFrame(rows)


def main(live: bool = False, days: int = 90) -> None:
    if not hasattr(config, "TAB_CASH_FLOWS"):
        config.TAB_CASH_FLOWS = "Cash_Flows"  # type: ignore

    df = build_ledger(days=days)
    print(f"CASH_FLOWS — proposed {len(df)} rows (days={days})")
    if not df.empty:
        print(df.to_string(index=False))
        print(f"unclassified={int((df['Classification']=='unclassified').sum())}")
        print(f"internal={int((df['Classification']=='internal').sum())}")
    else:
        print("(empty)")
    if not live:
        print("DRY RUN — no Sheet write.")
        return

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    tab = getattr(config, "TAB_CASH_FLOWS", "Cash_Flows")
    try:
        ws = ss.worksheet(tab)
        existing = ws.get_all_records()
        existing_fps = {str(r.get("Fingerprint", "")) for r in existing}
    except Exception:
        ws = ss.add_worksheet(tab, rows=2000, cols=10)
        existing_fps = set()
        ws.update("A1", [list(df.columns) if not df.empty else [
            "Date", "Account", "Type", "Amount", "Description",
            "Transaction ID", "Classification", "Fingerprint",
        ]])

    new_rows = []
    for _, r in df.iterrows():
        if r["Fingerprint"] in existing_fps:
            continue
        new_rows.append([r.get(c, "") for c in df.columns])
    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
    print(f"Appended {len(new_rows)} new Cash_Flows rows (dedup skipped {len(df)-len(new_rows)})")


@app.command()
def cli(
    live: bool = typer.Option(False, "--live"),
    days: int = typer.Option(90, "--days"),
):
    main(live=live, days=days)


if __name__ == "__main__":
    app()
