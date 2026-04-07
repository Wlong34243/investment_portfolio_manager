import gspread
import pandas as pd
import numpy as np
import time
from datetime import datetime
import config

# --- Position Pipeline Functions ---

def write_pipeline_log(level: str, source: str, message: str, details: str = "", dry_run: bool = False):
    """Writes a log entry to the Logs tab in the Portfolio Sheet."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_row = [timestamp, level, source, message, details]
    
    print(f"[{timestamp}] {level} | {source} | {message}")
    
    if dry_run:
        return

    try:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_LOGS)
        ws.append_row(log_row, value_input_option='USER_ENTERED')
    except Exception as e:
        print(f"Failed to write to Logs tab: {e}")

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
    Calculate unrealized_gl and pct if missing or zero.
    Build fingerprint = "{import_date}|{ticker}|{quantity}".
    Sort by market_value descending.
    """
    df = df.copy()
    
    # Add import_date if not present
    df['import_date'] = import_date
    
    # Ensure numeric types for calculation
    calc_cols = ['market_value', 'quantity', 'cost_basis', 'unrealized_gl', 'unrealized_gl_pct']
    for col in calc_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        else:
            df[col] = 0.0

    # Calculate weights
    total_value = df['market_value'].sum()
    if total_value > 0:
        df['weight'] = (df['market_value'] / total_value * 100)
    else:
        df['weight'] = 0.0
        
    # Calculate Unrealized G/L if zero but market_value/cost_basis exist
    # Only calculate for invested positions (where cost_basis > 0)
    mask = (df['unrealized_gl'] == 0) & (df['cost_basis'] > 0)
    df.loc[mask, 'unrealized_gl'] = df.loc[mask, 'market_value'] - df.loc[mask, 'cost_basis']
    
    # Calculate Unrealized G/L %
    mask_pct = (df['unrealized_gl_pct'] == 0) & (df['cost_basis'] > 0)
    df.loc[mask_pct, 'unrealized_gl_pct'] = (df.loc[mask_pct, 'unrealized_gl'] / df.loc[mask_pct, 'cost_basis']) * 100

    # Build fingerprint = "{import_date}|{ticker}|{quantity}|{market_value}"
    df['fingerprint'] = df.apply(
        lambda x: f"{import_date}|{x['ticker']}|{x.get('quantity',0)}|{round(x.get('market_value',0), 2)}", 
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

def append_holdings_history(ws, data: list[list], existing_fps: set = None) -> int:
    """
    Filter to rows whose fingerprint not in existing_fps.
    Uses col_values for efficient duplicate check if existing_fps is None.
    """
    # Fingerprint is the last column in POSITION_COLUMNS
    fp_idx = config.POSITION_COLUMNS.index('Fingerprint')
    
    # Optimized Check: Read only the Fingerprint column
    if existing_fps is None:
        fp_col_idx = len(config.POSITION_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])

    new_rows = [row for row in data if str(row[fp_idx]) not in existing_fps]
    
    if new_rows:
        ws.append_rows(new_rows, value_input_option='USER_ENTERED')
        time.sleep(1.0)
        print(f"Holdings_History: Appended {len(new_rows)} rows.")
        return len(new_rows)
    
    print("Holdings_History: No new rows to append.")
    return 0

def append_daily_snapshot(ws, df: pd.DataFrame, existing_fps: set = None) -> bool:
    """
    Build snapshot row and check fingerprint (date|pos_count|total_value).
    Uses col_values for efficient duplicate check.
    """
    from utils.column_guard import ensure_display_columns
    df = ensure_display_columns(df)

    # Ensure we have a string date
    import_date = str(df['Import Date'].iloc[0])
    
    total_value = float(df['Market Value'].sum())
    total_cost = float(df['Cost Basis'].sum())
    unrealized_gl = total_value - total_cost
    
    cash_mask = (df['Asset Class'].astype(str).str.lower() == 'cash') | df['Ticker'].isin(config.CASH_TICKERS)
    cash_df = df[cash_mask]
    cash_value = float(cash_df['Market Value'].sum())
    invested_value = total_value - cash_value
    position_count = int(len(df))
    
    # Blended yield
    total_income = float(df['Est Annual Income'].sum() if 'Est Annual Income' in df.columns else 0.0)
    blended_yield = (total_income / total_value * 100) if total_value > 0 else 0.0
    
    # Build fingerprint = f"{import_date}|{position_count}|{round(total_value, 2)}"
    fp = f"{import_date}|{position_count}|{round(total_value, 2)}"
    
    # Optimized Check: Read only the Fingerprint column (last column)
    if existing_fps is None:
        try:
            fp_col_idx = len(config.SNAPSHOT_COLUMNS)
            existing_fps = set(ws.col_values(fp_col_idx)[1:]) # Skip header
        except:
            existing_fps = set()

    if fp in existing_fps:
        print(f"Daily_Snapshots: Duplicate found for {import_date}. Skipping.")
        return False
        
    snapshot_row = [
        import_date,
        total_value,
        total_cost,
        unrealized_gl,
        cash_value,
        invested_value,
        position_count,
        blended_yield,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        fp
    ]
    
    # Final safety cast to ensure no numpy types reach gspread
    clean_row = []
    for x in snapshot_row:
        if isinstance(x, (np.integer, np.floating)):
            clean_row.append(x.item())
        else:
            clean_row.append(x)

    ws.append_rows([clean_row], value_input_option='USER_ENTERED')
    time.sleep(1.0)
    print(f"Daily_Snapshots: Appended snapshot for {import_date}.")
    return True

