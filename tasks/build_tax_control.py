"""
tasks/build_tax_control.py — Compute YTD tax KPIs and refresh the Tax_Control tab.
Deterministic Python math over Realized_GL and Config. No LLMs.
"""

import pandas as pd
from datetime import datetime
import logging
from typing import Dict, Any, List, Tuple

import config
from utils.sheet_readers import get_gspread_client, get_realized_gl, read_gsheet_robust
from utils.sheet_writers import safe_execute

logger = logging.getLogger(__name__)

def get_tax_rates() -> Tuple[float, float, float, int]:
    """
    Reads tax rates and thresholds from Config tab directly.
    Returns (rate_st, rate_lt, alert_threshold, wash_sale_cluster_threshold).
    """
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_CONFIG)
    
    # Direct read to avoid read_gsheet_robust cleaning numeric columns that are IDs
    all_vals = ws.get_all_values()
    if not all_vals:
        raise ValueError("Config tab is empty.")
    
    headers = all_vals[0]
    config_dict = {}
    for row in all_vals[1:]:
        if row:
            config_dict[row[0]] = row[1]
    
    try:
        # Use simple float conversion, handle empty/missing
        def safe_float(key, default):
            val = config_dict.get(key, "").strip()
            if not val:
                return default
            return float(val.replace('%', '').replace('$', '').replace(',', ''))

        rate_st = safe_float('tax_rate_short_term', 0.0)
        rate_lt = safe_float('tax_rate_long_term', 0.0)
        alert_threshold = safe_float('tax_estimated_tax_alert_threshold', 5000.0)
        wash_sale_threshold = int(safe_float('tax_wash_sale_cluster_threshold', 3))
        
        if rate_st == 0 or rate_lt == 0:
            logger.warning(f"Tax rates in Config appear to be zero (ST: {rate_st}, LT: {rate_lt}). Verify Config tab.")
            
        return rate_st, rate_lt, alert_threshold, wash_sale_threshold
    except (ValueError, TypeError) as e:
        raise ValueError(f"Error parsing tax rates from Config: {e}. Ensure keys 'tax_rate_short_term' and 'tax_rate_long_term' are populated with numbers.")

def get_realized_gl_robust() -> pd.DataFrame:
    """
    Reads Realized_GL tab, handling potential descriptive text or multiple headers at the top.
    Finds the row containing 'Ticker' to use as the true header.
    """
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_REALIZED_GL)
    
    all_values = ws.get_all_values()
    if not all_values:
        return pd.DataFrame()
    
    # Find the header row (the one that starts with 'Ticker' and has many columns)
    header_row_idx = -1
    for i, row in enumerate(all_values):
        if row and row[0] == 'Ticker' and len(row) > 10:
            header_row_idx = i
            break
            
    if header_row_idx == -1:
        logger.warning("Could not find 'Ticker' header row in Realized_GL. Falling back to row 0.")
        header_row_idx = 0
        
    headers = all_values[header_row_idx]
    data = all_values[header_row_idx + 1:]
    
    # Deduplicate headers if necessary
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
    
    # Filter out redundant header rows if they repeat
    df = df[df[headers[0]] != headers[0]]
    
    # Drop entirely empty rows
    df = df.replace('', None).dropna(how='all').fillna('')
    
    # Numeric cleaning similar to read_gsheet_robust
    skip_cols = [
        'ticker', 'symbol', 'description', 'sector', 'industry', 
        'asset class', 'asset strategy', 'import date', 'closed date', 
        'opened date', 'acquisition date', 'date', 'import timestamp', 'fingerprint',
        'is cash', 'wash sale', 'is primary acct', 'account', 'term'
    ]
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in skip_cols or col_lower.startswith('unnamed_'):
            continue
            
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace('%', '', regex=False).str.replace(',', '', regex=False).str.strip()
            df[col] = df[col].replace('', '0')
            # Handle parentheses for negative numbers
            mask = df[col].str.startswith('(') & df[col].str.endswith(')')
            df.loc[mask, col] = '-' + df.loc[mask, col].str[1:-1]
            
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
    return df

