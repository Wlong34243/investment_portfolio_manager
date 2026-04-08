"""
scripts/schwab_initial_auth.py — One-time Schwab OAuth setup.
Run locally, NOT in the cloud.
"""

import os
import sys
import json
import schwab.auth

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils import schwab_token_store
import config

def run_auth():
    print("="*60)
    print("Schwab Initial Auth — One-Time Setup")
    print("="*60)

    # 1. Verify secrets are present in environment/config
    missing = []
    if not config.SCHWAB_ACCOUNTS_APP_KEY: missing.append("SCHWAB_ACCOUNTS_APP_KEY")
    if not config.SCHWAB_ACCOUNTS_APP_SECRET: missing.append("SCHWAB_ACCOUNTS_APP_SECRET")
    if not config.SCHWAB_MARKET_APP_KEY: missing.append("SCHWAB_MARKET_APP_KEY")
    if not config.SCHWAB_MARKET_APP_SECRET: missing.append("SCHWAB_MARKET_APP_SECRET")
    if not config.SCHWAB_TOKEN_BUCKET: missing.append("SCHWAB_TOKEN_BUCKET")
    if not config.SCHWAB_CALLBACK_URL: missing.append("SCHWAB_CALLBACK_URL")

    if missing:
        print(f"Error: Missing required secrets in config/env: {', '.join(missing)}")
        print("Ensure these are set before running this script.")
        sys.exit(1)

    # 2. Accounts App Auth
    print("\n[1/2] Authenticating ACCOUNTS app...")
    tmp_accounts = "token_accounts_tmp.json"
    try:
        # This will open a browser window for login
        client = schwab.auth.client_from_login_flow(
            config.SCHWAB_ACCOUNTS_APP_KEY,
            config.SCHWAB_ACCOUNTS_APP_SECRET,
            config.SCHWAB_CALLBACK_URL,
            tmp_accounts
        )
        
        # Read temp file and upload to GCS
        with open(tmp_accounts, 'r') as f:
            token_data = json.load(f)
        
        if schwab_token_store.save_token(token_data, config.SCHWAB_TOKEN_BLOB_ACCOUNTS):
            print(f"[OK] Accounts token uploaded to GCS: {config.SCHWAB_TOKEN_BLOB_ACCOUNTS}")
        else:
            print("[ERROR] Failed to upload Accounts token to GCS.")
            sys.exit(1)
            
        if os.path.exists(tmp_accounts):
            os.remove(tmp_accounts)

        # 3. Retrieve Account Hashes
        print("\nRetrieving account hashes...")
        try:
            r = client.get_account_numbers()
            r.raise_for_status()
            accounts = r.json()
            print("-" * 40)
            for acc in accounts:
                print(f"Account: {acc.get('accountNumber')} | Hash: {acc.get('hashValue')}")
            print("-" * 40)
            print("ACTION REQUIRED:")
            print("Copy the account hash for your PRIMARY INVESTMENT ACCOUNT")
            print("and paste it into secrets.toml / config as schwab_account_hash")
        except Exception as hash_err:
            print(f"[WARN] Could not retrieve account hashes (API may need approval): {hash_err}")
            print("You can retrieve hashes later once 'Accounts and Trading Production' is approved.")
            print("Continuing to Market Data app auth...")
        
    except Exception as e:
        print(f"[ERROR] Accounts auth failed: {e}")
        sys.exit(1)

    # 4. Market Data App Auth
    print("\n[2/2] Authenticating MARKET DATA app...")
    tmp_market = "token_market_tmp.json"
    try:
        schwab.auth.client_from_login_flow(
            config.SCHWAB_MARKET_APP_KEY,
            config.SCHWAB_MARKET_APP_SECRET,
            config.SCHWAB_CALLBACK_URL,
            tmp_market
        )
        
        with open(tmp_market, 'r') as f:
            token_data = json.load(f)
            
        if schwab_token_store.save_token(token_data, config.SCHWAB_TOKEN_BLOB_MARKET):
            print(f"[OK] Market Data token uploaded to GCS: {config.SCHWAB_TOKEN_BLOB_MARKET}")
        else:
            print("[ERROR] Failed to upload Market Data token to GCS.")
            sys.exit(1)
            
        if os.path.exists(tmp_market):
            os.remove(tmp_market)
        
    except Exception as e:
        print(f"[ERROR] Market Data auth failed: {e}")
        sys.exit(1)

    # 5. Final Verification
    print("\nVerifying GCS storage...")
    if schwab_token_store.load_token(config.SCHWAB_TOKEN_BLOB_ACCOUNTS) and \
       schwab_token_store.load_token(config.SCHWAB_TOKEN_BLOB_MARKET):
        print("\n" + "="*60)
        print("[OK] SUCCESS: Both tokens stored and verified in GCS.")
        print("Next: deploy the Cloud Function keep-alive (P5-S-B).")
        print("="*60)
    else:
        print("[ERROR] Verification failed: Tokens not readable from GCS.")

if __name__ == "__main__":
    run_auth()
