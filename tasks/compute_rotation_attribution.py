"""
tasks/compute_rotation_attribution.py
──────────────────────────────────────
Computes post-hoc P&L attribution for rotations in the Trade_Log.
Calculates Sell Return, Buy Return, and Pair Return at 30, 90, and 180 trading day horizons.
Writes results to the Rotation_Review tab.

Architecture:
  1. Read Trade_Log.
  2. Load existing Rotation_Review for caching.
  3. For each rotation:
     - Check cache: skip if computed < 7 days ago AND all horizons filled.
     - Fetch historical prices for sell/buy tickers.
     - Identify price at T+0, T+30, T+90, T+180 (trading days).
     - Compute returns.
     - Handle CASH buy-side using pro-rated cash yield.
  4. Clear and rebuild the Rotation_Review tab.
"""

import json
import logging
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
import yfinance as yf

# Project root on path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)

# Cache for yfinance downloads to avoid redundant hits in one run
_YF_CACHE: Dict[str, pd.DataFrame] = {}

def get_ohlcv(ticker: str, start_date: date) -> Optional[pd.DataFrame]:
    """Fetch and cache OHLCV for ticker starting from start_date."""
    if ticker in _YF_CACHE:
        return _YF_CACHE[ticker]
    
    # yfinance uses [start, end)
    # Fetch 380 days to cover 180 trading days
    end_date = start_date + timedelta(days=380)
    
    try:
        df = yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), 
                         end=end_date.strftime("%Y-%m-%d"), 
                         progress=False, auto_adjust=True)
        if df.empty:
            return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
            
        _YF_CACHE[ticker] = df
        return df
    except Exception as e:
        logger.warning(f"Failed to download {ticker}: {e}")
        return None

def compute_return(ticker: str, anchor_date: date, trading_days: int, cash_yield: float) -> Optional[float]:
    """Compute cumulative return for ticker over N trading days from anchor_date."""
    if not ticker or ticker == "" or ticker.upper() == "CASH":
        # Handle CASH pro-rata
        cal_days = trading_days * (365.0 / 252.0)
        return round((cash_yield / 100.0) * (cal_days / 365.0), 4)

    df = get_ohlcv(ticker, anchor_date)
    if df is None or df.empty:
        return None
    
    available_dates = df.index
    start_date_actual = available_dates[available_dates.date >= anchor_date]
    if len(start_date_actual) == 0:
        return None
    
    idx0 = df.index.get_loc(start_date_actual[0])
    
    target_idx = idx0 + trading_days
    if target_idx >= len(df):
        return None
    
    price0 = df.iloc[idx0]["Close"]
    priceN = df.iloc[target_idx]["Close"]
    
    if price0 == 0: return None
    return round((priceN / price0) - 1.0, 4)

