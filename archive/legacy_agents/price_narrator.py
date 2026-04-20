import pandas as pd
import logging
import time
from pydantic import BaseModel
from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE
from utils.finnhub_client import get_company_news

class MovementExplanation(BaseModel):
    explanation: str
    catalyst_type: str
    confidence: str

def detect_significant_moves(holdings_df: pd.DataFrame, threshold_pct: float = 3.0) -> list[dict]:
    """
    Scan for positions where |Daily Change %| >= threshold.
    """
    if 'Daily Change %' not in holdings_df.columns:
        return []
        
    moves = holdings_df[holdings_df['Daily Change %'].abs() >= threshold_pct].copy()
    
    # Add dollar impact
    moves['day_pnl'] = moves['Market Value'] * (moves['Daily Change %'] / 100)
    
    # Sort by absolute dollar impact
    moves['abs_pnl'] = moves['day_pnl'].abs()
    moves = moves.sort_values(by='abs_pnl', ascending=False)
    
    return moves[['Ticker', 'Daily Change %', 'Market Value', 'day_pnl']].to_dict('records')

def generate_movement_explanation(ticker: str, change_pct: float) -> dict:
    """
    Fetch news and use Gemini to explain WHY.
    """
    news = get_company_news(ticker, days_back=2)
    if not news:
        return {"explanation": "No recent news detected to explain this movement.", "catalyst_type": "Unknown"}
        
    news_snippet = "\n".join([f"- {n['headline']}" for n in news[:5]])
    
    prompt = f"""
    Ticker: {ticker}
    Daily Change: {change_pct:+.2f}%
    
    Recent News:
    {news_snippet}
    
    Explain exactly WHY the stock moved today in 2 sentences maximum. 
    Identify the catalyst (Earnings, Macro, Upgrade/Downgrade, etc).
    """
    
    system_instruction = f"""
    {SAFETY_PREAMBLE}
    You are a sharp, concise financial analyst.
    """
    
    try:
        res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=MovementExplanation)
        if res:
            return res.model_dump()
        return {"error": "AI failed to generate explanation"}
    except Exception as e:
        logging.error(f"Narrator error for {ticker}: {e}")
        return {"error": str(e)}

def batch_analyze_daily_moves(holdings_df: pd.DataFrame) -> list[dict]:
    """
    Top 3 movers analysis.
    """
    moves = detect_significant_moves(holdings_df)
    results = []
    
    for m in moves[:3]:
        exp = generate_movement_explanation(m['Ticker'], m['Daily Change %'])
        if "error" not in exp:
            results.append({
                "ticker": m['Ticker'],
                "change_pct": m['Daily Change %'],
                "explanation": exp['explanation'],
                "catalyst": exp['catalyst_type']
            })
        time.sleep(1.0) # Rate limiting
        
    return results
