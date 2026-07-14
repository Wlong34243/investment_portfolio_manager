import pandas as pd
import numpy as np
import yfinance as yf
import json
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
    - Input/Output uses internal snake_case column names.
    """
    if df.empty:
        return df
        
    df = df.copy()
    
    # Ensure internal names are present
    ticker_col = 'ticker' if 'ticker' in df.columns else 'Ticker'
    mv_col = 'market_value' if 'market_value' in df.columns else 'Market Value'
    qty_col = 'quantity' if 'quantity' in df.columns else 'Quantity'
    desc_col = 'description' if 'description' in df.columns else 'Description'
    
    # 1. Identify top positions for enrichment
    invested_df = df[~df[ticker_col].isin(config.CASH_TICKERS)]
    significant_df = invested_df[invested_df[qty_col].fillna(0) > 0.001]
    
    top_tickers = significant_df.nlargest(config.TOP_N_ENRICH, mv_col)[ticker_col].tolist()
    
    if not top_tickers:
        return df

    # 2. Bulk download metadata
    enriched_data = {}
    try:
        # Use a comma-separated list of tickers for one large fetch
        tickers_obj = yf.Tickers(" ".join(top_tickers))
        for ticker in top_tickers:
            try:
                t = tickers_obj.tickers[ticker]
                info = t.info

                # Metadata
                # Fetch basic beta from info, fallback to 1.0
                beta = info.get("beta", 1.0)

                # yfinance now returns dividendYield in percent-scale (8.45 for
                # 8.45%, not the raw fraction 0.0845) -- confirmed live against
                # JEPI/JPIE/GOOG on 2026-07-05. Dividing unconditionally by 100
                # matches how utils/csv_parser.py already treats Schwab's own
                # CSV yield column. The >0.25 clamp is a second-layer guard in
                # case a ticker's value is still out of range after scaling.
                raw_yield = info.get("dividendYield")
                dividend_yield = (raw_yield / 100.0) if raw_yield else 0.0
                if dividend_yield > 0.25:
                    print(f"Warning: {ticker} dividend yield {dividend_yield:.2%} still looks too high after /100 scaling; dividing again.")
                    dividend_yield = dividend_yield / 100.0

                enriched_data[ticker] = {
                    'dividend_yield': dividend_yield,
                    'sector': info.get("sector"),
                    'asset_class_override': None,
                    'beta': beta,
                    'long_name': info.get("longName") or info.get("shortName") or "",
                }

                # Apply Ticker Overrides from config
                if ticker in config.TICKER_OVERRIDES:
                    overrides = config.TICKER_OVERRIDES[ticker]
                    for key, val in overrides.items():
                        if key == 'asset_class':
                            # Explicit overrides target the real Asset Class
                            # column, never the Sector column (see below).
                            enriched_data[ticker]['asset_class_override'] = val
                        elif key in enriched_data[ticker]:
                            enriched_data[ticker][key] = val

            except Exception as e:
                print(f"Failed to fetch metadata for {ticker}: {e}")
                enriched_data[ticker] = None
    except Exception as e:
        print(f"yfinance bulk fetch failed: {e}")

    # 3. Apply enrichment to DataFrame
    yield_col_target = 'dividend_yield' if 'dividend_yield' in df.columns else 'Dividend Yield'
    # yfinance's GICS sector (Technology, Utilities, ...) is NOT an asset class
    # (Equity, Fixed Income, Cash, ...) -- it must never overwrite Asset Class.
    # It goes in its own Sector column; explicit TICKER_OVERRIDES asset_class
    # entries (e.g. BABA) are the only thing allowed to touch Asset Class.
    sector_col_target = 'sector' if 'sector' in df.columns else 'Sector'
    asset_class_col_target = 'asset_class' if 'asset_class' in df.columns else 'Asset Class'
    income_col_target = 'est_annual_income' if 'est_annual_income' in df.columns else 'Est Annual Income'

    # Guarantee the Sector column exists even if every enriched ticker this run
    # happens to have sector=None (e.g. a top-20 list made entirely of ETFs) --
    # otherwise the fallback loop below raises KeyError on first access.
    if sector_col_target not in df.columns:
        df[sector_col_target] = pd.NA

    for ticker, info in enriched_data.items():
        if info is None: continue
        idx = df[df[ticker_col] == ticker].index
        if not idx.empty:
            if info['dividend_yield'] is not None:
                df.loc[idx, yield_col_target] = info['dividend_yield']
            if info['sector'] is not None:
                df.loc[idx, sector_col_target] = info['sector']
            if info.get('asset_class_override') is not None:
                df.loc[idx, asset_class_col_target] = info['asset_class_override']
            if info.get('long_name'):
                df.loc[idx, desc_col] = info['long_name']

            # Recalculate Est Annual Income using the now-correctly-scaled yield
            if info['dividend_yield'] is not None:
                df.loc[idx, income_col_target] = df.loc[idx, mv_col] * info['dividend_yield']

    # 3b. Name-only lookup for remaining invested tickers that still have empty descriptions
    already_enriched = set(top_tickers)
    remaining_no_desc = [
        row[ticker_col] for _, row in df.iterrows()
        if row[ticker_col] not in config.CASH_TICKERS
        and row[ticker_col] not in already_enriched
        and (pd.isna(row.get(desc_col, "")) or str(row.get(desc_col, "")).strip() == "")
    ]
    if remaining_no_desc:
        try:
            rem_obj = yf.Tickers(" ".join(remaining_no_desc))
            for rem_ticker in remaining_no_desc:
                try:
                    info = rem_obj.tickers[rem_ticker].info
                    name = info.get("longName") or info.get("shortName") or ""
                    if name:
                        idx = df[df[ticker_col] == rem_ticker].index
                        df.loc[idx, desc_col] = name
                except Exception:
                    pass
        except Exception as e:
            print(f"Name-only enrichment batch failed: {e}")

    # 4. Fallback for ALL positions
    for idx, row in df.iterrows():
        if row[ticker_col] not in config.CASH_TICKERS:
            # If description is still empty, use ticker symbol as minimum
            if pd.isna(df.loc[idx, desc_col]) or str(df.loc[idx, desc_col]).strip() == "":
                df.loc[idx, desc_col] = row[ticker_col]
            # If sector is still missing/Other, try get_sector_fast.
            # get_sector_fast() currently raises AttributeError (config.ETF_KEYWORDS
            # does not exist) -- guard so a broken fallback classifier can't take
            # down the whole snapshot; pre-existing bug, out of scope for this fix.
            if pd.isna(df.loc[idx, sector_col_target]) or df.loc[idx, sector_col_target] == "Other":
                try:
                    df.loc[idx, sector_col_target] = get_sector_fast(row[desc_col])
                except Exception as e:
                    print(f"get_sector_fast failed for {row[ticker_col]}: {e}")

    return df

def apply_smart_categorization(df: pd.DataFrame, mapping_file: str = "data/ticker_mapping.json") -> pd.DataFrame:
    """
    Overwrites 'asset_class' and 'asset_strategy' in the DataFrame
    using the Gemini-generated ticker mapping JSON produced by portfolio_enricher.py.
    If the mapping file is absent, returns df unchanged.
    """
    if not os.path.exists(mapping_file):
        print(f"Mapping file {mapping_file} not found. Proceeding with raw classifications.")
        return df

    with open(mapping_file, 'r') as f:
        mapping = json.load(f)

    def get_asset_class(ticker, current_val):
        return mapping.get(str(ticker), {}).get("asset_class", current_val)

    def get_asset_strategy(ticker, current_val):
        return mapping.get(str(ticker), {}).get("sector_strategy", current_val)

    if 'ticker' in df.columns:
        if 'asset_class' not in df.columns:
            df['asset_class'] = "Other"
        if 'asset_strategy' not in df.columns:
            df['asset_strategy'] = "Other"

        df['asset_class'] = df.apply(
            lambda row: get_asset_class(row['ticker'], row['asset_class']), axis=1
        )
        df['asset_strategy'] = df.apply(
            lambda row: get_asset_strategy(row['ticker'], row['asset_strategy']), axis=1
        )

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
