"""
pipeline.py — Migration compatibility shim.

Streamlit-coupled code has been archived to archive/streamlit_legacy/pipeline.py.
This module re-exposes the pure-Python and gspread functions still used by:
  - scripts/live_update.py        (normalize_positions, write_to_sheets, ingest_schwab_transactions)
  - tasks/sync_transactions.py    (sanitize_dataframe_for_sheets)
  - utils/risk.py                 (normalize_positions — lazy import inside calculate_beta)

New production pattern: use `python manager.py snapshot` instead of write_to_sheets.
The functions below will be decomposed into utils/sheet_writers.py in a future sprint.

REMOVED (Streamlit UploadedFile API — archived only):
  - ingest_realized_gl(uploaded_file, ...)
  - ingest_transactions(uploaded_file, ...)
"""

import gspread
import pandas as pd
import numpy as np
import time
from datetime import datetime
import config


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Data transformation (pure Python — no external I/O)
# ---------------------------------------------------------------------------

def sanitize_dataframe_for_sheets(df: pd.DataFrame, columns: list[str], col_map: dict = None, is_holdings: bool = False) -> list[list]:
    """
    Universal sanitizer for Google Sheets writes.
    1. Apply col_map rename if provided.
    2. Ensure all columns from the 'columns' list are present.
    3. Reorder to match 'columns' list exactly.
    4. Fill NA with empty string or "N/A" for specific fields.
    5. Cast every value to native Python types (no numpy, no NaT).
    6. If is_holdings=True, inject relative G/L formulas using {ROW} placeholder.
    """
    df = df.copy()

    if col_map:
        df = df.rename(columns=col_map)

    # Task 4: Explicitly fill N/A for specific missing data fields
    na_fill_cols = ['Acquisition Date', 'Macro Signal', 'Thesis Signal']
    for c in na_fill_cols:
        if c in df.columns:
            df[c] = df[c].replace(["", None, np.nan], "N/A")

    for col in columns:
        if col not in df.columns:
            df[col] = ""

    df_ordered = df[columns].copy()
    
    # Task 4: Handle ETF / Fixed Income display for valuation fields
    if is_holdings:
        # If it's an ETF or Cash, and certain fields are empty, mark as No Valuation
        etf_mask = df_ordered['Asset Class'].astype(str).str.upper().isin(['ETF', 'FUND', 'CASH', 'FIXED_INCOME'])
        # Note: we don't overwrite valid numbers, just provide context for blanks
        # This is a bit complex in a flat list loop, handled in the row loop below.
        pass

    data = []
    for _, row in df_ordered.iterrows():
        clean_row = []
        is_etf_or_cash = str(row.get('Asset Class', '')).upper() in ['ETF', 'FUND', 'CASH', 'FIXED_INCOME', 'CASH_EQUIVALENT']
        
        for col_name in columns:
            val = row[col_name]

            if is_holdings:
                if col_name == 'Unrealized G/L':
                    clean_row.append('=G{ROW}-H{ROW}')
                    continue
                elif col_name == 'Unrealized G/L %':
                    clean_row.append('=IF(H{ROW}<>0, J{ROW}/H{ROW}, 0)')
                    continue
                
                # Task 4: Label ETF fields that have no valuation metrics
                if is_etf_or_cash and col_name in ['Valuation Signal', 'Macro Signal'] and (val == "" or val == "N/A"):
                    clean_row.append("ETF - No Valuation")
                    continue

            if isinstance(val, pd.Series):
                val = val.iloc[0] if not val.empty else ""

            if isinstance(val, (np.float64, np.float32)):
                clean_row.append(float(val))
            elif isinstance(val, (np.int64, np.int32)):
                clean_row.append(int(val))
            elif isinstance(val, (np.bool_, bool)):
                clean_row.append(bool(val))
            elif pd.isna(val) is True or val is None or str(val).lower() == 'nat' or val == "":
                clean_row.append("N/A" if col_name in na_fill_cols else "")
            else:
                clean_row.append(val)
        data.append(clean_row)

    return data


