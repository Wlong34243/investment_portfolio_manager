import pandas as pd
import config
import logging

def ensure_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    NUCLEAR GUARD: Force-normalizes the DataFrame to the production schema.
    Guarantees Ticker existence and correct Title Case headers.
    """
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame(columns=config.POSITION_COLUMNS)
        
    df = df.copy()
    
    # 1. Standardize all headers to string/stripped
    df.columns = [str(c).strip() for c in df.columns]

    # 2. IDENTIFIER FALLBACK (Highest Priority)
    # If 'Ticker' isn't exact, find the closest match and FORCE it to 'Ticker'
    if 'Ticker' not in df.columns:
        id_aliases = ['ticker', 'symbol', 'unnamed: 0', 'unnamed_0', 'sym', 'tkr']
        found_id = False
        for col in df.columns:
            if col.lower() in id_aliases:
                df = df.rename(columns={col: 'Ticker'})
                found_id = True
                break
        
        # Last resort: rename the very first column to Ticker
        if not found_id and len(df.columns) > 0:
            df = df.rename(columns={df.columns[0]: 'Ticker'})

    # 3. Aggressive Rename for remaining columns
    lookup = {k.lower(): v for k, v in config.POSITION_COL_MAP.items()}
    # Extra aliases
    lookup.update({
        'desc': 'Description',
        'market value': 'Market Value',
        'cost': 'Cost Basis',
        'unrealized g/l': 'Unrealized G/L',
        'yield': 'Dividend Yield',
        'asset class': 'Asset Class'
    })
    
    rename_dict = {}
    for col in df.columns:
        if col in config.POSITION_COLUMNS: continue # Already correct
        
        clean_col = str(col).lower().replace(' ', '_')
        if clean_col in lookup:
            target = lookup[clean_col]
            if target not in df.columns:
                rename_dict[col] = target
            
    if rename_dict:
        df = df.rename(columns=rename_dict)
    
    # 4. Final Deduplication (Drop any accidental duplicate columns)
    df = df.loc[:, ~df.columns.duplicated()]

    # 5. Schema Coverage (Force create missing columns with defaults)
    for col in config.POSITION_COLUMNS:
        if col not in df.columns:
            if col in ['Market Value', 'Cost Basis', 'Quantity', 'Price', 'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %']:
                df[col] = 0.0
            elif col in ['Is Cash', 'Wash Sale']:
                df[col] = False
            else:
                df[col] = "Unknown"
        else:
            # Type Casting
            if col in ['Market Value', 'Cost Basis', 'Quantity', 'Price', 'Weight', 'Dividend Yield', 'Est Annual Income', 'Daily Change %']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            elif col in ['Is Cash', 'Wash Sale']:
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.upper().isin(['TRUE', 'YES', '1'])
                else:
                    df[col] = df[col].astype(bool)
            elif col in ['Ticker', 'Asset Class', 'Description']:
                df[col] = df[col].astype(str).fillna("N/A")
                
    return df[config.POSITION_COLUMNS] # Return ONLY and EXACTLY the schema columns
