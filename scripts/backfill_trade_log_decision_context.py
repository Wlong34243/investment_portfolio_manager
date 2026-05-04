"""
scripts/backfill_trade_log_decision_context.py
─────────────────────────────────────────────
Backfills missing technical snapshot columns (RSI, Trend, MA200) for existing 
rows in the Trade_Log sheet.

Usage:
    python scripts/backfill_trade_log_decision_context.py
"""

import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

# Project root on path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from utils.sheet_readers import get_gspread_client
from tasks.derive_rotations import _get_historical_technicals
from rich.console import Console
from rich.progress import track

console = Console()

def backfill():
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_TRADE_LOG)
    
    rows = ws.get_all_values()
    if len(rows) < 2:
        console.print("[yellow]Trade_Log is empty.[/]")
        return

    headers = rows[0]
    data = rows[1:]

    try:
        idx_date = headers.index("Date")
        idx_sell_t = headers.index("Sell_Ticker")
        idx_buy_t = headers.index("Buy_Ticker")
        
        idx_sell_rsi = headers.index("Sell_RSI_At_Decision")
        idx_sell_trend = headers.index("Sell_Trend_At_Decision")
        idx_sell_ma200 = headers.index("Sell_Price_vs_MA200_At_Decision")
        
        idx_buy_rsi = headers.index("Buy_RSI_At_Decision")
        idx_buy_trend = headers.index("Buy_Trend_At_Decision")
        idx_buy_ma200 = headers.index("Buy_Price_vs_MA200_At_Decision")
    except ValueError as e:
        console.print(f"[red]ERROR: Sheet headers missing new columns: {e}[/]")
        return

    updated_count = 0
    
    for i, row in enumerate(track(data, description="Backfilling technicals...")):
        row_num = i + 2
        
        # Parse date
        try:
            dt_str = row[idx_date]
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                try:
                    dt = datetime.strptime(dt_str, fmt).date()
                    break
                except: continue
            else: raise ValueError("Invalid date")
        except:
            continue

        sell_ticker = row[idx_sell_t].split(",")[0].strip() if row[idx_sell_t] else None
        buy_ticker = row[idx_buy_t].split(",")[0].strip() if row[idx_buy_t] else None
        
        # Check if we need to backfill
        needs_fill = any(not row[idx] for idx in [idx_sell_rsi, idx_buy_rsi])
        
        if needs_fill:
            if sell_ticker:
                s_tech = _get_historical_technicals(sell_ticker, dt)
                row[idx_sell_rsi] = str(s_tech.get("rsi") or "")
                row[idx_sell_trend] = s_tech.get("trend", "")
                row[idx_sell_ma200] = str(s_tech.get("ma200_dist") or "")
            
            if buy_ticker:
                b_tech = _get_historical_technicals(buy_ticker, dt)
                row[idx_buy_rsi] = str(b_tech.get("rsi") or "")
                row[idx_buy_trend] = b_tech.get("trend", "")
                row[idx_buy_ma200] = str(b_tech.get("ma200_dist") or "")
            
            # Update only these 6 columns for this row
            # We'll build a batch update at the end or update individually if small
            updated_count += 1
            time.sleep(0.5) # Avoid rate limits

    if updated_count > 0:
        # Write back full data
        ws.update(range_name=f"A2", values=data, value_input_option="USER_ENTERED")
        console.print(f"[bold green]SUCCESS:[/] Backfilled {updated_count} rows in {config.TAB_TRADE_LOG}.")
    else:
        console.print("[green]No rows needed backfilling.[/]")

if __name__ == "__main__":
    backfill()
