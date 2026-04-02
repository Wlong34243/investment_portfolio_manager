import gspread
import pandas as pd
import numpy as np
import time
from datetime import datetime
import config

# --- Position Pipeline Functions ---

def sanitize_dataframe_for_sheets(df: pd.DataFrame, columns: list[str], col_map: dict = None) -> list[list]:
    """
    Universal sanitizer for Google Sheets:
    1. Apply col_map rename if provided.
    2. Ensure all columns from the 'columns' list are present.
    3. Reorder to match 'columns' list exactly.
    4. Fill NA with empty string.
    5. Cast every value to native Python types (no numpy, no NaT).
    """
    df = df.copy()
    
    # 1. Rename if map provided
    if col_map:
        df = df.rename(columns=col_map)
        
    # 2. Ensure all required columns are present
    for col in columns:
        if col not in df.columns:
            df[col] = ""

    # 3. Reorder and Select
    df_ordered = df[columns].copy()
    
    # 4. Fill NA
    df_clean = df_ordered.fillna("")
    
    # 5. Cast to native types
    data = []
    for _, row in df_clean.iterrows():
        clean_row = []
        for val in row.values:
            if isinstance(val, (np.float64, np.float32)):
                clean_row.append(float(val))
            elif isinstance(val, (np.int64, np.int32)):
                clean_row.append(int(val))
            elif isinstance(val, (np.bool_, bool)):
                clean_row.append(bool(val))
            elif pd.isna(val) or val is None or str(val).lower() == 'nat':
                clean_row.append("")
            else:
                clean_row.append(val)
        data.append(clean_row)
    
    return data

def normalize_positions(df: pd.DataFrame, import_date: str) -> pd.DataFrame:
    """
    Add import_date column.
    Calculate weight = market_value / total_portfolio_value * 100.
    Build fingerprint = "{import_date}|{ticker}|{quantity}|{market_value}".
    Sort by market_value descending.
    """
    df = df.copy()
    
    # Mapping our internal snake_case to Sheet's Camel Case with spaces
    # NOTE: col_map is used inside sanitize_dataframe_for_sheets later
    
    # Add import_date if not present
    df['import_date'] = import_date
    
    # Ensure numeric types for calculation
    for col in ['market_value', 'quantity', 'cost_basis']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    total_value = df['market_value'].sum()
    if total_value > 0:
        df['weight'] = (df['market_value'] / total_value * 100)
    else:
        df['weight'] = 0.0
        
    # Build fingerprint = "{import_date}|{ticker}|{quantity}|{market_value}"
    df['fingerprint'] = df.apply(
        lambda x: f"{import_date}|{x['ticker']}|{x.get('quantity',0)}|{x.get('market_value',0)}", 
        axis=1
    )
    
    # Sort by market_value descending before mapping/renaming
    df = df.sort_values(by='market_value', ascending=False)
    
    return df

def write_holdings_current(ws, data: list[list]) -> None:
    """
    Update Holdings_Current worksheet atomically.
    1. Prepare full data block (headers + data).
    2. Clear worksheet.
    3. Update in a single API call to ensure integrity.
    """
    if not data:
        print("Holdings_Current: No data to write.")
        return

    # Prepare headers and data for a single update
    full_data = [config.POSITION_COLUMNS] + data
    
    # Clear the entire sheet (up to a reasonable limit) to ensure no stale data remains
    num_cols = len(config.POSITION_COLUMNS)
    col_letter = chr(ord('A') + num_cols - 1)
    ws.batch_clear([f"A1:{col_letter}2000"])
    
    # Write everything in one go starting at A1
    ws.update(range_name="A1", values=full_data, value_input_option='USER_ENTERED')
        
    time.sleep(1.0)
    print(f"Holdings_Current: Updated {len(data)} rows (plus headers).")

