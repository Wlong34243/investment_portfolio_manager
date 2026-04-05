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

def run_all_tests():
    success = test_imports()
    if success:
        test_agent_type_safety()
    print("\n--- Smoke Test Complete ---")

if __name__ == "__main__":
    run_all_tests()
