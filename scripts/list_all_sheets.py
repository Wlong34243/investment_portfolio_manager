import os
import sys

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.sheet_readers import get_gspread_client

def main():
    try:
        gc = get_gspread_client()
        files = gc.list_spreadsheet_files()
        print("Spreadsheets visible to service account:")
        for f in files:
            print(f"  - {f['name']} (ID: {f['id']})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
