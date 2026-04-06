import pandas as pd
import logging
import yfinance as yf
from pydantic import BaseModel, Field
from typing import List
from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE

OPTIONS_DISCLAIMER = "⚠️ **DISCLAIMER:** Educational analysis only. Covered call strategies involve risks (capping upside, potential assignment). Execute independently after your own research."

class StrategyProposal(BaseModel):
    label: str
    strike: float
    expiry: str
    premium: float
    annualized_yield_pct: float
    max_upside_cap_pct: float
    assignment_probability: str
    recommendation: str

class CoveredCallProposal(BaseModel):
    strategies: List[StrategyProposal]

def find_covered_call_candidates(holdings_df: pd.DataFrame) -> pd.DataFrame:
    if holdings_df.empty: return pd.DataFrame()
    candidates = holdings_df[holdings_df['Quantity'] >= 100].copy()
    candidates = candidates[candidates['Asset Class'].astype(str).str.lower() != 'cash']
    candidates = candidates[~candidates['Ticker'].astype(str).str.upper().isin({'QACDS', 'CASH_MANUAL', 'CASH & CASH INVESTMENTS'})]
    return candidates

def get_options_chain(ticker: str) -> pd.DataFrame:
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations: return pd.DataFrame()
        
        from datetime import datetime, timedelta
        target_date = datetime.now() + timedelta(days=45)
        best_exp = min(expirations, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - target_date).days))
        
        chain = stock.option_chain(best_exp).calls
        current_price = stock.fast_info['lastPrice']
        
        # Filter 5-15% OTM
        min_strike = current_price * 1.05
        max_strike = current_price * 1.15
        
        df = chain[(chain['strike'] >= min_strike) & (chain['strike'] <= max_strike)].copy()
        df['expiration'] = best_exp
        df['current_price'] = current_price
        
        # Python-calculated metrics (Fixing LLM Math Guardrail)
        dte = (datetime.strptime(best_exp, "%Y-%m-%d") - datetime.now()).days
        if dte <= 0: dte = 1
        
        # (Premium / Current Price) * (365 / DTE) * 100
        df['py_yield_ann'] = (df['lastPrice'] / current_price) * (365 / dte) * 100
        df['py_upside_pct'] = ((df['strike'] - current_price) / current_price) * 100
        
        return df
    except Exception as e:
        logging.error(f"Error fetching options for {ticker}: {e}")
        return pd.DataFrame()

def generate_covered_call_proposal(ticker: str, chain_df: pd.DataFrame, holdings_df: pd.DataFrame) -> dict:
    if chain_df.empty: return {"error": f"No valid OTM calls found for {ticker}."}
    
    top_3 = chain_df.head(3)
    
    # Pass calculated math to the prompt so AI just explains it
    prompt = f"""
    Ticker: {ticker} (Price: ${top_3['current_price'].iloc[0]:.2f})
    Expiration: {top_3['expiration'].iloc[0]}
    
    Option Data (Python Calculated):
    {top_3[['strike', 'lastPrice', 'py_yield_ann', 'py_upside_pct', 'impliedVolatility']].to_dict('records')}
    
    Analyze these strikes. Focus on the trade-off between premium yield and assignment risk.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\n{OPTIONS_DISCLAIMER}\n\nYou are an options strategist. Explain the provided math and suggest a conservative path."
    
    try:
        # Use Pydantic schema validation (Aligns with gemini.md)
        proposal = ask_gemini(prompt, system_instruction=system_instruction, response_schema=CoveredCallProposal)
        if proposal:
            return proposal.model_dump()
        return {"error": "AI failed to generate proposal"}
    except Exception as e:
        logging.error(f"Options proposal error for {ticker}: {e}")
        return {"error": str(e)}

def estimate_monthly_premium_potential(holdings_df: pd.DataFrame) -> dict:
    candidates = find_covered_call_candidates(holdings_df)
    total_potential = 0.0
    for _, row in candidates.iterrows():
        total_potential += (row['Market Value'] * 0.01) # Simple 1% estimate
    return {"candidate_count": len(candidates), "est_monthly_premium": total_potential}