def normalize_positions(df: pd.DataFrame, import_date: str, source: str = "csv") -> pd.DataFrame:
    """
    Add import_date, compute weight from market_value, calculate unrealized G/L
    if missing, build fingerprint, and sort by market_value descending.

    Guardrail: all numeric columns cast via pd.to_numeric (nuclear type enforcement).
    """
    df = df.copy()

    df['import_date'] = import_date

    # Task 3: Robust Acquisition Date extraction (ensure it's not left blank)
    if 'acquisition_date' not in df.columns:
        df['acquisition_date'] = "N/A"
    
    # If source is Schwab API, acquisition dates are often in tax_lots
    if 'tax_lots' in df.columns:
        def extract_acq_date(row):
            current = str(row.get('acquisition_date', '')).strip()
            if current and current.lower() not in ('', 'none', 'n/a', 'unknown'):
                return current
            lots = row.get('tax_lots')
            if isinstance(lots, list) and len(lots) > 0:
                # Take earliest date from lots if possible
                dates = [l.get('acquisition_date', l.get('acquisitionDate', '')) for l in lots if l.get('acquisition_date') or l.get('acquisitionDate')]
                if dates: return sorted(dates)[0]
            return "N/A"
        df['acquisition_date'] = df.apply(extract_acq_date, axis=1)

    df['acquisition_date'] = df['acquisition_date'].fillna("N/A").replace('', 'N/A')

    # Robust extraction/conversion for numeric columns
    calc_cols = ['market_value', 'quantity', 'cost_basis', 'unrealized_gl', 'unrealized_gl_pct', 'price']
    for col in calc_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        else:
            df[col] = 0.0

    # Ensure price is calculated if missing but market_value and quantity exist
    mask_price = (df['price'] == 0) & (df['quantity'] != 0)
    df.loc[mask_price, 'price'] = df.loc[mask_price, 'market_value'] / df.loc[mask_price, 'quantity']

    # Weight = market_value / total (Python math — guardrail #1)
    total_value = df['market_value'].sum()
    df['weight'] = (df['market_value'] / total_value) if total_value > 0 else 0.0

    # Back-fill unrealized G/L where zero but cost_basis > 0
    mask_gl = (df['unrealized_gl'] == 0) & (df['cost_basis'] > 0)
    df.loc[mask_gl, 'unrealized_gl'] = df.loc[mask_gl, 'market_value'] - df.loc[mask_gl, 'cost_basis']

    # Back-fill unrealized G/L %
    # Task 2: Raw decimal (remove * 100)
    mask_pct = (df['unrealized_gl_pct'] == 0) & (df['cost_basis'] > 0)
    df.loc[mask_pct, 'unrealized_gl_pct'] = (
        df.loc[mask_pct, 'unrealized_gl'] / df.loc[mask_pct, 'cost_basis']
    )

    # Fingerprint for dedup
    df['fingerprint'] = df.apply(
        lambda x: f"{import_date}|{x['ticker']}|{x.get('quantity', 0)}|{round(x.get('market_value', 0), 2)}",
        axis=1
    )

    # Explicit sort by market_value descending (Task 2)
    return df.sort_values(by='market_value', ascending=False)


# ---------------------------------------------------------------------------
# Sheet write helpers
# ---------------------------------------------------------------------------

def write_holdings_current(ws, data: list[list]) -> None:
    """Atomically update Holdings_Current starting at row 2 (row 1=KPI dashboard)."""
    if not data:
        print("Holdings_Current: No data to write.")
        return

    # Replace {ROW} placeholder with actual row index (starting at 3 because row 1 is KPI, row 2 is header)
    processed_data = []
    for i, row in enumerate(data):
        row_idx = i + 3
        new_row = [str(cell).replace("{ROW}", str(row_idx)) if "{ROW}" in str(cell) else cell for cell in row]
        processed_data.append(new_row)

    # Prepare headers and data for a single update starting at A2 (Task 1)
    full_data = [config.POSITION_COLUMNS] + processed_data
    
    num_cols = len(config.POSITION_COLUMNS)
    col_letter = chr(ord('A') + num_cols - 1)
    
    # Clear the data range starting from A2 (headers + positions) to ensure no stale data remains
    # Row 1 is preserved for the KPI dashboard.
    ws.batch_clear([f"A2:{col_letter}2000"])
    
    # Write everything in one go starting at A2
    # Headers go to Row 2, Data starts at Row 3.
    ws.update(range_name="A2", values=full_data, value_input_option='USER_ENTERED')
        
    time.sleep(1.0)
    print(f"Holdings_Current: Updated {len(data)} rows (starting at Row 2).")


