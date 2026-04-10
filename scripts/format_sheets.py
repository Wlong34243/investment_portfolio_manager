"""
scripts/format_sheets.py — Applies professional formatting to the Portfolio Sheet.
Sets currencies, percentages, freezes headers, and sets column widths.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils.sheet_readers import get_gspread_client

def apply_formatting():
    client = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    
    tabs = [config.TAB_HOLDINGS_CURRENT, config.TAB_HOLDINGS_HISTORY]
    
    for tab_name in tabs:
        print(f"Applying formats to {tab_name}...")
        ws = spreadsheet.worksheet(tab_name)
        
        # 1. Freeze Header and Set Bold
        # 2. Apply Number Formats:
        #    A-D (Ticker, Desc, Class, Strat): Text
        #    E (Qty): #,##0.00
        #    F-I (Price, MV, Cost, Unit Cost): $#,##0.00
        #    J (Unrealized G/L): $#,##0.00 (Conditional Red/Green is harder, but we'll do currency)
        #    K (G/L %): 0.00%
        #    L (Inc): $#,##0.00
        #    M (Yield): 0.00%
        #    Q (Daily Change %): 0.00%
        #    R (Weight): 0.00%
        
        requests = [
            # Freeze Row 1
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws.id,
                        "gridProperties": {"frozenRowCount": 1}
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            },
            # Bold Header Row
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)"
                }
            },
            # Currency Format ($) for columns F-J (5-10 index) and L (11 index)
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": 5, "endColumnIndex": 10},
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": 11, "endColumnIndex": 12},
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            },
            # Percentage Format (%) for K (10), M (12), Q (16), R (17)
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": 10, "endColumnIndex": 11},
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "PERCENT", "pattern": "0.00%"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": 12, "endColumnIndex": 13},
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "PERCENT", "pattern": "0.00%"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": 16, "endColumnIndex": 18},
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "PERCENT", "pattern": "0.00%"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            },
            # Column Widths
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                    "properties": {"pixelSize": 80}, # Ticker
                    "fields": "pixelSize"
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                    "properties": {"pixelSize": 250}, # Description
                    "fields": "pixelSize"
                }
            }
        ]
        
        spreadsheet.batch_update({"requests": requests})
    
    print("✅ Formatting complete.")

if __name__ == "__main__":
    apply_formatting()
