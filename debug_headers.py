
import os
import sys
import pandas as pd

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client

def debug():
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = spreadsheet.worksheet(config.TAB_HOLDINGS_CURRENT)
    all_values = ws.get_all_values()
    
    print(f"Tab: {config.TAB_HOLDINGS_CURRENT}")
    for i, row in enumerate(all_values[:5]):
        print(f"Row {i+1}: {row}")

if __name__ == "__main__":
    debug()
