import pandas as pd
import logging
import config

def validate_percentage_range(df: pd.DataFrame, col_name: str, min_val: float = -50.0, max_val: float = 100.0) -> pd.DataFrame:
    """
    Flag rows where the column value is outside the specified range.
    Returns a DataFrame of flagged rows with a 'Reason' column.
    """
    if col_name not in df.columns:
        return pd.DataFrame()
        
    invalid = df[(df[col_name] < min_val) | (df[col_name] > max_val)].copy()
    if not invalid.empty:
        invalid['Reason'] = f"Value outside reasonable range ({min_val}% to {max_val}%)"
        
    return invalid

def validate_no_negative_market_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag rows where market_value <= 0 (excluding CASH_MANUAL).
    """
    mv_col = 'market_value' if 'market_value' in df.columns else 'Market Value'
    ticker_col = 'ticker' if 'ticker' in df.columns else 'Ticker'
    
    if mv_col not in df.columns or ticker_col not in df.columns:
        return pd.DataFrame()
        
    invalid = df[(df[mv_col] <= 0) & (df[ticker_col] != 'CASH_MANUAL')].copy()
    if not invalid.empty:
        invalid['Reason'] = "Zero or negative market value detected for an investment position"
        
    return invalid

def validate_duplicate_tickers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag tickers that appear more than once after aggregation.
    """
    ticker_col = 'ticker' if 'ticker' in df.columns else 'Ticker'
    
    if ticker_col not in df.columns:
        return pd.DataFrame()
        
    duplicates = df[df.duplicated(subset=[ticker_col], keep=False)].copy()
    if not duplicates.empty:
        duplicates['Reason'] = "Duplicate ticker found after aggregation"
        
    return duplicates

def validate_total_sanity(df: pd.DataFrame, expected_range: tuple = (100000, 1000000)) -> list[str]:
    """
    Flag if total portfolio value is outside expected range.
    Returns a list of warning strings.
    """
    mv_col = 'market_value' if 'market_value' in df.columns else 'Market Value'
    
    if mv_col not in df.columns:
        return []
        
    total_val = df[mv_col].sum()
    min_val, max_val = expected_range
    
    if total_val < min_val:
        return [f"⚠️ Total portfolio value (${total_val:,.0f}) is below expected minimum (${min_val:,.0f})"]
    if total_val > max_val:
        return [f"⚠️ Total portfolio value (${total_val:,.0f}) exceeds expected maximum (${max_val:,.0f})"]
        
    return []
