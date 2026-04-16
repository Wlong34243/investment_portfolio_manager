"""
tasks/format_sheets_dashboard_v2.py — Applies V2 formatting to all tabs.
"""

import time
import os
import sys
import typer
from typing import List, Optional

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client

try:
    from gspread_formatting import (
        CellFormat, Color, TextFormat, Border, Borders,
        format_cell_range, set_frozen, NumberFormat,
        set_column_width, set_row_height, ConditionalFormatRule, BooleanRule,
        BooleanCondition, GradientRule, InterpolationPoint,
        get_conditional_format_rules, GridRange
    )
    HAS_FORMATTING = True
except ImportError:
    HAS_FORMATTING = False

app = typer.Typer()

# --- Shared Colors ---
COLOR_NAVY = Color(0.10, 0.15, 0.27)  # #1a2744
COLOR_WHITE = Color(1, 1, 1)
COLOR_GREY_LIGHT = Color(0.95, 0.95, 0.95)  # #f3f3f3
COLOR_RED_DARK = Color(0.92, 0.26, 0.21)    # #ea4335
COLOR_RED_LIGHT = Color(0.99, 0.91, 0.90)   # #fce8e6
COLOR_GREEN_DARK = Color(0.20, 0.66, 0.33)  # #34a853
COLOR_GREEN_LIGHT = Color(0.85, 0.92, 0.83) # #d9ead3
COLOR_YELLOW_LIGHT = Color(1.0, 0.95, 0.80) # #fff2cc
COLOR_BLUE_LIGHT = Color(0.81, 0.89, 0.95)  # #cfe2f3
COLOR_ORANGE = Color(1.0, 0.60, 0.0)        # #ff9900

def safe_format(ws, range_name, fmt, retries=3):
    """Applies formatting with retry logic for API quota limits."""
    for i in range(retries):
        try:
            format_cell_range(ws, range_name, fmt)
            return True
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                wait = (i + 1) * 5
                print(f"  ⚠ Quota exceeded, waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise e
    return False

def save_rules(ws, rules):
    """Robustly saves conditional format rules to the worksheet."""
    try:
        rules.save()
        # Add a sleep after every rule update as it is a heavy API call
        time.sleep(3)
    except Exception as e:
        if "429" in str(e):
            print("  ⚠ Quota exceeded on rules save, skipping.")
        else:
            raise e

def apply_alternating_banding(ws, start_row, end_row):
    """Applies alternating row banding."""
    rules = get_conditional_format_rules(ws)
    # Remove existing banding rules to prevent duplication
    new_rules = [r for r in rules if not (isinstance(r.booleanRule, BooleanRule) and "ISEVEN(ROW())" in str(r.booleanRule.condition.values))]
    
    # We must append the rule and clear the old ones safely in the rules object
    rules.clear()
    for r in new_rules:
        rules.append(r)
        
    rules.append(ConditionalFormatRule(
        ranges=[GridRange.from_a1_range(f"A{start_row}:Z{end_row}", ws)],
        booleanRule=BooleanRule(
            condition=BooleanCondition("CUSTOM_FORMULA", [f"=ISEVEN(ROW())"]),
            format=CellFormat(backgroundColor=COLOR_GREY_LIGHT)
        )
    ))
    
    save_rules(ws, rules)

def format_valuation_card(spreadsheet):
    """Part 1: Valuation_Card formatting"""
    tab_name = "Valuation_Card"
    try:
        ws = spreadsheet.worksheet(tab_name)
        set_frozen(ws, rows=1, cols=1)
        
        widths = {
            "A": 70, "B": 180, "C": 110, "D": 75, "E": 95,
            "F": 95, "G": 70, "H": 70, "I": 80, "J": 80,
            "K": 110, "L": 130, "M": 90, "N": 70, "O": 70, "P": 110
        }
        for col, width in widths.items():
            set_column_width(ws, col, width)
            
        header_fmt = CellFormat(
            backgroundColor=COLOR_NAVY,
            textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10),
            horizontalAlignment="CENTER"
        )
        format_cell_range(ws, "A1:R1", header_fmt)
        
        rules = get_conditional_format_rules(ws)
        rules.clear()
        
        # 52w Position % color scale: 0=red, 50=white, 100=green
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("K2:K200", ws)],
            gradientRule=GradientRule(
                minpoint=InterpolationPoint(color=COLOR_RED_DARK, type="NUMBER", value="0"),
                midpoint=InterpolationPoint(color=COLOR_WHITE, type="NUMBER", value="50"),
                maxpoint=InterpolationPoint(color=COLOR_GREEN_DARK, type="NUMBER", value="100")
            )
        ))
        # Discount from 52w High %: >30% green, <10% red
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("L2:L200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["30"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))
        ))
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("L2:L200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["10"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))
        ))
        #Trailiing P/E: >40 light red, <15 light green
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("E2:E200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["40"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))
        ))
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("E2:E200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["15"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))
        ))
        # PEG: >2 light red, <1 light green
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("H2:H200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["2"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))
        ))
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("H2:H200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["1"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))
        ))
        save_rules(ws, rules)
        
        apply_alternating_banding(ws, 2, 200)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