def compute_tax_control_data() -> Dict[str, Any]:
    """
    Reads Realized_GL, filters for current year, and computes all tax KPIs.
    Returns a dict of values and a DataFrame of tax-relevant lots.
    """
    df_gl = get_realized_gl_robust()
    if df_gl.empty:
        logger.warning("Realized_GL is empty. No tax data to compute.")
        return {}

    # Filter to taxable accounts only — 401(k) and IRA/contributory gains are
    # tax-deferred; including them in a cap-gains estimate would be wrong.
    if 'Is Primary Acct' in df_gl.columns:
        before = len(df_gl)
        df_gl = df_gl[df_gl['Is Primary Acct'].astype(str).str.upper() == 'TRUE']
        excluded = before - len(df_gl)
        if excluded:
            logger.info("compute_tax_control: excluded %d lots from protected accounts (401k/IRA)", excluded)
    else:
        logger.warning("compute_tax_control: 'Is Primary Acct' column missing — all accounts included. Re-import G/L CSV to fix.")

    # 1. Filter to current calendar year based on 'Closed Date'
    current_year = datetime.now().year
    
    # Ensure Closed Date is datetime
    df_gl['Closed Date'] = pd.to_datetime(df_gl['Closed Date'], format='%Y-%m-%d', errors='coerce')
    df_year = df_gl[df_gl['Closed Date'].dt.year == current_year].copy()
    
    if df_year.empty:
        logger.warning(f"No realized lots found for year {current_year}.")
        # We continue with empty metrics rather than failing
        
    # 2. Get rates
    rate_st, rate_lt, _, _ = get_tax_rates()

    # 3. Compute metrics
    # Note: read_gsheet_robust already handled numeric conversion and $/% removal
    
    st_mask = df_year['Term'].astype(str).str.lower().str.contains('short')
    lt_mask = df_year['Term'].astype(str).str.lower().str.contains('long')
    
    st_gl = df_year.loc[st_mask, 'ST Gain Loss']
    lt_gl = df_year.loc[lt_mask, 'LT Gain Loss']
    
    ytd_st_gains = st_gl[st_gl > 0].sum()
    ytd_st_losses = abs(st_gl[st_gl < 0].sum())
    ytd_lt_gains = lt_gl[lt_gl > 0].sum()
    ytd_lt_losses = abs(lt_gl[lt_gl < 0].sum())
    
    ytd_net_st = ytd_st_gains - ytd_st_losses
    ytd_net_lt = ytd_lt_gains - ytd_lt_losses
    
    # Wash sale logic
    # RealizedGL has Wash Sale (boolean-ish) and Disallowed Loss
    # We treat any row where Wash Sale is True or has disallowed loss > 0
    wash_mask = (df_year['Wash Sale'].astype(str).str.upper() == 'TRUE') | (df_year['Disallowed Loss'] > 0)
    ytd_disallowed_wash = df_year.loc[wash_mask, 'Disallowed Loss'].sum()
    wash_sale_count = wash_mask.sum()
    
    # Net Taxable (conservative: positive nets only, per spec)
    net_taxable_est = max(ytd_net_st, 0) + max(ytd_net_lt, 0)
    est_fed_tax = (max(ytd_net_st, 0) * rate_st) + (max(ytd_net_lt, 0) * rate_lt)
    
    # Offset Capacity: total taxable gains currently showing
    tax_offset_capacity = net_taxable_est if net_taxable_est > 0 else 0
    
    # Last updated: most recent Import Date in the filtered rows
    last_updated = "N/A"
    if not df_year.empty:
        try:
            last_updated = df_year['Import Date'].max()
        except:
            last_updated = datetime.now().strftime("%Y-%m-%d")

    metrics = {
        "Net ST (YTD)": ytd_net_st,
        "Net LT (YTD)": ytd_net_lt,
        "Disallowed Wash Loss (YTD)": ytd_disallowed_wash,
        "Est. Fed Cap Gains Tax": est_fed_tax,
        "Tax Offset Capacity": tax_offset_capacity,
        "Wash Sale Count": int(wash_sale_count),
        "Last Updated": last_updated,
        "ST_Gains": ytd_st_gains,
        "ST_Losses": ytd_st_losses,
        "LT_Gains": ytd_lt_gains,
        "LT_Losses": ytd_lt_losses
    }

    # 4. Tax-relevant lots table
    # Columns: Closed Date | Ticker | Account | Term | Gain Loss | ST Gain Loss | LT Gain Loss | Wash Sale | Disallowed Loss
    table_cols = [
        "Closed Date", "Ticker", "Account", "Term", "Gain Loss $", 
        "ST Gain Loss", "LT Gain Loss", "Wash Sale", "Disallowed Loss"
    ]
    
    # Sort: wash sales at top, then by abs(Gain Loss) descending
    df_year['abs_gl'] = df_year['Gain Loss $'].abs()
    df_year['is_wash'] = wash_mask
    
    df_table = df_year.sort_values(by=['is_wash', 'abs_gl'], ascending=[False, False])
    
    # Map 'Gain Loss $' to 'Gain Loss' as requested in config.TAX_CONTROL_LOTS_COLUMNS
    df_table = df_table.rename(columns={'Gain Loss $': 'Gain Loss'})
    
    # Ensure all columns exist
    for col in config.TAX_CONTROL_LOTS_COLUMNS:
        if col not in df_table.columns:
            df_table[col] = ""
            
    return {
        "metrics": metrics,
        "lots_df": df_table[config.TAX_CONTROL_LOTS_COLUMNS]
    }

