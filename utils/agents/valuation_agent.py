import pandas as pd
import logging
import streamlit as st
import config
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE
from utils.fmp_client import get_historical_pe, get_key_metrics, get_company_profile

def get_valuation_snapshot(ticker: str) -> dict:
    """
    Returns current_pe, avg_5yr_pe, pe_discount_pct, is_below_average,
    plus rich metadata for narrative generation.
    """
    try:
        metrics = get_key_metrics(ticker)
        hist_pe = get_historical_pe(ticker, years=5)
        profile = get_company_profile(ticker)
        
        current_pe = metrics.get('pe_ratio')
        if not current_pe:
            # Fallback to a basic check if PE is missing
            return {"error": "No current PE found"}
            
        avg_pe = hist_pe['pe_ratio'].mean() if not hist_pe.empty else current_pe
        pe_discount = ((avg_pe - current_pe) / avg_pe) * 100 if avg_pe else 0
        
        return {
            "ticker": ticker,
            "current_pe": current_pe,
            "avg_5yr_pe": avg_pe,
            "pe_discount_pct": pe_discount,
            "is_below_average": current_pe < avg_pe,
            "market_cap": profile.get('market_cap', 0),
            "eps": metrics.get('revenue_per_share', 0) * (metrics.get('roe', 0) / 100) if metrics.get('roe') else 0, # Rough calc if needed
            "dividend_yield": metrics.get('dividend_yield', 0),
            "sector": profile.get('sector', "Unknown")
        }
    except Exception as e:
        logging.error(f"Valuation snapshot error for {ticker}: {e}")
        return {"error": str(e)}

def generate_rich_valuation_report(ticker: str, val_snap: dict) -> dict:
    """
    Uses Gemini to generate the Perplexity-style rich narrative.
    """
    prompt = f"""
    Analyze the valuation of {ticker} ({val_snap['sector']}).
    
    Metrics:
    - Current P/E: {val_snap['current_pe']:.2f}
    - 5-Year Avg P/E: {val_snap['avg_5yr_pe']:.2f}
    - Market Cap: ${val_snap['market_cap']/1e9:.2f}B
    - Dividend Yield: {val_snap['dividend_yield']:.2f}%
    
    Provide a report with these exact sections:
    1. A lead paragraph summarizing if it's "Rich", "Fair", or "Undervalued".
    2. "What the market is pricing in": Discuss the current multiple vs growth expectations.
    3. "Valuation signals": Compare vs historical averages and peers.
    4. "Key metrics": Bulleted list of the stats.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a senior equity valuation analyst. Provide a professional, high-signal valuation report. Respond ONLY with JSON: {{'narrative': str, 'verdict': str, 'signals': str, 'metrics_summary': str}}"
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        return {"error": str(e)}

def scan_valuation_opportunities(holdings_df: pd.DataFrame, watchlist: list = None) -> list[dict]:
    """
    Scan top holdings or watchlist for PE discounts.
    """
    results = []
    # Take top 10 positions for scanning to be efficient
    tickers = holdings_df.nlargest(10, 'Weight')['Ticker'].tolist()
    if watchlist:
        tickers.extend([t for t in watchlist if t not in tickers])
        
    for t in tickers:
        if t in ['CASH_MANUAL', 'QACDS', 'Cash & Cash Investments']: continue
        snap = get_valuation_snapshot(t)
        if "error" not in snap and snap.get('is_below_average'):
            results.append(snap)
            
    return sorted(results, key=lambda x: x['pe_discount_pct'], reverse=True)

def generate_accumulation_plan(ticker: str, deploy_amount: float, valuation_data: dict, holdings_df: pd.DataFrame) -> dict:
    """
    Gemini JSON: analysis, shares_to_buy, new_weight_pct, entry_rationale.
    """
    prompt = f"""
    Ticker: {ticker}
    Current P/E: {valuation_data['current_pe']:.2f} (5yr Avg: {valuation_data['avg_5yr_pe']:.2f})
    Discount: {valuation_data['pe_discount_pct']:.1f}% below average.
    
    Investor wants to deploy ${deploy_amount:,.2f} into this position.
    
    Current Weight: {holdings_df[holdings_df['Ticker'] == ticker]['Weight'].iloc[0] if ticker in holdings_df['Ticker'].values else 0.0:.2f}%
    
    Suggest an accumulation plan. Is now a good entry point? 
    Consider risk factors and provide a trigger condition.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a valuation and accumulation strategist. Help the investor build positions at attractive prices. Respond ONLY with JSON: {{'analysis': str, 'shares_to_buy': str, 'new_weight_pct': float, 'entry_rationale': str, 'risk_factors': [str], 'trigger_condition': str}}"
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"Accumulation plan error for {ticker}: {e}")
        return {"error": str(e)}
