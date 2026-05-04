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
    print(f"Effective PORTFOLIO_SHEET_ID: {config.PORTFOLIO_SHEET_ID}")
    
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        print(f"Spreadsheet Title: {spreadsheet.title}")
        worksheets = spreadsheet.worksheets()
        print("Worksheets found:")
        for ws in worksheets:
            print(f"  - {ws.title} (ID: {ws.id})")
            # Let's check the first few cells of Valuation_Card and Decision_View
            if ws.title in ["Valuation_Card", "Decision_View"]:
                values = ws.get_all_values()
                print(f"    Rows: {len(values)}")
                if len(values) > 0:
                    print(f"    Headers: {values[0]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
