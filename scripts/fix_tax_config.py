from utils.sheet_readers import get_gspread_client
import config

def add_tax_config():
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_CONFIG)
    
    # Read existing
    all_vals = ws.get_all_values()
    existing_keys = [r[0] for r in all_vals if r]
    
    new_rows = [
        ['tax_rate_short_term', '0.37', "Bill's actual ST rate (Phase 3)"],
        ['tax_rate_long_term', '0.20', "Bill's actual LT rate (Phase 3)"],
        ['tax_estimated_tax_alert_threshold', '5000', 'Red background threshold for estimated tax'],
        ['tax_wash_sale_cluster_threshold', '3', 'Amber background threshold for wash sale count']
    ]
    
    to_add = [r for r in new_rows if r[0] not in existing_keys]
    
    if to_add:
        print(f"Adding {len(to_add)} config keys...")
        ws.append_rows(to_add, value_input_option='USER_ENTERED')
    else:
        print("Tax config keys already exist.")
        # If they exist but were read as 0, let's update them
        for r in new_rows:
            try:
                cell = ws.find(r[0])
                ws.update_cell(cell.row, 2, r[1])
                print(f"Updated {r[0]} to {r[1]}")
            except:
                pass

if __name__ == "__main__":
    add_tax_config()
