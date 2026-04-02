import pandas as pd
import logging
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE
from utils.fmp_client import screen_by_metrics

def parse_thesis_to_criteria(thesis: str) -> dict:
    """
    Call Gemini to translate plain English thesis into screening criteria.
    """
    prompt = f"Investment Thesis: {thesis}"
    
    system_instruction = f"""
    {SAFETY_PREAMBLE}
    You are a quantitative stock screener. Translate the investor's thesis into concrete screening criteria for a stock screening API.
    Respond ONLY with JSON: 
    {{
        "sector": str or null, 
        "marketCapMoreThan": float or null (in dollars), 
        "peRatioLowerThan": float or null, 
        "dividendYieldMoreThan": float or null (as decimal, e.g. 0.03 for 3%), 
        "isEtf": bool or null,
        "keywords": [str],
        "description": str
    }}
    """
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"Thesis parsing error: {e}")
        return {"error": str(e)}

def screen_stocks(criteria: dict, holdings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Call FMP screen_by_metrics.
    """
    if "error" in criteria:
        return pd.DataFrame()
        
    results = screen_by_metrics(criteria)
    
    if results.empty:
        # Retry once with broader criteria (e.g. remove PE constraint)
        broad_criteria = criteria.copy()
        broad_criteria['peRatioLowerThan'] = None
        results = screen_by_metrics(broad_criteria)
        
    if not results.empty:
        # Add portfolio context
        held_tickers = holdings_df['Ticker'].tolist()
        results['in_portfolio'] = results['ticker'].isin(held_tickers)
        
    return results.head(20)

def rank_and_explain(thesis: str, screened_df: pd.DataFrame, holdings_df: pd.DataFrame) -> dict:
    """
    Gemini JSON: thesis_summary, ranked_picks, portfolio_overlap_note.
    """
    if screened_df.empty:
        return {"error": "No stocks found for this thesis."}
        
    prompt = f"""
    Thesis: {thesis}
    
    Screened Stocks:
    {screened_df[['ticker', 'company_name', 'sector', 'market_cap']].to_dict('records')}
    
    Rank the top 5 candidates and explain why they fit the thesis.
    Note if any are already held in the portfolio.
    """
    
    system_instruction = f"""
    {SAFETY_PREAMBLE}
    You are an investment research analyst. Rank the best matches for the given thesis from the screened list.
    Respond ONLY with JSON:
    {{
        "thesis_summary": str,
        "ranked_picks": [
            {{ "rank": int, "ticker": str, "company": str, "rationale": str, "already_held": bool, "suggested_weight": str }}
        ],
        "portfolio_overlap_note": str
    }}
    """
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"Ranking error: {e}")
        return {"error": str(e)}