def append_holdings_history(ws, data: list[list], existing_fps: set) -> int:
    """
    Filter to rows whose fingerprint not in existing_fps.
    Append new rows in single batch call: ws.append_rows(new_rows).
    time.sleep(1.0) after. Return count of rows appended.
    """
    # Fingerprint is the last column in POSITION_COLUMNS
    fp_idx = config.POSITION_COLUMNS.index('Fingerprint')
    
    new_rows = [row for row in data if str(row[fp_idx]) not in existing_fps]
    
    if new_rows:
        ws.append_rows(new_rows, value_input_option='USER_ENTERED')
        time.sleep(1.0)
        print(f"Holdings_History: Appended {len(new_rows)} rows.")
        return len(new_rows)
    
    print("Holdings_History: No new rows to append.")
    return 0

def append_daily_snapshot(ws, df: pd.DataFrame, existing_fps: set) -> bool:
    """
    Build snapshot row: date, total_value, total_cost, unrealized_gl,
    cash_value, invested_value, position_count, blended_yield, import_ts.
    Check fingerprint (date|total_value) before inserting.
    Return True if inserted, False if duplicate.
    """
    import_date = df['Import Date'].iloc[0]
    total_value = df['Market Value'].sum()
    total_cost = df['Cost Basis'].sum()
    unrealized_gl = total_value - total_cost
    
    cash_df = df[df['Is Cash'] == True]
    cash_value = cash_df['Market Value'].sum()
    invested_value = total_value - cash_value
    position_count = len(df)
    
    # Blended yield
    total_income = df['Est Annual Income'].sum() if 'Est Annual Income' in df.columns else 0.0
    blended_yield = (total_income / total_value * 100) if total_value > 0 else 0.0
    
    # Build fingerprint = f"{import_date}|{total_value}"
    fp = f"{import_date}|{total_value}"
    
    if fp in existing_fps:
        print(f"Daily_Snapshots: Duplicate found for {import_date}. Skipping.")
        return False
        
    snapshot_row = [
        import_date,
        float(total_value),
        float(total_cost),
        float(unrealized_gl),
        float(cash_value),
        float(invested_value),
        int(position_count),
        float(blended_yield),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        fp
    ]
    
    # Cast to native python types
    snapshot_row = [float(x) if isinstance(x, (np.float64, np.float32)) else x for x in snapshot_row]
    snapshot_row = [int(x) if isinstance(x, (np.int64, np.int32)) else x for x in snapshot_row]

    ws.append_rows([snapshot_row], value_input_option='USER_ENTERED')
    time.sleep(1.0)
    print(f"Daily_Snapshots: Appended snapshot for {import_date}.")
    return True

def calculate_income_metrics(df: pd.DataFrame) -> dict:
    """
    - projected_annual_income = sum(row.Est_Annual_Income for all rows)
    - blended_yield_pct = total_income / total_portfolio_value * 100
    - top_generators = df sorted by Est_Annual_Income desc, top 5 rows
    """
    total_value = df['Market Value'].sum()
    projected_annual_income = df['Est Annual Income'].sum()
    blended_yield_pct = (projected_annual_income / total_value * 100) if total_value > 0 else 0.0
    
    cash_df = df[df['Is Cash'] == True]
    cash_contribution = cash_df['Est Annual Income'].sum()
    
    top_generators = df.nlargest(5, 'Est Annual Income')
    
    return {
        "projected_annual_income": float(projected_annual_income),
        "blended_yield_pct": float(blended_yield_pct),
        "cash_contribution": float(cash_contribution),
        "top_generators": top_generators,
        "total_value": float(total_value)
    }

