import gspread
import time
import config
from utils.sheet_readers import get_gspread_client

# Define the schema based on PORTFOLIO_SHEET_SCHEMA.md
SCHEMA = {
    "Holdings_Current": [
        "Ticker", "Description", "Asset Class", "Asset Strategy", "Quantity", 
        "Price", "Market Value", "Cost Basis", "Unit Cost", "Unrealized G/L", 
        "Unrealized G/L %", "Est Annual Income", "Dividend Yield", "Acquisition Date", 
        "Wash Sale", "Is Cash", "Weight", "Import Date", "Fingerprint"
    ],
    "Holdings_History": [
        "Ticker", "Description", "Asset Class", "Asset Strategy", "Quantity", 
        "Price", "Market Value", "Cost Basis", "Unit Cost", "Unrealized G/L", 
        "Unrealized G/L %", "Est Annual Income", "Dividend Yield", "Acquisition Date", 
        "Wash Sale", "Is Cash", "Weight", "Import Date", "Fingerprint"
    ],
    "Daily_Snapshots": [
        "Date", "Total Value", "Total Cost", "Total Unrealized G/L", 
        "Cash Value", "Invested Value", "Position Count", "Fingerprint"
    ],
    "Transactions": [
        "Trade Date", "Settlement Date", "Ticker", "Description", "Action", 
        "Quantity", "Price", "Amount", "Fees", "Net Amount", "Account", "Fingerprint"
    ],
    "Target_Allocation": [
        "Asset Class", "Asset Strategy", "Target %", "Min %", "Max %", "Notes"
    ],
    "Risk_Metrics": [
        "Date", "Portfolio Beta", "Top Position Conc %", "Top Position Ticker", 
        "Top Sector Conc %", "Top Sector", "Estimated VaR 95%", "Stress -10% Impact", "Fingerprint"
    ],
    "Income_Tracking": [
        "Date", "Projected Annual Income", "Blended Yield %", "Top Generator Ticker", 
        "Top Generator Income", "Cash Yield Contribution", "Fingerprint"
    ],
    "Realized_GL": [
        "Ticker", "Description", "Closed Date", "Opened Date", "Holding Days", 
        "Quantity", "Proceeds Per Share", "Cost Per Share", "Proceeds", 
        "Cost Basis", "Unadjusted Cost", "Gain Loss $", "Gain Loss %", 
        "LT Gain Loss", "ST Gain Loss", "Term", "Wash Sale", 
        "Disallowed Loss", "Account", "Is Primary Acct", "Import Date", "Fingerprint"
    ],
    "Config": [
        "Key", "Value", "Description"
    ],
    "Logs": [
        "Timestamp", "Level", "Source", "Message", "Details"
    ]
}

TABS_TO_FREEZE = ["Holdings_Current", "Holdings_History", "Daily_Snapshots", "Realized_GL"]

def create_sheets():
    print(f"Opening spreadsheet: {config.PORTFOLIO_SHEET_ID}")
    client = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    
    # Get existing worksheets
    existing_worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}
    
    for tab_name, headers in SCHEMA.items():
        if tab_name in existing_worksheets:
            print(f"Tab '{tab_name}' already exists. Skipping creation.")
            ws = existing_worksheets[tab_name]
        else:
            print(f"Creating tab '{tab_name}'...")
            ws = spreadsheet.add_worksheet(title=tab_name, rows="100", cols=len(headers))
            # Wait a bit to avoid rate limits
            time.sleep(1)
        
        # Check if header exists, if not, write it
        try:
            first_row = ws.row_values(1)
            if not first_row or first_row != headers:
                print(f"Writing headers for '{tab_name}'...")
                ws.insert_row(headers, 1)
                time.sleep(1)
        except Exception as e:
            print(f"Error checking/writing headers for {tab_name}: {e}")

        # Freeze row 1 if applicable
        if tab_name in TABS_TO_FREEZE:
            print(f"Freezing row 1 for '{tab_name}'...")
            ws.freeze(rows=1)
            time.sleep(1)
            
        # Print tab info
        row_count = ws.row_count
        print(f"SUCCESS: '{tab_name}' | Rows: {row_count}")

    # Final confirmation
    final_worksheets = [ws.title for ws in spreadsheet.worksheets()]
    print("\nFinal Tab List:")
    for title in final_worksheets:
        print(f" - {title}")

if __name__ == "__main__":
    create_sheets()
