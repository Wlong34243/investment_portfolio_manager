import pandas as pd
import config
import logging
import re

def ensure_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    ULTRA-ROBUST GUARD: Ensures exactly the columns in config.POSITION_COLUMNS exist.
    Sanitizes against non-printing characters and common variations.
    """
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame(columns=config.POSITION_COLUMNS)
        
    df = df.copy()
    
    # 1. Extreme Header Sanitization (Removes \xa0, \ufeff, spaces, etc.)
    def _clean_header(name):
        c = str(name).strip()
        c = re.sub(r'[^\x20-\x7E]', '', c) # Remove non-ascii
        return c

    df.columns = [_clean_header(c) for c in df.columns]

    # 2. Map aliases to production headers
    # lookup: normalized_lower_name -> Correct Title Case Name
    lookup = {str(k).lower().replace(' ', '_'): v for k, v in config.POSITION_COL_MAP.items()}
    
    # Common variations from Schwab / yfinance / manual edits
    lookup.update({
        'symbol': 'Ticker',
        'ticker': 'Ticker',
        'unnamed: 0': 'Ticker',
        'unnamed_0': 'Ticker',
        'market_value': 'Market Value',
        'marketvalue': 'Market Value',
        'cost_basis': 'Cost Basis',
        'costbasis': 'Cost Basis',
        'asset_class': 'Asset Class',
        'assetclass': 'Asset Class'
    })
    
    rename_dict = {}
    for col in df.columns:
        if col in config.POSITION_COLUMNS:
            continue
        
        # Try finding a match
        norm_col = str(col).lower().replace(' ', '_').replace('-', '_')
        if norm_col in lookup:
            target = lookup[norm_col]
            if target not in df.columns:
                rename_dict[col] = target
            
    if rename_dict:
        df = df.rename(columns=rename_dict)
        
    # 3. Final Fallback for Ticker (Plotly Requirement)
    if 'Ticker' not in df.columns:
        # If we see any column that looks like a ticker, take it
        for col in df.columns:
            if col.lower() in ['ticker', 'symbol', 'unnamed: 0', 'unnamed_0']:
                df = df.rename(columns={col: 'Ticker'})
                break
        
        # If still not found, rename column 0
        if 'Ticker' not in df.columns and len(df.columns) > 0:
            df = df.rename(columns={df.columns[0]: 'Ticker'})

    # 4. Guarantee all columns exist
    _NUMERIC_COLS = [
        'Market Value', 'Cost Basis', 'Unit Cost', 'Quantity', 'Price',
        'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %',
        'Unrealized G/L', 'Unrealized G/L %',
    ]
    for col in config.POSITION_COLUMNS:
        if col not in df.columns:
            if col in _NUMERIC_COLS:
                df[col] = 0.0
            elif col in ['Is Cash', 'Wash Sale']:
                df[col] = False
            else:
                df[col] = "N/A"

        # Type Casting
        if col in _NUMERIC_COLS:
            # Shared strip/$/%/, path — do not duplicate locally (pandas 3.0
            # string dtype is handled inside coerce_sheet_numeric_series).
            from utils.sheet_readers import coerce_sheet_numeric_series
            df[col] = coerce_sheet_numeric_series(df[col])
        elif col in ['Is Cash', 'Wash Sale']:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.upper().isin(['TRUE', 'YES', '1', 'T'])
            else:
                df[col] = df[col].astype(bool)
        else:
            df[col] = df[col].astype(str).fillna("N/A")

    # 5. Return exactly the schema columns in order
    # (Removes any persistent garbage columns)
    return df[config.POSITION_COLUMNS]


def ensure_trade_log_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Guard Trade_Log against silent column drift (documented 2026-08-08 misalignment).
    Ensures exactly config.TRADE_LOG_COLUMNS exist, in order. Missing rationale
    columns are added blank — never invent Implicit_Bet text.
    """
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame(columns=config.TRADE_LOG_COLUMNS)

    df = df.copy()

    def _clean_header(name):
        c = str(name).strip()
        c = re.sub(r"[^\x20-\x7E]", "", c)
        return c

    df.columns = [_clean_header(c) for c in df.columns]

    # Alias map for shortened Sheet display headers
    aliases = {
        "sell rsi": "Sell_RSI_At_Decision",
        "sell_rsi": "Sell_RSI_At_Decision",
        "sell trend": "Sell_Trend_At_Decision",
        "sell_trend": "Sell_Trend_At_Decision",
        "sell vs ma200": "Sell_Price_vs_MA200_At_Decision",
        "buy rsi": "Buy_RSI_At_Decision",
        "buy trend": "Buy_Trend_At_Decision",
        "buy vs ma200": "Buy_Price_vs_MA200_At_Decision",
    }
    rename = {}
    for col in df.columns:
        key = col.lower().replace(" ", "_")
        spaced = col.lower()
        if col in config.TRADE_LOG_COLUMNS:
            continue
        target = aliases.get(spaced) or aliases.get(key)
        if target and target not in df.columns:
            rename[col] = target
    if rename:
        df = df.rename(columns=rename)

    for col in config.TRADE_LOG_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    return df[config.TRADE_LOG_COLUMNS]
