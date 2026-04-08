"""
scripts/schwab_manual_reauth.py — Emergency token recovery.
Use if tokens expire or connectivity is lost.
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

from utils import schwab_token_store, schwab_client
import config

def run_reauth():
    print("="*60)
    print("Schwab Manual Re-Auth — Emergency Recovery")
    print("="*60)

    # 1. Accounts App Re-Auth
    print("\n[1/2] Re-authenticating ACCOUNTS app...")
    tmp_accounts = "token_accounts_reauth.json"
    try:
        client = schwab.auth.client_from_login_flow(
            config.SCHWAB_ACCOUNTS_APP_KEY,
            config.SCHWAB_ACCOUNTS_APP_SECRET,
            config.SCHWAB_CALLBACK_URL,
            tmp_accounts
        )
        with open(tmp_accounts, 'r') as f:
            token_data = json.load(f)
        
        if schwab_token_store.save_token(token_data, config.SCHWAB_TOKEN_BLOB_ACCOUNTS):
            print(f"✅ Accounts token updated in GCS.")
            
            # Verify connectivity immediately
            print("Verifying connectivity...")
            df = schwab_client.fetch_positions(client)
            if not df.empty:
                print(f"✅ Success: API returned {len(df)} positions.")
            else:
                print("⚠️ Warning: API connected but returned 0 positions.")
        else:
            print("❌ Failed to save Accounts token to GCS.")
            
        if os.path.exists(tmp_accounts): 
            os.remove(tmp_accounts)
    except Exception as e:
        print(f"❌ Accounts re-auth failed: {e}")

    # 2. Market Data App Re-Auth
    print("\n[2/2] Re-authenticating MARKET DATA app...")
    tmp_market = "token_market_reauth.json"
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
            print(f"✅ Market Data token updated in GCS.")
        else:
            print("❌ Failed to save Market Data token to GCS.")
            
        if os.path.exists(tmp_market): 
            os.remove(tmp_market)
    except Exception as e:
        print(f"❌ Market Data re-auth failed: {e}")

    # 3. Clear any existing alerts
    print("\nClearing standing API alerts...")
    if schwab_token_store.clear_alert():
        print("✅ Alerts cleared.")
    
    print("\nRecovery complete.")

if __name__ == "__main__":
    run_reauth()