def calculate_income_metrics(df: pd.DataFrame) -> dict:
    """
    - projected_annual_income = sum(row.Est_Annual_Income for all rows)
    - blended_yield_pct = total_income / total_portfolio_value * 100
    """
    from utils.column_guard import ensure_display_columns
    df = ensure_display_columns(df)

    # Ensure required columns exist for calculation
    for col in ['Market Value', 'Est Annual Income', 'Is Cash', 'Ticker']:
        if col not in df.columns:
            if col == 'Ticker': df[col] = 'Unknown'
            elif col == 'Is Cash': df[col] = False
            else: df[col] = 0.0

    total_value = float(df['Market Value'].sum())
    projected_annual_income = float(df['Est Annual Income'].sum())
    blended_yield_pct = (projected_annual_income / total_value * 100) if total_value > 0 else 0.0
    
    cash_mask = (df['Asset Class'].astype(str).str.lower() == 'cash') | df['Ticker'].isin(config.CASH_TICKERS)
    cash_df = df[cash_mask]
    cash_contribution = float(cash_df['Est Annual Income'].sum())
    
    # Use 'Ticker' safely
    top_generators = df.nlargest(5, 'Est Annual Income')[['Ticker', 'Est Annual Income']]
    
    return {
        "projected_annual_income": projected_annual_income,
        "blended_yield_pct": blended_yield_pct,
        "cash_contribution": cash_contribution,
        "top_generators": top_generators,
        "total_value": total_value,
        "position_count": int(len(df))
    }

def append_income_snapshot(ws, metrics: dict, existing_fps: set = None) -> bool:
    """
    - Builds Income_Tracking row and check fingerprint (date|pos_count|income).
    - Uses col_values for efficient duplicate check.
    """
    import_date = datetime.now().strftime("%Y-%m-%d")
    position_count = metrics.get("position_count", 0)
    
    top_ticker = metrics["top_generators"]['Ticker'].iloc[0] if not metrics["top_generators"].empty else "N/A"
    top_income = metrics["top_generators"]['Est Annual Income'].iloc[0] if not metrics["top_generators"].empty else 0.0
    
    # Build fingerprint = f"{import_date}|{position_count}|{metrics['projected_annual_income']:.2f}"
    fp = f"{import_date}|{position_count}|{metrics['projected_annual_income']:.2f}"
    
    # Optimized Check: Read only the Fingerprint column (last column)
    if existing_fps is None:
        fp_col_idx = len(config.INCOME_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])

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

def write_risk_snapshot(ws, risk_metrics: dict, existing_fps: set = None) -> bool:
    """
    - Builds Risk_Metrics row and check fingerprint (date|beta|top_pos).
    - Uses col_values for efficient duplicate check.
    """
    import_date = datetime.now().strftime("%Y-%m-%d")
    
    fp = f"{import_date}|{risk_metrics['portfolio_beta']:.4f}|{risk_metrics['top_pos_pct']:.2f}"
    
    # Optimized Check: Read only the Fingerprint column (last column)
    if existing_fps is None:
        fp_col_idx = len(config.RISK_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])

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