def refresh_tax_control_sheet(live: bool = False) -> Dict[str, Any]:
    """
    Main entry point for refreshing the Tax_Control tab.
    """
    data = compute_tax_control_data()
    if not data:
        return {}
    
    metrics = data['metrics']
    lots_df = data['lots_df']
    
    if not live:
        return data

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_TAX_CONTROL)
    
    # Prepare rows
    # Row 1: Header
    row1 = [["TAX CONTROL — YTD Realized Tax Posture"]]
    
    # Row 2-3: KPI Strip
    row2 = [config.TAX_CONTROL_KPI_LABELS]
    row3 = [[metrics.get(label, 0) for label in config.TAX_CONTROL_KPI_LABELS]]
    
    # Row 4: Disclaimer
    row4 = [["Planning tool — not tax advice. Estimates based on configured rates and realized data only."]]
    
    # Row 5: Bridge Headers
    row5 = [["Short-Term Bridge (gains vs losses)", "", "Long-Term Bridge (gains vs losses)", ""]]
    
    # Row 6: Bridge Values
    row6 = [[
        f"Gains: {metrics['ST_Gains']:,.0f}", 
        f"Losses: {metrics['ST_Losses']:,.0f}",
        f"Gains: {metrics['LT_Gains']:,.0f}", 
        f"Losses: {metrics['LT_Losses']:,.0f}"
    ]]
    
    # Row 7: Spacer
    row7 = [[""]]
    
    # Row 8: Section Header
    row8 = [["Tax-Relevant Realized Lots (YTD) — wash sales pinned on top"]]
    
    # Row 9: Table Headers
    row9 = [config.TAX_CONTROL_LOTS_COLUMNS]
    
    # Row 10+: Data rows
    # Convert datetime to string for sheet
    lots_df_out = lots_df.copy()
    if not lots_df_out.empty:
        lots_df_out['Closed Date'] = pd.to_datetime(
            lots_df_out['Closed Date'], errors='coerce'
        ).dt.strftime('%Y-%m-%d').fillna('')
    
    table_data = lots_df_out.values.tolist()

    all_values = (
        row1 +
        row2 +
        row3 +
        row4 +
        [[""]] +
        row5 +
        row6 +
        row7 +
        row8 +
        row9 +
        table_data
    )

    # Scrub numpy scalars — gspread serializes to JSON and numpy int64/float64 are not
    # JSON-serializable. Convert everything to plain Python types before the write.
    import numpy as np

    def _to_python(v):
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v) if not np.isnan(v) else ""
        if isinstance(v, np.bool_):
            return bool(v)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        return v

    all_values = [[_to_python(cell) for cell in row] for row in all_values]

    # Batch update
    safe_execute(ws.clear)
    safe_execute(ws.update, range_name="A1", values=all_values, value_input_option="USER_ENTERED")
    
    logger.info(f"LIVE — refreshed {config.TAB_TAX_CONTROL} with {len(table_data)} lots.")
    return data

if __name__ == "__main__":
    # Test run
    logging.basicConfig(level=logging.INFO)
    res = compute_tax_control_data()
    if res:
        print("Metrics:", res['metrics'])
        print("First 5 lots:\n", res['lots_df'].head())
