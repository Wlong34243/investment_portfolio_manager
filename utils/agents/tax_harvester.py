import pandas as pd
import logging
from datetime import datetime, timedelta
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE
from utils.fmp_client import get_company_profile

def scan_harvest_opportunities(holdings_df: pd.DataFrame, min_loss_dollars: float = 500.0) -> pd.DataFrame:
    """
    Filter for positions where Unrealized_GL <= -min_loss_dollars.
    Calculate Tax_Asset_Value (15% offset rate).
    """
    losses = holdings_df[holdings_df['Unrealized G/L'] <= -min_loss_dollars].copy()
    losses['tax_asset_value'] = losses['Unrealized G/L'].abs() * 0.15
    return losses.sort_values(by='Unrealized G/L')

def verify_wash_sale_clearance(ticker: str, realized_gl_df: pd.DataFrame) -> bool:
    """
    Check if ticker was sold at a loss in the past 30 days.
    """
    if realized_gl_df.empty:
        return True
        
    thirty_days_ago = datetime.now() - timedelta(days=30)
    try:
        realized_gl_df['Closed Date'] = pd.to_datetime(realized_gl_df['Closed Date'])
        recent_losses = realized_gl_df[
            (realized_gl_df['Ticker'] == ticker) & 
            (realized_gl_df['Closed Date'] > thirty_days_ago) & 
            (realized_gl_df['Gain Loss $'] < 0)
        ]
        return recent_losses.empty
    except:
        return True

def generate_harvest_proposal(ticker: str, loss_amount: float, tax_asset: float, profile: dict) -> dict:
    """
    Gemini JSON: rationale, savings, proxy_options, risks.
    """
    prompt = f"""
    Ticker: {ticker}
    Unrealized Loss: ${abs(loss_amount):,.2f}
    Estimated Tax Savings (15% rate): ${tax_asset:,.2f}
    
    Company Profile: {profile.get('sector')}, {profile.get('industry')}
    
    Suggest 2 highly correlated but legally distinct proxy securities (ETFs or competitors) 
    to maintain market exposure for 31 days while avoiding the wash-sale rule.
    """
    
    system_instruction = f"""
    {SAFETY_PREAMBLE}
    You are a tax-loss harvesting advisor for a CPA.
    Suggest proxy options to maintain exposure while harvesting losses.
    Respond ONLY with JSON:
    {{
        "harvest_rationale": str,
        "estimated_tax_savings": float,
        "proxy_options": [{{ "ticker": str, "description": str, "correlation_rationale": str }}],
        "risks": [str]
    }}
    """
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"TLH proposal error for {ticker}: {e}")
        return {"error": str(e)}

def build_tlh_report(holdings_df: pd.DataFrame, realized_gl_df: pd.DataFrame) -> list[dict]:
    """
    Scan, filter wash sales, and generate proposals for top 3 losses.
    """
    opps = scan_harvest_opportunities(holdings_df)
    results = []
    
    # Filter wash sales
    cleared_opps = opps[opps['Ticker'].apply(lambda x: verify_wash_sale_clearance(x, realized_gl_df))]
    
    for _, row in cleared_opps.head(3).iterrows():
        ticker = row['Ticker']
        profile = get_company_profile(ticker)
        proposal = generate_harvest_proposal(ticker, row['Unrealized G/L'], row['tax_asset_value'], profile)
        if "error" not in proposal:
            proposal['ticker'] = ticker
            proposal['loss'] = row['Unrealized G/L']
            results.append(proposal)
            
    return results