def append_holdings_history(ws, data: list[list], existing_fps: set = None) -> int:
    """Append rows whose fingerprint is not already in Holdings_History."""
    fp_idx = config.POSITION_COLUMNS.index('Fingerprint')

    if existing_fps is None:
        fp_col_idx = len(config.POSITION_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])

    new_rows_raw = [row for row in data if str(row[fp_idx]) not in existing_fps]

    if new_rows_raw:
        current_rows = len(ws.col_values(1))
        if current_rows == 0:
            current_rows = 1

        processed_rows = []
        for i, row in enumerate(new_rows_raw):
            row_idx = current_rows + i + 1
            new_row = [str(cell).replace("{ROW}", str(row_idx)) if "{ROW}" in str(cell) else cell for cell in row]
            processed_rows.append(new_row)

        ws.append_rows(processed_rows, value_input_option='USER_ENTERED')
        time.sleep(1.0)
        print(f"Holdings_History: Appended {len(processed_rows)} rows.")
        return len(processed_rows)

    print("Holdings_History: No new rows to append.")
    return 0


def append_daily_snapshot(ws, df: pd.DataFrame, existing_fps: set = None) -> bool:
    """Build a Daily_Snapshots row and append if fingerprint is new."""
    from utils.column_guard import ensure_display_columns
    df = ensure_display_columns(df)

    # Nuclear Type Enforcement: Strip [$,] and ensure numeric before summation (Task 1)
    for col in ['Market Value', 'Cost Basis', 'Est Annual Income']:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    import_date = str(df['Import Date'].iloc[0])

    # All aggregations in Python — guardrail #1
    total_value   = float(df['Market Value'].sum())
    total_cost    = float(df['Cost Basis'].sum())
    unrealized_gl = total_value - total_cost

    # Robust Cash Mask (Task 1: include centralized CASH_TICKERS)
    df['Ticker_Clean'] = df['Ticker'].astype(str).str.strip().str.upper()
    cash_tickers_upper = {str(t).strip().upper() for t in config.CASH_TICKERS}
    cash_mask = (df['Asset Class'].astype(str).str.lower() == 'cash') | df['Ticker_Clean'].isin(cash_tickers_upper)
    
    cash_value    = float(df.loc[cash_mask, 'Market Value'].sum())
    invested_value = total_value - cash_value
    position_count = int(len(df))

    # Task 5: Sum (Market Value * Dividend Yield) across ALL positions for Authoritative Income
    # Task 2: Pass as raw decimal (remove any remaining * 100)
    if 'Dividend Yield' in df.columns:
        dy = pd.to_numeric(df['Dividend Yield'], errors='coerce').fillna(0.0)
        # Assuming dy is already raw decimal in df (Step 2 enforces this)
        total_income = (df['Market Value'] * dy).sum()
    else:
        total_income = float(df['Est Annual Income'].sum() if 'Est Annual Income' in df.columns else 0.0)
    
    blended_yield = (total_income / total_value) if total_value > 0 else 0.0

    fp = f"{import_date}|{position_count}|{round(total_value, 2)}"

    if existing_fps is None:
        try:
            fp_col_idx  = len(config.SNAPSHOT_COLUMNS)
            existing_fps = set(ws.col_values(fp_col_idx)[1:])
        except Exception:
            existing_fps = set()

    if fp in existing_fps:
        print(f"Daily_Snapshots: Duplicate found for {import_date}. Skipping.")
        return False

    snapshot_row = [
        import_date, total_value, total_cost, unrealized_gl,
        cash_value, invested_value, position_count, blended_yield,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fp,
    ]

    clean_row = [x.item() if isinstance(x, (np.integer, np.floating)) else x for x in snapshot_row]
    ws.append_rows([clean_row], value_input_option='USER_ENTERED')
    time.sleep(1.0)
    print(f"Daily_Snapshots: Appended snapshot for {import_date}.")
    return True