def format_decision_view(spreadsheet):
    """Part 2: Decision_View formatting"""
    tab_name = "Decision_View"
    try:
        ws = spreadsheet.worksheet(tab_name)
        set_frozen(ws, rows=1, cols=1)
        
        widths = {
            "A": 70, "B": 70, "C": 110, "D": 100, "E": 90,
            "F": 80, "G": 90, "H": 100, "I": 120, "J": 200,
            "K": 200, "L": 90, "M": 400
        }
        for col, width in widths.items():
            set_column_width(ws, col, width)
            
        header_fmt = CellFormat(
            backgroundColor=COLOR_NAVY,
            textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10),
            horizontalAlignment="CENTER"
        )
        format_cell_range(ws, "A1:M1", header_fmt)
        
        set_row_height(ws, "2:200", 60)
        wrap_fmt = CellFormat(wrapStrategy="WRAP", verticalAlignment="MIDDLE")
        format_cell_range(ws, "A2:M200", wrap_fmt)
        
        rules = get_conditional_format_rules(ws)
        rules.clear()
        
        # TLH Flag: red bg, white bold
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("L2:L200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("TEXT_CONTAINS", ["TLH"]), format=CellFormat(backgroundColor=COLOR_RED_DARK, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE)))
        ))
        # Highlight full row if TLH
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("A2:M200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("CUSTOM_FORMULA", ['=ISNUMBER(SEARCH("TLH", $L2))']), format=CellFormat(backgroundColor=COLOR_YELLOW_LIGHT, textFormat=TextFormat(bold=True)))
        ))
        # Valuation Signal colors
        signal_map = {"accumulate": COLOR_GREEN_LIGHT, "trim": COLOR_RED_LIGHT, "hold": COLOR_YELLOW_LIGHT, "monitor": COLOR_BLUE_LIGHT}
        for val, color in signal_map.items():
            rules.append(ConditionalFormatRule(
                ranges=[GridRange.from_a1_range("I2:I200", ws)],
                booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", [val]), format=CellFormat(backgroundColor=color))
            ))
        # Unreal G/L %: green font if > 0, red if < 0
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("D2:D200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_GREEN_DARK)))
        ))
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("D2:D200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_RED_DARK)))
        ))
        # 52w Pos % color scale: low=green, high=red
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("G2:G200", ws)],
            gradientRule=GradientRule(
                minpoint=InterpolationPoint(color=COLOR_GREEN_DARK, type="NUMBER", value="0"),
                midpoint=InterpolationPoint(color=COLOR_WHITE, type="NUMBER", value="50"),
                maxpoint=InterpolationPoint(color=COLOR_RED_DARK, type="NUMBER", value="100")
            )
        ))
        save_rules(ws, rules)
        
        apply_alternating_banding(ws, 2, 200)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

