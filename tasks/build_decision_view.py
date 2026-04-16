"""
tasks/build_decision_view.py — Joins Holdings, Valuation, and Agent Outputs into Decision_View tab.
"""

import os
import sys
import pandas as pd
import typer
from typing import Optional
import time

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client

app = typer.Typer()

def get_latest_agent_outputs(ws_agent):
    """Reads Agent_Outputs and returns the latest signal per ticker per agent."""
    all_values = ws_agent.get_all_values()
    if len(all_values) < 2:
        return pd.DataFrame()
        
    # Detect where headers are (search first 5 rows for 'agent' column)
    header_row_idx = -1
    for i, row in enumerate(all_values[:5]):
        if 'agent' in [str(h).strip().lower() for h in row]:
            header_row_idx = i
            break
            
    if header_row_idx == -1:
        print("Warning: Could not find 'agent' column in first 5 rows of Agent_Outputs.")
        return pd.DataFrame()

    headers = all_values[header_row_idx]
    data = all_values[header_row_idx + 1:]
    
    df = pd.DataFrame(data, columns=headers)
    
    if df.empty:
        return pd.DataFrame()
        
    # Standardize column names if they are different from what we expect
    # run_id, run_ts, composite_hash, agent, signal_type, ticker, action, rationale, scale_step, severity, dry_run
    
    # Sort by run_ts descending to get latest first
    df['run_ts'] = pd.to_datetime(df['run_ts'], errors='coerce')
    df = df.sort_values(by='run_ts', ascending=False)
    
    return df

