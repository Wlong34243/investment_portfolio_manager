import pandas as pd
import config
import logging

def ensure_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize any DataFrame to use display-format column names 
    (Title Case with spaces, matching config.POSITION_COLUMNS).
    Handles both snake_case internal names and already-correct names.
    """
    if df.empty:
        return df
        
    df = df.copy()
    
    # Build a lookup map of lower_case_name -> Correct Title Case Name
    # This covers both snake_case and variations like 'SYMBOL'
    lookup = {k.lower(): v for k, v in config.POSITION_COL_MAP.items()}
    # Add common variations that might come from raw CSVs before normalization
    lookup['symbol'] = 'Ticker'
    lookup['ticker'] = 'Ticker'
    
    rename_dict = {}
    for col in df.columns:
        # If already in Title Case, leave it
        if col in config.POSITION_COLUMNS:
            continue
            
        # Try to find a match in our lookup
        clean_col = str(col).strip().lower().replace(' ', '_')
        if clean_col in lookup:
            rename_dict[col] = lookup[clean_col]
        elif col.lower() in lookup:
            rename_dict[col] = lookup[col.lower()]
            
    if rename_dict:
        logging.info(f"Column Guard renaming: {rename_dict}")
        df = df.rename(columns=rename_dict)
    
    return df
