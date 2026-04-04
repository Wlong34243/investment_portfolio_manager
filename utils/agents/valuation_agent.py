import pandas as pd
import logging
import streamlit as st
import config
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE
from utils.fmp_client import get_historical_pe, get_key_metrics, get_company_profile
from utils.finnhub_client import get_basic_financials
import yfinance as yf

def get_valuation_snapshot(ticker: str) -> dict:
    """
    Returns current_pe, avg_5yr_pe, pe_discount_pct, is_below_average,
    plus rich metadata for narrative generation.
    Tries FMP first, falls back to yfinance for current metrics if FMP 402s.
    """
    try:
        # 1. Try FMP for historical and current
        metrics = get_key_metrics(ticker)
        hist_pe = get_historical_pe(ticker, years=5)
        profile = get_company_profile(ticker)
        basic = get_basic_financials(ticker) 
        
        current_pe = metrics.get('pe_ratio')
        
        # 2. FALLBACK: If FMP PE is missing (likely 402/limit), try yfinance
        if current_pe is None or current_pe == 0:
            try:
                y_ticker = yf.Ticker(ticker)
                y_info = y_ticker.info
                current_pe = y_info.get('trailingPE') or y_info.get('forwardPE')
                
                # If we still have no profile/market cap, fill from yfinance
                if not profile.get('market_cap'):
                    profile['market_cap'] = y_info.get('marketCap', 0)
                if not profile.get('sector'):
                    profile['sector'] = y_info.get('sector', 'Unknown')
            except Exception as ye:
                logging.warning(f"yfinance fallback failed for {ticker}: {ye}")

        if current_pe is None:
            return {"error": f"No valuation data available for {ticker} (FMP restricted & yfinance empty)"}
            
        avg_pe = hist_pe['pe_ratio'].mean() if not hist_pe.empty else current_pe
        pe_discount = ((avg_pe - current_pe) / avg_pe) * 100 if avg_pe else 0
        
        # Robust metrics extraction helper
        def _to_float(v, default=0.0):
            try:
                return float(v) if v is not None else default
            except:
                return default

        rev_per_share = _to_float(metrics.get('revenue_per_share'))
        roe = _to_float(metrics.get('roe'))
        eps_calc = rev_per_share * (roe / 100) if roe else 0.0

        return {
            "ticker": ticker,
            "current_pe": float(current_pe),
            "avg_5yr_pe": float(avg_pe),
            "pe_discount_pct": float(pe_discount),
            "is_below_average": current_pe < avg_pe,
            "market_cap": _to_float(profile.get('market_cap')),
            "dividend_yield": _to_float(metrics.get('dividend_yield')),
            "eps": eps_calc,
            "sector": profile.get('sector', "Unknown"),
            "high_52w": _to_float(basic.get('52WeekHigh')),
            "low_52w": _to_float(basic.get('52WeekLow')),
            "forward_pe": _to_float(basic.get('forwardPE'))
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
    
    Provide a report with these exact sections (formatted in Markdown):
    
    ### [Ticker] Valuation Verdict
    [A lead paragraph summarizing if it's "Rich", "Fair", or "Undervalued". Mention the current price vs target context.]
    
    #### What the market is pricing in
    [Discuss the current multiple vs growth expectations and historical rerating.]
    
    #### Valuation signals
    [Compare vs historical averages and peers. Mention intrinsic value estimates if applicable.]
    
    #### Key metrics
    - Price: $[Price]
    - Trailing P/E: [PE]
    - Market Cap: $[MCap]
    - 52W Range: [Low] to [High]
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a senior equity valuation analyst. Provide a professional, high-signal valuation report mirroring the style of Perplexity Finance. Respond ONLY with JSON: {{'narrative': str, 'verdict': str, 'signals': str, 'metrics_summary': str}}"
    
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
