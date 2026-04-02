import pandas as pd
import logging
import streamlit as st
from datetime import datetime
from utils.gemini_client import ask_gemini, ask_gemini_json, SAFETY_PREAMBLE
from utils.fmp_client import get_earnings_calendar

def scan_upcoming_earnings(holdings_df: pd.DataFrame, days_ahead: int = 14) -> pd.DataFrame:
    """
    Get earnings calendar for all tickers in holdings.
    """
    tickers = holdings_df['Ticker'].unique().tolist()
    # Filter out cash
    tickers = [t for t in tickers if t not in ['CASH_MANUAL', 'QACDS', 'Cash & Cash Investments']]
    
    calendar_df = get_earnings_calendar(tickers, days_ahead=days_ahead)
    return calendar_df

def generate_earnings_alerts(upcoming_df: pd.DataFrame, holdings_df: pd.DataFrame, max_alerts: int = 5) -> list[dict]:
    """
    Gemini per ticker: 2-sentence pre-earnings alert.
    """
    alerts = []
    
    # Sort upcoming by portfolio weight to prioritize
    weights = holdings_df.set_index('Ticker')['Weight'].to_dict()
    upcoming_df['Weight'] = upcoming_df['ticker'].map(weights).fillna(0)
    upcoming_df = upcoming_df.sort_values(by='Weight', ascending=False)
    
    for _, row in upcoming_df.head(max_alerts).iterrows():
        ticker = row['ticker']
        prompt = f"""
        {ticker} has earnings on {row['date']}. 
        Estimated EPS: {row['eps_estimated']}, Estimated Revenue: {row['revenue_estimated']}.
        This position is {row['Weight']:.2f}% of the portfolio.
        
        Provide a 2-sentence pre-earnings alert for the investor. 
        Focus on what's at stake or what the market is watching.
        """
        
        system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a financial news sentinel. Provide concise, high-signal earnings alerts."
        
        try:
            alert_text = ask_gemini(prompt, system_instruction=system_instruction)
            if alert_text:
                alerts.append({
                    "ticker": ticker,
                    "date": row['date'],
                    "alert": alert_text,
                    "badge": get_earnings_badge(row['date'])
                })
        except Exception as e:
            logging.error(f"Earnings alert error for {ticker}: {e}")
            
    return alerts

def get_earnings_badge(date_str: str) -> str:
    """Returns a status emoji based on proximity."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        days = (dt - datetime.now()).days
        if days <= 2: return "🔴"
        if days <= 7: return "🟡"
        return "🟢"
    except:
        return "⚪"

def generate_post_earnings_analysis(ticker: str, transcript: str, holdings_df: pd.DataFrame) -> dict:
    """
    Gemini JSON: bull/bear points, sentiment, metrics.
    """
    prompt = f"""
    Analyze the earnings transcript for {ticker}.
    
    TRANSCRIPT SNIPPET:
    {transcript[:15000]}
    
    Identify key bull/bear points and sentiment.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are an earnings analyst. Extract key insights from transcripts. Respond ONLY with JSON: {{'bull_points': [str], 'bear_points': [str], 'sentiment': str, 'key_metrics': dict, 'portfolio_implication': str}}"
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"Post-earnings analysis error for {ticker}: {e}")
        return {"error": str(e)}
