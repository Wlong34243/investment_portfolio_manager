import pandas as pd
import logging
import yfinance as yf
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE

OPTIONS_DISCLAIMER = "⚠️ **DISCLAIMER:** Educational analysis only. Covered call strategies involve risks (capping upside, potential assignment). Execute independently after your own research."

def find_covered_call_candidates(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """
    qty >= 100: GOOG 100.27, XOM 101.73.
    """
    # 1. Filter for quantity >= 100
    candidates = holdings_df[holdings_df['Quantity'] >= 100].copy()
    
    # 2. Exclude Cash
    candidates = candidates[candidates['Is Cash'] == False]
    
    return candidates

def get_options_chain(ticker: str) -> pd.DataFrame:
    """
    yfinance options, filter 5-15% OTM, within DTE range (30-60 days).
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return pd.DataFrame()
            
        # Target ~45 DTE
        # Simple: take the expiration closest to 45 days out
        from datetime import datetime, timedelta
        target_date = datetime.now() + timedelta(days=45)
        
        # Sort expirations by proximity to 45 days
        best_exp = min(expirations, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - target_date).days))
        
        calls = stock.option_chain(best_exp).calls
        current_price = stock.fast_info['lastPrice']
        
        # Filter 5-15% OTM
        min_strike = current_price * 1.05
        max_strike = current_price * 1.15
        
        filtered_calls = calls[(calls['strike'] >= min_strike) & (calls['strike'] <= max_strike)]
        filtered_calls['expiration'] = best_exp
        filtered_calls['current_price'] = current_price
        
        return filtered_calls
    except Exception as e:
        logging.error(f"Error fetching options for {ticker}: {e}")
        return pd.DataFrame()

def generate_covered_call_proposal(ticker: str, chain_df: pd.DataFrame, holdings_df: pd.DataFrame) -> dict:
    """
    Gemini JSON: strategies: strike, expiry, premium, yield, max_upside, assignment_prob.
    """
    if chain_df.empty:
        return {"error": "No valid OTM calls found for {ticker}."}
        
    # Pick top 3 strikes to show Gemini
    top_3 = chain_df.head(3)
    
    prompt = f"""
    Ticker: {ticker} (Current Price: ${top_3['current_price'].iloc[0]:.2f})
    Option Expiration: {top_3['expiration'].iloc[0]}
    
    Available Strikes:
    {top_3[['strike', 'lastPrice', 'bid', 'ask', 'impliedVolatility']].to_dict('records')}
    
    Propose 1-2 covered call strategies. 
    Explain the trade-off between premium and assignment risk.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\n{OPTIONS_DISCLAIMER}\n\nYou are an options strategist. Suggest conservative income-generating strategies. Respond ONLY with JSON: {{'strategies': [{{'label': str, 'strike': float, 'expiry': str, 'premium': float, 'annualized_yield_pct': float, 'max_upside_cap_pct': float, 'assignment_probability': str, 'recommendation': str}}]}}"
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"Options proposal error for {ticker}: {e}")
        return {"error": str(e)}

def estimate_monthly_premium_potential(holdings_df: pd.DataFrame) -> dict:
    """
    Quick estimate of potential premium from all 100+ share positions.
    """
    candidates = find_covered_call_candidates(holdings_df)
    total_potential = 0.0
    
    for t in candidates['Ticker'].tolist():
        # Simple heuristic: assume 1% monthly premium on 10% OTM
        val = candidates[candidates['Ticker'] == t]['Market Value'].iloc[0]
        total_potential += (val * 0.01)
        
    return {
        "candidate_count": len(candidates),
        "est_monthly_premium": total_potential
    }
