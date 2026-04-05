import pandas as pd
import config

def ensure_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize any DataFrame to use display-format column names 
    (Title Case with spaces, matching config.POSITION_COLUMNS).
    Handles both snake_case internal names and already-correct names.
    """
    if df.empty:
        return df
        
    # Build map: internal_name -> display_name
    # config.POSITION_COL_MAP is already {internal: display}
    mapping = config.POSITION_COL_MAP
    
    # Only rename columns that exist and aren't already correct
    rename_dict = {}
    for col in df.columns:
        if col in mapping:
            rename_dict[col] = mapping[col]
    
    if rename_dict:
        # Avoid inplace to be safer with streamlit caching
        df = df.rename(columns=rename_dict)
    
    return df
