import requests
import time
import os
import sys

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import config
except ImportError:
    pass

try:
    import streamlit as st
except ImportError:
    st = None

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"

def _get_fmp_data(endpoint: str, params: dict = None) -> list | dict:
    """Helper for FMP API calls with API key injection."""
    if not config.FMP_API_KEY:
        print("Warning: FMP_API_KEY not set in config.py")
        return []
        
    url = f"{FMP_BASE_URL}/{endpoint}"
    query_params = {"apikey": config.FMP_API_KEY}
    if params:
        query_params.update(params)
        
    try:
        response = requests.get(url, params=query_params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"FMP API Error ({endpoint}): {e}")
        return []

def get_earnings_transcripts(ticker: str) -> list[dict]:
    """
    Fetch last 2 earnings transcripts for ticker.
    Returns: [{"date": str, "content": str, "quarter": int, "year": int}]
    """
    # 1. Check cache
    if st and "fmp_cache" in st.session_state:
        cache_key = f"transcripts_{ticker}"
        if cache_key in st.session_state["fmp_cache"]:
            entry = st.session_state["fmp_cache"][cache_key]
            if time.time() - entry["ts"] < config.CACHE_TTL_SECONDS:
                return entry["data"]

    # 2. Call API
    # First get available transcript dates/quarters
    metadata = _get_fmp_data(f"earning_call_transcript/{ticker}")
    
    transcripts = []
    # FMP returns a list of [year, quarter, date, content]
    # We take top 2
    for item in metadata[:2]:
        transcripts.append({
            "date": item.get("date"),
            "content": item.get("content"),
            "quarter": item.get("quarter"),
            "year": item.get("year")
        })
        
    # 3. Update cache
    if st:
        if "fmp_cache" not in st.session_state: st.session_state["fmp_cache"] = {}
        st.session_state["fmp_cache"][f"transcripts_{ticker}"] = {"ts": time.time(), "data": transcripts}
        
    return transcripts

def get_company_news(ticker: str) -> list[dict]:
    """
    Fetch last 5 news items for ticker.
    Returns: [{"date": str, "title": str, "text": str, "url": str, "site": str}]
    """
    # 1. Check cache
    if st and "fmp_cache" in st.session_state:
        cache_key = f"news_{ticker}"
        if cache_key in st.session_state["fmp_cache"]:
            entry = st.session_state["fmp_cache"][cache_key]
            if time.time() - entry["ts"] < config.CACHE_TTL_SECONDS:
                return entry["data"]

    # 2. Call API
    news_raw = _get_fmp_data("stock_news", params={"tickers": ticker, "limit": 5})
    
    news = []
    for item in news_raw:
        news.append({
            "date": item.get("publishedDate"),
            "title": item.get("title"),
            "text": item.get("text"),
            "url": item.get("url"),
            "site": item.get("site")
        })
        
    # 3. Update cache
    if st:
        if "fmp_cache" not in st.session_state: st.session_state["fmp_cache"] = {}
        st.session_state["fmp_cache"][f"news_{ticker}"] = {"ts": time.time(), "data": news}
        
    return news

if __name__ == "__main__":
    # Simple test (requires API key)
    if config.FMP_API_KEY:
        ticker = "AAPL"
        print(f"Testing FMP news for {ticker}...")
        news = get_company_news(ticker)
        for n in news:
            print(f"- {n['title']} ({n['date']})")
            
        print(f"\nTesting FMP transcripts for {ticker}...")
        trans = get_earnings_transcripts(ticker)
        for t in trans:
            print(f"- Q{t['quarter']} {t['year']} ({t['date']}) | Length: {len(t['content'])}")
    else:
        print("FMP_API_KEY not set.")
