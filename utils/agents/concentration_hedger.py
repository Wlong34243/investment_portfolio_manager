import pandas as pd
import logging
import config
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE
from utils.technicals import calculate_technical_indicators

def scan_concentration_risks(holdings_df: pd.DataFrame) -> list[dict]:
    """
    Positions > SINGLE_POSITION_WARN_PCT, sectors > SECTOR_CONCENTRATION_WARN_PCT.
    Fetch 50-day MA, flag if price < 50MA.
    """
    risks = []
    
    # 1. Single Position Risk
    concentrated_pos = holdings_df[holdings_df['Weight'] > config.SINGLE_POSITION_WARN_PCT]
    for _, row in concentrated_pos.iterrows():
        ticker = row['Ticker']
        techs = calculate_technical_indicators(ticker)
        price_vs_ma = techs.get('signals', {}).get('price_vs_sma50', 'Unknown')
        
        risks.append({
            "ticker": ticker,
            "weight": row['Weight'],
            "risk_type": "Single Position Concentration",
            "price_vs_ma": price_vs_ma,
            "severity": "High" if row['Weight'] > 15.0 else "Medium"
        })
        
    # 2. Sector Risk
    # Assuming 'Asset Class' is used for broad sector/class in this app context
    sector_weights = holdings_df.groupby('Asset Class')['Weight'].sum()
    heavy_sectors = sector_weights[sector_weights > config.SECTOR_CONCENTRATION_WARN_PCT]
    
    for sector, weight in heavy_sectors.items():
        risks.append({
            "ticker": sector, # Using ticker field for sector name here
            "weight": weight,
            "risk_type": "Sector Concentration",
            "price_vs_ma": "N/A",
            "severity": "High" if weight > 40.0 else "Medium"
        })
        
    return risks

def generate_hedge_suggestions(risks: list[dict], holdings_df: pd.DataFrame) -> list[dict]:
    """
    Gemini call per flagged risk.
    """
    all_suggestions = []
    
    for risk in risks:
        if risk['risk_type'] == "Sector Concentration":
            continue # Focus LLM on specific ticker risks for now
            
        ticker = risk['ticker']
        prompt = f"""
        Risk detected: {ticker} is {risk['weight']:.2f}% of the portfolio.
        Current price trend: {risk['price_vs_ma']} 50-day Moving Average.
        
        Suggest 2-3 hedging strategies for this concentrated position. 
        Consider: trimming, sector rotation, protective options (educational only), diversification.
        """
        
        system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a portfolio risk advisor. Suggest hedging strategies for concentrated positions. Respond ONLY with JSON: {{'ticker': str, 'suggestions': [{{'strategy': str, 'description': str, 'impact_estimate': str}}]}}"
        
        try:
            res = ask_gemini_json(prompt, system_instruction=system_instruction)
            if res and "suggestions" in res:
                all_suggestions.append(res)
        except Exception as e:
            logging.error(f"Hedge suggestion error for {ticker}: {e}")
            
    return all_suggestions

def check_on_page_load(holdings_df: pd.DataFrame) -> list[str]:
    """Quick scan, no LLM. Return alert strings."""
    alerts = []
    
    conc = holdings_df[holdings_df['Weight'] > config.SINGLE_POSITION_WARN_PCT]
    for _, row in conc.iterrows():
        alerts.append(f"⚠️ **Concentration Alert:** {row['Ticker']} is {row['Weight']:.1f}% of your portfolio.")
        
    sector_weights = holdings_df.groupby('Asset Class')['Weight'].sum()
    heavy = sector_weights[sector_weights > config.SECTOR_CONCENTRATION_WARN_PCT]
    for sector, weight in heavy.items():
        alerts.append(f"⚠️ **Sector Alert:** {sector} is {weight:.1f}% of your portfolio.")
        
    return alerts