def append_income_snapshot(ws, metrics: dict) -> bool:
    """
    - Builds Income_Tracking row from calculate_income_metrics() result
    - Columns: Date | Projected Annual Income | Blended Yield % |
              Top Generator Ticker | Top Generator Income |
              Cash Yield Contribution | Fingerprint
    """
    import_date = datetime.now().strftime("%Y-%m-%d")
    
    top_ticker = metrics["top_generators"]['Ticker'].iloc[0] if not metrics["top_generators"].empty else "N/A"
    top_income = metrics["top_generators"]['Est Annual Income'].iloc[0] if not metrics["top_generators"].empty else 0.0
    
    fp = f"{import_date}|{metrics['projected_annual_income']:.2f}|{metrics['blended_yield_pct']:.2f}"
    
    # Check for existing
    existing_data = ws.get_all_records()
    existing_fps = {str(r.get('Fingerprint')) for r in existing_data if r.get('Fingerprint')}
    
    if fp in existing_fps:
        print("Income_Tracking: Duplicate found. Skipping.")
        return False
        
    row = [
        import_date,
        metrics["projected_annual_income"],
        metrics["blended_yield_pct"],
        top_ticker,
        top_income,
        metrics["cash_contribution"],
        fp
    ]
    
    ws.append_rows([row], value_input_option='USER_ENTERED')
    time.sleep(1.0)
    print(f"Income_Tracking: Appended snapshot for {import_date}.")
    return True

def write_risk_snapshot(ws, risk_metrics: dict) -> bool:
    """
    - Builds Risk_Metrics row
    - Columns: Date | Portfolio Beta | Top Position Conc % | Top Position Ticker |
              Top Sector Conc % | Top Sector | Estimated VaR 95% | Stress -10% Impact | Fingerprint
    """
    import_date = datetime.now().strftime("%Y-%m-%d")
    
    fp = f"{import_date}|{risk_metrics['portfolio_beta']:.4f}|{risk_metrics['top_pos_pct']:.2f}"
    
    # Check for existing
    existing_data = ws.get_all_records()
    existing_fps = {str(r.get('Fingerprint')) for r in existing_data if r.get('Fingerprint')}
    
    if fp in existing_fps:
        print("Risk_Metrics: Duplicate found. Skipping.")
        return False
        
    row = [
        import_date,
        risk_metrics["portfolio_beta"],
        risk_metrics["top_pos_pct"],
        risk_metrics["top_pos_ticker"],
        risk_metrics["top_sector_pct"],
        risk_metrics["top_sector_name"],
        risk_metrics.get("var_95", 0.0),
        risk_metrics.get("stress_impact", 0.0),
        fp
    ]
    
    ws.append_rows([row], value_input_option='USER_ENTERED')
    time.sleep(1.0)
    print(f"Risk_Metrics: Appended snapshot for {import_date}.")
    return True

def sanitize_gl_for_sheets(df: pd.DataFrame) -> list[list]:
    """
    Ensure all columns from config.GL_COLUMNS are present.
    Return list of lists with native Python types.
    """
    df = df.copy()
    
    # Mapping our internal snake_case to Sheet's headers
    col_map = {
        'ticker': 'Ticker',
        'description': 'Description',
        'closed_date': 'Closed Date',
        'opened_date': 'Opened Date',
        'holding_days': 'Holding Days',
        'quantity': 'Quantity',
        'proceeds_per_share': 'Proceeds Per Share',
        'cost_per_share': 'Cost Per Share',
        'proceeds': 'Proceeds',
        'cost_basis': 'Cost Basis',
        'unadjusted_cost': 'Unadjusted Cost',
        'gain_loss_dollars': 'Gain Loss $',
        'gain_loss_pct': 'Gain Loss %',
        'lt_gain_loss': 'LT Gain Loss',
        'st_gain_loss': 'ST Gain Loss',
        'term': 'Term',
        'wash_sale': 'Wash Sale',
        'disallowed_loss': 'Disallowed Loss',
        'account': 'Account',
        'is_primary_acct': 'Is Primary Acct',
        'import_date': 'Import Date',
        'fingerprint': 'Fingerprint',
    }
    
    df = df.rename(columns=col_map)
    
    # Ensure all config.GL_COLUMNS are present
    for col in config.GL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Reorder columns to match GL_COLUMNS exactly
    df_ordered = df[config.GL_COLUMNS].copy()
    
    # Fill NA with empty string
    df_clean = df_ordered.fillna("")
    
    # Cast every value to native Python types
    data = []
    for _, row in df_clean.iterrows():
        clean_row = []
        for val in row.values:
            if isinstance(val, (np.float64, np.float32)):
                clean_row.append(float(val))
            elif isinstance(val, (np.int64, np.int32)):
                clean_row.append(int(val))
            elif isinstance(val, (np.bool_, bool)):
                clean_row.append(bool(val))
            elif pd.isna(val) or val is None:
                clean_row.append("")
            else:
                clean_row.append(str(val))
        data.append(clean_row)
    
    return data

