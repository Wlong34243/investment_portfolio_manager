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
    for col in config.POSITION_COLUMNS:
        if col not in df.columns:
            if col in ['Market Value', 'Cost Basis', 'Quantity', 'Price', 'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %']:
                df[col] = 0.0
            elif col in ['Is Cash', 'Wash Sale']:
                df[col] = False
            else:
                df[col] = "N/A"
        
        # Type Casting
        if col in ['Market Value', 'Cost Basis', 'Quantity', 'Price', 'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
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
