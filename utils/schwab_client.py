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

import pandas as pd
import logging
from datetime import datetime, timedelta
import schwab.auth
import schwab.client
from utils import schwab_token_store
import config

try:
    import streamlit as st
except ImportError:
    st = None

def get_accounts_client() -> schwab.client.Client | None:
    """
    Builds Schwab client for the Accounts app with GCS token persistence.
    Wrapped in Streamlit cache_resource to reuse the client object.
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
        if st:
            @st.cache_resource(ttl=config.SCHWAB_CLIENT_CACHE_TTL)
            def _cached_accounts_client():
                return schwab.auth.client_from_access_functions(
                    config.SCHWAB_ACCOUNTS_APP_KEY,
                    config.SCHWAB_ACCOUNTS_APP_SECRET,
                    token_loader,
                    token_saver
                )
            return _cached_accounts_client()
        else:
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
        if st:
            @st.cache_resource(ttl=config.SCHWAB_CLIENT_CACHE_TTL)
            def _cached_market_client():
                return schwab.auth.client_from_access_functions(
                    config.SCHWAB_MARKET_APP_KEY,
                    config.SCHWAB_MARKET_APP_SECRET,
                    token_loader,
                    token_saver
                )
            return _cached_market_client()
        else:
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
    Uses get_accounts() so no single account hash is required.
    Positions with the same ticker across accounts are summed so the
    portfolio view is unified (e.g. AMZN in brokerage + IRA = one row).
    Returns empty DataFrame on error or if no invested positions found.
    """
    try:
        r = client.get_accounts(fields=client.Account.Fields.POSITIONS)
        r.raise_for_status()
        accounts = r.json()

        if not isinstance(accounts, list) or not accounts:
            logging.info("No accounts returned from Schwab API.")
            return pd.DataFrame()

        # Collect every position row across all accounts; sum cash from balances
        all_rows = []
        total_cash = 0.0

        for acc in accounts:
            sa = acc.get('securitiesAccount', {})

            # Sum cash from account-level balances (most reliable source)
            balances = sa.get('currentBalances', {})
            total_cash += float(balances.get('cashBalance', 0) or 0)

            # Derive tax treatment from account type
            acct_type = sa.get('type', '').upper()
            if 'ROTH' in acct_type:
                tax_treatment = 'tax_exempt'
            elif 'IRA' in acct_type:
                tax_treatment = 'tax_deferred'
            else:
                tax_treatment = 'taxable'

            positions = sa.get('positions', [])
            for p in positions:
                instr = p.get('instrument', {})
                ticker = instr.get('symbol', 'UNKNOWN')

                # Skip cash sweep positions — cash is captured from account balances above
                if ticker in config.CASH_TICKERS or instr.get('assetClass') == 'CASH_EQUIVALENT':
                    continue

                qty = p.get('longQuantity', 0)
                market_value = p.get('marketValue', 0)
                unit_cost = p.get('averagePrice', 0)
                cost_basis = unit_cost * qty
                unrealized_gl = p.get('unrealizedProfitLoss', 0)
                current_price = market_value / qty if qty > 0 else 0

                all_rows.append({
                    'Ticker': ticker,
                    'Description': instr.get('description', ''),
                    'Asset Class': instr.get('assetClass', 'Equity'),
                    'Asset Strategy': '',  # Filled by downstream enrichment
                    'Quantity': qty,
                    'Price': current_price,
                    'Market Value': market_value,
                    'Cost Basis': cost_basis,
                    'Unit Cost': unit_cost,
                    'Unrealized G/L': unrealized_gl,
                    'Unrealized G/L %': (unrealized_gl / cost_basis * 100) if cost_basis > 0 else 0,
                    'Est Annual Income': 0.0,  # Filled by enrichment/yfinance
                    'Dividend Yield': 0.0,     # Filled by enrichment
                    'Acquisition Date': '',    # Not provided in positions summary
                    'Wash Sale': False,
                    'Is Cash': False,
                    'Daily Change %': 0.0,
                    'Weight': 0.0,             # Computed by pipeline.normalize_positions
                    'Tax Treatment': tax_treatment,
                })

        if not all_rows:
            logging.info("No invested positions found across all accounts.")
            return pd.DataFrame()

        # Append a single consolidated cash row if cash > 0
        if total_cash > 0:
            all_rows.append({
                'Ticker': 'CASH_MANUAL',
                'Description': 'Cash & Cash Investments',
                'Asset Class': 'Cash',
                'Asset Strategy': 'Cash',
                'Quantity': 1.0,
                'Price': total_cash,
                'Market Value': total_cash,
                'Cost Basis': total_cash,
                'Unit Cost': total_cash,
                'Unrealized G/L': 0.0,
                'Unrealized G/L %': 0.0,
                'Est Annual Income': 0.0,
                'Dividend Yield': 0.0,
                'Acquisition Date': '',
                'Wash Sale': False,
                'Is Cash': True,
                'Daily Change %': 0.0,
                'Weight': 0.0,
                'Tax Treatment': 'taxable',
            })
            logging.info(f"fetch_positions: added cash row ${total_cash:,.2f} from account balances")

        # Aggregate duplicate tickers (same stock held in multiple accounts)
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
                e['Price']            = mv / qty if qty > 0 else 0
                e['Unit Cost']        = cb / qty if qty > 0 else 0
                e['Unrealized G/L %'] = (e['Unrealized G/L'] / cb * 100) if cb > 0 else 0
                # Keep the best (non-empty) description across accounts
                if not e['Description'] and row['Description']:
                    e['Description'] = row['Description']

        df = pd.DataFrame(list(agg.values()))
        
        # Fallback: If description is still empty/UNKNOWN, use the ticker symbol 
        # as a placeholder so enrichment has something to work with.
        df['Description'] = df.apply(
            lambda x: x['Description'] if x['Description'] and x['Description'] != 'UNKNOWN' else x['Ticker'],
            axis=1
        )

        logging.info(f"fetch_positions: {len(df)} unique tickers from {len(accounts)} accounts")

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

