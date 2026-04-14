import json
import os
import requests
import logging
import pandas as pd
from pathlib import Path
from typing import List
from datetime import datetime, timedelta

try:
    import streamlit as st
    CACHE = st.cache_data
except ImportError:
    # Dummy decorator for CLI testing
    def CACHE(**kwargs):
        def decorator(func):
            return func
        return decorator

try:
    import config
except ImportError:
    config = None

BASE_URL = "https://financialmodelingprep.com/stable"

# ---------------------------------------------------------------------------
# Local file cache (7-day TTL) — prevents FMP free-tier exhaustion on repeated runs
# ---------------------------------------------------------------------------
FMP_CACHE_DIR = Path("data/fmp_cache")
FMP_CACHE_TTL_DAYS = 7


def get_fmp_api_key() -> str:
    return getattr(config, 'FMP_API_KEY', os.environ.get('FMP_API_KEY', ''))


def _get_fmp_cached(ticker: str) -> dict | None:
    """
    Returns cached FMP key metrics for ticker if < 7 days old, else calls FMP.
    Returns None if FMP call fails (rate limit, network error, etc.).

    Cache location: data/fmp_cache/{TICKER}.json
    Caches the transformed metrics dict (output of get_key_metrics), not raw API JSON.
    """
    FMP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = FMP_CACHE_DIR / f"{ticker.upper()}.json"

    # Check cache freshness
    if cache_path.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        if age < timedelta(days=FMP_CACHE_TTL_DAYS):
            try:
                cached = json.loads(cache_path.read_text())
                return cached if cached else None
            except Exception:
                pass  # corrupted cache file — fall through to API call

    # Cache miss or stale — call FMP
    try:
        data = get_key_metrics(ticker)
        if data:
            cache_path.write_text(json.dumps(data))
        return data if data else None
    except Exception as e:
        logging.warning("FMP API call failed for %s: %s", ticker, e)
        return None

@CACHE(ttl=86400)
def get_earnings_calendar(tickers: List[str], days_ahead: int = 14) -> pd.DataFrame:
    api_key = get_fmp_api_key()
    if not api_key:
        return pd.DataFrame()
        
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    # Corrected path: earnings-calendar (hyphenated and plural)
    url = f"{BASE_URL}/earnings-calendar?from={start_date}&to={end_date}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning(f"FMP API: Payment Required (402). Subscription limit reached.")
            return {} if 'metrics' in url or 'profile' in url else pd.DataFrame() if 'calendar' in url or 'ratios' in url or 'screener' in url else ""
        response.raise_for_status()
        data = response.json()
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        df = df[df['symbol'].isin(tickers)]
        
        if df.empty:
            return pd.DataFrame()
            
        return df[['symbol', 'date', 'epsEstimated', 'revenueEstimated']].rename(
            columns={'symbol': 'ticker', 'epsEstimated': 'eps_estimated', 'revenueEstimated': 'revenue_estimated'}
        )
    except Exception as e:
        logging.warning(f"FMP earnings calendar error: {e}")
        return pd.DataFrame()

@CACHE(ttl=86400)
def get_earnings_transcript(ticker: str, year: int = None, quarter: int = None) -> str:
    api_key = get_fmp_api_key()
    if not api_key:
        return ""
        
    # Corrected path: earning-call-transcript (hyphenated)
    url = f"{BASE_URL}/earning-call-transcript?symbol={ticker}&"
    if year and quarter:
        url += f"year={year}&quarter={quarter}&"
    url += f"apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning(f"FMP API: Payment Required (402). Subscription limit reached.")
            return {} if 'metrics' in url or 'profile' in url else pd.DataFrame() if 'calendar' in url or 'ratios' in url or 'screener' in url else ""
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            transcript = data[0].get('content', '')
            return transcript[:4000]  # Truncate to save context window
        return ""
    except Exception as e:
        logging.warning(f"FMP transcript error for {ticker}: {e}")
        return ""

