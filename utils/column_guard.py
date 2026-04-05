import pandas as pd
import config
import logging

def ensure_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize any DataFrame to use display-format column names 
    (Title Case with spaces, matching config.POSITION_COLUMNS).
    Guarantees that all required columns exist and have correct types.
    """
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame(columns=config.POSITION_COLUMNS)
        
    df = df.copy()
    
    # 1. Aggressive Rename Logic
    lookup = {k.lower(): v for k, v in config.POSITION_COL_MAP.items()}
    lookup.update({
        'symbol': 'Ticker',
        'ticker': 'Ticker',
        'desc': 'Description',
        'market value': 'Market Value',
        'cost': 'Cost Basis',
        'unrealized g/l': 'Unrealized G/L',
        'yield': 'Dividend Yield',
        'asset class': 'Asset Class'
    })
    
    rename_dict = {}
    for col in df.columns:
        if col in config.POSITION_COLUMNS:
            continue
        clean_col = str(col).strip().lower().replace(' ', '_')
        if clean_col in lookup:
            rename_dict[col] = lookup[clean_col]
        elif col.lower() in lookup:
            rename_dict[col] = lookup[col.lower()]
            
    if rename_dict:
        df = df.rename(columns=rename_dict)
    
    # 2. Guarantee Column Existence & Types
    for col in config.POSITION_COLUMNS:
        if col not in df.columns:
            if col in ['Market Value', 'Cost Basis', 'Quantity', 'Price', 'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %']:
                df[col] = 0.0
            elif col in ['Is Cash', 'Wash Sale']:
                df[col] = False
            else:
                df[col] = ""
        else:
            # Type Enforcement for existing columns
            if col in ['Market Value', 'Cost Basis', 'Quantity', 'Price', 'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            elif col in ['Is Cash', 'Wash Sale']:
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.upper().isin(['TRUE', 'YES', '1'])
                else:
                    df[col] = df[col].astype(bool)
            elif col in ['Ticker', 'Asset Class', 'Description']:
                df[col] = df[col].astype(str).fillna("")
                
    return df
