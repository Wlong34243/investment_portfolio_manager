"""
utils/sheet_readers.py — Google Sheets authentication and reader functions.

Credential resolution: ADC (local CLI) → env var (CI) → Streamlit secrets → file
"""

import os
import sys
import gspread
import pandas as pd
from functools import lru_cache
from google.oauth2.service_account import Credentials

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
    2. GCP_SERVICE_ACCOUNT_JSON env var               ← GitHub Actions
    3. ADC via gcloud auth application-default login  ← local CLI fallback
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

    # Option 2: Environment variable (standard .env loading)
    env_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            info = json.loads(env_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Warning: Failed to load GCP_SERVICE_ACCOUNT_JSON from .env: {e}")

    # Option 3: Environment variable (GitHub Actions)

    # Option 3: ADC — works after gcloud auth application-default login
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
    
    # Identify header row. Some tabs have a KPI strip in row 1.
    header_idx = 0
    for i, row in enumerate(all_values[:10]):
        # Look for "Ticker" or other standard headers
        if "Ticker" in row or "Trade Date" in row or "Date" in row:
            header_idx = i
            break
            
    headers = all_values[header_idx]
    data = all_values[header_idx + 1:]
    
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
        # Check if any row matches the header exactly
        df = df[df[df.columns[0]] != clean_headers[0]]

    # ROOT CAUSE FIX: If the first column is unnamed, it's our Ticker column.
    if 'Unnamed_0' in df.columns:
        df = df.rename(columns={'Unnamed_0': 'Ticker'})

    # Drop entirely empty rows (often present at end of sheet)
    df = df.replace('', None).dropna(how='all').fillna('')

    if df.empty:
        return df
    
    # Identify columns that should NOT be converted to numeric
    # Using lowercase and substring matches for robustness
    text_indicators = [
        'ticker', 'symbol', 'description', 'sector', 'industry',
        'asset class', 'asset strategy', 'import date', 'closed date',
        'opened date', 'acquisition date', 'date', 'import timestamp', 'fingerprint',
        'is cash', 'wash sale', 'is primary acct', 'winner', 'unnamed_',
        'action', 'account', 'status', 'rotation', 'implicit', 'thesis', 'term',
        'trade date', 'settlement date',
        # Valuation_Card's declared trigger_type label (price/fwd_pe/
        # trailing_pe/price_to_book/discount_from_high/ceiling_only) --
        # without this, coerce_sheet_numeric_series zeroes it (real value
        # written to the Sheet correctly; only the read-back was broken).
        # See prompts/typed_trigger_crosshairs_2026-08-24.md.
        'trigger',
        'data_source', 'source',
    ]
    
    for col in df.columns:
        col_lower = col.lower()
        should_skip = any(ind in col_lower for ind in text_indicators)

        if should_skip:
            continue

        # Coercion lives in coerce_sheet_numeric_series() so other callers
        # (valuation card Position MV) share the same strip path.
        # pandas >=3.0 infers plain-string columns as a dedicated string dtype,
        # not legacy `object` -- coerce_sheet_numeric_series handles both.
        df[col] = coerce_sheet_numeric_series(df[col])

    return df


def coerce_sheet_numeric_series(s: pd.Series) -> pd.Series:
    """
    Strip $, %, commas and parenthesized negatives, then to_numeric.
    Shared by read_gsheet_robust() and callers that build a DataFrame without
    going through that reader (e.g. valuation card Position MV).
    """
    had_pct = pd.Series(False, index=s.index)
    out = s
    if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
        out = s.astype(str)
        had_pct = out.str.contains("%", regex=False)
        out = (
            out.str.replace("$", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
        )
        out = out.replace("", "0")
        mask = out.str.startswith("(") & out.str.endswith(")")
        out.loc[mask] = "-" + out.loc[mask].str[1:-1]
    result = pd.to_numeric(out, errors="coerce").fillna(0.0)
    result.loc[had_pct] = result.loc[had_pct] / 100.0
    return result


@lru_cache(maxsize=32)
def get_transactions() -> pd.DataFrame:
    """Reads Transactions tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_TRANSACTIONS)
        return read_gsheet_robust(ws)
    except Exception as e:
        print(f"Error reading Transactions: {e}")
        return pd.DataFrame()

@lru_cache(maxsize=32)
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

@lru_cache(maxsize=32)
def get_risk_metrics() -> pd.DataFrame:
    """Reads Risk_Metrics tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_RISK_METRICS)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@lru_cache(maxsize=32)
def get_income_history() -> pd.DataFrame:
    """Reads Income_Tracking tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_INCOME_TRACKING)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@lru_cache(maxsize=32)
def get_realized_gl() -> pd.DataFrame:
    """Reads Realized_GL tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_REALIZED_GL)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@lru_cache(maxsize=32)
def get_daily_snapshots() -> pd.DataFrame:
    """Reads Daily_Snapshots tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_DAILY_SNAPSHOTS)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@lru_cache(maxsize=32)
def get_target_allocation() -> pd.DataFrame:
    """Reads Target_Allocation tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_TARGET_ALLOCATION)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@lru_cache(maxsize=32)
def get_ai_suggested_allocation() -> pd.DataFrame:
    """Reads AI_Suggested_Allocation tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_AI_SUGGESTED_ALLOCATION)
        return read_gsheet_robust(ws)
    except Exception:
        return pd.DataFrame()

@lru_cache(maxsize=32)
def get_trade_log() -> pd.DataFrame:
    """Reads Trade_Log tab."""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_TRADE_LOG)
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