@CACHE(ttl=86400)
def get_key_metrics(ticker: str) -> dict:
    api_key = get_fmp_api_key()
    if not api_key:
        return {}
        
    url = f"{BASE_URL}/key-metrics-ttm?symbol={ticker}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning(f"FMP API: Payment Required (402). Subscription limit reached.")
            return {} if 'metrics' in url or 'profile' in url else pd.DataFrame() if 'calendar' in url or 'ratios' in url or 'screener' in url else ""
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            m = data[0]
            # Try peRatioTTM, then calculate from earningsYieldTTM
            pe = m.get('peRatioTTM')
            if not pe and m.get('earningsYieldTTM'):
                ey = float(m.get('earningsYieldTTM'))
                pe = 1.0 / ey if ey != 0 else None

            return {
                'pe_ratio': pe,
                'pb_ratio': m.get('pbRatioTTM'),
                'dividend_yield': m.get('dividendYieldPercentageTTM'),
                'roe': m.get('returnOnEquityTTM'),
                'debt_to_equity': m.get('debtToEquityTTM'),
                'revenue_per_share': m.get('revenuePerShareTTM'),
                'free_cash_flow_per_share': m.get('freeCashFlowPerShareTTM')
            }
        return {}
    except Exception as e:
        logging.warning(f"FMP key metrics error for {ticker}: {e}")
        return {}

@CACHE(ttl=86400)
def get_historical_pe(ticker: str, years: int = 5) -> pd.DataFrame:
    api_key = get_fmp_api_key()
    if not api_key:
        return pd.DataFrame()
        
    url = f"{BASE_URL}/ratios?symbol={ticker}&period=annual&limit={years}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning(f"FMP API: Payment Required (402). Subscription limit reached.")
            return {} if 'metrics' in url or 'profile' in url else pd.DataFrame() if 'calendar' in url or 'ratios' in url or 'screener' in url else ""
        response.raise_for_status()
        data = response.json()
        if data:
            df = pd.DataFrame(data)
            if 'priceEarningsRatio' in df.columns:
                return df[['date', 'priceEarningsRatio']].rename(columns={'priceEarningsRatio': 'pe_ratio'})
        return pd.DataFrame()
    except Exception as e:
        logging.warning(f"FMP historical PE error for {ticker}: {e}")
        return pd.DataFrame()

@CACHE(ttl=86400)
def get_company_profile(ticker: str) -> dict:
    api_key = get_fmp_api_key()
    if not api_key:
        return {}
        
    url = f"{BASE_URL}/profile?symbol={ticker}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning(f"FMP API: Payment Required (402). Subscription limit reached.")
            return {} if 'metrics' in url or 'profile' in url else pd.DataFrame() if 'calendar' in url or 'ratios' in url or 'screener' in url else ""
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            p = data[0]
            return {
                'sector': p.get('sector'),
                'industry': p.get('industry'),
                'description': p.get('description'),
                'market_cap': float(p.get('mktCap') or 0.0),
                'beta': float(p.get('beta') or 0.0)
            }
        return {}
    except Exception as e:
        logging.warning(f"FMP profile error for {ticker}: {e}")
        return {}

@CACHE(ttl=86400)
def screen_by_metrics(criteria: dict) -> pd.DataFrame:
    """
    Screen stocks by metric thresholds.
    Accept criteria like: marketCapMoreThan, peRatioLowerThan, dividendYieldMoreThan, sector
    """
    api_key = get_fmp_api_key()
    if not api_key:
        return pd.DataFrame()
        
    url = f"{BASE_URL}/stock-screener?apikey={api_key}"
    for key, val in criteria.items():
        if val is not None:
            url += f"&{key}={val}"
            
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning(f"FMP API: Payment Required (402). Subscription limit reached.")
            return {} if 'metrics' in url or 'profile' in url else pd.DataFrame() if 'calendar' in url or 'ratios' in url or 'screener' in url else ""
        response.raise_for_status()
        data = response.json()
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        # Standardize columns
        cols = ['symbol', 'companyName', 'marketCap', 'pe', 'dividendYield', 'sector']
        # Use only existing columns
        existing_cols = [c for t in cols for c in df.columns if t == c]
        
        return df[existing_cols].rename(columns={
            'symbol': 'ticker',
            'companyName': 'company_name',
            'marketCap': 'market_cap',
            'dividendYield': 'dividend_yield'
        })
    except Exception as e:
        logging.warning(f"FMP screener error: {e}")
        return pd.DataFrame()