def fetch_transactions(client: schwab.client.Client, start_date=None, end_date=None) -> pd.DataFrame:
    """
    Fetch transaction history for the configured account.
    Filters to: TRADE, DIVIDEND_OR_INTEREST, RECEIVE_AND_DELIVER.
    """
    if not start_date:
        start_date = datetime.now() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now()
        
    try:
        r = client.get_transactions(config.SCHWAB_ACCOUNT_HASH, start_date=start_date, end_date=end_date)
        r.raise_for_status()
        txns = r.json()
        
        rows = []
        for t in txns:
            t_type = t.get('type', '')
            if t_type not in ['TRADE', 'DIVIDEND_OR_INTEREST', 'RECEIVE_AND_DELIVER']:
                continue
            
            # Extract instrument details from the first item
            items = t.get('transferItems', [])
            ticker = ""
            qty = 0
            price = 0
            if items:
                ticker = items[0].get('instrument', {}).get('symbol', '')
                qty = items[0].get('amount', 0)
                price = items[0].get('price', 0)
            
            trade_date = t.get('transactionDate', '')[:10]
            net_amount = t.get('netAmount', 0)
            
            row = {
                'Trade Date': trade_date,
                'Settlement Date': t.get('settlementDate', '')[:10],
                'Ticker': ticker,
                'Description': t.get('description', ''),
                'Action': t_type,
                'Quantity': qty,
                'Price': price,
                'Amount': net_amount,
                'Fees': 0,
                'Net Amount': net_amount,
                'Account': 'Schwab Primary',
            }
            rows.append(row)
            
        df = pd.DataFrame(rows)
        if df.empty: return df

        # Nuclear type enforcement
        txn_numeric_cols = ['Quantity', 'Price', 'Amount', 'Fees']
        for col in txn_numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # Build Fingerprint
        df['Fingerprint'] = df.apply(
            lambda x: f"{str(x['Trade Date'])}|{str(x['Ticker'])}|{str(x['Action'])}|{str(x['Quantity'])}|{str(x['Price'])}",
            axis=1
        )
        
        # Ensure all TRANSACTION_COLUMNS exist
        for col in config.TRANSACTION_COLUMNS:
            if col not in df.columns:
                df[col] = ""
                
        return df[config.TRANSACTION_COLUMNS]
    except Exception as e:
        logging.error(f"fetch_transactions failed: {e}")
        return pd.DataFrame()

def fetch_balances(client: schwab.client.Client) -> dict:
    """Fetch current account balances."""
    try:
        r = client.get_account(config.SCHWAB_ACCOUNT_HASH)
        r.raise_for_status()
        acc = r.json().get('securitiesAccount', {})
        bal = acc.get('currentBalances', {})
        return {
            "total_value": bal.get('liquidationValue', 0),
            "cash_value": bal.get('cashBalance', 0),
            "buying_power": bal.get('buyingPower', 0),
            "day_trading_buying_power": bal.get('dayTradingBuyingPower', 0)
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
