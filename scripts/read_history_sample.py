
import os
import sys
import pandas as pd

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils.sheet_readers import get_gspread_client

def read_history_sample():
    client = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = spreadsheet.worksheet(config.TAB_HOLDINGS_HISTORY)
    
    # Get rows 1 to 4 (Header + 3 data rows)
    rows = ws.get("A1:T4")
    
    import json
    print(json.dumps(rows, indent=2))

if __name__ == "__main__":
    read_history_sample()