def calculate_income_metrics(df: pd.DataFrame) -> dict:
    """Compute income KPIs in Python. No LLM math."""
    from utils.column_guard import ensure_display_columns
    df = ensure_display_columns(df)

    # Nuclear Type Enforcement (Task 1)
    for col in ['Market Value', 'Est Annual Income']:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    for col in ['Market Value', 'Est Annual Income', 'Is Cash', 'Ticker']:
        if col not in df.columns:
            df[col] = 'Unknown' if col == 'Ticker' else (False if col == 'Is Cash' else 0.0)

    total_value              = float(df['Market Value'].sum())
    
    # Task 5: Authoritative Income Sum
    if 'Dividend Yield' in df.columns:
        dy = pd.to_numeric(df['Dividend Yield'], errors='coerce').fillna(0.0)
        projected_annual_income = (df['Market Value'] * dy).sum()
    else:
        projected_annual_income  = float(df['Est Annual Income'].sum())
    
    # Task 2: raw decimal for blended yield
    blended_yield_pct        = (projected_annual_income / total_value) if total_value > 0 else 0.0

    df['Ticker_Clean'] = df['Ticker'].astype(str).str.strip().str.upper()
    cash_tickers_upper = {str(t).strip().upper() for t in config.CASH_TICKERS}
    cash_mask          = (df['Asset Class'].astype(str).str.lower() == 'cash') | df['Ticker_Clean'].isin(cash_tickers_upper)
    cash_contribution  = float(df.loc[cash_mask, 'Est Annual Income'].sum())
    top_generators     = df.nlargest(5, 'Est Annual Income')[['Ticker', 'Est Annual Income']]

    return {
        "projected_annual_income": projected_annual_income,
        "blended_yield_pct":       blended_yield_pct,
        "cash_contribution":       cash_contribution,
        "top_generators":          top_generators,
        "total_value":             total_value,
        "position_count":          int(len(df)),
    }


def append_income_snapshot(ws, metrics: dict, existing_fps: set = None) -> bool:
    """Append Income_Tracking row if fingerprint is new."""
    import_date    = datetime.now().strftime("%Y-%m-%d")
    position_count = metrics.get("position_count", 0)

    top_ticker = metrics["top_generators"]['Ticker'].iloc[0] if not metrics["top_generators"].empty else "N/A"
    top_income = metrics["top_generators"]['Est Annual Income'].iloc[0] if not metrics["top_generators"].empty else 0.0

    fp = f"{import_date}|{position_count}|{metrics['projected_annual_income']:.2f}"

    if existing_fps is None:
        fp_col_idx  = len(config.INCOME_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])

    if fp in existing_fps:
        print("Income_Tracking: Duplicate found. Skipping.")
        return False

    row = [
        import_date, metrics["projected_annual_income"], metrics["blended_yield_pct"],
        top_ticker, top_income, metrics["cash_contribution"], fp,
    ]
    ws.append_rows([row], value_input_option='USER_ENTERED')
    time.sleep(1.0)
    print(f"Income_Tracking: Appended snapshot for {import_date}.")
    return True


def write_risk_snapshot(ws, risk_metrics: dict, existing_fps: set = None) -> bool:
    """Append Risk_Metrics row if fingerprint is new."""
    import_date = datetime.now().strftime("%Y-%m-%d")
    fp = f"{import_date}|{risk_metrics['portfolio_beta']:.4f}|{risk_metrics['top_pos_pct']:.2f}"

    if existing_fps is None:
        fp_col_idx  = len(config.RISK_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])

    if fp in existing_fps:
        print("Risk_Metrics: Duplicate found. Skipping.")
        return False

    row = [
        import_date,
        risk_metrics["portfolio_beta"],   risk_metrics["top_pos_pct"],
        risk_metrics["top_pos_ticker"],   risk_metrics["top_sector_pct"],
        risk_metrics["top_sector_name"],  risk_metrics.get("var_95", 0.0),
        risk_metrics.get("stress_impact", 0.0), fp,
    ]
    ws.append_rows([row], value_input_option='USER_ENTERED')
    time.sleep(1.0)
    print(f"Risk_Metrics: Appended snapshot for {import_date}.")
    return True


