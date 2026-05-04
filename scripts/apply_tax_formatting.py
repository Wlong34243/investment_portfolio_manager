import gspread
from utils.sheet_readers import get_gspread_client
import config
from tasks.format_sheets_dashboard_v2 import format_tax_control

def run_tax_formatting():
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    print(f"Applying Tax_Control formatting to {ss.title}...")
    format_tax_control(ss)
    print("Done.")

if __name__ == "__main__":
    run_tax_formatting()
