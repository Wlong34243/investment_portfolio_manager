"""
utils/sheet_readers.py — Google Sheets authentication and reader functions.
"""

import os
import sys
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# Streamlit Cache Fallback
try:
    import streamlit as st
    CACHE = st.cache_data
except ImportError:
    st = None
    def CACHE(ttl=None, **kwargs):
        def decorator(func):
            return func
        return decorator

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import config
except ImportError:
    pass

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

class AuthError(Exception):
    """Raised when no valid credentials can be found."""

def get_gspread_client() -> gspread.Client:
    """Return an authenticated gspread client."""
    # Method 1: Streamlit secrets
    if st and hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        try:
            creds = Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]),
                scopes=SCOPES,
            )
            return gspread.authorize(creds)
        except:
            pass

    # Method 2: local service_account.json
    sa_path = os.path.join(_ROOT, "service_account.json")
    if os.path.isfile(sa_path):
        creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        return gspread.authorize(creds)

    raise AuthError("Could not authenticate with Google Sheets.")

def read_gsheet_robust(ws: gspread.Worksheet) -> pd.DataFrame:
    """Reads worksheet into DataFrame with aggressive numeric cleaning."""
    all_values = ws.get_all_values()
    if not all_values:
        return pd.DataFrame()
    
    headers = all_values[0]
    data = all_values[1:]
    
    clean_headers = []
    seen = {}
    for i, h in enumerate(headers):
        h = h.strip() or f"Unnamed_{i}"
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        clean_headers.append(h)
    
    df = pd.DataFrame(data, columns=clean_headers)
    
    # Cleaning
    for col in df.columns:
        if col.lower() in ['ticker', 'symbol', 'description', 'sector', 'industry', 'asset class', 'asset strategy', 'import date', 'closed date', 'opened date', 'acquisition date']:
            continue
        
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace('%', '', regex=False).str.replace(',', '', regex=False).str.strip()
            df[col] = df[col].replace('', '0')
            mask = df[col].str.startswith('(') & df[col].str.endswith(')')
            df.loc[mask, col] = '-' + df.loc[mask, col].str[1:-1]
        
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
    return df

@CACHE(ttl=300)
def get_holdings_current() -> pd.DataFrame:
    """Reads Holdings_Current tab."""
    from utils.column_guard import ensure_display_columns
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)
        df = read_gsheet_robust(ws)
        return ensure_display_columns(df)
    except Exception as e:
        print(f"Error reading Holdings_Current: {e}")
        return pd.DataFrame()

@CACHE(ttl=300)
def get_risk_metrics() -> pd.DataFrame:
    """Reads Risk_Metrics tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_RISK_METRICS)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@CACHE(ttl=300)
def get_income_history() -> pd.DataFrame:
    """Reads Income_Tracking tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_INCOME_TRACKING)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@CACHE(ttl=300)
def get_realized_gl() -> pd.DataFrame:
    """Reads Realized_GL tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_REALIZED_GL)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@CACHE(ttl=300)
def get_daily_snapshots() -> pd.DataFrame:
    """Reads Daily_Snapshots tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_DAILY_SNAPSHOTS)
        df = read_gsheet_robust(ws)
        return df
    except Exception:
        return pd.DataFrame()

def smoke_test() -> bool:
    """Verify connectivity."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        print(f"Auth OK — tabs: {[ws.title for ws in spreadsheet.worksheets()]}")
        return True
    except Exception as e:
        print(f"Smoke test failed: {e}")
        return False

if __name__ == "__main__":
    smoke_test()
