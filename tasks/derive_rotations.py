"""
Derive Rotations Task — clusters sell/buy transactions into candidate rotation records
and writes them to the Trade_Log_Staging sheet tab for Bill's review.

Architecture:
  1. Read Transactions tab for the requested date range.
  2. Identify sells (Action contains "Sell") and buys (Action contains "Buy").
  3. Cluster sells and buys that fall within CLUSTER_WINDOW_DAYS of each other
     (default: same day ± 1 day).  A cluster is anchored to the earliest sell date.
  4. Infer rotation_type per cluster:
       dry_powder   — sell with no buy within window
       cash_parking — sell followed by SGOV / cash-like buy
       upgrade      — sell followed by equity buy (different ticker)
       rebalance    — same ticker sold and then bought (trim + re-add)
       unknown      — cannot determine from transaction data alone
  5. Write candidates to Trade_Log_Staging (append, dedup by fingerprint).
     Implicit_Bet and Thesis_Brief are left blank for Bill to fill in.
  6. Rows stay in staging (Status=pending) until:
       python manager.py journal promote
     which moves approved rows to Trade_Log.

Usage:
    python tasks/derive_rotations.py                       # last 90 days
    python tasks/derive_rotations.py --days 180
    python tasks/derive_rotations.py --since 2026-01-01
    python tasks/derive_rotations.py --since 2026-01-01 --until 2026-03-31
    python tasks/derive_rotations.py --dry-run            # print candidates, no write
    python -m tasks.derive_rotations                      # module form

Notes:
    - Amounts: Schwab sign convention — sells are positive Net Amount (cash in),
      buys are negative Net Amount (cash out).  This script normalises both to
      absolute values in the Sell_Proceeds / Buy_Amount columns.
    - Dedup: each cluster gets a SHA256[:12] fingerprint from
      date + sell_tickers + buy_tickers.  Re-running the same date range
      will not create duplicate staging rows.
    - CASH_TICKERS (SGOV, QACDS, CASH_MANUAL) are always treated as cash
      destinations, never as buy targets for "upgrade" classification.
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLUSTER_WINDOW_DAYS_DEFAULT = 1        # ± days around each sell date
DEFAULT_LOOKBACK_DAYS = 90

# Actions that represent outright sells (cash-generating)
SELL_ACTIONS = {"sell", "sell to open", "sell to close"}

# Actions that represent outright buys (cash-deploying)
BUY_ACTIONS  = {"buy", "buy to open", "buy to close", "reinvest shares"}

# Tickers that map to "cash destination" — buy of these = cash_parking
CASH_DEST_TICKERS = config.CASH_TICKERS | {"SGOV", "QACDS", "SPAXX", "VMFXX"}


# ---------------------------------------------------------------------------
# Helper: parse the Transactions tab into a clean DataFrame
# ---------------------------------------------------------------------------

def _read_transactions(
    since: date,
    until: date,
) -> pd.DataFrame:
    """
    Pull the Transactions tab and return rows within [since, until].

    Returns DataFrame with columns:
        trade_date (date), ticker (str), action_raw (str),
        action_lc (str), net_amount (float)

    Returns empty DataFrame if the tab is missing or empty.
    """
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    existing_tabs = {ws.title for ws in ss.worksheets()}
    if config.TAB_TRANSACTIONS not in existing_tabs:
        logger.warning("Transactions tab '%s' not found in sheet.", config.TAB_TRANSACTIONS)
        return pd.DataFrame()

    ws = ss.worksheet(config.TAB_TRANSACTIONS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        logger.info("Transactions tab is empty.")
        return pd.DataFrame()

    headers = [h.strip() for h in rows[0]]
    df = pd.DataFrame(rows[1:], columns=headers)

    # Normalise column names to lower-snake
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    # Identify columns
    date_col = next((c for c in df.columns if c in ("trade_date", "date")), None)
    ticker_col = next((c for c in df.columns if c in ("ticker", "symbol")), None)
    action_col = next((c for c in df.columns if c in ("action",)), None)
    qty_col = next((c for c in df.columns if "quantity" in c), None)
    price_col = next((c for c in df.columns if "price" in c), None)
    fees_col = next((c for c in df.columns if "fees" in c), None)
    fp_col = next((c for c in df.columns if "fingerprint" in c), None)
    
    # Preferred amount column
    amount_col = next((c for c in ("net_amount", "amount") if c in df.columns), None)

    if date_col is None or ticker_col is None or action_col is None:
        logger.error("Required columns missing from Transactions tab. Columns: %s", list(df.columns))
        return pd.DataFrame()

    # Robust parsing function
    def _get_row_amount(row) -> float:
        # Helper to clean string numbers
        def _clean(v):
            if v is None or v == "": return 0.0
            s = str(v).strip().replace("$", "").replace(",", "")
            if s.startswith("(") and s.endswith(")"):
                s = "-" + s[1:-1]
            try: return float(s)
            except: return 0.0

        # 1. Try dedicated amount column
        amt = _clean(row.get(amount_col)) if amount_col else 0.0
        if amt != 0.0:
            return amt

        # 2. Fallback: Extract from fingerprint
        if fp_col:
            fp = str(row.get(fp_col, ""))
            parts = fp.split("|")
            if len(parts) >= 4:
                try:
                    fp_amt = float(parts[-1])
                    if fp_amt != 0.0: return fp_amt
                except: pass

        # 3. Fallback: Calculate from Quantity * Price
        if qty_col and price_col:
            q = _clean(row.get(qty_col))
            p = _clean(row.get(price_col))
            action = str(row.get(action_col, "")).lower()
            if q != 0 and p != 0:
                multiplier = -1.0 if "buy" in action else 1.0
                principal = q * p
                fees = _clean(row.get(fees_col)) if fees_col else 0.0
                # Schwab sign convention:
                # Sell: proceeds = principal - fees (positive)
                # Buy: total_cost = -(principal + fees) (negative)
                if multiplier > 0: # Sell
                    return round(principal - fees, 2)
                else: # Buy
                    return round(-(principal + fees), 2)
        
        return 0.0

    # Parse dates first
    def _parse_date(val: str) -> Optional[date]:
        val = str(val).strip()
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
        return None

    df["_trade_date"] = df[date_col].apply(_parse_date)
    df = df[df["_trade_date"].notna()].copy()

    # Filter date range
    df = df[(df["_trade_date"] >= since) & (df["_trade_date"] <= until)]
    if df.empty:
        return pd.DataFrame()

    # Apply robust amount parsing
    df["_amount"] = df.apply(_get_row_amount, axis=1)
    df["_ticker"] = df[ticker_col].str.strip().str.upper()
    df["_action_raw"] = df[action_col].str.strip()
    df["_action_lc"] = df["_action_raw"].str.lower()

    return df[[
        "_trade_date", "_ticker", "_action_raw", "_action_lc", "_amount"
    ]].rename(columns={
        "_trade_date": "trade_date",
        "_ticker":     "ticker",
        "_action_raw": "action_raw",
        "_action_lc":  "action_lc",
        "_amount":     "net_amount",
    }).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Core clustering logic
# ---------------------------------------------------------------------------

def _classify_action(action_lc: str) -> str:
    """Returns 'sell', 'buy', or 'other'."""
    for kw in SELL_ACTIONS:
        if kw in action_lc:
            return "sell"
    for kw in BUY_ACTIONS:
        if kw in action_lc:
            return "buy"
    return "other"


def _infer_rotation_type(
    sell_tickers: list[str],
    buy_tickers: list[str],
) -> str:
    """
    Infer the rotation type from the cluster's ticker sets.

    dry_powder   — no buys at all
    cash_parking — all buys are cash-equivalent tickers (SGOV etc.)
    rebalance    — at least one ticker appears on both sides
    upgrade      — sold one thing, bought another equity
    unknown      — mixed or unclassifiable
    """
    if not buy_tickers:
        return "dry_powder"

    buy_set  = set(buy_tickers)
    sell_set = set(sell_tickers)

    all_cash = all(t in CASH_DEST_TICKERS for t in buy_set)
    if all_cash:
        return "cash_parking"

    has_overlap = bool(buy_set & sell_set)
    if has_overlap:
        return "rebalance"

    return "upgrade"


def _fingerprint(dt: date, sell_tickers: list[str], buy_tickers: list[str]) -> str:
    """SHA256[:12] of canonical (date, sorted sells, sorted buys)."""
    key = f"{dt}|{','.join(sorted(sell_tickers))}|{','.join(sorted(buy_tickers))}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def derive_clusters(
    df: pd.DataFrame,
    window_days: int = CLUSTER_WINDOW_DAYS_DEFAULT,
) -> list[dict]:
    """
    Group sell and buy transactions into rotation clusters.

    Algorithm:
      1. Identify all sell dates.
      2. For each unique sell date D, collect:
           - all sells on dates in [D - window, D + window]
           - all buys  on dates in [D - window, D + window]
      3. Merge sell dates that are themselves within window of each other
         so that a "sell A on Mon, sell B on Tue, buy C on Wed" becomes
         one cluster anchored at Mon.
      4. Assign buys that fall between two sell clusters to the nearer one.

    Returns a list of cluster dicts ready for the staging schema.
    """
    if df.empty:
        return []

    df = df.copy()
    df["side"] = df["action_lc"].apply(_classify_action)

    sells = df[df["side"] == "sell"].copy()
    buys  = df[df["side"] == "buy"].copy()

    if sells.empty:
        logger.info("No sell transactions found in the date range.")
        return []

    # -------------------------------------------------------------------
    # Step 1: group sell dates into clusters using a greedy scan.
    # Any two sell dates within window_days of each other are merged.
    # -------------------------------------------------------------------
    sell_dates_sorted = sorted(sells["trade_date"].unique())
    clusters_sell_dates: list[list[date]] = []

    for sd in sell_dates_sorted:
        merged = False
        for group in clusters_sell_dates:
            # Merge if this date is within window_days of any date in the group
            if any(abs((sd - existing).days) <= window_days for existing in group):
                group.append(sd)
                merged = True
                break
        if not merged:
            clusters_sell_dates.append([sd])

    # -------------------------------------------------------------------
    # Step 2: for each sell cluster, collect sells + assign buys
    # -------------------------------------------------------------------
    clusters: list[dict] = []
    assigned_buy_indices: set[int] = set()

    for sell_date_group in clusters_sell_dates:
        anchor_date = min(sell_date_group)
        window_start = anchor_date - timedelta(days=window_days)
        window_end   = max(sell_date_group) + timedelta(days=window_days)

        # Sells in this cluster
        cluster_sells = sells[sells["trade_date"].isin(sell_date_group)]
        sell_tickers  = cluster_sells["ticker"].tolist()
        sell_proceeds = round(cluster_sells["net_amount"].apply(abs).sum(), 2)
        sell_dates_raw = sorted({str(d) for d in cluster_sells["trade_date"]})

        # Buys in the window (not yet assigned to another cluster)
        candidate_buys = buys[
            (buys["trade_date"] >= window_start) &
            (buys["trade_date"] <= window_end) &
            (~buys.index.isin(assigned_buy_indices))
        ]
        buy_tickers   = candidate_buys["ticker"].tolist()
        buy_amount    = round(candidate_buys["net_amount"].apply(abs).sum(), 2)
        buy_dates_raw = sorted({str(d) for d in candidate_buys["trade_date"]})
        assigned_buy_indices.update(candidate_buys.index.tolist())

        # Deduplicate ticker lists (preserve order, remove duplicates)
        sell_tickers_dedup = list(dict.fromkeys(sell_tickers))
        buy_tickers_dedup  = list(dict.fromkeys(buy_tickers))

        # Determine buy display — "CASH" if truly no equity buys
        buy_display = buy_tickers_dedup if buy_tickers_dedup else ["CASH"]

        rotation_type = _infer_rotation_type(sell_tickers_dedup, buy_tickers_dedup)
        fp = _fingerprint(anchor_date, sell_tickers_dedup, buy_tickers_dedup)

        import uuid
        clusters.append({
            "Stage_ID":            str(uuid.uuid4()),
            "Date":                str(anchor_date),
            "Sell_Tickers":        ", ".join(sell_tickers_dedup),
            "Sell_Proceeds":       sell_proceeds,
            "Buy_Tickers":         ", ".join(buy_display),
            "Buy_Amount":          buy_amount,
            "Rotation_Type":       rotation_type,
            "Implicit_Bet":        "",      # Bill fills in
            "Thesis_Brief":        "",      # Bill fills in
            "Status":              "pending",
            "Cluster_Window_Days": window_days,
            "Sell_Dates":          " | ".join(sell_dates_raw),
            "Buy_Dates":           " | ".join(buy_dates_raw) if buy_dates_raw else "",
            "Fingerprint":         fp,
        })

    return clusters


# ---------------------------------------------------------------------------
# Staging writer — append-with-dedup
# ---------------------------------------------------------------------------

def _ensure_staging_tab(ss) -> "gspread.Worksheet":
    """Get or create Trade_Log_Staging tab with correct headers."""
    existing_tabs = {ws.title for ws in ss.worksheets()}
    if config.TAB_TRADE_LOG_STAGING not in existing_tabs:
        ws = ss.add_worksheet(
            title=config.TAB_TRADE_LOG_STAGING,
            rows=2000,
            cols=len(config.TRADE_LOG_STAGING_COLUMNS) + 1,
        )
        time.sleep(1.0)
        ws.update(
            range_name="A1",
            values=[config.TRADE_LOG_STAGING_COLUMNS],
            value_input_option="USER_ENTERED",
        )
        time.sleep(0.5)
        logger.info("Created %s tab.", config.TAB_TRADE_LOG_STAGING)
    else:
        ws = ss.worksheet(config.TAB_TRADE_LOG_STAGING)
    return ws


def _existing_fingerprints(ws) -> set[str]:
    """Return set of fingerprints already in staging (column 14)."""
    try:
        fp_col_index = config.TRADE_LOG_STAGING_COLUMNS.index("Fingerprint") + 1
        values = ws.col_values(fp_col_index)
        return set(v.strip() for v in values[1:] if v.strip())  # skip header
    except Exception as e:
        logger.warning("Could not read existing fingerprints: %s", e)
        return set()


def write_staging(clusters: list[dict], dry_run: bool = True) -> int:
    """
    Append new clusters to Trade_Log_Staging.
    Skips clusters whose fingerprint already exists in staging.
    Returns count of rows written (0 if dry_run).
    """
    if not clusters:
        logger.info("No clusters to write.")
        return 0

    if dry_run:
        print(f"\n[DRY RUN] Would write {len(clusters)} candidate(s) to "
              f"{config.TAB_TRADE_LOG_STAGING}:\n")
        for c in clusters:
            print(f"  {c['Date']}  {c['Sell_Tickers']!s:30s} → "
                  f"{c['Buy_Tickers']!s:30s}  [{c['Rotation_Type']}]  "
                  f"proceeds=${c['Sell_Proceeds']:,.0f}  "
                  f"deployed=${c['Buy_Amount']:,.0f}")
        print()
        return 0

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = _ensure_staging_tab(ss)

    existing_fps = _existing_fingerprints(ws)
    new_clusters = [c for c in clusters if c["Fingerprint"] not in existing_fps]

    if not new_clusters:
        logger.info("All %d cluster(s) already in staging — nothing to write.", len(clusters))
        return 0

    rows = [
        [c.get(col, "") for col in config.TRADE_LOG_STAGING_COLUMNS]
        for c in new_clusters
    ]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    time.sleep(1.0)
    logger.info("Wrote %d new row(s) to %s.", len(rows), config.TAB_TRADE_LOG_STAGING)
    return len(rows)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Derive rotation candidates from Transactions tab → Trade_Log_Staging."
    )
    p.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Start date (inclusive). Default: today minus --days.",
    )
    p.add_argument(
        "--until",
        metavar="YYYY-MM-DD",
        help="End date (inclusive). Default: today.",
    )
    p.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        metavar="N",
        help=f"Lookback window in days when --since not specified (default: {DEFAULT_LOOKBACK_DAYS}).",
    )
    p.add_argument(
        "--window",
        type=int,
        default=CLUSTER_WINDOW_DAYS_DEFAULT,
        metavar="N",
        help=(
            f"Cluster window: sell/buy transactions within ±N days are grouped "
            f"(default: {CLUSTER_WINDOW_DAYS_DEFAULT})."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print candidates without writing to the sheet.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        default=False,
    )
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    today = date.today()
    until = (
        datetime.strptime(args.until, "%Y-%m-%d").date()
        if args.until
        else today
    )
    since = (
        datetime.strptime(args.since, "%Y-%m-%d").date()
        if args.since
        else today - timedelta(days=args.days)
    )

    if since > until:
        print(f"ERROR: --since {since} is after --until {until}.")
        sys.exit(1)

    logger.info(
        "Reading transactions %s → %s (cluster window: ±%d day(s))",
        since, until, args.window,
    )

    df = _read_transactions(since=since, until=until)
    if df.empty:
        print(f"No transactions found between {since} and {until}.")
        return

    logger.info("Loaded %d transaction row(s).", len(df))

    clusters = derive_clusters(df, window_days=args.window)
    logger.info("Derived %d rotation cluster(s).", len(clusters))

    if not clusters:
        print("No rotation clusters found in the date range.")
        return

    written = write_staging(clusters, dry_run=args.dry_run)

    if not args.dry_run:
        print(
            f"Done. {written} new candidate(s) written to "
            f"'{config.TAB_TRADE_LOG_STAGING}'. "
            f"{len(clusters) - written} duplicate(s) skipped."
        )
        print(
            "\nNext steps:\n"
            "  1. Open the Trade_Log_Staging tab in Google Sheets.\n"
            "  2. Fill in Implicit_Bet and Thesis_Brief for each pending row.\n"
            "  3. Set Status to 'approved' (or 'rejected' to discard).\n"
            "  4. Run:  python manager.py journal promote\n"
            "     to move approved rows → Trade_Log."
        )


if __name__ == "__main__":
    main()