def ingest_realized_gl(uploaded_file, dry_run=True):
    """
    Parse Schwab G/L CSV, dedup against Realized_GL tab, append new rows.
    Returns: {"parsed": int, "new": int, "skipped": int, "errors": list}
    """
    from utils.gl_parser import parse_realized_gl
    results = {"parsed": 0, "new": 0, "skipped": 0, "errors": []}

    try:
        # 1. Parse CSV
        df = parse_realized_gl(uploaded_file)
        results["parsed"] = len(df)
        
        if df.empty:
            return results
            
        # Add import date
        df["import_date"] = datetime.now().strftime("%Y-%m-%d")
        
        if dry_run:
            print(f"DRY RUN: WOULD write {len(df)} rows to Realized_GL")
            results["new"] = len(df)
            return results

        # 2. Get existing fingerprints from Sheet
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_REALIZED_GL)
        
        existing_data = ws.get_all_records()
        existing_fps = {str(r.get('Fingerprint')) for r in existing_data if r.get('Fingerprint')}
        
        # 3. Filter new rows
        new_df = df[~df["fingerprint"].isin(existing_fps)]
        results["skipped"] = len(df) - len(new_df)
        results["new"] = len(new_df)
        
        if not new_df.empty:
            # Sort by closed_date ascending for the ledger
            new_df = new_df.sort_values(by="closed_date")
            
            # Mapping our internal snake_case to Sheet's headers
            col_map = {
                'ticker': 'Ticker',
                'description': 'Description',
                'closed_date': 'Closed Date',
                'opened_date': 'Opened Date',
                'holding_days': 'Holding Days',
                'quantity': 'Quantity',
                'proceeds_per_share': 'Proceeds Per Share',
                'cost_per_share': 'Cost Per Share',
                'proceeds': 'Proceeds',
                'cost_basis': 'Cost Basis',
                'unadjusted_cost': 'Unadjusted Cost',
                'gain_loss_dollars': 'Gain Loss $',
                'gain_loss_pct': 'Gain Loss %',
                'lt_gain_loss': 'LT Gain Loss',
                'st_gain_loss': 'ST Gain Loss',
                'term': 'Term',
                'wash_sale': 'Wash Sale',
                'disallowed_loss': 'Disallowed Loss',
                'account': 'Account',
                'is_primary_acct': 'Is Primary Acct',
                'import_date': 'Import Date',
                'fingerprint': 'Fingerprint',
            }
            
            data_to_write = sanitize_dataframe_for_sheets(new_df, config.GL_COLUMNS, col_map)
            
            # Batch append
            ws.append_rows(data_to_write, value_input_option='USER_ENTERED')
            time.sleep(1.0)
            print(f"Realized_GL: Appended {len(data_to_write)} new lots.")
            
    except Exception as e:
        results["errors"].append(str(e))
        print(f"Error ingesting Realized G/L: {e}")
        
    return results

