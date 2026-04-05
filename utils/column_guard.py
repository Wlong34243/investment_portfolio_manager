import pandas as pd
import config
import logging

def ensure_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    BULLETPROOF GUARD: Ensures 'Ticker' and all required columns exist.
    Forces correct types and reorders to schema.
    """
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame(columns=config.POSITION_COLUMNS)
        
    df = df.copy()
    
    # 1. Strip whitespace from headers
    df.columns = [str(c).strip() for c in df.columns]

    # 2. Force detect Ticker if missing (Crucial for Plotly)
    if 'Ticker' not in df.columns:
        # Search for aliases
        aliases = ['symbol', 'ticker', 'unnamed: 0', 'unnamed_0', 'tkr']
        found = False
        for col in df.columns:
            if col.lower() in aliases:
                df = df.rename(columns={col: 'Ticker'})
                found = True
                break
        # Ultimate fallback: rename the first column to Ticker
        if not found and len(df.columns) > 0:
            df = df.rename(columns={df.columns[0]: 'Ticker'})

    # 3. Rename others based on config
    lookup = {k.lower(): v for k, v in config.POSITION_COL_MAP.items()}
    lookup.update({'desc': 'Description', 'market value': 'Market Value', 'cost': 'Cost Basis'})
    
    rename_dict = {}
    for col in df.columns:
        if col in config.POSITION_COLUMNS: continue
        low_col = col.lower().replace(' ', '_')
        if low_col in lookup:
            target = lookup[low_col]
            if target not in df.columns:
                rename_dict[col] = target
                
    if rename_dict:
        df = df.rename(columns=rename_dict)

    # 4. Final deduplication of headers
    df = df.loc[:, ~df.columns.duplicated()]

    # 5. Schema enforcement (Force create missing + cast types)
    for col in config.POSITION_COLUMNS:
        if col not in df.columns:
            if col in ['Market Value', 'Cost Basis', 'Quantity', 'Price', 'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %']:
                df[col] = 0.0
            elif col in ['Is Cash', 'Wash Sale']:
                df[col] = False
            else:
                df[col] = "N/A"
        
        # Explicit type casting
        if col in ['Market Value', 'Cost Basis', 'Quantity', 'Price', 'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        elif col in ['Is Cash', 'Wash Sale']:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.upper().isin(['TRUE', 'YES', '1', 'T'])
            else:
                df[col] = df[col].astype(bool)
        else:
            df[col] = df[col].astype(str).fillna("")

    # 6. Reorder to exact schema
    return df[config.POSITION_COLUMNS]