def format_agent_outputs_v2(spreadsheet):
    """Part 3: Agent_Outputs revised formatting"""
    tab_name = config.TAB_AGENT_OUTPUTS
    try:
        ws = spreadsheet.worksheet(tab_name)
        all_values = ws.get_all_values()
        
        # Ensure frozen summary row exists
        first_cell = all_values[0][0] if all_values and all_values[0] else None
        if first_cell and "Accumulate:" not in str(first_cell):
            ws.insert_row([""], 1)
            time.sleep(1)
            all_values = ws.get_all_values() # Refresh
            
        # Detect where headers are (usually Row 2 now)
        header_row_idx = 1
        headers = all_values[header_row_idx]
        
        def get_col_letter(name):
            try:
                idx = next(i for i, h in enumerate(headers) if h.strip().lower() == name.lower())
                return chr(ord('A') + idx), idx + 1
            except StopIteration:
                return None, None

        col_agent_let, col_agent_idx = get_col_letter('agent')
        col_signal_let, col_signal_idx = get_col_letter('signal_type')
        col_action_let, col_action_idx = get_col_letter('action')
        col_rationale_let, col_rationale_idx = get_col_letter('rationale')
        
        # Default fallback indices if detection fails
        col_agent_let = col_agent_let or 'B'
        col_agent_idx = col_agent_idx or 2
        col_signal_let = col_signal_let or 'E'
        col_signal_idx = col_signal_idx or 5
        col_action_let = col_action_let or 'F'
        col_action_idx = col_action_idx or 6
        col_rationale_let = col_rationale_let or 'H'
        
        # Summary Row (Row 1)
        # Using detected column letters
        summary_formula = (
            f'="Accumulate: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"accumulate")&'
            f'" | Trim: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"trim")&'
            f'" | TLH: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"tlh_candidate")&'
            f'" | Rebalance: "&COUNTIF({col_action_let}3:{col_action_let}1000,"Rebalance")&'
            f'" | Monitor: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"monitor")'
        )
        ws.update(range_name='A1', values=[[summary_formula]], value_input_option="USER_ENTERED")
        
        # Split merge to avoid "You can't merge frozen and non-frozen columns" error
        # Freezing cols A-D (indices 1-4)
        ws.merge_cells("A1:D1")
        ws.merge_cells("E1:K1")
        
        format_cell_range(ws, "A1:K1", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=12), horizontalAlignment="CENTER"))
        
        # Header Row is now Row 2
        format_cell_range(ws, "A2:K2", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE), horizontalAlignment="CENTER"))
        set_frozen(ws, rows=2, cols=4)
        
        # Note in Summary Narrative (Col K) for valuation noise
        rules = get_conditional_format_rules(ws)
        rules.clear()
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("I3:K1000", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("TEXT_CONTAINS", ["Insufficient data"]), format=CellFormat(textFormat=TextFormat(italic=True, foregroundColor=Color(0.5, 0.5, 0.5))))
        ))
        # Highlight 3 tax rebalance rows
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("A3:K1000", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("CUSTOM_FORMULA", [f'=AND(${col_agent_let}3="tax", ${col_action_let}3="Rebalance")']), format=CellFormat(backgroundColor=COLOR_YELLOW_LIGHT, textFormat=TextFormat(bold=True)))
        ))
        save_rules(ws, rules)
        
        # Visual grouping by agent (thick top border for first row of new agent)
        # Read Agent column
        agents = ws.col_values(col_agent_idx)[2:] # Skip summary and header
        if agents:
            current_agent = None
            for i, agent in enumerate(agents):
                if agent != current_agent:
                    row_num = i + 3
                    border = Border("SOLID_THICK", COLOR_NAVY)
                    format_cell_range(ws, f"A{row_num}:K{row_num}", CellFormat(borders=Borders(top=border), backgroundColor=COLOR_GREY_LIGHT))
                    current_agent = agent
                    time.sleep(0.1)
        
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

