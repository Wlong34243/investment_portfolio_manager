"""
Derive Rotations Task — clusters sell/buy transactions into candidate rotation records
and writes them to the Trade_Log_Staging sheet tab for Bill's review.

Architecture:
  1. Read Transactions tab for the requested date range.
  2. Identify sells (Action contains "Sell") and buys (Action contains "Buy").
  3. Cluster sells and buys that fall within CLUSTER_WINDOW_DAYS of each other
     (default: same day ± 1 day).  A cluster is anchored to the earliest sell date.
  4. Infer rotation_type per cluster.
  5. Capture Technical Snapshots for each rotation (RSI, Trend, Price vs MA200).
  6. Write candidates to Trade_Log_Staging (append, dedup by fingerprint).

Usage:
    python tasks/derive_rotations.py                       # last 90 days
    python tasks/derive_rotations.py --days 180
    python tasks/derive_rotations.py --dry-run-verify
"""

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Project root on path
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLUSTER_WINDOW_DAYS_DEFAULT = 1        # ± days around each sell date
DEFAULT_LOOKBACK_DAYS = 90
SANITY_BOUND_MULTIPLIER = 3.0          # flag if Buy/Sell or Sell/Buy > this

# Actions that represent outright sells (cash-generating)
SELL_ACTIONS = {"sell", "sell to open", "sell to close"}

# Actions that represent outright buys (cash-deploying)
BUY_ACTIONS  = {"buy", "buy to open", "buy to close", "reinvest shares"}

# Tickers that map to "cash destination"
CASH_DEST_TICKERS = set(config.CASH_TICKERS) | {"SGOV", "QACDS", "SPAXX", "VMFXX"}

# Historical Technical Cache to minimize yfinance hits
_YF_CACHE: dict[str, pd.DataFrame] = {}

# ---------------------------------------------------------------------------
# Technical Indicator Helpers (Synchronized with enrich_technicals.py)
# ---------------------------------------------------------------------------

def _compute_rsi(close: pd.Series) -> Optional[float]:
    if len(close) < 15:
        return None
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    last_loss = avg_loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs  = avg_gain.iloc[-1] / last_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(float(rsi), 1)

def _get_historical_technicals(ticker: str, decision_date: date) -> dict:
    """Fetch 1y OHLCV leading up to decision_date and return RSI, Trend, MA200 distance."""
    if ticker in CASH_DEST_TICKERS or not ticker or ticker == "CASH":
        return {
            "rsi": None, "trend": "neutral", "ma200_dist": None
        }

    # Fetch 1y data ending at decision_date (plus some buffer for calculation)
    # yfinance uses [start, end) so end should be decision_date + 1 day
    end_dt = decision_date + timedelta(days=1)
    start_dt = decision_date - timedelta(days=365)
    
    cache_key = f"{ticker}|{decision_date}"
    if cache_key in _YF_CACHE:
        df = _YF_CACHE[cache_key]
    else:
        try:
            # We fetch a bit more than a year to ensure 200-day MA is stable
            df = yf.download(ticker, start=start_dt.strftime("%Y-%m-%d"), 
                             end=end_dt.strftime("%Y-%m-%d"), 
                             progress=False, auto_adjust=True)
            if df.empty:
                return {"rsi": None, "trend": "unknown", "ma200_dist": None}
            _YF_CACHE[cache_key] = df
        except Exception as e:
            logger.warning("yfinance fetch failed for %s on %s: %s", ticker, decision_date, e)
            return {"rsi": None, "trend": "error", "ma200_dist": None}

    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)

    close = df["Close"].dropna()
    if len(close) < 15:
        return {"rsi": None, "trend": "insufficient_data", "ma200_dist": None}

    # RSI
    rsi = _compute_rsi(close)

    # MA50 and MA200
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
    
    curr_price = close.iloc[-1]
    ma200_dist = round((curr_price - ma200) / ma200 * 100, 2) if ma200 else None

    # Trend Label (Simplified Murphy version from enrich_technicals.py)
    score = 0
    if ma50 and curr_price > ma50: score += 1
    else: score -= 1
    if ma200 and curr_price > ma200: score += 1
    else: score -= 1
    if rsi and 40 <= rsi <= 70: score += 1
    elif rsi: score -= 1

    trend_label = "neutral"
    if score >= 2: trend_label = "uptrend"
    elif score == 3: trend_label = "strong_uptrend" # Score can be 3 if all 3 match
    elif score <= -2: trend_label = "downtrend"
    
    # Refining labels to match version murphy_v1
    if score == 3: trend_label = "strong_uptrend"
    elif score in (1, 2): trend_label = "uptrend"
    elif score == 0: trend_label = "neutral"
    elif score in (-1, -2): trend_label = "downtrend"
    else: trend_label = "strong_downtrend"

    return {
        "rsi": rsi,
        "trend": trend_label,
        "ma200_dist": ma200_dist
    }