def ingest_schwab_transactions(df: pd.DataFrame, dry_run=True):
    """Dedup Schwab API transactions (DataFrame input) and append to Sheet."""
    results = {"parsed": 0, "new": 0, "skipped": 0, "errors": []}
    source  = "Schwab_API_Transactions"

    try:
        if df is None or len(df) == 0:
            write_pipeline_log("INFO", source, "No transactions to ingest.", dry_run=dry_run)
            return results

        results["parsed"] = len(df)

        if dry_run:
            write_pipeline_log("INFO", source, f"DRY RUN: Would ingest {len(df)} transactions.", dry_run=dry_run)
            results["new"] = len(df)
            return results

        from utils.sheet_readers import get_gspread_client
        client      = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws          = spreadsheet.worksheet(config.TAB_TRANSACTIONS)

        fp_col_idx   = len(config.TRANSACTION_COLUMNS)
        existing_fps = set(ws.col_values(fp_col_idx)[1:])

        if 'Fingerprint' not in df.columns:
            raise ValueError("Fingerprint column missing from transactions dataframe")

        is_existing = df["Fingerprint"].astype(str).apply(lambda x: x in existing_fps)
        new_df      = df[~is_existing].copy()

        results["skipped"] = int(len(df) - len(new_df))
        results["new"]     = int(len(new_df))

        if len(new_df) > 0:
            sort_col = 'Trade Date' if 'Trade Date' in new_df.columns else 'trade_date'
            if sort_col in new_df.columns:
                new_df = new_df.sort_values(by=sort_col)

            data_to_write = sanitize_dataframe_for_sheets(new_df, config.TRANSACTION_COLUMNS, config.TRANSACTION_COL_MAP)
            ws.append_rows(data_to_write, value_input_option='USER_ENTERED')
            time.sleep(1.0)
            write_pipeline_log("SUCCESS", source, f"Appended {len(data_to_write)} new transactions.",
                               f"Total fetched: {len(df)}, Skipped: {results['skipped']}", dry_run=dry_run)
        else:
            write_pipeline_log("INFO", source, "No new unique transactions found.",
                               f"Total fetched: {len(df)}", dry_run=dry_run)

    except Exception as e:
        results["errors"].append(str(e))
        write_pipeline_log("ERROR", source, f"Ingestion failed: {e}", dry_run=dry_run)

    return results


def append_decision_log(date_str: str, tickers: str, action: str,
                        context: str, rationale: str, tags: str) -> bool:
    """Append a decision journal entry. Respects config.DRY_RUN."""
    timestamp   = datetime.now().strftime("%H:%M:%S")
    fingerprint = f"{date_str}|{timestamp}|{action}|{tickers}"
    row = [str(date_str), f"{date_str} {timestamp}", str(tickers), str(action),
           str(context), str(rationale), str(tags), fingerprint]

    if config.DRY_RUN:
        write_pipeline_log("INFO", "Decision_Journal",
                           f"DRY RUN: Would log decision for {tickers} ({action})", dry_run=True)
        return True

    try:
        from utils.sheet_readers import get_gspread_client
        client      = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws          = spreadsheet.worksheet(config.TAB_DECISION_LOG)
        ws.append_rows([row], value_input_option='USER_ENTERED')
        write_pipeline_log("SUCCESS", "Decision_Journal", f"Logged decision: {action} {tickers}",
                           f"Tags: {tags}")
        return True
    except Exception as e:
        write_pipeline_log("ERROR", "Decision_Journal", f"Failed to log decision: {e}")
        return False