def ingest_realized_gl(uploaded_file, dry_run=True):
    """
    Parse Schwab G/L CSV, dedup against Realized_GL tab, append new rows.
    """
    from utils.gl_parser import parse_realized_gl
    results = {"parsed": 0, "new": 0, "skipped": 0, "errors": []}
    source = "Realized_GL_Ingestion"

    try:
        # 1. Parse CSV
        df = parse_realized_gl(uploaded_file)
        results["parsed"] = len(df)
        
        if df.empty:
            write_pipeline_log("INFO", source, "Parsed file is empty.", dry_run=dry_run)
            return results
            
        # Add import date
        df["import_date"] = datetime.now().strftime("%Y-%m-%d")
        
        if dry_run:
            write_pipeline_log("INFO", source, f"DRY RUN: Parsed {len(df)} rows.", dry_run=dry_run)
            results["new"] = len(df)
            return results

        # 2. Get existing fingerprints from Sheet (Optimized: read just FP column)
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_REALIZED_GL)
        
        fp_col_idx = len(config.GL_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])
        
        # 3. Filter new rows
        new_df = df[~df["fingerprint"].isin(existing_fps)]
        results["skipped"] = len(df) - len(new_df)
        results["new"] = len(new_df)
        
        if not new_df.empty:
            # Sort by closed_date ascending for the ledger
            new_df = new_df.sort_values(by="closed_date")
            
            data_to_write = sanitize_dataframe_for_sheets(new_df, config.GL_COLUMNS, config.GL_COL_MAP)
            
            # Batch append
            ws.append_rows(data_to_write, value_input_option='USER_ENTERED')
            time.sleep(1.0)
            write_pipeline_log("SUCCESS", source, f"Appended {len(data_to_write)} new lots.", f"Total parsed: {len(df)}, Skipped: {results['skipped']}", dry_run=dry_run)
        else:
            write_pipeline_log("INFO", source, "No new unique lots found.", f"Total parsed: {len(df)}", dry_run=dry_run)
            
    except Exception as e:
        results["errors"].append(str(e))
        write_pipeline_log("ERROR", source, f"Ingestion failed: {e}", dry_run=dry_run)
        
    return results

def ingest_transactions(uploaded_file, dry_run=True):
    """Parse transaction CSV, dedup, and append."""
    from utils.gl_parser import parse_transaction_history
    results = {"parsed": 0, "new": 0, "skipped": 0, "errors": []}
    source = "Transactions_Ingestion"

    try:
        df = parse_transaction_history(uploaded_file)
        results["parsed"] = len(df)
        
        if df.empty:
            write_pipeline_log("INFO", source, "Parsed file is empty.", dry_run=dry_run)
            return results
            
        df["import_date"] = datetime.now().strftime("%Y-%m-%d")
        
        if dry_run:
            write_pipeline_log("INFO", source, f"DRY RUN: Parsed {len(df)} rows.", dry_run=dry_run)
            results["new"] = len(df)
            return results

        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_TRANSACTIONS)
        
        fp_col_idx = len(config.TRANSACTION_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])
        
        # Note: gl_parser builds 'Fingerprint' with capital F
        new_df = df[~df["Fingerprint"].isin(existing_fps)]
        results["skipped"] = len(df) - len(new_df)
        results["new"] = len(new_df)
        
        if not new_df.empty:
            new_df = new_df.sort_values(by="Date")
            
            data_to_write = sanitize_dataframe_for_sheets(new_df, config.TRANSACTION_COLUMNS, config.TRANSACTION_COL_MAP)
            ws.append_rows(data_to_write, value_input_option='USER_ENTERED')
            time.sleep(1.0)
            write_pipeline_log("SUCCESS", source, f"Appended {len(data_to_write)} new transactions.", f"Total parsed: {len(df)}, Skipped: {results['skipped']}", dry_run=dry_run)
        else:
            write_pipeline_log("INFO", source, "No new unique transactions found.", f"Total parsed: {len(df)}", dry_run=dry_run)
            
    except Exception as e:
        results["errors"].append(str(e))
        write_pipeline_log("ERROR", source, f"Ingestion failed: {e}", dry_run=dry_run)
        
    return results