@CACHE(ttl=86400)
def get_financial_statements(ticker: str) -> dict:
    """
    Fetches the most recent annual income statement and cash flow statement
    to extract R&D, CapEx, and calculate ROIC.
    """
    api_key = get_fmp_api_key()
    if not api_key:
        return {}

    results = {}
    try:
        # Income Statement for R&D
        is_url = f"{BASE_URL}/income-statement/{ticker}?limit=1&apikey={api_key}"
        is_res = requests.get(is_url, timeout=10)
        if is_res.status_code == 200:
            is_data = is_res.json()
            if is_data:
                results['research_and_development_expenses'] = is_data[0].get('researchAndDevelopmentExpenses', 0)
                results['operating_income'] = is_data[0].get('operatingIncome', 0)
                results['net_income'] = is_data[0].get('netIncome', 0)

        # Cash Flow for CapEx
        cf_url = f"{BASE_URL}/cash-flow-statement/{ticker}?limit=1&apikey={api_key}"
        cf_res = requests.get(cf_url, timeout=10)
        if cf_res.status_code == 200:
            cf_data = cf_res.json()
            if cf_data:
                results['capital_expenditure'] = cf_data[0].get('capitalExpenditure', 0)

        # Key Metrics for ROIC
        km_url = f"{BASE_URL}/key-metrics/{ticker}?limit=1&apikey={api_key}"
        km_res = requests.get(km_url, timeout=10)
        if km_res.status_code == 200:
            km_data = km_res.json()
            if km_data:
                results['roic'] = km_data[0].get('roic', 0)

    except Exception as e:
        logging.warning(f"FMP financial statements error for {ticker}: {e}")

    return results

def get_fundamentals(ticker: str, bundle_quote: dict = None) -> dict:
    """
    Returns fundamentals using field names expected by the framework rule engine.

    Tier 1: bundle_quote (Schwab /marketdata/v1/quotes data from the market bundle).
            Provides trailing_pe, eps_ttm, market_cap, div_yield at zero API cost.
            Only populated when data_source='schwab_api'; None for CSV-sourced bundles
            (the current default). Acts as a scaffold for future Schwab API source.
    Tier 2: FMP key-metrics TTM via 7-day file cache (data/fmp_cache/{TICKER}.json).
            Falls back gracefully on 402 / network errors — returns None, not raised.

    Returns an empty dict if both tiers return nothing, so callers treat all fields
    as insufficient_data rather than crashing.
    """
    # Tier 1: Schwab bundle fields (zero API cost)
    tier1: dict = {}
    if bundle_quote:
        if bundle_quote.get("peRatio") is not None:
            tier1["trailing_pe"] = float(bundle_quote["peRatio"])
        if bundle_quote.get("eps") is not None:
            tier1["eps_ttm"] = float(bundle_quote["eps"])
        if bundle_quote.get("marketCap") is not None:
            tier1["market_cap"] = float(bundle_quote["marketCap"])
        if bundle_quote.get("dividendYield") is not None:
            tier1["div_yield"] = float(bundle_quote["dividendYield"])

    # Tier 2: FMP (7-day file cache; 402 returns None gracefully)
    metrics = _get_fmp_cached(ticker) or {}
    if not metrics and not tier1:
        return {}

    result = {
        "peg_ratio": metrics.get("peg_ratio"),              # pegRatioTTM from FMP
        "trailing_pe": tier1.get("trailing_pe") or metrics.get("pe_ratio"),  # tier1 wins
        "debt_to_equity": metrics.get("debt_to_equity"),
        "earnings_growth_rate_3yr": None,                   # requires separate growth endpoint
    }
    # Pass through extra tier-1 fields not in the standard contract
    for k in ("eps_ttm", "market_cap", "div_yield"):
        if k in tier1:
            result[k] = tier1[k]
    return result


if __name__ == "__main__":
    print("Testing FMP Client...")
    print(get_key_metrics("AMZN"))