"""
tasks/build_valuation_card.py — Fetches yfinance data and writes Valuation_Card tab.
"""

import os
import sys
import pandas as pd
import yfinance as yf
import typer
from typing import Optional
import time

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client, read_gsheet_robust

app = typer.Typer()

# Centralized exclusion list from config (Task 1)
EXCLUDE_TICKERS = set(config.VALUATION_SKIP)

def fetch_ticker_valuation(ticker_symbol: str):
    """Fetches valuation data for a single ticker via yfinance."""
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info
        
        # Validation: include only equities
        if info.get('quoteType') != 'EQUITY':
            return None
            
        high = info.get('fiftyTwoWeekHigh')
        low = info.get('fiftyTwoWeekLow')
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        
        pos_52w = None
        if high and low and price and (high - low) != 0:
            pos_52w = (price - low) / (high - low)
            
        disc_52w_high = None
        if high and price:
            disc_52w_high = (high - price) / high
            
        # Handle PEG N/A gracefully (Task 5)
        peg = info.get('pegRatio')
        if peg is None or str(peg).lower() in ('nan', 'none', ''):
            peg = "N/A"

        return {
            'Ticker': ticker_symbol,
            'Name': info.get('shortName', ''),
            'Market Cap': info.get('marketCap'),
            'Price': price,
            'Trailing P/E': info.get('trailingPE'),
            'Forward P/E': info.get('forwardPE'),
            'P/B': info.get('priceToBook'),
            'PEG': peg,
            '52w Low': low,
            '52w High': high,
            '52w Position %': pos_52w,
            'Discount from 52w High %': disc_52w_high,
            'Rev Growth %': info.get('revenueGrowth'),
            'ROE %': info.get('returnOnEquity'),
            'D/E': info.get('debtToEquity'),
            'FCF': info.get('freeCashflow'),
            'Div Yield %': info.get('dividendYield'),
            'Last Updated': time.strftime('%Y-%m-%d %H:%M')
        }
    except Exception as e:
        print(f"  ⚠ Failed to fetch {ticker_symbol}: {e}")
        return None

@app.command()
def main(live: bool = typer.Option(False, "--live", help="Write to Google Sheets")):
    print(f"Building Valuation Card (Live={live})...")
    
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws_holdings = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)
    
    # Read Holdings_Current skipping KPI row
    all_values = ws_holdings.get_all_values()
    if len(all_values) < 2:
        print("Error: Holdings_Current is empty.")
        return
        
    # Detect where headers are (search first 5 rows)
    header_row_idx = -1
    for i, row in enumerate(all_values[:5]):
        if 'Ticker' in row or 'ticker' in [str(h).strip().lower() for h in row]:
            header_row_idx = i
            break
            
    if header_row_idx == -1:
        print("Error: Could not find 'Ticker' column in first 5 rows of Holdings_Current.")
        return
        
    headers = all_values[header_row_idx]
    data = all_values[header_row_idx + 1:]
        
    df_holdings = pd.DataFrame(data, columns=headers)
    
    # Use column_guard for normalization
    from utils.column_guard import ensure_display_columns
    df_holdings = ensure_display_columns(df_holdings)
    
    # Filter tickers
    tickers = df_holdings['Ticker'].unique()
    tickers = [t for t in tickers if t and t not in EXCLUDE_TICKERS]
    
    print(f"Fetching data for {len(tickers)} tickers...")
    
    results = []
    for t in tickers:
        print(f"  Processing {t}...", end="\r")
        val = fetch_ticker_valuation(t)
        if val:
            results.append(val)
        time.sleep(0.1) # Respect rate limits
        
    if not results:
        print("No valuation data found.")
        return
        
    df_val = pd.DataFrame(results)
    df_val = df_val.sort_values(by='Market Cap', ascending=False)
    
    # Clean NaNs to empty strings for GSheets
    df_val = df_val.fillna('')
    
    if not live:
        print("\nDRY RUN: Valuation Data Preview")
        print(df_val.to_string(index=False))
        return
        
    # Live Write
    tab_name = "Valuation_Card"
    try:
        ws_val = spreadsheet.worksheet(tab_name)
        ws_val.clear()
    except:
        ws_val = spreadsheet.add_worksheet(title=tab_name, rows=100, cols=20)
        
    # Prepare data for update
    data_to_write = [df_val.columns.tolist()] + df_val.values.tolist()
    ws_val.update(range_name='A1', values=data_to_write)
    
    print(f"\n✅ Successfully wrote {len(df_val)} rows to {tab_name}")

if __name__ == "__main__":
    app()
