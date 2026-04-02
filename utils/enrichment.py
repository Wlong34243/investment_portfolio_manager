import pandas as pd
import numpy as np
import yfinance as yf
import time
import os
import sys
from datetime import datetime

# Add project root to path so config is importable
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import config
    from utils.csv_parser import get_sector_fast
except ImportError:
    # Basic stubs if not importable
    def get_sector_fast(desc): return "Other"

try:
    import streamlit as st
except ImportError:
    st = None

def get_live_price(ticker: str) -> float | None:
    """
    Single ticker price lookup via yf.Ticker(ticker).fast_info["last_price"]
    Wrap entirely in try/except -- return None on ANY error.
    """
    try:
        if ticker in config.CASH_TICKERS:
            return 1.0
        t = yf.Ticker(ticker)
        # Try different ways to get price
        price = t.fast_info.get("last_price")
        if price is None:
            price = t.info.get("regularMarketPrice")
        return float(price) if price is not None else None
    except Exception:
        return None

def enrich_positions(df: pd.DataFrame) -> pd.DataFrame:
    """
    - Filter to top config.TOP_N_ENRICH (20) positions by market_value.
      Exclude CASH_TICKERS from enrichment entirely.
    - Bulk download 1yr daily closes in ONE call.
    - Extract: current_price, dividend_yield, sector, beta_raw.
    - Handle edge cases: CRWV, BABA, ET, SPY dust.
    - Cache in st.session_state["enrichment_cache"].
    - Input/Output uses internal snake_case column names.
    """
    if df.empty:
        return df
        
    df = df.copy()
    
    # Ensure internal names are present (if called after normalization, this might need adjust)
    # But we aim to call this BEFORE normalization
    ticker_col = 'ticker' if 'ticker' in df.columns else 'Ticker'
    mv_col = 'market_value' if 'market_value' in df.columns else 'Market Value'
    qty_col = 'quantity' if 'quantity' in df.columns else 'Quantity'
    desc_col = 'description' if 'description' in df.columns else 'Description'
    
    # 1. Check cache
    now = time.time()
    if st and "enrichment_cache" in st.session_state:
        cache = st.session_state["enrichment_cache"]
        if now - cache.get("timestamp", 0) < config.YFINANCE_CACHE_TTL:
            cached_df = cache.get("df")
            if cached_df is not None and set(df[ticker_col]) == set(cached_df[ticker_col]):
                return cached_df

    # 2. Identify top positions for enrichment
    invested_df = df[~df[ticker_col].isin(config.CASH_TICKERS)]
    significant_df = invested_df[invested_df[qty_col].fillna(0) > 0.001]
    
    top_tickers = significant_df.nlargest(config.TOP_N_ENRICH, mv_col)[ticker_col].tolist()
    
    if not top_tickers:
        return df

    # 3. Bulk download metadata
    enriched_data = {}
    try:
        # Use a comma-separated list of tickers for one large fetch
        tickers_obj = yf.Tickers(" ".join(top_tickers))
        for ticker in top_tickers:
            try:
                t = tickers_obj.tickers[ticker]
                info = t.info
                
                # Metadata
                price = t.fast_info.get("last_price")
                if price is None: price = info.get("regularMarketPrice")
                
                change_pct = info.get("regularMarketChangePercent", 0.0)
                
                # Fetch basic beta from info, fallback to 1.0
                beta = info.get("beta", 1.0)
                
                enriched_data[ticker] = {
                    'price': price,
                    'dividend_yield': info.get("dividendYield", 0.0) if info.get("dividendYield") else 0.0,
                    'sector': info.get("sector"),
                    'beta': beta,
                    'daily_change_pct': change_pct
                }
                
                # Apply Ticker Overrides from config
                if ticker in config.TICKER_OVERRIDES:
                    overrides = config.TICKER_OVERRIDES[ticker]
                    for key, val in overrides.items():
                        if key in enriched_data[ticker] or key == 'asset_class':
                            # Map asset_class override to 'sector' in this loop
                            target_key = 'sector' if key == 'asset_class' else key
                            enriched_data[ticker][target_key] = val

            except Exception as e:
                print(f"Failed to fetch metadata for {ticker}: {e}")
                enriched_data[ticker] = None
    except Exception as e:
        if st: st.warning(f"yfinance bulk fetch failed: {e}")

    # 4. Apply enrichment to DataFrame
    # Target columns (snake_case)
    price_col_target = 'price' if 'price' in df.columns else 'Price'
    yield_col_target = 'dividend_yield' if 'dividend_yield' in df.columns else 'Dividend Yield'
    sector_col_target = 'asset_class' if 'asset_class' in df.columns else 'Asset Class'
    income_col_target = 'est_annual_income' if 'est_annual_income' in df.columns else 'Est Annual Income'

    for ticker, info in enriched_data.items():
        if info is None: continue
        idx = df[df[ticker_col] == ticker].index
        if not idx.empty:
            if info['price'] is not None:
                df.loc[idx, price_col_target] = info['price']
            if info['dividend_yield'] is not None:
                df.loc[idx, yield_col_target] = info['dividend_yield']
            if info['sector'] is not None:
                df.loc[idx, sector_col_target] = info['sector']
            
            # Recalculate Est Annual Income
            if info['dividend_yield'] is not None:
                df.loc[idx, income_col_target] = df.loc[idx, mv_col] * info['dividend_yield'] / 100

    # 5. Fallback for ALL positions
    for idx, row in df.iterrows():
        if row[ticker_col] not in config.CASH_TICKERS:
            # If sector is still missing/Other, try get_sector_fast
            if pd.isna(df.loc[idx, sector_col_target]) or df.loc[idx, sector_col_target] == "Other":
                df.loc[idx, sector_col_target] = get_sector_fast(row[desc_col])

    # 6. Update cache
    if st:
        st.session_state["enrichment_cache"] = {
            "timestamp": now,
            "df": df
        }
        
    return df

if __name__ == "__main__":
    import pandas as pd
    from utils.csv_parser import parse_schwab_csv, inject_cash_manual
    
    test_file = "All-Accounts-Positions-2026-03-30-103853.csv"
    if os.path.exists(test_file):
        df = parse_schwab_csv(open(test_file,'rb').read())
        df = inject_cash_manual(df, 10000)
        df2 = enrich_positions(df)
        # Use whatever column names were in df2
        cols = [c for c in ['ticker', 'market_value', 'dividend_yield', 'asset_class'] if c in df2.columns]
        print(df2[cols].head(10))
    else:
        print(f"Test file {test_file} not found.")
