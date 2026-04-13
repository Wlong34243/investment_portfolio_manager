"""
utils/sheet_readers.py — Google Sheets authentication and reader functions.

Credential resolution: ADC (local CLI) → env var (CI) → Streamlit secrets → file
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

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

class AuthError(Exception):
    """Raised when no valid credentials can be found."""

def get_gspread_client() -> gspread.Client:
    """
    Return an authenticated gspread client.

    Credential resolution order:
    1. Local service_account.json file                ← most reliable for specific scopes
    2. st.secrets["gcp_service_account"]              ← Streamlit Cloud
    3. GCP_SERVICE_ACCOUNT_JSON env var               ← GitHub Actions
    4. ADC via gcloud auth application-default login  ← local CLI fallback
    """
    import json

    # Option 1: local service_account.json
    sa_path = os.path.join(_ROOT, "service_account.json")
    if os.path.isfile(sa_path):
        try:
            creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Warning: Failed to load service_account.json: {e}")

    # Option 2: Streamlit secrets
    if st and hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        try:
            creds = Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]),
                scopes=SCOPES,
            )
            return gspread.authorize(creds)
        except Exception:
            pass

    # Option 3: Environment variable (GitHub Actions)
    env_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            info = json.loads(env_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Warning: Failed to load credentials from env var: {e}")

    # Option 4: ADC — works after gcloud auth application-default login
    try:
        import google.auth
        credentials, _ = google.auth.default(scopes=SCOPES)
        return gspread.authorize(credentials)
    except Exception:
        pass

    raise AuthError(
        "No Google Sheets credentials found."
    )

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

    # Filter out redundant header rows (sometimes happens with insert_row at row 1)
    if not df.empty:
        # Check if the first column's content is the same as its header
        first_col = df.columns[0]
        df = df[df[first_col] != first_col]

    # ROOT CAUSE FIX: If the first column is unnamed, it's our Ticker column.
    if 'Unnamed_0' in df.columns:
        df = df.rename(columns={'Unnamed_0': 'Ticker'})

    # Drop entirely empty rows (often present at end of sheet)
    df = df.replace('', None).dropna(how='all').fillna('')

    if df.empty:
        return df
    skip_cols = [
        'ticker', 'symbol', 'description', 'sector', 'industry', 
        'asset class', 'asset strategy', 'import date', 'closed date', 
        'opened date', 'acquisition date', 'date', 'import timestamp', 'fingerprint',
        'is cash', 'wash sale', 'is primary acct', 'winner', 'unnamed_0'
    ]
    for col in df.columns:
        col_lower = col.lower()
        # Skip known text/identifier columns AND any unnamed columns (Unnamed_0, Unnamed_1 etc.)
        # Unnamed columns arise when a Sheet header is blank; they typically hold ticker/identifier data
        if col_lower in skip_cols or col_lower.startswith('unnamed_'):
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
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@CACHE(ttl=300)
def get_target_allocation() -> pd.DataFrame:
    """Reads Target_Allocation tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_TARGET_ALLOCATION)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@CACHE(ttl=300)
def get_ai_suggested_allocation() -> pd.DataFrame:
    """Reads AI_Suggested_Allocation tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_AI_SUGGESTED_ALLOCATION)
        return read_gsheet_robust(ws)
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
