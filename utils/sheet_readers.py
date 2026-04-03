"""
utils/sheet_readers.py — Google Sheets authentication and smoke test.

Auth priority:
  1. st.secrets["gcp_service_account"] (Streamlit Cloud / local with secrets.toml)
  2. service_account.json in project root
  3. GOOGLE_APPLICATION_CREDENTIALS env var pointing to a service_account.json file
"""

import os
import sys
import gspread
from google.oauth2.service_account import Credentials

# Add project root to path so config is importable when run directly
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import config
except ImportError:
    # If config not found, we might be in a different context
    pass

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class AuthError(Exception):
    """Raised when no valid credentials can be found."""


def get_gspread_client() -> gspread.Client:
    """
    Return an authenticated gspread client.

    Tries Streamlit secrets first, then local service_account.json, then GOOGLE_APPLICATION_CREDENTIALS env var.
    Raises AuthError with clear instructions if all methods fail.
    """
    # --- Method 1: Streamlit secrets ---
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]),
                scopes=SCOPES,
            )
            return gspread.authorize(creds)
    except Exception:
        pass  # Not in a Streamlit context, or secret missing — fall through

    # --- Method 2: local service_account.json ---
    # Look in the root of the project
    sa_path_root = os.path.join(_ROOT, "service_account.json")
    if os.path.isfile(sa_path_root):
        creds = Credentials.from_service_account_file(sa_path_root, scopes=SCOPES)
        return gspread.authorize(creds)
    
    # Also look in the current working directory as a fallback
    sa_path_cwd = "service_account.json"
    if os.path.isfile(sa_path_cwd):
        creds = Credentials.from_service_account_file(sa_path_cwd, scopes=SCOPES)
        return gspread.authorize(creds)

    # --- Method 3: GOOGLE_APPLICATION_CREDENTIALS env var ---
    sa_path_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if sa_path_env and os.path.isfile(sa_path_env):
        creds = Credentials.from_service_account_file(sa_path_env, scopes=SCOPES)
        return gspread.authorize(creds)

    # --- All failed ---
    raise AuthError(
        "Could not authenticate with Google Sheets.\n\n"
        "Fix one of the following:\n"
        "  A) Streamlit: add [gcp_service_account] to .streamlit/secrets.toml\n"
        "  B) Local dev: ensure 'service_account.json' exists in the project root\n"
        "  C) Env var: set the GOOGLE_APPLICATION_CREDENTIALS environment variable\n"
        "     e.g.  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service_account.json\n"
        "     or    set GOOGLE_APPLICATION_CREDENTIALS=C:\\path\\to\\service_account.json\n"
        "     Then re-run this script."
    )


def smoke_test() -> bool:
    """
    Verify end-to-end connectivity:
      - Authenticate via get_gspread_client()
      - Open the Portfolio Sheet by config.PORTFOLIO_SHEET_ID
      - List all worksheet tab names
      - Read and print headers from Holdings_Current (first row)

    Prints "Auth OK — tabs: [...]" on success.
    Returns True on success, raises on any failure.
    """
    client = get_gspread_client()

    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    tab_names = [ws.title for ws in spreadsheet.worksheets()]
    print(f"Auth OK — tabs: {tab_names}")

    try:
        holdings_ws = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)
        first_row = holdings_ws.row_values(1)
        if first_row:
            print(f"Holdings_Current headers: {first_row}")
        else:
            print("Holdings_Current: sheet exists but is empty (no headers yet)")
    except gspread.exceptions.WorksheetNotFound:
        print(f"Note: '{config.TAB_HOLDINGS_CURRENT}' tab not found yet — sheet setup pending")

    return True


import pandas as pd

try:
    import streamlit as st
except ImportError:
    st = None

def read_gsheet_robust(ws: gspread.Worksheet) -> pd.DataFrame:
    """
    Reads a worksheet into a DataFrame, handling duplicate or empty headers
    that cause get_all_records() to fail.
    """
    all_values = ws.get_all_values()
    if not all_values:
        return pd.DataFrame()
    
    headers = all_values[0]
    data = all_values[1:]
    
    # Clean headers: handle empty or duplicate headers
    clean_headers = []
    seen = {}
    for i, h in enumerate(headers):
        h = h.strip()
        if not h:
            h = f"Unnamed_{i}"
        
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        
        clean_headers.append(h)
    
    df = pd.DataFrame(data, columns=clean_headers)
    
    # Drop "Unnamed" columns if they are entirely empty
    cols_to_drop = [c for c in df.columns if c.startswith("Unnamed_") and (df[c] == "").all()]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
        
    return df

if st:
    @st.cache_data(ttl=300)
    def get_holdings_current() -> pd.DataFrame:
        """
        Reads Holdings_Current tab and returns DataFrame.
        """
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            ws = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)
            return read_gsheet_robust(ws)
        except Exception as e:
            print(f"Error reading Holdings_Current: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def get_risk_metrics() -> pd.DataFrame:
        """Reads Risk_Metrics tab and returns DataFrame."""
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            ws = spreadsheet.worksheet(config.TAB_RISK_METRICS)
            return read_gsheet_robust(ws)
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def get_income_history() -> pd.DataFrame:
        """Reads Income_Tracking tab and returns DataFrame."""
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            ws = spreadsheet.worksheet(config.TAB_INCOME_TRACKING)
            return read_gsheet_robust(ws)
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def get_realized_gl() -> pd.DataFrame:
        """Reads Realized_GL tab and returns DataFrame."""
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            ws = spreadsheet.worksheet(config.TAB_REALIZED_GL)
            return read_gsheet_robust(ws)
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def get_daily_snapshots() -> pd.DataFrame:
        """Reads Daily_Snapshots tab and returns DataFrame."""
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            ws = spreadsheet.worksheet(config.TAB_DAILY_SNAPSHOTS)
            df = read_gsheet_robust(ws)
            if not df.empty:
                # Convert numeric columns to float
                for col in config.SNAPSHOT_COLUMNS:
                    if col in df.columns and col != 'Date':
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            return df
        except Exception:
            return pd.DataFrame()


if __name__ == "__main__":
    smoke_test()
