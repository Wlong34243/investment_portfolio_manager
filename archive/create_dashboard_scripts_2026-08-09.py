
import sys
import os
import time
# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils.sheet_readers import get_gspread_client

def create_dashboard():
    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    
    title = "Agent_Dashboard"
    try:
        ws = ss.add_worksheet(title=title, rows=100, cols=10)
        print(f"Created {title}")
    except:
        ws = ss.worksheet(title)
        print(f"{title} already exists")

    # 1. Setup Headers
    # We pull from Agent_Outputs (Compact 10-col format):
    # C: agent, D: signal, E: ticker, F: action, G: narrative, H: scale_step, I: severity
    headers = ["Ticker", "Signal", "Action", "Rationale", "Scale Step", "Severity", "Agent Source"]
    ws.update(range_name="A1:G1", values=[headers], value_input_option="USER_ENTERED")
    
    # 2. Add Dynamic Formula (Presentation Layer)
    # Range C2:I1000:
    # Col1=C(agent), Col2=D(signal), Col3=E(ticker), Col4=F(action), Col5=G(narrative), Col6=H(scale_step), Col7=I(severity)
    # Desired Dashboard Mapping:
    # A:Ticker(Col3), B:Signal(Col2), C:Action(Col4), D:Rationale(Col5), E:ScaleStep(Col6), F:Severity(Col7), G:Agent(Col1)
    formula = (
        "=QUERY(Agent_Outputs!C2:I1000, "
        "\"SELECT Col3, Col2, Col4, Col5, Col6, Col7, Col1 WHERE Col3 IS NOT NULL\", 0)"
    )
    
    ws.update(range_name="A2", values=[[formula]], value_input_option="USER_ENTERED")
    
    # 3. Apply basic formatting
    from gspread_formatting import (
        CellFormat, Color, TextFormat, format_cell_range, set_column_width, set_row_height
    )
    
    COLOR_NAVY = Color(0.10, 0.15, 0.27)
    COLOR_WHITE = Color(1, 1, 1)
    
    header_fmt = CellFormat(
        backgroundColor=COLOR_NAVY,
        textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=11),
        horizontalAlignment="CENTER"
    )
    format_cell_range(ws, "A1:G1", header_fmt)
    set_row_height(ws, "1", 40)
    
    # Widths
    set_column_width(ws, "A", 80)  # Ticker
    set_column_width(ws, "B", 100) # Signal
    set_column_width(ws, "C", 120) # Action
    set_column_width(ws, "D", 450) # Rationale
    set_column_width(ws, "E", 150) # Scale Step
    set_column_width(ws, "F", 90)  # Severity
    set_column_width(ws, "G", 100) # Agent
    
    # Wrap Rationale
    wrap_fmt = CellFormat(wrapStrategy="WRAP", verticalAlignment="TOP")
    format_cell_range(ws, "D2:D100", wrap_fmt)
    format_cell_range(ws, "C2:C100", wrap_fmt)
    
    print(f"✅ {title} presentation layer initialized.")

if __name__ == "__main__":
    create_dashboard()
