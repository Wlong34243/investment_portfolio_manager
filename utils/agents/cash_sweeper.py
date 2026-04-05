import pandas as pd
import logging
import streamlit as st
import config
from pydantic import BaseModel
from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE

class CashSweepSuggestion(BaseModel):
    recommendation: str
    proposed_action: str
    yield_improvement: str
    risk_note: str

def analyze_cash_position(holdings_df: pd.DataFrame) -> dict:
    """
    cash_value, cash_yield, alternatives with yield comparison.
    """
    cash_rows = holdings_df[holdings_df['Is Cash'] == True]
    cash_value = cash_rows['Market Value'].sum()
    
    # Assume default yield from config or from the data if available
    current_yield = config.DEFAULT_CASH_YIELD_PCT
    
    # Alternatives (Hardcoded for analysis context)
    alternatives = [
        {"name": "SGOV (0-3mo Treasury ETF)", "yield": 5.25, "risk": "Very Low"},
        {"name": "JPIE (JPMorgan Income ETF)", "yield": 6.50, "risk": "Moderate"},
        {"name": "Money Market Fund", "yield": 5.05, "risk": "Low"}
    ]
    
    return {
        "cash_value": float(cash_value),
        "current_yield": current_yield,
        "alternatives": alternatives
    }

def generate_cash_deployment_suggestion(cash_analysis: dict, holdings_df: pd.DataFrame) -> dict:
    """
    Gemini: Compare money market vs income ETF yields.
    """
    prompt = f"""
    The investor has ${cash_analysis['cash_value']:,.2f} in cash earning {cash_analysis['current_yield']:.2f}%.
    
    Yield Alternatives:
    {cash_analysis['alternatives']}
    
    Suggest a deployment plan for the idle cash. Consider the portfolio's overall context.
    The goal is to improve yield while maintaining appropriate liquidity.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a yield optimization advisor. Suggest reallocation of idle cash to higher-yielding alternatives."
    
    try:
        res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=CashSweepSuggestion)
        if res:
            return res.model_dump()
        return {"error": "AI failed to generate suggestion"}
    except Exception as e:
        logging.error(f"Cash sweep suggestion error: {e}")
        return {"error": str(e)}

def get_cash_sweep_alert(holdings_df: pd.DataFrame) -> str:
    """Quick check: if cash > 5% AND any position yields 2x cash."""
    total_val = holdings_df['Market Value'].sum()
    cash_val = holdings_df[holdings_df['Is Cash'] == True]['Market Value'].sum()
    
    if total_val > 0 and (cash_val / total_val * 100) > 5.0:
        return f"💰 **Yield Alert:** You have ${cash_val:,.0f} ({cash_val/total_val*100:.1f}%) in cash. AI can suggest yield improvements."
        
    return None
