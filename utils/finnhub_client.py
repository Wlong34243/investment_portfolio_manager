import os
import logging
from typing import List, Dict
from datetime import datetime, timedelta

try:
    import finnhub
except ImportError:
    finnhub = None

try:
    import streamlit as st
    CACHE = st.cache_data
except ImportError:
    def CACHE(**kwargs):
        def decorator(func):
            return func
        return decorator

try:
    import config
except ImportError:
    config = None

def get_finnhub_client():
    if not finnhub:
        logging.warning("finnhub-python not installed.")
        return None
    api_key = getattr(config, 'FINNHUB_API_KEY', os.environ.get('FINNHUB_API_KEY', ''))
    if not api_key:
        return None
    return finnhub.Client(api_key=api_key)

@CACHE(ttl=1800)
def get_company_news(ticker: str, days_back: int = 7) -> List[Dict]:
    client = get_finnhub_client()
    if not client:
        return []
        
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    try:
        news = client.company_news(ticker, _from=start_date, to=end_date)
        formatted_news = []
        for item in news[:10]:
            formatted_news.append({
                'headline': item.get('headline'),
                'source': item.get('source'),
                'datetime': datetime.fromtimestamp(item.get('datetime')).strftime("%Y-%m-%d %H:%M"),
                'url': item.get('url'),
                'summary': item.get('summary')
            })
        return formatted_news
    except Exception as e:
        logging.warning(f"Finnhub news error for {ticker}: {e}")
        return []

@CACHE(ttl=3600)
def get_basic_financials(ticker: str) -> dict:
    client = get_finnhub_client()
    if not client:
        return {}
    try:
        metrics = client.company_basic_financials(ticker, 'all')
        if 'metric' in metrics:
            m = metrics['metric']
            return {
                '52WeekHigh': m.get('52WeekHigh'),
                '52WeekLow': m.get('52WeekLow'),
                'peNormalizedAnnual': m.get('peNormalizedAnnual'),
                'forwardPE': m.get('pfedPriceEarningsTTM') or m.get('peExclExtraTTM'),
                'dividendYield': m.get('dividendYieldIndicatedAnnual'),
                'beta': m.get('beta')
            }
        return {}
    except Exception as e:
        logging.warning(f"Finnhub financials error for {ticker}: {e}")
        return {}

@CACHE(ttl=3600)
def get_earnings_surprises(ticker: str) -> List[Dict]:
    client = get_finnhub_client()
    if not client:
        return []
    try:
        surprises = client.company_earnings(ticker, limit=4)
        return [{
            'period': s.get('period'),
            'actual': s.get('actual'),
            'estimate': s.get('estimate'),
            'surprise': s.get('surprise'),
            'surprisePct': s.get('surprisePercent')
        } for s in surprises]
    except Exception as e:
        logging.warning(f"Finnhub earnings surprise error for {ticker}: {e}")
        return []

if __name__ == "__main__":
    print("Testing Finnhub Client...")
    print(get_basic_financials("AMZN"))