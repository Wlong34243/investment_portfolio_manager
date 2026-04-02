import pandas as pd
import logging
import streamlit as st
import config
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE
from utils.sheet_readers import get_gspread_client

@st.cache_data(ttl=300)
def get_target_allocation():
    """Read Target_Allocation tab from Google Sheets."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_TARGET_ALLOCATION)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        logging.error(f"Error reading Target_Allocation: {e}")
        return pd.DataFrame()

def calculate_drift(holdings_df: pd.DataFrame, targets_df: pd.DataFrame) -> pd.DataFrame:
    """
    Actual vs Target, drift, breach flags.
    Targets are usually by 'Asset Class' or 'Asset Strategy'.
    """
    if targets_df.empty:
        return pd.DataFrame()
        
    # Group actuals by the target dimension (assume 'Asset Class')
    actual_weights = holdings_df.groupby('Asset Class')['Weight'].sum().reset_index()
    actual_weights.columns = ['Category', 'Actual %']
    
    # Merge with targets
    # Assume targets_df has 'Category' and 'Target %'
    drift_df = pd.merge(actual_weights, targets_df, on='Category', how='outer').fillna(0)
    drift_df['Drift %'] = drift_df['Actual %'] - drift_df['Target %']
    
    # Simple breach logic (e.g., > 5% absolute drift)
    drift_df['Breach'] = drift_df['Drift %'].abs() > 5.0
    
    return drift_df

def get_tax_lots_for_ticker(ticker: str) -> pd.DataFrame:
    """
    Fetch lots from Realized_GL or a dedicated Lots tab if available.
    In this app's current schema, we ingest Realized_GL, but individual lots 
    for CURRENT holdings are usually in the CSV positions.
    """
    # This is a placeholder for more complex lot tracking
    return pd.DataFrame()

def check_wash_sale_risk(ticker: str, realized_gl_df: pd.DataFrame) -> dict:
    """Check for recent losses in this ticker (past 30 days)."""
    if realized_gl_df.empty:
        return {"at_risk": False}
        
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # Assume realized_gl_df has 'Ticker', 'Closed Date', and 'Gain Loss $'
    # Need to handle date parsing
    try:
        realized_gl_df['Closed Date'] = pd.to_datetime(realized_gl_df['Closed Date'])
        recent_losses = realized_gl_df[
            (realized_gl_df['Ticker'] == ticker) & 
            (realized_gl_df['Closed Date'] > thirty_days_ago) & 
            (realized_gl_df['Gain Loss $'] < 0)
        ]
        
        if not recent_losses.empty:
            last_loss = recent_losses.iloc[0]
            return {
                "at_risk": True,
                "last_loss_date": last_loss['Closed Date'].strftime("%Y-%m-%d"),
                "loss_amount": last_loss['Gain Loss $'],
                "warning": f"Wash sale risk: Loss of ${abs(last_loss['Gain Loss $']):,.2f} on {last_loss['Closed Date'].strftime('%m/%d')}"
            }
    except Exception:
        pass
        
    return {"at_risk": False}

def generate_rebalance_proposals(drift_df: pd.DataFrame, holdings_df: pd.DataFrame) -> list[dict]:
    """
    "Rule of Three" per overweight strategy via Gemini.
    """
    proposals = []
    overweight = drift_df[drift_df['Drift %'] > 2.0] # 2% threshold for proposal
    
    for _, row in overweight.iterrows():
        cat = row['Category']
        prompt = f"""
        Category '{cat}' is overweight by {row['Drift %']:.2f}%.
        Target: {row['Target %']:.2f}%, Actual: {row['Actual %']:.2f}%.
        
        Suggest 3 rebalancing options for this overweight position.
        Include tax impact considerations (LT vs ST gains).
        Reference specific tickers within this category: {holdings_df[holdings_df['Asset Class'] == cat]['Ticker'].tolist()}
        """
        
        system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a tax-aware rebalancing advisor for a CPA. Provide 3 options (The Rule of Three) per overweight position. JSON format: {{'category': str, 'options': [{{'label': str, 'description': str, 'tax_impact': str, 'estimated_tax': str}}]}}"
        
        try:
            res = ask_gemini_json(prompt, system_instruction=system_instruction)
            if res:
                proposals.append(res)
        except Exception as e:
            logging.error(f"Rebalance proposal error for {cat}: {e}")
            
    return proposals
