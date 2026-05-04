'''
SAFETY: This module provides READ-ONLY access to Schwab account and
market data. It NEVER imports or calls order placement endpoints.

PROHIBITED methods (do not import, do not call, do not even reference):
  - place_order
  - replace_order
  - cancel_order
  - get_orders_for_account
  - get_orders_for_all_linked_accounts

Code review checkpoint: grep this file for "order" — only matches
allowed are this docstring and comments. Any other match is a bug.
'''

import os
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
import schwab.auth
import schwab.client
from utils import schwab_token_store
import config

def get_accounts_client() -> schwab.client.Client | None:
    """
    Builds Schwab client for the Accounts app with GCS token persistence.
    """
    token = schwab_token_store.load_token(config.SCHWAB_TOKEN_BLOB_ACCOUNTS)
    if not token:
        schwab_token_store.write_alert("Accounts token missing — run initial auth", "critical")
        return None
    
    def token_loader():
        return schwab_token_store.load_token(config.SCHWAB_TOKEN_BLOB_ACCOUNTS)

    def token_saver(new_token, **kwargs):
        schwab_token_store.save_token(new_token, config.SCHWAB_TOKEN_BLOB_ACCOUNTS)

    try:
        return schwab.auth.client_from_access_functions(
            config.SCHWAB_ACCOUNTS_APP_KEY,
            config.SCHWAB_ACCOUNTS_APP_SECRET,
            token_loader,
            token_saver
        )
    except Exception as e:
        logging.error(f"Failed to initialize Accounts client: {e}")
        return None

def get_market_client() -> schwab.client.Client | None:
    """
    Builds Schwab client for the Market Data app with GCS token persistence.
    Physically scoped to Market Data endpoints by the app key.
    """
    token = schwab_token_store.load_token(config.SCHWAB_TOKEN_BLOB_MARKET)
    if not token:
        schwab_token_store.write_alert("Market token missing — run initial auth", "critical")
        return None
    
    def token_loader():
        return schwab_token_store.load_token(config.SCHWAB_TOKEN_BLOB_MARKET)

    def token_saver(new_token, **kwargs):
        schwab_token_store.save_token(new_token, config.SCHWAB_TOKEN_BLOB_MARKET)

    try:
        return schwab.auth.client_from_access_functions(
            config.SCHWAB_MARKET_APP_KEY,
            config.SCHWAB_MARKET_APP_SECRET,
            token_loader,
            token_saver
        )
    except Exception as e:
        logging.error(f"Failed to initialize Market client: {e}")
        return None

