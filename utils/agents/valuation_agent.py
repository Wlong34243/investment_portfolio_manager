import pandas as pd
import logging
import streamlit as st
import config
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE
from utils.fmp_client import get_historical_pe, get_key_metrics

def get_valuation_snapshot(ticker: str) -> dict:
    """
    current_pe, avg_5yr_pe, pe_discount_pct, is_below_average.
    """
    try:
        metrics = get_key_metrics(ticker)
        hist_pe = get_historical_pe(ticker, years=5)
        
        current_pe = metrics.get('pe_ratio')
        if not current_pe:
            return {"error": "No current PE found"}
            
        if not hist_pe.empty:
            avg_pe = hist_pe['pe_ratio'].mean()
        else:
            avg_pe = None
            
        pe_discount = 0.0
        is_below = False
        if avg_pe and current_pe:
            pe_discount = ((avg_pe - current_pe) / avg_pe) * 100
            is_below = current_pe < avg_pe
            
        return {
            "ticker": ticker,
            "current_pe": current_pe,
            "avg_5yr_pe": avg_pe,
            "pe_discount_pct": pe_discount,
            "is_below_average": is_below
        }
    except Exception as e:
        logging.error(f"Valuation snapshot error for {ticker}: {e}")
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
