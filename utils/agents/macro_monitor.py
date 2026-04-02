import pandas as pd
import logging
import streamlit as st
import config
import yfinance as yf
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE

try:
    from fredapi import Fred
except ImportError:
    Fred = None

def get_fred_client():
    if not Fred:
        logging.warning("fredapi not installed.")
        return None
    api_key = getattr(config, 'FRED_API_KEY', '')
    if not api_key:
        return None
    return Fred(api_key=api_key)

@st.cache_data(ttl=86400)
def get_macro_snapshot() -> dict:
    """
    Fetch from FRED API (cache 24hr).
    CPI, Fed Funds, 10Y Treasury, Unemployment, VIX.
    """
    fred = get_fred_client()
    data = {
        "cpi": 0.0, "cpi_trend": "Unknown", 
        "fed_rate": 0.0, "treasury_10y": 0.0, 
        "unemployment": 0.0, "vix": 0.0, "vix_signal": "Neutral"
    }
    
    if fred:
        try:
            # CPI: series_id='CPIAUCSL'
            cpi_series = fred.get_series('CPIAUCSL')
            if not cpi_series.empty:
                data['cpi'] = cpi_series.iloc[-1]
                # Trend direction (last 3 months)
                data['cpi_trend'] = "Rising" if cpi_series.iloc[-1] > cpi_series.iloc[-4] else "Falling"
                
            data['fed_rate'] = fred.get_series('FEDFUNDS').iloc[-1]
            data['treasury_10y'] = fred.get_series('DGS10').iloc[-1]
            data['unemployment'] = fred.get_series('UNRATE').iloc[-1]
        except Exception as e:
            logging.error(f"FRED API error: {e}")
            
    # VIX from yfinance
    try:
        vix = yf.Ticker('^VIX').fast_info['lastPrice']
        data['vix'] = vix
        if vix > 30: data['vix_signal'] = "Extreme Fear"
        elif vix > 20: data['vix_signal'] = "Elevated"
        else: data['vix_signal'] = "Normal"
    except:
        pass
        
    return data

def detect_macro_triggers(macro_data: dict, holdings_df: pd.DataFrame) -> list[dict]:
    """
    Rule-based checks (no LLM).
    """
    triggers = []
    
    if macro_data['vix'] > 25:
        triggers.append({
            "trigger": "High Volatility",
            "description": f"VIX is at {macro_data['vix']:.1f}. Markets are nervous.",
            "severity": "Elevated",
            "relevant_sectors": ["Tech", "Consumer Discretionary"]
        })
        
    if macro_data['treasury_10y'] > 4.5:
        triggers.append({
            "trigger": "High Interest Rates",
            "description": f"10Y Treasury yield is {macro_data['treasury_10y']:.2f}%. Bonds are competitive with stocks.",
            "severity": "Moderate",
            "relevant_sectors": ["Real Estate", "Utilities", "Financials"]
        })
        
    return triggers

def generate_macro_strategy(triggers: list[dict], macro_data: dict, holdings_df: pd.DataFrame) -> dict:
    """
    Gemini JSON: macro_outlook, risk_level, sector_rotations, defensive_moves.
    """
    prompt = f"""
    Current Macro Data:
    {macro_data}
    
    Active Triggers:
    {triggers}
    
    Investor Portfolio Sector Exposure:
    {holdings_df.groupby('Asset Class')['Weight'].sum().to_dict()}
    
    Suggest a macro strategy for this portfolio (~$480K). 
    Should the investor rotate sectors? Identify specific holdings that might be affected.
    """
    
    system_instruction = f"""
    {SAFETY_PREAMBLE}
    You are a macro-economic investment strategist.
    Provide portfolio positioning adjustments based on current conditions.
    Respond ONLY with JSON:
    {{
        "macro_outlook": str,
        "risk_level": str,
        "sector_rotations": [{{ "from_sector": str, "to_sector": str, "rationale": str, "specific_holdings_affected": [str] }}],
        "defensive_moves": [str],
        "opportunity_plays": [str]
    }}
    """
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"Macro strategy error: {e}")
        return {"error": str(e)}