@app.command()
def main(live: bool = typer.Option(False, "--live", help="Write to Google Sheets")):
    print(f"Building Decision View (Live={live})...")
    
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    
    # 1. Read Holdings_Current
    ws_holdings = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)
    all_holdings = ws_holdings.get_all_values()
    
    # Detect where headers are (search first 5 rows)
    header_row_idx = -1
    for i, row in enumerate(all_holdings[:5]):
        if 'Ticker' in row or 'ticker' in [str(h).strip().lower() for h in row]:
            header_row_idx = i
            break
            
    if header_row_idx == -1:
        print("Error: Could not find 'Ticker' column in first 5 rows of Holdings_Current.")
        return
        
    headers = all_holdings[header_row_idx]
    data = all_holdings[header_row_idx + 1:]

    df_holdings = pd.DataFrame(data, columns=headers)
    
    # Use column_guard for normalization
    from utils.column_guard import ensure_display_columns
    df_holdings = ensure_display_columns(df_holdings)
    
    # Filter out cash
    df_holdings = df_holdings[~df_holdings['Ticker'].isin(['CASH_MANUAL', 'QACDS', 'CASH & CASH INVESTMENTS'])]
    
    # 2. Read Valuation_Card
    try:
        ws_val = spreadsheet.worksheet("Valuation_Card")
        df_val = pd.DataFrame(ws_val.get_all_records())
    except Exception as e:
        print(f"Warning: Could not read Valuation_Card: {e}")
        df_val = pd.DataFrame(columns=['Ticker', 'Forward P/E', '52w Position %', 'Discount from 52w High %'])

    # 3. Read Agent_Outputs
    ws_agent = spreadsheet.worksheet(config.TAB_AGENT_OUTPUTS)
    df_agent = get_latest_agent_outputs(ws_agent)
    
    # Join Logic
    # We want one row per ticker from Holdings_Current
    results = []
    
    tickers = df_holdings['Ticker'].unique()
    
    for ticker in tickers:
        row_h = df_holdings[df_holdings['Ticker'] == ticker].iloc[0]
        
        # Valuation Data
        val_data = {}
        if not df_val.empty and ticker in df_val['Ticker'].values:
            row_v = df_val[df_val['Ticker'] == ticker].iloc[0]
            val_data = {
                'Fwd P/E': row_v.get('Forward P/E', ''),
                '52w Pos %': row_v.get('52w Position %', ''),
                'Disc from High %': row_v.get('Discount from 52w High %', '')
            }
        else:
            val_data = {'Fwd P/E': '', '52w Pos %': '', 'Disc from High %': ''}
            
        # Agent Signals
        ticker_agents = df_agent[df_agent['ticker'] == ticker] if not df_agent.empty else pd.DataFrame()
        
        def get_agent_signal(agent_name):
            if ticker_agents.empty: return ''
            matches = ticker_agents[ticker_agents['agent'] == agent_name]
            if matches.empty: return ''
            return matches.iloc[0].get('signal_type', '') or matches.iloc[0].get('action', '')
            
        val_signal = get_agent_signal('valuation')
        macro_signal = get_agent_signal('macro')
        thesis_signal = get_agent_signal('thesis')
        tax_signal = get_agent_signal('tax')
        
        # TLH Flag
        tlh_flag = ""
        if tax_signal.lower() == 'tlh_candidate':
            tlh_flag = "⚠️ TLH"
            
        # Top Rationale
        top_rationale = ""
        # Priority: Valuation (if not insufficient) > Macro > Thesis
        val_match = ticker_agents[ticker_agents['agent'] == 'valuation']
        if not val_match.empty:
            rat = val_match.iloc[0].get('rationale', '')
            if "Insufficient data" not in rat:
                top_rationale = rat[:120]
        
        if not top_rationale:
            macro_match = ticker_agents[ticker_agents['agent'] == 'macro']
            if not macro_match.empty:
                top_rationale = macro_match.iloc[0].get('action', '')[:60]
                
        if not top_rationale:
            thesis_match = ticker_agents[ticker_agents['agent'] == 'thesis']
            if not thesis_match.empty:
                top_rationale = thesis_match.iloc[0].get('action', '')[:60]
                
        results.append({
            'Ticker': ticker,
            'Weight %': row_h.get('Weight', 0.0),
            'Market Value': row_h.get('Market Value', 0.0),
            'Unreal G/L %': row_h.get('Unrealized G/L %', 0.0),
            'Daily Chg %': row_h.get('Daily Change %', 0.0),
            'Fwd P/E': val_data['Fwd P/E'],
            '52w Pos %': val_data['52w Pos %'],
            'Disc from High %': val_data['Disc from High %'],
            'Valuation Signal': val_signal,
            'Macro Signal': macro_signal,
            'Thesis Signal': thesis_signal,
            'TLH Flag': tlh_flag,
            'Top Rationale': top_rationale
        })
            
    df_decision = pd.DataFrame(results)
    
    # Sorting: TLH first, then Weight % descending
    df_decision['is_tlh'] = df_decision['TLH Flag'].apply(lambda x: 1 if x else 0)
    df_decision = df_decision.sort_values(by=['is_tlh', 'Weight %'], ascending=[False, False])
    df_decision = df_decision.drop(columns=['is_tlh'])
    
    # Final data cleaning for display (format percentages/currency if desired, 
    # but GSheets formatting usually handles this better if kept numeric)
    # We will keep them numeric for GSheets formatting.
    
    if not live:
        print("\nDRY RUN: Decision View Preview")
        print(df_decision.to_string(index=False))
        return
        
    # Live Write
    tab_name = "Decision_View"
    try:
        ws_dec = spreadsheet.worksheet(tab_name)
        ws_dec.clear()
    except:
        ws_dec = spreadsheet.add_worksheet(title=tab_name, rows=100, cols=20)
        
    # Clean NaNs
    df_decision = df_decision.fillna('')
    
    data_to_write = [df_decision.columns.tolist()] + df_decision.values.tolist()
    ws_dec.update(range_name='A1', values=data_to_write)
    
    print(f"\n✅ Successfully wrote {len(df_decision)} rows to {tab_name}")

if __name__ == "__main__":
    app()