def format_holdings_current_v2(spreadsheet):
    """Part 4: Holdings_Current KPI Fix"""
    tab_name = config.TAB_HOLDINGS_CURRENT
    try:
        ws = spreadsheet.worksheet(tab_name)
        all_values = ws.get_all_values()
        
        # In V2 layout:
        # Row 1: KPI Dashboard
        # Row 2: Headers
        # Row 3+: Data
        header_row_idx = 1 # 0-indexed means Row 2
        if len(all_values) <= header_row_idx:
            print(f"  ⚠ Not enough rows in {tab_name} to find headers at Row 2")
            return
            
        headers = all_values[header_row_idx]
        data_start_row = 3 # 1-based sheet row for data
        
        # Verify if Row 2 actually contains headers (check for 'Ticker')
        if 'Ticker' not in [str(h).strip() for h in headers]:
            # Fallback search if Row 2 is empty/wrong
            header_row_idx = -1
            for i, row in enumerate(all_values[:5]):
                if 'Ticker' in row or 'ticker' in [str(h).strip().lower() for h in row]:
                    header_row_idx = i
                    break
            
            if header_row_idx == -1:
                print(f"  ⚠ Could not find headers for {tab_name} in first 5 rows")
                return
            headers = all_values[header_row_idx]
            data_start_row = header_row_idx + 2

        def get_col_letter(name):
            try:
                # Case insensitive match
                idx = next(i for i, h in enumerate(headers) if h.strip().lower() == name.lower())
                return chr(ord('A') + idx)
            except StopIteration:
                return None

        col_ticker = get_col_letter('Ticker') or 'A'
        col_mv = get_col_letter('Market Value') or 'G'
        col_cb = get_col_letter('Cost Basis') or 'H'
        col_ugl = get_col_letter('Unrealized G/L') or 'J'
        
        # KPI Row (Row 1) - Labels and Formulas
        kpi_data = [
            "📊 PORTFOLIO SNAPSHOT", "", 
            'Total Value: ', f'=SUM({col_mv}{data_start_row}:{col_mv}200)',
            'Dry Powder: ', f'=SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"CASH_MANUAL",{col_mv}{data_start_row}:{col_mv}200)+SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"SGOV",{col_mv}{data_start_row}:{col_mv}200)',
            'Cash + SGOV: ', f'=SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"CASH_MANUAL",{col_mv}{data_start_row}:{col_mv}200)+SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"SGOV",{col_mv}{data_start_row}:{col_mv}200)+SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"QACDS",{col_mv}{data_start_row}:{col_mv}200)',
            'G/L %: ', f'=SUM({col_ugl}{data_start_row}:{col_ugl}200)/SUM({col_cb}{data_start_row}:{col_cb}200)',
            'Positions: ', f'=COUNTA({col_ticker}{data_start_row}:{col_ticker}200)-COUNTIF({col_ticker}{data_start_row}:{col_ticker}200,"CASH_MANUAL")-COUNTIF({col_ticker}{data_start_row}:{col_ticker}200,"QACDS")'
        ]
        ws.update(range_name="A1:L1", values=[kpi_data], value_input_option="USER_ENTERED")
        
        format_cell_range(ws, "D1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))
        format_cell_range(ws, "F1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))
        format_cell_range(ws, "H1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))
        
        print(f"  ✓ updated KPI for {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to update KPI for {tab_name}: {e}")

def format_realized_gl_v2(spreadsheet):
    """Part 5: Realized_GL Wash Sale UI"""
    tab_name = config.TAB_REALIZED_GL
    try:
        ws = spreadsheet.worksheet(tab_name)
        
        # Ensure second KPI row
        row2_val = ws.cell(2, 1).value
        if row2_val and "WASH SALE RISK" not in str(row2_val):
            ws.insert_row([""], 2)
            time.sleep(1)
            
        # Row 1 formatting update for Disallowed Loss
        # Assuming Disallowed Loss Label is in I1 and Value in J1 (based on previous format_realized_gl)
        format_cell_range(ws, "J1", CellFormat(textFormat=TextFormat(bold=True, foregroundColor=COLOR_RED_DARK, fontSize=12), numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0')))
        
        # Row 2 Wash Sale Warning
        ws.update(range_name="A2", values=[["⚠️ WASH SALE RISK: Review before year-end. Disallowed losses cannot offset gains."]], value_input_option="USER_ENTERED")
        ws.merge_cells("A2:S2")
        format_cell_range(ws, "A2:S2", CellFormat(backgroundColor=COLOR_ORANGE, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE), horizontalAlignment="CENTER"))
        
        # Row 3 is now Header, Data starts at Row 4
        set_frozen(ws, rows=3, cols=0)
        
        rules = get_conditional_format_rules(ws)
        rules.clear()
        
        # Flag rows where Disallowed Loss > 0 (Col R)
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("A4:S500", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("CUSTOM_FORMULA", ["=$R4>0"]), format=CellFormat(backgroundColor=COLOR_YELLOW_LIGHT))
        ))
        # Red border on Disallowed Loss cell (Col R)
        # Borders can't be easily applied via conditional formatting in gspread-formatting currently
        # but we can do a background color change
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("R4:R500", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT, textFormat=TextFormat(bold=True, foregroundColor=COLOR_RED_DARK)))
        ))
        save_rules(ws, rules)
        
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

@app.command()
def main(
    live: bool = typer.Option(False, "--live", help="Write formatting (default: dry run)"),
):
    if not HAS_FORMATTING:
        typer.echo("ERROR: pip install gspread-formatting")
        raise typer.Exit(code=1)

    if not live:
        typer.echo("DRY RUN — no changes will be written. Pass --live to apply.")
        return
    
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    print(f"Formatting spreadsheet: {spreadsheet.title} ({config.PORTFOLIO_SHEET_ID})")
    
    format_valuation_card(spreadsheet)
    time.sleep(2)
    format_decision_view(spreadsheet)
    time.sleep(2)
    format_agent_outputs_v2(spreadsheet)
    time.sleep(2)
    format_holdings_current_v2(spreadsheet)
    time.sleep(2)
    format_realized_gl_v2(spreadsheet)
    
    typer.echo("✅ V2 Formatting task complete.")

if __name__ == "__main__":
    app()