import pandas as pd
import logging
import streamlit as st
import config
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE
from utils.sheet_readers import get_gspread_client
from utils.fmp_client import get_company_profile

# --- Schemas ---

class RebalanceOption(BaseModel):
    label: str
    description: str
    tax_impact: str
    estimated_tax_impact_level: str

class RebalanceProposal(BaseModel):
    category: str
    options: List[RebalanceOption]

class TLHProxyOption(BaseModel):
    ticker: str
    description: str
    correlation_rationale: str

class TLHProposal(BaseModel):
    ticker: str
    harvest_rationale: str
    unrealized_loss: float
    estimated_tax_savings: float
    proxy_options: List[TLHProxyOption]
    risks: List[str]

# --- Target Allocation & Drift (Rebalancing) ---

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
    """Compare actual weight vs target with robust column matching."""
    if targets_df.empty or holdings_df.empty: return pd.DataFrame()
    
    # 1. Standardize Target Labels
    # If "Asset Class" exists in targets, use it as the merge key
    if 'Asset Class' in targets_df.columns:
        targets_df = targets_df.rename(columns={'Asset Class': 'Category'})
    elif 'Category' not in targets_df.columns:
        potential_labels = [c for c in targets_df.columns if 'target' not in c.lower() and '%' not in c.lower()]
        if potential_labels: 
            targets_df = targets_df.rename(columns={potential_labels[0]: 'Category'})
        else: 
            return pd.DataFrame()

    # 2. Standardize Holdings Labels
    # Many mappings: Technology -> Information Technology, etc.
    h_df = holdings_df.copy()
    mapping = {
        'Technology': 'Information Technology',
        'Broad Market': 'Equities', # Or map to a specific target if known
        'Healthcare': 'Healthcare',
        'Communication Services': 'Communication Services',
        'Financials': 'Financials'
    }
    h_df['Asset Class'] = h_df['Asset Class'].replace(mapping)

    actual_weights = h_df.groupby('Asset Class')['Weight'].sum().reset_index()
    actual_weights.columns = ['Category', 'Actual %']
    
    # Merge with targets
    drift_df = pd.merge(actual_weights, targets_df, on='Category', how='outer')

    # Fill NA before type conversion
    drift_df = drift_df.infer_objects(copy=False).fillna(0)

    # Standardize Percentage Math
    target_col = next((c for c in drift_df.columns if 'Target' in c or '%' in c), None)
    if target_col:
        # Explicit conversion to float
        raw_targets = pd.to_numeric(drift_df[target_col], errors='coerce').fillna(0).astype(float)
        drift_df['Target %'] = raw_targets if raw_targets.max() > 1.0 else raw_targets * 100
        drift_df['Actual %'] = drift_df['Actual %'].astype(float)
        drift_df['Drift %'] = drift_df['Actual %'] - drift_df['Target %']
    else:
        drift_df['Target %'] = 0.0
        drift_df['Actual %'] = drift_df['Actual %'].astype(float)
        drift_df['Drift %'] = 0.0

    drift_df['Target %'] = drift_df['Target %'].astype(float)
    drift_df['Actual %'] = drift_df['Actual %'].astype(float)
    drift_df['Drift %'] = drift_df['Drift %'].astype(float)
    drift_df['Breach'] = drift_df['Drift %'].abs() > 5.0

    return drift_df

def generate_rebalance_proposals(drift_df: pd.DataFrame, holdings_df: pd.DataFrame) -> list[dict]:
    """AI-generated rebalancing suggestions using the Rule of Three."""
    proposals = []
    overweight = drift_df[drift_df['Drift %'] > 2.0]
    
    for _, row in overweight.iterrows():
        cat = row['Category']
        tickers = holdings_df[holdings_df['Asset Class'] == cat]['Ticker'].tolist()
        prompt = f"""
        Category '{cat}' is overweight by {row['Drift %']:.2f}%.
        Target: {row['Target %']:.2f}%, Actual: {row['Actual %']:.2f}%.
        
        Suggest 3 rebalancing options for these tickers: {tickers}.
        Analyze tax impact qualitatively (LT vs ST). Do NOT attempt to calculate exact tax dollars.
        """
        
        system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a tax-aware rebalancing advisor for a CPA. Focus on 'The Rule of Three' options."
        
        try:
            res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=RebalanceProposal)
            if res:
                proposals.append(res.model_dump())
        except Exception as e:
            logging.error(f"Rebalance proposal error for {cat}: {e}")
            
    return proposals

# --- Tax Loss Harvesting (TLH) ---

def scan_harvest_opportunities(holdings_df: pd.DataFrame, min_loss_dollars: float = 500.0) -> pd.DataFrame:
    """Filter for positions with significant unrealized losses."""
    df = holdings_df.copy()
    df['Unrealized G/L'] = pd.to_numeric(df['Unrealized G/L'], errors='coerce').fillna(0.0)
    losses = df[df['Unrealized G/L'] <= -min_loss_dollars].copy()
    losses['tax_asset_value'] = losses['Unrealized G/L'].abs() * 0.15
    return losses.sort_values(by='Unrealized G/L')

def check_wash_sale_risk(ticker: str, realized_gl_df: pd.DataFrame) -> dict:
    """Check for recent losses in this ticker (past 30 days). Returns status dict."""
    if realized_gl_df.empty:
        return {"at_risk": False}
        
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
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

def build_tlh_report(holdings_df: pd.DataFrame, realized_gl_df: pd.DataFrame) -> list[dict]:
    """Scan, filter wash sales, and generate AI proposals for top losses."""
    opps = scan_harvest_opportunities(holdings_df)
    results = []
    
    # Filter wash sales (Helper function inside for boolean filtering)
    def _is_safe(ticker):
        risk = check_wash_sale_risk(ticker, realized_gl_df)
        return not risk['at_risk']

    cleared_opps = opps[opps['Ticker'].apply(_is_safe)]
    
    for _, row in cleared_opps.head(3).iterrows():
        ticker = row['Ticker']
        profile = get_company_profile(ticker)
        
        prompt = f"""
        Ticker: {ticker}
        Unrealized Loss: ${abs(row['Unrealized G/L']):,.2f}
        Estimated Tax Savings (15% rate): ${row['tax_asset_value']:,.2f}
        Company Profile: {profile.get('sector')}, {profile.get('industry')}
        
        Suggest 2 highly correlated but legally distinct proxy securities (ETFs or competitors) 
        to maintain market exposure for 31 days while avoiding the wash-sale rule.
        """
        
        system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a tax-loss harvesting advisor for a CPA. Suggest proxy options to maintain exposure."
        
        try:
            res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=TLHProposal)
            if res:
                p_dict = res.model_dump()
                p_dict['unrealized_loss'] = abs(row['Unrealized G/L'])
                results.append(p_dict)
        except Exception as e:
            logging.error(f"TLH proposal error for {ticker}: {e}")
            
    return results
