import pandas as pd
import logging
import streamlit as st
import config
from pydantic import BaseModel
from typing import List
from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE
from utils.fmp_client import get_historical_pe, get_key_metrics, get_company_profile
from utils.finnhub_client import get_basic_financials
import yfinance as yf

class ValuationReport(BaseModel):
    narrative: str
    verdict: str
    signals: str
    metrics_summary: str

class AccumulationPlan(BaseModel):
    analysis: str
    shares_to_buy: str
    new_weight_pct: float
    entry_rationale: str
    risk_factors: List[str]
    trigger_condition: str

def get_valuation_snapshot(ticker: str) -> dict:
    """
    Returns current_pe, avg_5yr_pe, pe_discount_pct, is_below_average,
    plus rich metadata for narrative generation.
    """
    try:
        metrics = get_key_metrics(ticker)
        hist_pe = get_historical_pe(ticker, years=5)
        profile = get_company_profile(ticker)
        basic = get_basic_financials(ticker) 
        
        # Detect FMP availability: both metrics and hist_pe must return real data
        fmp_available = bool(metrics) and not hist_pe.empty

        current_pe = metrics.get('pe_ratio')

        # Always attempt yfinance fallback for profile enrichment
        y_info = {}
        try:
            y_ticker = yf.Ticker(ticker)
            y_info = y_ticker.info
        except Exception as ye:
            logging.warning(f"yfinance fallback failed for {ticker}: {ye}")

        if current_pe is None or current_pe == 0:
            current_pe = y_info.get('trailingPE') or y_info.get('forwardPE')

        if not profile.get('market_cap'):
            profile['market_cap'] = y_info.get('marketCap', 0)
        if not profile.get('sector'):
            profile['sector'] = y_info.get('sector', 'Unknown')

        if current_pe is None:
            return {"error": f"No valuation data available for {ticker}"}

        # Historical P/E comparison — only valid when FMP provides multiple years of data
        if not hist_pe.empty:
            avg_pe = hist_pe['pe_ratio'].mean()
            pe_discount = ((avg_pe - current_pe) / avg_pe) * 100 if avg_pe else 0
            is_below_avg = current_pe < avg_pe
        else:
            # FMP historical unavailable — cannot make a valid historical comparison
            avg_pe = None
            pe_discount = None
            is_below_avg = None
        
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
            "avg_5yr_pe": float(avg_pe) if avg_pe is not None else None,
            "pe_discount_pct": float(pe_discount) if pe_discount is not None else None,
            "is_below_average": is_below_avg,
            "fmp_unavailable": not fmp_available,
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
    hist_pe_line = (
        f"- 5-Year Avg P/E: {val_snap['avg_5yr_pe']:.2f} (Discount vs avg: {val_snap['pe_discount_pct']:.1f}%)"
        if val_snap.get('avg_5yr_pe') is not None
        else "- Historical P/E: Unavailable (FMP subscription required). Evaluate on absolute basis vs sector norms."
    )

    prompt = f"""
    Analyze the valuation of {ticker} ({val_snap['sector']}).

    Metrics:
    - Current P/E: {val_snap['current_pe']:.2f}
    {hist_pe_line}
    - Market Cap: ${val_snap['market_cap']/1e9:.2f}B
    - Dividend Yield: {val_snap['dividend_yield']:.2f}%
    - Forward P/E: {val_snap.get('forward_pe', 0):.2f}
    - 52W Range: {val_snap.get('low_52w', 0):.2f} — {val_snap.get('high_52w', 0):.2f}

    {"NOTE: Historical P/E data is unavailable. Do NOT mention comparing to a 5-year average. Instead, compare the current multiple to typical sector P/E ranges and forward growth expectations." if val_snap.get('fmp_unavailable') else ""}

    Provide a report with these exact sections (formatted in Markdown):

    ### {ticker} Valuation Verdict
    [A lead paragraph summarizing if it's "Rich", "Fair", or "Undervalued". Base it on current P/E vs sector norms and growth rate.]

    #### What the market is pricing in
    [Discuss the current multiple vs growth expectations and any recent re-rating catalysts.]

    #### Valuation signals
    [Compare vs sector peers. Mention forward P/E, PEG ratio context, and intrinsic value estimates.]

    #### Key metrics
    - Trailing P/E: {val_snap['current_pe']:.2f}
    - Market Cap: ${val_snap['market_cap']/1e9:.2f}B
    - 52W Range: {val_snap.get('low_52w', 0):.2f} to {val_snap.get('high_52w', 0):.2f}
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a senior equity valuation analyst. Provide a professional, high-signal valuation report mirroring the style of Perplexity Finance."
    
    try:
        res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=ValuationReport)
        if res:
            return res.model_dump()
        return {"error": "AI failed to generate valuation report"}
    except Exception as e:
        return {"error": str(e)}

def scan_valuation_opportunities(holdings_df: pd.DataFrame, watchlist: list = None) -> list[dict]:
    """
    Scan top holdings or watchlist for PE discounts.
    """
    results = []
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
    avg_pe_text = (
        f"5yr Avg: {valuation_data['avg_5yr_pe']:.2f}, Discount: {valuation_data['pe_discount_pct']:.1f}% below average"
        if valuation_data.get('avg_5yr_pe') is not None
        else "historical avg P/E unavailable"
    )

    prompt = f"""
    Ticker: {ticker}
    Current P/E: {valuation_data['current_pe']:.2f} ({avg_pe_text}).
    
    Investor wants to deploy ${deploy_amount:,.2f} into this position.
    
    Current Weight: {holdings_df[holdings_df['Ticker'] == ticker]['Weight'].iloc[0] if ticker in holdings_df['Ticker'].values else 0.0:.2f}%
    
    Suggest an accumulation plan. Is now a good entry point? 
    Consider risk factors and provide a trigger condition.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a valuation and accumulation strategist. Help the investor build positions at attractive prices."
    
    try:
        res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=AccumulationPlan)
        if res:
            return res.model_dump()
        return {"error": "AI failed to generate accumulation plan"}
    except Exception as e:
        logging.error(f"Accumulation plan error for {ticker}: {e}")
        return {"error": str(e)}
