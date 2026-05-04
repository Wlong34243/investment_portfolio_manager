import os
import sys

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client

def main():
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        
        for tab_name in ["Valuation_Card", "Decision_View"]:
            ws = spreadsheet.worksheet(tab_name)
            values = ws.get_all_values()
            print(f"\n--- {tab_name} (Total Rows: {len(values)}) ---")
            for i, row in enumerate(values[:3]):
                print(f"Row {i+1}: {row}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
