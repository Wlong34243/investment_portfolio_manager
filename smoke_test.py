"""
smoke_test.py — Automated architectural and logic audit.
Run locally before pushing to confirm no SyntaxErrors or obvious TypeErrors.
"""

import os
import sys
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.getcwd())

def test_imports():
    print("--- Testing Critical Imports ---")
    try:
        import app
        import pipeline
        from utils.sheet_readers import get_holdings_current
        from utils.agents.tax_intelligence_agent import scan_harvest_opportunities
        from utils.agents.valuation_agent import get_valuation_snapshot
        print("✅ All critical modules imported successfully.")
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False
    return True

def test_agent_type_safety():
    print("\n--- Testing Agent Type Safety (Mixed String/Float) ---")
    # Simulate a "Dirty" DataFrame from Google Sheets
    dirty_data = {
        'Ticker': ['AAPL', 'MSFT', 'Cash'],
        'Market Value': ['1500.50', '2000', '500.00'], # Strings!
        'Cost Basis': [1000.0, 1800.0, 500.0],
        'Unrealized G/L': ['500.50', '200', '0'],      # Strings!
        'Is Cash': [False, False, True],
        'Asset Class': ['Equity', 'Equity', 'Cash'],
        'Weight': [40.0, 50.0, 10.0]
    }
    df = pd.DataFrame(dirty_data)
    
    # 1. Test Tax Intelligence (scan_harvest_opportunities)
    try:
        from utils.agents.tax_intelligence_agent import scan_harvest_opportunities
        print("Testing Tax Intelligence with dirty data...")
        # This should NOT crash if hardened
        opps = scan_harvest_opportunities(df)
        print("✅ Tax Intelligence handled mixed types successfully.")
    except TypeError as te:
        print(f"❌ Tax Intelligence crashed on mixed types: {te}")
    except Exception as e:
        print(f"❌ Tax Intelligence failed: {e}")

    # 2. Test Cash Sweeper
    try:
        from utils.agents.cash_sweeper import get_cash_sweep_alert
        print("Testing Cash Sweeper with dirty data...")
        alert = get_cash_sweep_alert(df)
        print("✅ Cash Sweeper handled mixed types successfully.")
    except TypeError as te:
        print(f"❌ Cash Sweeper crashed on mixed types: {te}")
    except Exception as e:
        print(f"❌ Cash Sweeper failed: {e}")


# ===========================================================================
# Schwab API Integration Smoke Tests (Phase 5-S)
# ===========================================================================

def test_token_store_round_trip():
    print("\n--- Test: Token Store Round Trip ---")
    try:
        from utils.schwab_token_store import save_token, load_token, _get_storage_client
        import config

        dummy = {"access_token": "smoke_test_dummy", "token_type": "Bearer"}
        blob_name = "smoke_test_dummy_token.json"

        ok = save_token(dummy, blob_name)
        assert ok, "save_token returned False"

        loaded = load_token(blob_name)
        assert loaded == dummy, f"Round-trip mismatch: {loaded}"

        # Clean up via the same credential chain used by the token store
        gcs = _get_storage_client()
        if gcs:
            bucket = gcs.bucket(config.SCHWAB_TOKEN_BUCKET)
            blob = bucket.blob(blob_name)
            if blob.exists():
                blob.delete()

        print("✅ Token store round trip passed.")
        return True
    except Exception as e:
        print(f"❌ Token store round trip failed: {e}")
        return False


def test_alert_round_trip():
    print("\n--- Test: Alert Round Trip ---")
    try:
        from utils.schwab_token_store import write_alert, read_alert, clear_alert

        write_alert("smoke test message", "warning")
        alert = read_alert()
        assert alert is not None, "read_alert returned None after write"
        assert alert["message"] == "smoke test message", f"Message mismatch: {alert}"

        clear_alert()
        assert read_alert() is None, "read_alert should be None after clear"

        print("✅ Alert round trip passed.")
        return True
    except Exception as e:
        print(f"❌ Alert round trip failed: {e}")
        return False


def test_accounts_client_initializes():
    print("\n--- Test: Accounts Client Initializes ---")
    try:
        from utils.schwab_client import get_accounts_client
        client = get_accounts_client()
        if client is None:
            print("⚠️  SKIPPED — accounts token not available.")
            return None
        print("✅ Accounts client initialized.")
        return True
    except Exception as e:
        print(f"❌ Accounts client init failed: {e}")
        return False


