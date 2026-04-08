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
    
    def token_saver(new_token):
        schwab_token_store.save_token(new_token, config.SCHWAB_TOKEN_BLOB_ACCOUNTS)

    try:
        if st:
            @st.cache_resource(ttl=config.SCHWAB_CLIENT_CACHE_TTL)
            def _cached_accounts_client():
                return schwab.auth.client_from_access_functions(
                    config.SCHWAB_ACCOUNTS_APP_KEY,
                    config.SCHWAB_ACCOUNTS_APP_SECRET,
                    config.SCHWAB_CALLBACK_URL,
                    token_loader,
                    token_saver
                )
            return _cached_accounts_client()
        else:
            return schwab.auth.client_from_access_functions(
                config.SCHWAB_ACCOUNTS_APP_KEY,
                config.SCHWAB_ACCOUNTS_APP_SECRET,
                config.SCHWAB_CALLBACK_URL,
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
    
    def token_saver(new_token):
        schwab_token_store.save_token(new_token, config.SCHWAB_TOKEN_BLOB_MARKET)

    try:
        if st:
            @st.cache_resource(ttl=config.SCHWAB_CLIENT_CACHE_TTL)
            def _cached_market_client():
                return schwab.auth.client_from_access_functions(
                    config.SCHWAB_MARKET_APP_KEY,
                    config.SCHWAB_MARKET_APP_SECRET,
                    config.SCHWAB_CALLBACK_URL,
                    token_loader,
                    token_saver
                )
            return _cached_market_client()
        else:
            return schwab.auth.client_from_access_functions(
                config.SCHWAB_MARKET_APP_KEY,
                config.SCHWAB_MARKET_APP_SECRET,
                config.SCHWAB_CALLBACK_URL,
                token_loader,
                token_saver
            )
    except Exception as e:
        logging.error(f"Failed to initialize Market client: {e}")
        return None

def fetch_positions(client: schwab.client.Client) -> pd.DataFrame:
    """
    Fetch positions from Schwab API and normalize to project schema.
    Returns empty DataFrame on error or if no positions found.
    """
    if not config.SCHWAB_ACCOUNT_HASH:
        logging.error("SCHWAB_ACCOUNT_HASH not set in config.")
        return pd.DataFrame()

    try:
        r = client.get_account(config.SCHWAB_ACCOUNT_HASH, fields=client.Account.Fields.POSITIONS)
        r.raise_for_status()
        data = r.json()
        
        # securitiesAccount -> positions
        positions = data.get('securitiesAccount', {}).get('positions', [])
        if not positions:
            logging.info("No positions returned from Schwab API.")
            return pd.DataFrame()

        rows = []
        for p in positions:
            instr = p.get('instrument', {})
            ticker = instr.get('symbol', 'UNKNOWN')
            
            # Skip cash sweep tickers (managed via manual entry/logic in app)
            if ticker in config.CASH_TICKERS or instr.get('assetClass') == 'CASH_EQUIVALENT':
                continue
                
            qty = p.get('longQuantity', 0)
            market_value = p.get('marketValue', 0)
            unit_cost = p.get('averagePrice', 0)
            cost_basis = unit_cost * qty
            unrealized_gl = p.get('unrealizedProfitLoss', 0)
            current_price = market_value / qty if qty > 0 else 0
            
            row = {
                'Ticker': ticker,
                'Description': instr.get('description', ''),
                'Asset Class': instr.get('assetClass', 'Equity'),
                'Asset Strategy': '', # Filled by downstream enrichment
                'Quantity': qty,
                'Price': current_price,
                'Market Value': market_value,
                'Cost Basis': cost_basis,
                'Unit Cost': unit_cost,
                'Unrealized G/L': unrealized_gl,
                'Unrealized G/L %': (unrealized_gl / cost_basis * 100) if cost_basis > 0 else 0,
                'Est Annual Income': 0.0, # Filled by enrichment/yfinance
                'Dividend Yield': 0.0,    # Filled by enrichment
                'Acquisition Date': '',   # Not provided in positions summary
                'Wash Sale': False,
                'Is Cash': False,
                'Daily Change %': 0.0,
                'Weight': 0.0,            # Computed by pipeline.normalize_positions
            }
            rows.append(row)

        df = pd.DataFrame(rows)

        # Nuclear type enforcement — schwab-py occasionally returns numeric
        # fields as strings; coerce before downstream code touches the frame.
        numeric_cols = [
            'Quantity', 'Price', 'Market Value', 'Cost Basis', 'Unit Cost',
            'Unrealized G/L', 'Unrealized G/L %', 'Est Annual Income',
            'Dividend Yield', 'Daily Change %', 'Weight'
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # Add Import Date and Fingerprint
        import_date = datetime.utcnow().strftime("%Y-%m-%d")
        df['Import Date'] = import_date
        df['Fingerprint'] = df.apply(
            lambda x: f"{import_date}|{x['Ticker']}|{x['Quantity']}|{round(x['Market Value'], 2)}", 
            axis=1
        )

        # Ensure all columns exist to avoid KeyError in downstream code
        for col in config.POSITION_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        
        return df[config.POSITION_COLUMNS]
    except Exception as e:
        logging.error(f"fetch_positions failed: {e}")
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
            lambda x: f"{x['Trade Date']}|{x['Ticker']}|{x['Action']}|{x['Quantity']}|{x['Price']}",
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