def write_risk_metrics(res: dict, df: pd.DataFrame, dry_run: bool = False) -> bool:
    """Persist deep risk results to the Risk_Metrics tab."""
    import_date = datetime.now().strftime("%Y-%m-%d")
    
    # Nuclear Type Enforcement (Task 1)
    if 'Market Value' in df.columns:
        if df['Market Value'].dtype == object:
            df['Market Value'] = df['Market Value'].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
        df['Market Value'] = pd.to_numeric(df['Market Value'], errors='coerce').fillna(0.0)

    # Python math — guardrail #1
    total_val       = float(df['Market Value'].sum())
    top_pos         = df.nlargest(1, 'Market Value').iloc[0]
    top_pos_ticker  = top_pos['Ticker']
    # Task 2: raw decimal (e.g. 0.08 for 8%)
    top_pos_pct     = (float(top_pos['Market Value']) / total_val) if total_val > 0 else 0.0

    sector_weights  = df.groupby('Asset Class')['Market Value'].sum()
    top_sector_name = sector_weights.idxmax() if not sector_weights.empty else "N/A"
    # Task 2: raw decimal
    top_sector_pct  = (float(sector_weights.max()) / total_val) if total_val > 0 else 0.0

    stress_10    = [s['impact'] for s in res['stress'] if '-10%' in s['scenario']]
    stress_impact = stress_10[0] if stress_10 else 0.0

    # Task 2: Fix Zero VaR by using the historical percentile method from utils.risk
    from utils.risk import calculate_var, build_price_histories
    hist = build_price_histories(df)
    var_95 = calculate_var(df, hist, confidence=0.95)

    metrics = {
        "portfolio_beta":  res['p_beta'],
        "top_pos_pct":     top_pos_pct,
        "top_pos_ticker":  top_pos_ticker,
        "top_sector_pct":  top_sector_pct,
        "top_sector_name": top_sector_name,
        "var_95":          var_95,
        "stress_impact":   stress_impact,
    }

    if dry_run:
        print(f"DRY RUN: Would write risk metrics for {import_date}")
        return True

    try:
        from utils.sheet_readers import get_gspread_client
        client      = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws          = spreadsheet.worksheet(config.TAB_RISK_METRICS)
        return write_risk_snapshot(ws, metrics)
    except Exception as e:
        print(f"Failed to write risk metrics: {e}")
        return False


def write_to_sheets(df: pd.DataFrame, cash_amount: float, dry_run: bool = True) -> dict:
    """
    Orchestrate Holdings_Current → Holdings_History → Daily_Snapshots → Income_Tracking.
    Respects dry_run flag (guardrail #3).
    """
    results = {"holdings_written": 0, "history_appended": 0, "snapshot": False, "income_snapshot": False}
    source  = "Positions_Ingestion"

    data_list     = sanitize_dataframe_for_sheets(df, config.POSITION_COLUMNS, config.POSITION_COL_MAP, is_holdings=True)
    income_metrics = calculate_income_metrics(df)

    if dry_run:
        write_pipeline_log("INFO", source, f"DRY RUN: Prepared {len(data_list)} positions.", dry_run=dry_run)
        results.update({"holdings_written": len(data_list), "history_appended": len(data_list),
                        "snapshot": True, "income_snapshot": True})
        return results

    from utils.sheet_readers import get_gspread_client
    client      = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    for attempt in range(3):
        try:
            ws_current  = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)
            write_holdings_current(ws_current, data_list)
            results["holdings_written"] = len(data_list)

            ws_history  = spreadsheet.worksheet(config.TAB_HOLDINGS_HISTORY)
            results["history_appended"] = append_holdings_history(ws_history, data_list)

            ws_snapshots = spreadsheet.worksheet(config.TAB_DAILY_SNAPSHOTS)
            results["snapshot"] = append_daily_snapshot(ws_snapshots, df)

            ws_income   = spreadsheet.worksheet(config.TAB_INCOME_TRACKING)
            results["income_snapshot"] = append_income_snapshot(ws_income, income_metrics)

            write_pipeline_log("SUCCESS", source,
                               f"Updated Holdings_Current ({len(data_list)} rows) "
                               f"and History ({results['history_appended']} new).",
                               dry_run=dry_run)
            break

        except gspread.exceptions.APIError as e:
            if attempt < 2:
                write_pipeline_log("WARNING", source, f"API Error, retrying in 60s... {e}", dry_run=dry_run)
                time.sleep(60)
            else:
                write_pipeline_log("ERROR", source, f"Ingestion failed after 3 attempts: {e}", dry_run=dry_run)
                raise

    return results
