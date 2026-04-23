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

# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------

def _load_latest_composite_bundle():
    """Return latest CompositeBundle object, or None if not found."""
    from core.composite_bundle import resolve_latest_bundles, load_composite_bundle, CompositeBundle
    from core.composite_bundle import build_composite_bundle
    try:
        market_path, vault_path = resolve_latest_bundles()
        return build_composite_bundle(market_path, vault_path)
    except Exception as e:
        print(f"Warning: Could not load composite bundle for Decision_View: {e}")
        return None

def _load_latest_market_bundle() -> dict | None:
    """Return latest market bundle dict, or None if not found."""
    from pathlib import Path
    import json
    candidates = sorted(
        Path("bundles").glob("context_bundle_*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    try:
        with open(candidates[-1], "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        print(f"Warning: Could not load market bundle: {e}")
        return None

app = typer.Typer()

_ACTION_SEVERITIES = {"action", "alert", "data_quality"}


def get_latest_agent_outputs(ws_agent):
    """
    Reads Agent_Outputs and returns signals from the LATEST run only.

    Handles both legacy 11-col format (run_id, run_ts, ...) and
    compact 10-col format (run_date, run_id_short, ...) written by analyze-all.
    """
    all_values = ws_agent.get_all_values()
    if len(all_values) < 2:
        return pd.DataFrame()

    # Detect header row
    header_row_idx = -1
    for i, row in enumerate(all_values[:5]):
        if 'agent' in [str(h).strip().lower() for h in row]:
            header_row_idx = i
            break

    if header_row_idx == -1:
        return pd.DataFrame()

    headers = [str(h).strip().lower() for h in all_values[header_row_idx]]
    data = all_values[header_row_idx + 1:]

    df = pd.DataFrame(data, columns=headers)
    if df.empty:
        return pd.DataFrame()

    # Normalize column aliases
    rename_map = {
        "run_date":      "run_ts",
        "run_id_short":  "run_id",
        "signal":        "signal_type",
        "narrative":     "rationale",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Filter to LATEST run only (Task 3 fix)
    df["run_ts_dt"] = pd.to_datetime(df["run_ts"], errors="coerce")
    if not df["run_ts_dt"].dropna().empty:
        latest_ts = df["run_ts_dt"].max()
        # Get one of the run_ids from the latest timestamp
        latest_run_id = df[df["run_ts_dt"] == latest_ts]["run_id"].iloc[0]
        df = df[df["run_id"] == latest_run_id]
        print(f"  ✓ Filtering Decision View to latest run: {latest_run_id} ({latest_ts})")

    return df

@app.command()
def main(live: bool = typer.Option(False, "--live", help="Write to Google Sheets")):
    print(f"Building Decision View (Live={live})...")
    
    # --- Load bundles ---
    composite_bundle = _load_latest_composite_bundle()
    
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
            
        # Agent Signals — only surface severity in (action, alert, data_quality)
        # Empty cell = "no active signal" (not "Not Evaluated"); hold/info/watch rows are noise
        ticker_agents = df_agent[df_agent['ticker'] == ticker] if not df_agent.empty else pd.DataFrame()

        def get_active_signal(agent_name: str) -> str:
            """Return signal_type if latest row has action-level severity, else ''."""
            if ticker_agents.empty:
                return ''
            agent_rows = ticker_agents[ticker_agents['agent'] == agent_name]
            if agent_rows.empty:
                return ''
            row = agent_rows.iloc[0]  # already sorted by run_ts descending
            sev = str(row.get('severity', '')).lower()
            if sev not in _ACTION_SEVERITIES:
                return ''
            return str(row.get('signal_type', '') or row.get('action', ''))

        def get_concentration_flag(tkr: str) -> str:
            """Return concentration flag text if this ticker is flagged at action severity."""
            if df_agent.empty:
                return ''
            conc_rows = df_agent[
                (df_agent['agent'] == 'concentration')
                & (df_agent['ticker'] == tkr)
                & (df_agent['severity'].str.lower().isin(_ACTION_SEVERITIES))
            ]
            if conc_rows.empty:
                return ''
            return str(conc_rows.iloc[0].get('signal_type', 'flagged'))

        val_signal = get_active_signal('valuation')
        macro_signal = get_active_signal('macro')
        thesis_signal = get_active_signal('thesis')
        conc_flag = get_concentration_flag(ticker)

        # TLH Flag — tax agent uses ticker-level rows
        tlh_flag = ""
        if not ticker_agents.empty:
            tax_rows = ticker_agents[ticker_agents['agent'] == 'tax']
            if not tax_rows.empty:
                sig = str(tax_rows.iloc[0].get('signal_type', '')).lower()
                if 'tlh' in sig:
                    tlh_flag = "TLH"

        # Top Rationale — highest-severity, non-generic narrative for this ticker
        top_rationale = ""
        for agent_name in ('valuation', 'macro', 'thesis'):
            if ticker_agents.empty:
                break
            agent_rows = ticker_agents[ticker_agents['agent'] == agent_name]
            if agent_rows.empty:
                continue
            row = agent_rows.iloc[0]
            sev = str(row.get('severity', '')).lower()
            if sev not in _ACTION_SEVERITIES:
                continue
            rat = str(row.get('rationale', '') or row.get('action', ''))
            if rat and "Insufficient data" not in rat:
                top_rationale = rat[:120]
                break

        # Goal 1: Map results and ensure raw decimals for percentages
        results.append({
            'Ticker': ticker,
            'Weight %': row_h.get('Weight', 0.0),
            'Market Value': row_h.get('Market Value', 0.0),
            'Unreal G/L %': row_h.get('Unrealized G/L %', 0.0),
            'Daily Chg %': row_h.get('Daily Change %', 0.0),
            'Price': row_h.get('Price', 0.0),
            'Trim Target': composite_bundle.get_ticker_triggers(ticker).get('price_trim_above') if composite_bundle else None,
            'Add Target': composite_bundle.get_ticker_triggers(ticker).get('price_add_below') if composite_bundle else None,
            'Fwd P/E': val_data['Fwd P/E'],
            '52w Pos %': val_data['52w Pos %'],
            'Disc from High %': val_data['Disc from High %'],
            'Valuation Signal': val_signal,
            'Top Rationale': top_rationale,
        })
            
    df_decision = pd.DataFrame(results)
    
    # Sorting: Weight % descending
    df_decision = df_decision.sort_values(by=['Weight %'], ascending=[False])
    
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
