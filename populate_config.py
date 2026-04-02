import gspread
import time
import config
from utils.sheet_readers import get_gspread_client

# Config keys from PORTFOLIO_SHEET_SCHEMA.md
CONFIG_ROWS = [
    ["rebalance_threshold_pct", "5", "Drift % that triggers rebalance alert"],
    ["cash_yield_pct", "4.5", "Current money market yield (default: 4.5)"],
    ["benchmark_ticker", "SPY", "Primary benchmark (default: SPY)"],
    ["tax_rate_short_term", "0.35", "Short-term cap gains rate for tax impact estimates"],
    ["tax_rate_long_term", "0.15", "Long-term cap gains rate"],
    ["contribution_target_monthly", "2000", "Target monthly contribution amount"],
    ["risk_free_rate", "0.045", "T-bill rate for CAPM (default: 0.045)"],
    ["market_premium", "0.055", "Equity risk premium for CAPM (default: 0.055)"]
]

def populate_config():
    print("Populating Config tab...")
    client = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = spreadsheet.worksheet("Config")
    
    # Check if already populated (more than just header)
    existing_data = ws.get_all_values()
    if len(existing_data) > 1:
        print("Config tab already has data. Skipping population.")
        return

    print(f"Writing {len(CONFIG_ROWS)} config rows...")
    ws.append_rows(CONFIG_ROWS, value_input_option='USER_ENTERED')
    print("SUCCESS: Config tab populated.")

if __name__ == "__main__":
    populate_config()