def append_decision_log(date_str: str, tickers: str, action: str,
                        context: str, rationale: str, tags: str) -> bool:
    """
    Append a decision journal entry to the Decision_Log tab.
    Returns True on success, False on failure.
    Respects config.DRY_RUN.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    fingerprint = f"{date_str}|{timestamp}|{action}|{tickers}"
    row = [
        str(date_str),
        f"{date_str} {timestamp}",
        str(tickers),
        str(action),
        str(context),
        str(rationale),
        str(tags),
        fingerprint,
    ]

    if config.DRY_RUN:
        write_pipeline_log("INFO", "Decision_Journal",
            f"DRY RUN: Would log decision for {tickers} ({action})",
            dry_run=True)
        return True

    try:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_DECISION_LOG)
        ws.append_rows([row], value_input_option='USER_ENTERED')
        write_pipeline_log("SUCCESS", "Decision_Journal",
            f"Logged decision: {action} {tickers}",
            f"Tags: {tags}")
        return True
    except Exception as e:
        write_pipeline_log("ERROR", "Decision_Journal",
            f"Failed to log decision: {e}")
        return False


def write_risk_metrics(res: dict, df: pd.DataFrame, dry_run: bool = False) -> bool:
    """
    Persists deep risk results to the Risk_Metrics tab.
    Calculates top concentration metrics from the dataframe.
    """
    import_date = datetime.now().strftime("%Y-%m-%d")
    total_val = df['Market Value'].sum()
    
    # Calculate concentration
    top_pos = df.nlargest(1, 'Market Value').iloc[0]
    top_pos_ticker = top_pos['Ticker']
    top_pos_pct = (top_pos['Market Value'] / total_val * 100) if total_val > 0 else 0.0
    
    sector_weights = df.groupby('Asset Class')['Market Value'].sum()
    top_sector_name = sector_weights.idxmax() if not sector_weights.empty else "N/A"
    top_sector_pct = (sector_weights.max() / total_val * 100) if total_val > 0 else 0.0
    
    # Stress -10% impact
    stress_10 = [s['impact'] for s in res['stress'] if '-10%' in s['scenario']]
    stress_impact = stress_10[0] if stress_10 else 0.0
    
    # Build metrics dict for write_risk_snapshot
    metrics = {
        "portfolio_beta": res['p_beta'],
        "top_pos_pct": top_pos_pct,
        "top_pos_ticker": top_pos_ticker,
        "top_sector_pct": top_sector_pct,
        "top_sector_name": top_sector_name,
        "var_95": 0.0, # Placeholder for VaR if added later
        "stress_impact": stress_impact
    }
    
    if dry_run:
        print(f"DRY RUN: Would write risk metrics for {import_date}")
        return True

    try:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_RISK_METRICS)
        return write_risk_snapshot(ws, metrics)
    except Exception as e:
        print(f"Failed to write risk metrics: {e}")
        return False

def write_to_sheets(df: pd.DataFrame, cash_amount: float, dry_run: bool = True) -> dict:
    """
    Orchestrate: Holdings_Current -> Holdings_History -> Daily_Snapshots -> Income_Tracking.
    """
    results = {"holdings_written": 0, "history_appended": 0, "snapshot": False, "income_snapshot": False}
    source = "Positions_Ingestion"
    
    # Prepare data using centralized mapping
    data_list = sanitize_dataframe_for_sheets(df, config.POSITION_COLUMNS, config.POSITION_COL_MAP)
    income_metrics = calculate_income_metrics(df)
    
    if dry_run:
        write_pipeline_log("INFO", source, f"DRY RUN: Prepared {len(data_list)} positions.", dry_run=dry_run)
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
            
            # 2. Holdings_History (Optimized check inside function)
            ws_history = spreadsheet.worksheet(config.TAB_HOLDINGS_HISTORY)
            appended_count = append_holdings_history(ws_history, data_list)
            results["history_appended"] = appended_count
            
            # 3. Daily_Snapshots (Optimized check inside function)
            ws_snapshots = spreadsheet.worksheet(config.TAB_DAILY_SNAPSHOTS)
            snapshot_added = append_daily_snapshot(ws_snapshots, df)
            results["snapshot"] = snapshot_added
            
            # 4. Income_Tracking (Optimized check inside function)
            ws_income = spreadsheet.worksheet(config.TAB_INCOME_TRACKING)
            income_snapshot_added = append_income_snapshot(ws_income, income_metrics)
            results["income_snapshot"] = income_snapshot_added
            
            write_pipeline_log("SUCCESS", source, f"Updated Holdings_Current ({len(data_list)} rows) and History ({appended_count} new).", dry_run=dry_run)
            break
            
        except gspread.exceptions.APIError as e:
            if attempt < max_retries - 1:
                write_pipeline_log("WARNING", source, f"API Error, retrying in 60s... {e}", dry_run=dry_run)
                time.sleep(60)
            else:
                write_pipeline_log("ERROR", source, f"Ingestion failed after {max_retries} attempts: {e}", dry_run=dry_run)
                raise e
    
    return results
