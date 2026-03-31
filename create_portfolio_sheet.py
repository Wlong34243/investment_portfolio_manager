import gspread
import argparse
import json
from datetime import datetime

# Import configuration from config_template
import config_template as config

def create_and_configure_portfolio_sheet(credentials_path, share_email):
    """
    Creates a new Google Sheet for the Investment Portfolio Manager,
    configures its tabs and headers, and shares it with the specified email.
    """
    try:
        # Authenticate with Google Sheets using service account
        gc = gspread.service_account(filename=credentials_path)
        print(f"Successfully authenticated with Google Sheets using {credentials_path}")

        # Create a new spreadsheet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sheet_title = f"Investment Portfolio - {timestamp}"
        spreadsheet = gc.create(sheet_title)
        print(f"Created new spreadsheet: '{sheet_title}' (ID: {spreadsheet.id})")

        # Share the spreadsheet with the specified email
        spreadsheet.share(share_email, perm_type='user', role='writer')
        print(f"Shared spreadsheet with {share_email} as a writer.")

        # Get the default "Sheet1" and rename it, or delete it later
        default_sheet = spreadsheet.get_worksheet(0)
        
        # Define tab names and their headers from config and schema
        tab_schemas = {
            config.TAB_HOLDINGS_CURRENT: [
                'Ticker', 'Description', 'Asset Class', 'Asset Strategy', 'Quantity', 'Price',
                'Market Value', 'Cost Basis', 'Unit Cost', 'Unrealized G/L', 'Unrealized G/L %',
                'Est Annual Income', 'Dividend Yield', 'Acquisition Date', 'Wash Sale', 'Is Cash',
                'Weight', 'Import Date', 'Fingerprint'
            ],
            config.TAB_HOLDINGS_HISTORY: [
                'Ticker', 'Description', 'Asset Class', 'Asset Strategy', 'Quantity', 'Price',
                'Market Value', 'Cost Basis', 'Unit Cost', 'Unrealized G/L', 'Unrealized G/L %',
                'Est Annual Income', 'Dividend Yield', 'Acquisition Date', 'Wash Sale', 'Is Cash',
                'Weight', 'Import Date', 'Fingerprint'
            ],
            config.TAB_DAILY_SNAPSHOTS: [
                'Date', 'Total Value', 'Total Cost', 'Total Unrealized G/L', 'Cash Value',
                'Invested Value', 'Position Count', 'Fingerprint'
            ],
            config.TAB_TRANSACTIONS: [
                'Trade Date', 'Settlement Date', 'Ticker', 'Description', 'Action', 'Quantity',
                'Price', 'Amount', 'Fees', 'Net Amount', 'Account', 'Fingerprint'
            ],
            config.TAB_TARGET_ALLOCATION: [
                'Asset Class', 'Asset Strategy', 'Target %', 'Min %', 'Max %', 'Notes'
            ],
            config.TAB_RISK_METRICS: [
                'Date', 'Portfolio Beta', 'Top Position Conc %', 'Top Position Ticker',
                'Top Sector Conc %', 'Top Sector', 'Estimated VaR 95%', 'Stress -10% Impact',
                'Fingerprint'
            ],
            config.TAB_INCOME_TRACKING: [
                'Date', 'Projected Annual Income', 'Blended Yield %', 'Top Generator Ticker',
                'Top Generator Income', 'Cash Yield Contribution', 'Fingerprint'
            ],
            config.TAB_REALIZED_GL: [
                'Ticker', 'Description', 'Closed Date', 'Opened Date', 'Holding Days',
                'Quantity', 'Proceeds Per Share', 'Cost Per Share', 'Proceeds', 'Cost Basis',
                'Unadjusted Cost', 'Gain Loss $', 'Gain Loss %', 'LT Gain Loss',
                'ST Gain Loss', 'Term', 'Wash Sale', 'Disallowed Loss', 'Account',
                'Is Primary Acct', 'Import Date', 'Fingerprint'
            ],
            config.TAB_CONFIG: [
                'Key', 'Value', 'Description'
            ]
        }

        # Rename default sheet to the first tab name and set header
        first_tab_name = list(tab_schemas.keys())[0]
        first_tab_headers = tab_schemas[first_tab_name]
        default_sheet.update_title(first_tab_name)
        default_sheet.append_row(first_tab_headers)
        print(f"Renamed default sheet to '{first_tab_name}' and set headers.")

        # Create remaining tabs and set their headers
        for tab_name, headers in list(tab_schemas.items())[1:]:
            worksheet = spreadsheet.add_worksheet(title=tab_name, rows="100", cols="26")
            worksheet.append_row(headers)
            print(f"Created tab '{tab_name}' and set headers.")
        
        print("\n--- Sheet Configuration Complete ---")
        print(f"Please update the PORTFOLIO_SHEET_ID in your config_template.py (or Streamlit secrets) with this ID:")
        print(f"Google Sheet ID: {spreadsheet.id}")
        print(f"Google Sheet URL: {spreadsheet.url}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create and configure a new Google Sheet for the Investment Portfolio Manager."
    )
    parser.add_argument(
        "--credentials",
        type=str,
        required=True,
        help="Path to the Google service account JSON key file."
    )
    parser.add_argument(
        "--share",
        type=str,
        required=True,
        help="Email address to share the created Google Sheet with (e.g., your.personal@gmail.com)."
    )

    args = parser.parse_args()
    create_and_configure_portfolio_sheet(args.credentials, args.share)