def run_attribution(live: bool = False):
    """Main execution logic for attribution."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    
    # 1. Load existing Trade_Log
    try:
        log_ws = ss.worksheet(config.TAB_TRADE_LOG)
        log_data = log_ws.get_all_values()
    except Exception:
        logger.error(f"Tab '{config.TAB_TRADE_LOG}' not found.")
        return

    if len(log_data) < 2:
        logger.info("Trade_Log is empty.")
        return

    log_headers = log_data[0]
    trade_rows = log_data[1:]
    
    def get_log_idx(name):
        try: return config.TRADE_LOG_COLUMNS.index(name)
        except: return -1

    # 2. Load existing Rotation_Review for caching
    existing_review = {}
    try:
        review_ws = ss.worksheet(config.TAB_ROTATION_REVIEW)
        review_data = review_ws.get_all_values()
        if len(review_data) > 1:
            rev_headers = review_data[0]
            for r in review_data[1:]:
                try:
                    rid_idx = rev_headers.index("Trade_Log_ID")
                    existing_review[r[rid_idx]] = dict(zip(rev_headers, r))
                except: continue
    except:
        pass

    # 3. Get cash yield
    cash_yield = getattr(config, 'DEFAULT_CASH_YIELD_PCT', 4.5)
    try:
        config_ws = ss.worksheet(config.TAB_CONFIG)
        for row in config_ws.get_all_values():
            if row[0] == "cash_yield_pct":
                cash_yield = float(row[1]); break
    except: pass

    review_rows = []
    today_str = date.today().strftime("%Y-%m-%d")
    today_dt = date.today()

    for i, row in enumerate(trade_rows):
        rid = row[get_log_idx("Trade_Log_ID")]
        
        # Check cache logic:
        # If exists AND (as_of < 7 days old OR all horizons non-null), reuse.
        cached = existing_review.get(rid)
        needs_recompute = True
        
        if cached:
            try:
                as_of_str = cached.get("Attribution_As_Of", "")
                as_of_dt = datetime.strptime(as_of_str, "%Y-%m-%d").date()
                age_days = (today_dt - as_of_dt).days
                
                horizons_filled = all(cached.get(f"Pair_Return_{h}d") not in ("", None) for h in [30, 90, 180])
                
                if age_days <= 7 or horizons_filled:
                    needs_recompute = False
            except:
                pass
        
        if not needs_recompute and cached:
            # Reconstruct row from cache
            row_list = [cached.get(col, "") for col in config.ROTATION_REVIEW_COLUMNS]
            review_rows.append(row_list)
            continue

        # Re-compute
        dt_str = row[get_log_idx("Date")]
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        except:
            try: dt = datetime.strptime(dt_str, "%m/%d/%Y").date()
            except: logger.warning(f"Bad date '{dt_str}' at row {i}"); continue

        sell_ticker = row[get_log_idx("Sell_Ticker")].split(",")[0].strip()
        buy_ticker = row[get_log_idx("Buy_Ticker")].split(",")[0].strip()
        
        returns = {}
        for h in [30, 90, 180]:
            s_ret = compute_return(sell_ticker, dt, h, cash_yield)
            b_ret = compute_return(buy_ticker, dt, h, cash_yield)
            p_ret = round(b_ret - s_ret, 4) if b_ret is not None and s_ret is not None else None
            returns[f"Sell_{h}d"] = s_ret
            returns[f"Buy_{h}d"] = b_ret
            returns[f"Pair_{h}d"] = p_ret

        review_row = {
            "Trade_Log_ID": rid,
            "Date": dt_str,
            "Sell_Ticker": row[get_log_idx("Sell_Ticker")],
            "Buy_Ticker": row[get_log_idx("Buy_Ticker")],
            "Rotation_Type": row[get_log_idx("Rotation_Type")],
            "Implicit_Bet": row[get_log_idx("Implicit_Bet")],
            "Sell_RSI_At_Decision": row[get_log_idx("Sell_RSI_At_Decision")],
            "Buy_RSI_At_Decision": row[get_log_idx("Buy_RSI_At_Decision")],
            "Sell_Trend_At_Decision": row[get_log_idx("Sell_Trend_At_Decision")],
            "Buy_Trend_At_Decision": row[get_log_idx("Buy_Trend_At_Decision")],
            "Sell_Return_30d": returns["Sell_30d"],
            "Sell_Return_90d": returns["Sell_90d"],
            "Sell_Return_180d": returns["Sell_180d"],
            "Buy_Return_30d": returns["Buy_30d"],
            "Buy_Return_90d": returns["Buy_90d"],
            "Buy_Return_180d": returns["Buy_180d"],
            "Pair_Return_30d": returns["Pair_30d"],
            "Pair_Return_90d": returns["Pair_90d"],
            "Pair_Return_180d": returns["Pair_180d"],
            "Attribution_As_Of": today_str,
            "Fingerprint": f"{rid}|{today_str}"
        }
        review_rows.append([review_row.get(col, "") for col in config.ROTATION_REVIEW_COLUMNS])

    if not live:
        logger.info(f"DRY RUN: Would write {len(review_rows)} rows to {config.TAB_ROTATION_REVIEW}")
        return

    # 4. Live Write: Clear and Rebuild
    try:
        review_ws = ss.worksheet(config.TAB_ROTATION_REVIEW)
    except Exception:
        review_ws = ss.add_worksheet(title=config.TAB_ROTATION_REVIEW, rows=1000, cols=len(config.ROTATION_REVIEW_COLUMNS))
        time.sleep(1)

    review_ws.clear()
    time.sleep(1)
    review_ws.update(range_name="A1", values=[config.ROTATION_REVIEW_COLUMNS], value_input_option="USER_ENTERED")
    time.sleep(1)
    if review_rows:
        review_ws.update(range_name="A2", values=review_rows, value_input_option="USER_ENTERED")
        logger.info(f"SUCCESS: Wrote {len(review_rows)} rows to {config.TAB_ROTATION_REVIEW}")
    
    # 5. Apply Formatting
    try:
        from tasks.format_sheets_dashboard_v2 import format_rotation_review
        format_rotation_review(ss)
    except Exception as e:
        logger.warning(f"Formatting failed: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    run_attribution(args.live)
