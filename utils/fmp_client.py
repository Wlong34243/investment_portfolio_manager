import os
import requests
import logging
import pandas as pd
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

def get_fmp_api_key() -> str:
    return getattr(config, 'FMP_API_KEY', os.environ.get('FMP_API_KEY', ''))

@CACHE(ttl=86400)
def get_earnings_calendar(tickers: List[str], days_ahead: int = 14) -> pd.DataFrame:
    api_key = get_fmp_api_key()
    if not api_key:
        return pd.DataFrame()
        
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    url = f"{BASE_URL}/earning_calendar?from={start_date}&to={end_date}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
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
        
    url = f"{BASE_URL}/earning_call_transcript?symbol={ticker}&"
    if year and quarter:
        url += f"year={year}&quarter={quarter}&"
    url += f"apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
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
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            m = data[0]
            return {
                'pe_ratio': m.get('peRatioTTM'),
                'pb_ratio': m.get('pbRatioTTM'),
                'dividend_yield': m.get('dividendYieldPercentageTTM'),
                'roe': m.get('roeTTM'),
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
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            p = data[0]
            return {
                'sector': p.get('sector'),
                'industry': p.get('industry'),
                'description': p.get('description'),
                'market_cap': p.get('mktCap'),
                'beta': p.get('beta')
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

if __name__ == "__main__":
    print("Testing FMP Client...")
    print(get_key_metrics("AMZN"))