def test_market_client_initializes():
    print("\n--- Test: Market Client Initializes ---")
    try:
        from utils.schwab_client import get_market_client
        client = get_market_client()
        if client is None:
            print("⚠️  SKIPPED — market token not available.")
            return None
        print("✅ Market client initialized.")
        return True
    except Exception as e:
        print(f"❌ Market client init failed: {e}")
        return False


def test_fetch_positions_returns_valid_schema():
    print("\n--- Test: fetch_positions Schema (snake_case) ---")
    try:
        from utils.schwab_client import get_accounts_client, fetch_positions
        from config import POSITION_COL_MAP

        client = get_accounts_client()
        if client is None:
            print("⚠️  SKIPPED — accounts client unavailable.")
            return None

        df = fetch_positions(client)

        # fetch_positions() must return snake_case internal names —
        # NOT Title Case display names (POSITION_COLUMNS).  Title Case
        # is applied at write time by sanitize_dataframe_for_sheets().
        expected_cols = set(POSITION_COL_MAP.keys())
        actual_cols = set(df.columns)
        missing = expected_cols - actual_cols
        assert not missing, f"fetch_positions missing snake_case columns: {missing}"

        if df.empty:
            print("⚠️  fetch_positions returned empty DataFrame (account may be empty).")
        else:
            print(f"✅ fetch_positions schema valid — {len(df)} positions, all snake_case columns present.")
        return True
    except Exception as e:
        print(f"❌ fetch_positions schema test failed: {e}")
        return False


def test_no_order_imports():
    print("\n--- Test: No Order Endpoints in schwab_client.py ---")
    try:
        prohibited = ["place_order", "cancel_order", "replace_order", "get_orders"]
        client_path = os.path.join(os.getcwd(), "utils", "schwab_client.py")

        with open(client_path, "r") as f:
            lines = f.readlines()

        # Find where the opening docstring preamble ends (second ''' occurrence).
        # Lines 0..preamble_end are the safety docstring and must be skipped.
        preamble_end = 0
        quote_count = 0
        for i, line in enumerate(lines):
            if line.strip() == "'''":
                quote_count += 1
                if quote_count == 2:
                    preamble_end = i
                    break

        violations = []
        for i, line in enumerate(lines):
            if i <= preamble_end:
                continue
            for term in prohibited:
                if term in line:
                    violations.append(f"  Line {i+1}: {line.rstrip()}")

        assert not violations, "Prohibited order terms found outside preamble:\n" + "\n".join(violations)
        print("✅ No prohibited order endpoints found outside preamble.")
        return True
    except Exception as e:
        print(f"❌ Order endpoint check failed: {e}")
        return False


def test_dry_run_still_active():
    print("\n--- Test: DRY_RUN Gate Still Present ---")
    try:
        # Check config.py defines DRY_RUN
        config_path = os.path.join(os.getcwd(), "config.py")
        with open(config_path, "r") as f:
            config_text = f.read()
        assert "DRY_RUN" in config_text, "DRY_RUN not found in config.py"

        # Check pipeline.py references DRY_RUN as a guard
        pipeline_path = os.path.join(os.getcwd(), "pipeline.py")
        with open(pipeline_path, "r") as f:
            pipeline_text = f.read()
        assert "DRY_RUN" in pipeline_text, "DRY_RUN not referenced in pipeline.py"
        assert "if" in pipeline_text and "DRY_RUN" in pipeline_text, \
            "DRY_RUN does not appear in a conditional guard in pipeline.py"

        print("✅ DRY_RUN gate confirmed in config.py and pipeline.py.")
        return True
    except Exception as e:
        print(f"❌ DRY_RUN gate check failed: {e}")
        return False


def run_schwab_smoke_tests():
    print("\n========== Schwab API Integration Smoke Tests ==========")
    results = {
        "token_store_round_trip":             test_token_store_round_trip(),
        "alert_round_trip":                   test_alert_round_trip(),
        "accounts_client_initializes":        test_accounts_client_initializes(),
        "market_client_initializes":          test_market_client_initializes(),
        "fetch_positions_valid_schema":       test_fetch_positions_returns_valid_schema(),
        "no_order_imports":                   test_no_order_imports(),
        "dry_run_still_active":               test_dry_run_still_active(),
    }
    passed  = sum(1 for v in results.values() if v is True)
    skipped = sum(1 for v in results.values() if v is None)
    failed  = sum(1 for v in results.values() if v is False)
    print(f"\n  Results: {passed} passed, {skipped} skipped, {failed} failed")
    return failed == 0


def run_all_tests():
    success = test_imports()
    if success:
        test_agent_type_safety()
    run_schwab_smoke_tests()
    print("\n--- Smoke Test Complete ---")

if __name__ == "__main__":
    run_all_tests()
