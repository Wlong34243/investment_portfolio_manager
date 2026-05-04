"""
One-off script to audit the Trade_Log sheet for data corruption.
Flags suspicious rows for manual review/cleanup.

Usage:
    python scripts/repair_trade_log.py
"""

import sys
from pathlib import Path
import logging

# ---------------------------------------------------------------------------
# Project root on path
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from utils.sheet_readers import get_gspread_client
from rich.console import Console
from rich.table import Table

console = Console()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_numeric(v):
    if v is None: return False
    s = str(v).strip().replace("$", "").replace(",", "")
    try:
        float(s)
        return True
    except ValueError:
        return False

def audit_trade_log():
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    
    try:
        ws = ss.worksheet(config.TAB_TRADE_LOG)
    except Exception:
        console.print(f"[red]ERROR: Tab '{config.TAB_TRADE_LOG}' not found.[/]")
        return

    rows = ws.get_all_values()
    if len(rows) < 2:
        console.print("[yellow]Trade_Log is empty.[/]")
        return

    headers = rows[0]
    data = rows[1:]

    # Indices (0-based)
    # Expected: Date, Sell_Ticker, Sell_Proceeds, Buy_Ticker, Buy_Amount, Implicit_Bet, Thesis_Brief, Rotation_Type, Trade_Log_ID, Fingerprint
    try:
        idx_date = headers.index("Date")
        idx_sell_t = headers.index("Sell_Ticker")
        idx_sell_p = headers.index("Sell_Proceeds")
        idx_buy_t = headers.index("Buy_Ticker")
        idx_buy_a = headers.index("Buy_Amount")
        idx_type = headers.index("Rotation_Type")
    except ValueError as e:
        console.print(f"[red]ERROR: Missing expected column in Trade_Log: {e}[/]")
        return

    suspicious = []

    for i, row in enumerate(data):
        row_num = i + 2
        issues = []
        
        # 1. Date check
        d_val = row[idx_date]
        if not ("-" in d_val or "/" in d_val):
            issues.append(f"Suspicious Date: '{d_val}'")
            
        # 2. Ticker check (should not be numeric)
        s_ticker = row[idx_sell_t]
        if is_numeric(s_ticker):
            issues.append(f"Sell_Ticker looks numeric: '{s_ticker}'")
            
        b_ticker = row[idx_buy_t]
        if is_numeric(b_ticker):
            issues.append(f"Buy_Ticker looks numeric: '{b_ticker}'")

        # 3. Numeric checks
        s_proceeds = row[idx_sell_p]
        if not is_numeric(s_proceeds) and s_proceeds.strip() != "":
            issues.append(f"Sell_Proceeds not numeric: '{s_proceeds}'")
            
        b_amount = row[idx_buy_a]
        if not is_numeric(b_amount) and b_amount.strip() != "":
            issues.append(f"Buy_Amount not numeric: '{b_amount}'")

        # 4. Rotation Type check
        valid_types = {"dry_powder", "upgrade", "rebalance", "tax_loss", "cash_parking", "anomalous", "unknown"}
        r_type = row[idx_type].strip().lower()
        if r_type not in valid_types and r_type != "":
            issues.append(f"Unknown Rotation_Type: '{r_type}'")

        if issues:
            suspicious.append({
                "row": row_num,
                "ticker": s_ticker,
                "date": d_val,
                "issues": issues
            })

    if not suspicious:
        console.print("[bold green]Audit Complete:[/] No suspicious rows found in Trade_Log.")
    else:
        table = Table(title=f"Trade_Log Audit Report ({len(suspicious)} suspicious rows)", show_header=True, header_style="bold red")
        table.add_column("Row #", justify="right")
        table.add_column("Date")
        table.add_column("Ticker")
        table.add_column("Issues")
        
        for item in suspicious:
            table.add_row(
                str(item["row"]),
                item["date"],
                item["ticker"],
                "\n".join(item["issues"])
            )
            
        console.print(table)
        console.print("\n[yellow]ACTION REQUIRED:[/] Please review and clean these rows manually in the Google Sheet.")

if __name__ == "__main__":
    audit_trade_log()
