
import os
import sys
import pandas as pd
import json

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils.sheet_readers import get_gspread_client

def read_sheet_sample(tab_name, limit=5):
    client = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = spreadsheet.worksheet(tab_name)
    
    # Get rows 1 to limit
    rows = ws.get(f"A1:T{limit}")
    
    print(json.dumps(rows, indent=2))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tab", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    
    read_sheet_sample(args.tab, args.limit)