def fetch_positions(client: schwab.client.Client) -> pd.DataFrame:
    """
    Fetch and aggregate positions from ALL linked Schwab accounts.
    Uses get_accounts() — no single account hash required.

    Multi-account aggregation:
    - Positions with the same ticker are summed (e.g. VTI in brokerage + IRA = one row).
    - Net quantity = longQuantity - shortQuantity (handles margin short positions).
    - Positions where net qty == 0 are skipped (fully netted out across accounts).
    - Tax treatment: if the same ticker exists in accounts with different tax treatment
      (e.g. VTI in taxable + IRA), it is flagged as 'mixed' for TLH safety.
    - Per-account breakdown is logged at DEBUG level with masked account numbers.

    Returns empty DataFrame on error or if no invested positions found.
    """
    try:
        r = client.get_accounts(fields=client.Account.Fields.POSITIONS)
        r.raise_for_status()
        accounts = r.json()

        if not isinstance(accounts, list) or not accounts:
            logging.info("No accounts returned from Schwab API.")
            return pd.DataFrame()

        # Collect every position row across all accounts; accumulate cash from balances
        all_rows: list[dict] = []
        total_cash = 0.0
        # Audit trail: ticker → set of (masked_acct_id, tax_treatment) tuples
        _acct_sources: dict[str, list[str]] = {}

        # Pure sweep tickers that are usually reflected in cashBalance.
        # SGOV is an ETF and should be captured as a position even if it's "cash equivalent".
        PURE_CASH_SWEEP_TICKERS = {'QACDS', 'CASH & CASH INVESTMENTS'}

        for acct_idx, acc in enumerate(accounts):
            sa = acc.get('securitiesAccount', {})

            # Mask account number to last 4 digits for audit logging (never log full hash)
            raw_acct_num  = sa.get('accountNumber', '') or sa.get('accountId', '')
            masked_acct   = f"...{str(raw_acct_num)[-4:]}" if raw_acct_num else f"acct_{acct_idx}"

            # Cash from account-level balances (more reliable than sweep positions)
            balances    = sa.get('currentBalances', {})
            acct_cash   = float(balances.get('cashBalance', 0) or 0)
            total_cash += acct_cash

            # Derive tax treatment from Schwab account type field
            acct_type = sa.get('type', '').upper()
            if 'ROTH' in acct_type:
                tax_treatment = 'tax_exempt'
            elif 'IRA' in acct_type:
                tax_treatment = 'tax_deferred'
            else:
                tax_treatment = 'taxable'

            positions = sa.get('positions', [])
            logging.debug(
                "fetch_positions: %s (%s) — %d positions, cash $%.2f",
                masked_acct, acct_type or 'UNKNOWN', len(positions), acct_cash,
            )

            for p in positions:
                instr  = p.get('instrument', {})
                ticker = instr.get('symbol', 'UNKNOWN')

                # Skip ONLY pure cash sweep tickers already reflected in balances.
                # SGOV is an ETF and should stay as a position even if it's "cash equivalent".
                if ticker in PURE_CASH_SWEEP_TICKERS:
                    continue

                # Net quantity: long minus short (handles margin short positions).
                # Positions that are fully netted (qty == 0) are skipped.
                long_qty  = float(p.get('longQuantity',  0) or 0)
                short_qty = float(p.get('shortQuantity', 0) or 0)
                qty       = long_qty - short_qty
                if qty == 0:
                    logging.debug("fetch_positions: %s qty nets to zero in %s — skipped", ticker, masked_acct)
                    continue

                # Robust extraction from Schwab payload
                market_value  = float(p.get('marketValue', 0) or 0)
                # AveragePrice in Schwab API is cost per share
                avg_price     = float(p.get('averagePrice', 0) or 0)
                # Total cost basis
                cost_basis    = avg_price * abs(qty)
                # Unrealized Profit/Loss
                unrealized_gl = float(p.get('unrealizedProfitLoss', 0) or 0)
                
                # Extraction of Price (usually under 'price' or 'lastPrice')
                current_price = float(p.get('price', 0) or 0)
                if current_price == 0 and qty != 0:
                    current_price = market_value / qty

                # Track account sources for post-aggregation tax-treatment merge audit
                _acct_sources.setdefault(ticker, []).append(f"{masked_acct}/{tax_treatment}")

                daily_change_raw = p.get('currentDayProfitLossPercentage', 0)
                daily_change_val = float(daily_change_raw or 0) / 100.0
                
                if os.environ.get("PORTFOLIO_DEBUG_DAILY_CHANGE"):
                    logging.info(f"DEBUG: {ticker} raw_daily={daily_change_raw} stored={daily_change_val}")

                all_rows.append({
                    'Ticker':         ticker,
                    'Description':    instr.get('description', ''),
                    'Asset Class':    instr.get('assetClass', 'Equity'),
                    'Asset Strategy': '',       # Filled by downstream enrichment
                    'Quantity':       qty,
                    'Price':          current_price,
                    'Market Value':   market_value,
                    'Cost Basis':     cost_basis,
                    'Unit Cost':      avg_price,
                    'Unrealized G/L': unrealized_gl,
                    'Unrealized G/L %': (unrealized_gl / cost_basis) if cost_basis > 0 else 0,
                    'Est Annual Income': float(p.get('estimatedAnnualIncome', 0) or 0),
                    'Dividend Yield':    0.0,   # Filled by enrichment
                    'Acquisition Date':  '',    # Not in positions summary endpoint
                    'Wash Sale':   False,
                    'Is Cash':     False,
                    'Daily Change %': daily_change_val,
                    'Weight':      0.0,         # Computed by normalize_positions
                    'Tax Treatment': tax_treatment,
                    '_acct_idx':   acct_idx,    # Internal only — dropped before return
                })

        if not all_rows and total_cash <= 0:
            logging.info("No invested positions found across all accounts.")
            return pd.DataFrame()

        # Append consolidated cash row if we have ANY cash balance
        if total_cash > 0:
            all_rows.append({
                'Ticker': 'CASH_MANUAL', 'Description': 'Cash & Cash Investments',
                'Asset Class': 'Cash', 'Asset Strategy': 'Cash',
                'Quantity': 1.0, 'Price': total_cash, 'Market Value': total_cash,
                'Cost Basis': total_cash, 'Unit Cost': total_cash,
                'Unrealized G/L': 0.0, 'Unrealized G/L %': 0.0,
                'Est Annual Income': 0.0, 'Dividend Yield': 0.0,
                'Acquisition Date': '', 'Wash Sale': False, 'Is Cash': True,
                'Daily Change %': 0.0, 'Weight': 0.0, 'Tax Treatment': 'taxable',
                '_acct_idx': -1,
            })
            logging.info("fetch_positions: added cash row $%.2f from account balances", total_cash)

        # -----------------------------------------------------------------------
        # Aggregate duplicate tickers (same ticker held across multiple accounts)
        # -----------------------------------------------------------------------
        agg: dict = {}
        for row in all_rows:
            t = row['Ticker']
            if t not in agg:
                agg[t] = row.copy()
            else:
                e = agg[t]
                e['Quantity']       += row['Quantity']
                e['Market Value']   += row['Market Value']
                e['Cost Basis']     += row['Cost Basis']
                e['Unrealized G/L'] += row['Unrealized G/L']
                qty = e['Quantity']
                mv  = e['Market Value']
                cb  = e['Cost Basis']
                e['Price']            = mv / qty if qty != 0 else 0
                e['Unit Cost']        = cb / abs(qty) if qty != 0 else 0
                e['Unrealized G/L %'] = (e['Unrealized G/L'] / cb) if cb > 0 else 0
                # Tax treatment: if accounts disagree, flag 'mixed' (TLH-safe default)
                if row['Tax Treatment'] != e['Tax Treatment']:
                    e['Tax Treatment'] = 'mixed'
                # Keep the best (non-empty) description
                if not e['Description'] and row['Description']:
                    e['Description'] = row['Description']

        # Log any tickers that span multiple accounts (DEBUG for audit trail)
        for ticker, sources in _acct_sources.items():
            if len(sources) > 1:
                logging.info(
                    "fetch_positions: %s spans %d accounts — %s",
                    ticker, len(sources), ", ".join(sources),
                )

        df = pd.DataFrame(list(agg.values()))
        # Drop internal tracking column before schema enforcement
        df = df.drop(columns=['_acct_idx'], errors='ignore')

        # Fallback: empty/UNKNOWN description → use ticker symbol
        df['Description'] = df.apply(
            lambda x: x['Description'] if x['Description'] and x['Description'] != 'UNKNOWN' else x['Ticker'],
            axis=1
        )

        logging.info(
            "fetch_positions: %d unique tickers aggregated from %d accounts",
            len(df), len(accounts),
        )

        # Add Import Date and Fingerprint (Title Case names still active here)
        import_date = datetime.utcnow().strftime("%Y-%m-%d")
        df['Import Date'] = import_date
        df['Fingerprint'] = df.apply(
            lambda x: f"{import_date}|{x['Ticker']}|{x['Quantity']}|{round(x['Market Value'], 2)}",
            axis=1
        )

        # Rename Title Case → snake_case so normalize_positions() and all
        # downstream code can operate on internal names.  Title Case is
        # reapplied at write time by sanitize_dataframe_for_sheets().
        inverse_map = {v: k for k, v in config.POSITION_COL_MAP.items()}
        df = df.rename(columns=inverse_map)

        # Nuclear type enforcement — operates on snake_case names after rename.
        # schwab-py occasionally returns numeric fields as strings; also forces
        # int64 columns (e.g. unrealized_gl) to float64 for pipeline consistency.
        numeric_cols = [
            'quantity', 'price', 'market_value', 'cost_basis', 'unit_cost',
            'unrealized_gl', 'unrealized_gl_pct', 'est_annual_income',
            'dividend_yield', 'daily_change_pct', 'weight'
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype(float)

        # Ensure all snake_case columns exist to avoid KeyError downstream
        for col in config.POSITION_COL_MAP.keys():
            if col not in df.columns:
                df[col] = ""

        # 'Tax Treatment' is not in POSITION_COL_MAP (not written to Sheets) but
        # bundle.py reads it to set tax_treatment_available. Append it after the
        # standard slice so it isn't silently dropped.
        base_cols = list(config.POSITION_COL_MAP.keys())
        result = df[base_cols].copy()
        if 'Tax Treatment' in df.columns:
            result['tax_treatment'] = df['Tax Treatment'].values
        return result
    except Exception as e:
        err_msg = str(e)
        logging.error(f"fetch_positions failed: {err_msg}")
        if "Unauthorized" in err_msg or "invalid_client" in err_msg:
            logging.error("CRITICAL: App Key mismatch detected between tokens and config.")
            schwab_token_store.write_alert("Schwab App Key mismatch — check Cloud Secrets vs Local Re-Auth", "critical")
        else:
            schwab_token_store.write_alert(f"Failed to fetch positions: {e}", "warning")
        return pd.DataFrame()

# ---------------------------------------------------------------------------
# Action normalization map for Schwab transaction types.
# TRADE requires positionEffect inspection (handled inline).
# ---------------------------------------------------------------------------
_SCHWAB_ACTION_MAP = {
    "DIVIDEND_OR_INTEREST": "Dividend",
    "ELECTRONIC_FUND":      "Transfer",
    "ACH_RECEIPT":          "Transfer",
    "ACH_DISBURSEMENT":     "Transfer",
    "CASH_RECEIPT":         "Transfer",
    "WIRE_IN":              "Transfer",
    "WIRE_OUT":             "Transfer",
    "CASH_IN_OR_CASH_OUT":  "Transfer",
    "RECEIVE_AND_DELIVER":  "Transfer",
    "JOURNAL":              "Journal",
    "MEMORANDUM":           "Journal",
}


def _normalize_action(t_type: str, transfer_items: list, net_amount: float) -> str:
    """Map raw Schwab transaction type to human-readable action."""
    if t_type == "TRADE":
        if transfer_items:
            effect = transfer_items[0].get("positionEffect", "")
            if effect == "OPENING":
                return "Buy"
            if effect == "CLOSING":
                return "Sell"
        # Fallback: cash-out (negative) = Buy, cash-in (positive) = Sell
        if net_amount < 0:
            return "Buy"
        if net_amount > 0:
            return "Sell"
        return "Trade"
    return _SCHWAB_ACTION_MAP.get(t_type, t_type)


def _fetch_account_transactions(
    client: "schwab.client.Client",
    acct_hash: str,
    start_date: datetime,
    end_date: datetime,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> list:
    """
    Fetch raw transaction list for one account with exponential-backoff retry.
    Returns list of raw dicts, or empty list on permanent failure.
    Isolated per-account so a single bad account does not abort others.
    """
    masked = f"...{acct_hash[-4:]}"
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            r_tx = client.get_transactions(
                acct_hash,
                start_date=start_date.date(),
                end_date=end_date.date(),
                transaction_types=None
            )
            if r_tx.status_code == 429 or r_tx.status_code >= 500:
                delay = base_delay * (2 ** attempt)
                logging.warning(
                    "fetch_transactions: %s HTTP %d on attempt %d/%d, retrying in %.0fs",
                    masked, r_tx.status_code, attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
                continue
            r_tx.raise_for_status()
            txns = r_tx.json()
            if not isinstance(txns, list):
                logging.warning("fetch_transactions: %s non-list response, skipping", masked)
                return []
            # Warn if result count is suspiciously round (possible silent truncation)
            n = len(txns)
            if n > 0 and n % 500 == 0:
                logging.warning(
                    "fetch_transactions: %s returned exactly %d results — possible API truncation",
                    masked, n,
                )
            logging.info("fetch_transactions: %s — %d transactions", masked, n)
            return txns
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logging.warning(
                    "fetch_transactions: %s error on attempt %d/%d (%s), retrying in %.0fs",
                    masked, attempt + 1, max_retries, exc, delay,
                )
                time.sleep(delay)

    logging.error(
        "fetch_transactions: %s failed after %d attempts: %s",
        masked, max_retries, last_exc,
    )
    return []


def fetch_transactions(client: "schwab.client.Client", start_date=None, end_date=None) -> pd.DataFrame:
    """
    Fetch transaction history for ALL linked Schwab accounts.
    Uses get_account_numbers() to retrieve the hashValue required for the
    transactions endpoint.
    """
    if not start_date:
        start_date = datetime.now() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now()

    # Get account hashes — required for the transactions endpoint
    try:
        r_nums = client.get_account_numbers()
        r_nums.raise_for_status()
        account_mappings = r_nums.json()
    except Exception as e:
        logging.error("fetch_transactions: failed to list account numbers: %s", e)
        return pd.DataFrame(columns=config.TRANSACTION_COLUMNS)

    all_transactions: list[dict] = []
    accounts_ok = 0
    accounts_failed = 0

    for mapping in account_mappings:
        acct_hash = mapping.get('hashValue')
        acct_num  = mapping.get('accountNumber')
        if not acct_hash:
            logging.warning("fetch_transactions: account missing hashValue, skipping")
            continue

        masked = f"...{str(acct_num)[-4:]}" if acct_num else "...????"
        txns = _fetch_account_transactions(client, acct_hash, start_date, end_date)

        if txns is None:
            accounts_failed += 1
            continue

        accounts_ok += 1

        for t in txns:
            t_type = t.get('type', '')
            transfer_items = t.get('transferItems', [])
            net_amount = float(t.get('netAmount', 0) or 0)

            action = _normalize_action(t_type, transfer_items, net_amount)

            # Goal 3: Extract actual equity symbol, filtering out CURRENCY_USD
            ticker = ""
            qty = 0.0
            price = 0.0

            if transfer_items:
                # Find first item that is NOT CURRENCY_USD
                equity_item = None
                for item in transfer_items:
                    instr = item.get('instrument', {})
                    sym = instr.get('symbol', '')
                    if sym and sym != "CURRENCY_USD":
                        equity_item = item
                        break
                
                # Fallback to first item if all are CURRENCY_USD (e.g. pure cash transfer)
                if not equity_item:
                    equity_item = transfer_items[0]

                instr = equity_item.get('instrument', {})
                ticker = instr.get('symbol', '') or ""
                price = float(equity_item.get('price', 0) or 0)
                if t_type == "TRADE":
                    qty = float(equity_item.get('amount', 0) or 0)

            # Fallback ticker: parse description only as last resort
            if not ticker or ticker == "CURRENCY_USD":
                raw_desc = t.get('description', '') or ''
                # Example: "QUALCOMM INC COM" -> QUALCOMM
                candidate = raw_desc.split(' ')[0] if raw_desc else ''
                if candidate and len(candidate) <= 6 and candidate.isalpha() and candidate != "USD":
                    ticker = candidate
                else:
                    # If still no ticker and it's a dividend/trade, we might want it, 
                    # but if it's CURRENCY_USD it will be filtered out below.
                    pass

            # Filter Goal 3: Drop CURRENCY_USD noise and Journal/Transfer entries
            if ticker in ["CURRENCY_USD", "USD", ""] or action in ["Journal", "Transfer"]:
                continue

            trade_date = (t.get('transactionDate') or t.get('time') or '')[:10]
            settlement_date = (t.get('settlementDate') or '')[:10]
            activity_id = t.get('activityId') or t.get('transactionId')

            # Fingerprint: use Schwab's native activityId when available (most stable).
            # Fallback uses settlement_date to distinguish same-day multi-lot trades.
            if activity_id:
                fingerprint = str(activity_id)
            else:
                fingerprint = f"{trade_date}|{ticker}|{action}|{net_amount}|{settlement_date}"

            all_transactions.append({
                'Trade Date':      trade_date,
                'Settlement Date': settlement_date,
                'Ticker':          ticker,
                'Description':     t.get('description', ''),
                'Action':          action,
                'Quantity':        qty,
                'Price':           price,
                'Amount':          net_amount,
                'Fees':            0.0,
                'Net Amount':      net_amount,
                'Account':         f"Schwab{masked}",
                'Fingerprint':     fingerprint,
            })

        # Polite rate-limit spacing between accounts
        time.sleep(0.5)

    logging.info(
        "fetch_transactions: %d accounts OK, %d failed, %d total transactions",
        accounts_ok, accounts_failed, len(all_transactions),
    )

    df = pd.DataFrame(all_transactions)
    if df.empty:
        return pd.DataFrame(columns=config.TRANSACTION_COLUMNS)

    # Type enforcement
    for col in ['Quantity', 'Price', 'Amount', 'Fees', 'Net Amount']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    for col in config.TRANSACTION_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    return df[config.TRANSACTION_COLUMNS]

def fetch_tax_lots(client: "schwab.client.Client") -> list[dict]:
    """
    Derive tax-lot data from the Schwab positions endpoint.

    The Schwab Developer API does not expose individual cost-lot detail (that
    data lives in Schwab's internal systems, not the public API).  This function
    therefore creates one *synthetic* lot per position per account using the
    aggregate cost data the positions endpoint does return:
        - taxLotAverageLongPrice  (most accurate for tax purposes)
        - averagePrice            (fallback)

    All returned lots carry source='schwab' and lot_id=None.  Acquisition date
    is not available from the positions endpoint; holding_period is therefore
    'unknown' unless a date can be inferred.  For full lot-level granularity,
    call utils.tax.reconstruct_lots_fifo() against the Transactions history.

    Returns empty list on API failure; never raises.
    """
    from utils.tax import classify_holding_period, days_until_long_term

    try:
        r = client.get_accounts(fields=client.Account.Fields.POSITIONS)
        r.raise_for_status()
        accounts = r.json()
    except Exception as e:
        logging.error("fetch_tax_lots: failed to list accounts: %s", e)
        return []

    lots: list[dict] = []

    for acc in accounts:
        sa = acc.get('securitiesAccount', {})
        acct_hash = str(acc.get('hashValue') or sa.get('accountNumber', ''))

        acct_type_raw = sa.get('type', '').upper()
        if 'ROTH' in acct_type_raw:
            account_type = 'roth'
        elif 'IRA' in acct_type_raw:
            account_type = 'ira'
        else:
            account_type = 'taxable'

        for p in sa.get('positions', []):
            instr  = p.get('instrument', {})
            ticker = instr.get('symbol', '')
            if not ticker or ticker in config.CASH_TICKERS:
                continue

            long_qty  = float(p.get('longQuantity',  0) or 0)
            short_qty = float(p.get('shortQuantity', 0) or 0)
            qty = long_qty - short_qty
            if qty <= 0:
                continue

            # taxLotAverageLongPrice is the IRS-relevant average; fall back to averagePrice
            cost_per_share = float(
                p.get('taxLotAverageLongPrice') or p.get('averagePrice') or 0
            )
            cost_total = round(cost_per_share * qty, 2)

            # Acquisition date is not exposed by the positions endpoint
            acquisition_date = None
            holding_period   = "unknown"
            days_lt          = None

            lots.append({
                'ticker':               ticker,
                'account_hash':         acct_hash,
                'account_type':         account_type,
                'lot_id':               None,
                'acquisition_date':     acquisition_date,
                'quantity':             qty,
                'cost_basis_per_share': cost_per_share,
                'cost_basis_total':     cost_total,
                'holding_period':       holding_period,
                'days_until_long_term': days_lt,
                'source':               'schwab',
            })

    logging.info(
        "fetch_tax_lots: %d synthetic lots from %d accounts "
        "(source=schwab, aggregate — no individual lot IDs from public API)",
        len(lots), len(accounts),
    )
    return lots


def fetch_balances(client: schwab.client.Client) -> dict:
    """Fetch aggregated account balances across all accounts."""
    try:
        r = client.get_accounts(fields=client.Account.Fields.POSITIONS)
        r.raise_for_status()
        accounts = r.json()
        
        total_liq = 0.0
        total_cash = 0.0
        
        for acc in accounts:
            bal = acc.get('securitiesAccount', {}).get('currentBalances', {})
            total_liq += float(bal.get('liquidationValue', 0) or 0)
            total_cash += float(bal.get('cashBalance', 0) or 0)
            
        return {
            "total_value": total_liq,
            "cash_value": total_cash,
            "buying_power": 0.0, # Aggregated BP is complex
            "day_trading_buying_power": 0.0
        }
    except Exception as e:
        logging.error(f"fetch_balances failed: {e}")
        return {}

def fetch_quotes(client: schwab.client.Client, tickers: list[str]) -> pd.DataFrame:
    """
    Fetch real-time quotes via the Market Data client.
    Returns DataFrame: ticker, last_price, bid, ask, volume, change_pct, timestamp
    """
    if not tickers:
        return pd.DataFrame()
        
    try:
        r = client.get_quotes(tickers)
        r.raise_for_status()
        data = r.json()
        
        rows = []
        for ticker, quote in data.items():
            rows.append({
                'ticker': ticker,
                'last_price': quote.get('lastPrice', 0),
                'bid': quote.get('bidPrice', 0),
                'ask': quote.get('askPrice', 0),
                'volume': quote.get('totalVolume', 0),
                'change_pct': quote.get('netPercentChange', 0),
                'timestamp': datetime.utcnow().isoformat()
            })
        df = pd.DataFrame(rows)

        # Nuclear type enforcement
        quote_numeric_cols = ['last_price', 'bid', 'ask', 'volume', 'change_pct']
        for col in quote_numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        return df
    except Exception as e:
        logging.error(f"fetch_quotes failed: {e}")
        return pd.DataFrame()

def is_api_available() -> dict:
    """Returns availability status for both Accounts and Market Data APIs."""
    acc_token = schwab_token_store.load_token(config.SCHWAB_TOKEN_BLOB_ACCOUNTS)
    mkt_token = schwab_token_store.load_token(config.SCHWAB_TOKEN_BLOB_MARKET)
    return {
        "accounts": acc_token is not None,
        "market": mkt_token is not None
    }