# ---------------------------------------------------------------------------
# Helper: parse the Transactions tab into a clean DataFrame
# ---------------------------------------------------------------------------

def _read_transactions(
    since: date,
    until: date,
) -> pd.DataFrame:
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    existing_tabs = {ws.title for ws in ss.worksheets()}
    if config.TAB_TRANSACTIONS not in existing_tabs:
        logger.warning("Transactions tab '%s' not found in sheet.", config.TAB_TRANSACTIONS)
        return pd.DataFrame()

    ws = ss.worksheet(config.TAB_TRANSACTIONS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return pd.DataFrame()

    headers = [h.strip() for h in rows[0]]
    df = pd.DataFrame(rows[1:], columns=headers)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    date_col = next((c for c in df.columns if c in ("trade_date", "date")), None)
    ticker_col = next((c for c in df.columns if c in ("ticker", "symbol")), None)
    action_col = next((c for c in df.columns if c in ("action",)), None)
    amount_col = next((c for c in ("net_amount", "amount") if c in df.columns), None)

    if not all([date_col, ticker_col, action_col]):
        return pd.DataFrame()

    def _parse_date(val: str) -> Optional[date]:
        val = str(val).strip()
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try: return datetime.strptime(val, fmt).date()
            except: continue
        return None

    df["_trade_date"] = df[date_col].apply(_parse_date)
    df = df[df["_trade_date"].notna()].copy()
    df = df[(df["_trade_date"] >= since) & (df["_trade_date"] <= until)]

    def _clean(v):
        if not v: return 0.0
        s = str(v).strip().replace("$", "").replace(",", "")
        if s.startswith("(") and s.endswith(")"): s = "-" + s[1:-1]
        try: return float(s)
        except: return 0.0

    df["_amount"] = df[amount_col].apply(_clean) if amount_col else 0.0
    df["_ticker"] = df[ticker_col].str.strip().str.upper()
    df["_action_lc"] = df[action_col].str.strip().str.lower()

    return df[[
        "_trade_date", "_ticker", "_action_lc", "_amount"
    ]].rename(columns={
        "_trade_date": "trade_date",
        "_ticker":     "ticker",
        "_action_lc":  "action_lc",
        "_amount":     "net_amount",
    }).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Core clustering logic
# ---------------------------------------------------------------------------

def _classify_action(action_lc: str) -> str:
    for kw in SELL_ACTIONS:
        if kw in action_lc: return "sell"
    for kw in BUY_ACTIONS:
        if kw in action_lc: return "buy"
    return "other"

def _infer_rotation_type(sell_tickers: list[str], buy_tickers: list[str]) -> str:
    if not buy_tickers: return "dry_powder"
    buy_set, sell_set = set(buy_tickers), set(sell_tickers)
    if all(t in CASH_DEST_TICKERS for t in buy_set): return "cash_parking"
    if bool(buy_set & sell_set): return "rebalance"
    return "upgrade"

def _fingerprint(dt: date, sell_tickers: list[str], buy_tickers: list[str]) -> str:
    key = f"{dt}|{','.join(sorted(sell_tickers))}|{','.join(sorted(buy_tickers))}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]

def derive_clusters(
    df: pd.DataFrame,
    window_days: int = CLUSTER_WINDOW_DAYS_DEFAULT,
) -> list[dict]:
    if df.empty: return []

    df = df.copy()
    df["side"] = df["action_lc"].apply(_classify_action)
    sells = df[df["side"] == "sell"].copy()
    buys  = df[df["side"] == "buy"].copy()

    if sells.empty: return []

    sell_dates_sorted = sorted(sells["trade_date"].unique())
    clusters_sell_dates: list[list[date]] = []
    for sd in sell_dates_sorted:
        merged = False
        for group in clusters_sell_dates:
            if any(abs((sd - existing).days) <= window_days for existing in group):
                group.append(sd); merged = True; break
        if not merged: clusters_sell_dates.append([sd])

    clusters: list[dict] = []
    assigned_buy_indices: set[int] = set()

    for sell_date_group in clusters_sell_dates:
        anchor_date = min(sell_date_group)
        window_start, window_end = anchor_date - timedelta(days=window_days), max(sell_date_group) + timedelta(days=window_days)

        cluster_sells = sells[sells["trade_date"].isin(sell_date_group)]
        sell_tickers = list(dict.fromkeys(cluster_sells["ticker"].tolist()))
        sell_proceeds = round(cluster_sells["net_amount"].apply(abs).sum(), 2)
        sell_dates_raw = sorted({str(d) for d in cluster_sells["trade_date"]})

        candidate_buys = buys[(buys["trade_date"] >= window_start) & (buys["trade_date"] <= window_end) & (~buys.index.isin(assigned_buy_indices))]
        buy_tickers = list(dict.fromkeys(candidate_buys["ticker"].tolist()))
        buy_amount = round(candidate_buys["net_amount"].apply(abs).sum(), 2)
        buy_dates_raw = sorted({str(d) for d in candidate_buys["trade_date"]})
        assigned_buy_indices.update(candidate_buys.index.tolist())

        buy_display = buy_tickers if buy_tickers else ["CASH"]
        rotation_type = _infer_rotation_type(sell_tickers, buy_tickers)
        if sell_proceeds > 0 and buy_amount > 0:
            ratio = max(sell_proceeds, buy_amount) / min(sell_proceeds, buy_amount)
            if ratio > SANITY_BOUND_MULTIPLIER: rotation_type = "anomalous"

        # Capture Technical Context
        primary_sell = sell_tickers[0] if sell_tickers else None
        primary_buy = buy_tickers[0] if buy_tickers else None
        
        sell_tech = _get_historical_technicals(primary_sell, anchor_date) if primary_sell else {}
        buy_tech = _get_historical_technicals(primary_buy, anchor_date) if primary_buy else {}

        import uuid
        clusters.append({
            "Stage_ID":            str(uuid.uuid4()),
            "Date":                str(anchor_date),
            "Sell_Tickers":        ", ".join(sell_tickers),
            "Sell_Proceeds":       sell_proceeds,
            "Buy_Tickers":         ", ".join(buy_display),
            "Buy_Amount":          buy_amount,
            "Rotation_Type":       rotation_type,
            "Implicit_Bet":        "",
            "Thesis_Brief":        "",
            "Status":              "pending",
            "Cluster_Window_Days": window_days,
            "Sell_Dates":          " | ".join(sell_dates_raw),
            "Buy_Dates":           " | ".join(buy_dates_raw),
            "Sell_RSI_At_Decision": sell_tech.get("rsi"),
            "Sell_Trend_At_Decision": sell_tech.get("trend"),
            "Sell_Price_vs_MA200_At_Decision": sell_tech.get("ma200_dist"),
            "Buy_RSI_At_Decision": buy_tech.get("rsi"),
            "Buy_Trend_At_Decision": buy_tech.get("trend"),
            "Buy_Price_vs_MA200_At_Decision": buy_tech.get("ma200_dist"),
            "Fingerprint":         _fingerprint(anchor_date, sell_tickers, buy_tickers),
        })

    return clusters


# ---------------------------------------------------------------------------
# Staging writer
# ---------------------------------------------------------------------------

def _ensure_staging_tab(ss) -> "gspread.Worksheet":
    existing_tabs = {ws.title for ws in ss.worksheets()}
    if config.TAB_TRADE_LOG_STAGING not in existing_tabs:
        ws = ss.add_worksheet(title=config.TAB_TRADE_LOG_STAGING, rows=2000, cols=len(config.TRADE_LOG_STAGING_COLUMNS) + 1)
        time.sleep(1.0)
        ws.update(range_name="A1", values=[config.TRADE_LOG_STAGING_COLUMNS], value_input_option="USER_ENTERED")
        logger.info("Created %s tab.", config.TAB_TRADE_LOG_STAGING)
    else: ws = ss.worksheet(config.TAB_TRADE_LOG_STAGING)
    return ws

def _existing_fingerprints(ws) -> set[str]:
    try:
        fp_col_index = config.TRADE_LOG_STAGING_COLUMNS.index("Fingerprint") + 1
        return set(v.strip() for v in ws.col_values(fp_col_index)[1:] if v.strip())
    except: return set()

def write_staging(clusters: list[dict], dry_run: bool = True, dry_run_verify: bool = False) -> int:
    if not clusters: return 0
    if dry_run or dry_run_verify:
        label = "DRY RUN VERIFY" if dry_run_verify else "DRY RUN"
        console.print(f"\n[bold yellow][{label}][/] Previewing candidates for {config.TAB_TRADE_LOG_STAGING}:\n")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Date"); table.add_column("Sell Tickers"); table.add_column("Proceeds", justify="right"); table.add_column("Buy Tickers"); table.add_column("Amount", justify="right"); table.add_column("Type"); table.add_column("Sell RSI"); table.add_column("Buy RSI")
        for c in clusters[:5] if dry_run_verify else clusters:
            table.add_row(c["Date"], c["Sell_Tickers"], f"${c['Sell_Proceeds']:,.2f}", c["Buy_Tickers"], f"${c['Buy_Amount']:,.2f}", c["Rotation_Type"], str(c.get("Sell_RSI_At_Decision") or ""), str(c.get("Buy_RSI_At_Decision") or ""))
        console.print(table); console.print()
        if dry_run_verify: sys.exit(0)
        return 0

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = _ensure_staging_tab(ss)
    existing_fps = _existing_fingerprints(ws)
    new_clusters = [c for c in clusters if c["Fingerprint"] not in existing_fps]
    if not new_clusters: return 0
    rows = [[c.get(col, "") for col in config.TRADE_LOG_STAGING_COLUMNS] for c in new_clusters]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    logger.info("Wrote %d new row(s) to %s.", len(rows), config.TAB_TRADE_LOG_STAGING)
    return len(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--since", metavar="YYYY-MM-DD")
    p.add_argument("--until", metavar="YYYY-MM-DD")
    p.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--window", type=int, default=CLUSTER_WINDOW_DAYS_DEFAULT)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dry-run-verify", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    today = date.today()
    until = datetime.strptime(args.until, "%Y-%m-%d").date() if args.until else today
    since = datetime.strptime(args.since, "%Y-%m-%d").date() if args.since else today - timedelta(days=args.days)

    df = _read_transactions(since=since, until=until)
    if df.empty: return
    clusters = derive_clusters(df, window_days=args.window)
    if not clusters: return
    write_staging(clusters, dry_run=args.dry_run, dry_run_verify=args.dry_run_verify)

if __name__ == "__main__":
    main()