def ingest_transactions(uploaded_file, dry_run=True):
    """Parse transaction CSV, dedup, and append."""
    from utils.gl_parser import parse_transaction_history
    results = {"parsed": 0, "new": 0, "skipped": 0, "errors": []}

    try:
        df = parse_transaction_history(uploaded_file)
        results["parsed"] = len(df)
        
        if df.empty:
            return results
            
        df["import_date"] = datetime.now().strftime("%Y-%m-%d")
        
        if dry_run:
            results["new"] = len(df)
            return results

        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_TRANSACTIONS)
        
        existing_data = ws.get_all_records()
        existing_fps = {str(r.get('Fingerprint')) for r in existing_data if r.get('Fingerprint')}
        
        new_df = df[~df["Fingerprint"].isin(existing_fps)]
        results["skipped"] = len(df) - len(new_df)
        results["new"] = len(new_df)
        
        if not new_df.empty:
            new_df = new_df.sort_values(by="Date")
            
            # Map Schwab Transaction headers to our SCHEMA headers
            col_map = {
                'Date': 'Trade Date',
                'Symbol': 'Ticker',
                'Fees & Comm': 'Fees',
                'Amount': 'Net Amount',
                'import_date': 'Import Date',
                'Fingerprint': 'Fingerprint'
            }
            # Note: Amount in Schwab CSV is already the net amount in most cases, 
            # but we can refine this later if needed.
            
            data_to_write = sanitize_dataframe_for_sheets(new_df, config.TRANSACTION_COLUMNS, col_map)
            ws.append_rows(data_to_write, value_input_option='USER_ENTERED')
            time.sleep(1.0)
            
    except Exception as e:
        results["errors"].append(str(e))
        
    return results

def write_to_sheets(df: pd.DataFrame, cash_amount: float, dry_run: bool = True) -> dict:
    """
    Orchestrate: Holdings_Current -> Holdings_History -> Daily_Snapshots -> Income_Tracking.
    """
    results = {"holdings_written": 0, "history_appended": 0, "snapshot": False, "income_snapshot": False}
    
    # Prepare data using centralized mapping
    data_list = sanitize_dataframe_for_sheets(df, config.POSITION_COLUMNS, config.POSITION_COL_MAP)
    income_metrics = calculate_income_metrics(df)
    
    if dry_run:
        print(f"DRY RUN: WOULD write {len(data_list)} rows to Holdings_Current")
        results["holdings_written"] = len(data_list)
        results["history_appended"] = len(data_list)
        results["snapshot"] = True
        results["income_snapshot"] = True
        return results

    # Live execution
    from utils.sheet_readers import get_gspread_client
    client = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 1. Holdings_Current
            ws_current = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)
            write_holdings_current(ws_current, data_list)
            results["holdings_written"] = len(data_list)
            
            # 2. Holdings_History
            ws_history = spreadsheet.worksheet(config.TAB_HOLDINGS_HISTORY)
            existing_data_history = ws_history.get_all_records()
            existing_fps_history = {str(r.get('Fingerprint')) for r in existing_data_history if r.get('Fingerprint')}
            appended_count = append_holdings_history(ws_history, data_list, existing_fps_history)
            results["history_appended"] = appended_count
            
            # 3. Daily_Snapshots
            ws_snapshots = spreadsheet.worksheet(config.TAB_DAILY_SNAPSHOTS)
            existing_data_snapshots = ws_snapshots.get_all_records()
            existing_fps_snapshots = {str(r.get('Fingerprint')) for r in existing_data_snapshots if r.get('Fingerprint')}
            snapshot_added = append_daily_snapshot(ws_snapshots, df, existing_fps_snapshots)
            results["snapshot"] = snapshot_added
            
            # 4. Income_Tracking
            ws_income = spreadsheet.worksheet(config.TAB_INCOME_TRACKING)
            income_snapshot_added = append_income_snapshot(ws_income, income_metrics)
            results["income_snapshot"] = income_snapshot_added
            
            break
            
        except gspread.exceptions.APIError as e:
            if attempt < max_retries - 1:
                print(f"API Error, retrying in 60s... {e}")
                time.sleep(60)
            else:
                raise e
    
    return results
