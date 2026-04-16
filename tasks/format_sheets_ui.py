"""
Google Sheets UI Formatting Script
Applies visual formatting to Agent_Outputs, Holdings_Current,
Daily_Snapshots, and Realized_GL tabs.

Usage:
    python tasks/format_sheets_ui.py           # DRY RUN (default)
    python tasks/format_sheets_ui.py --live    # Write formatting to Sheet
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
        CellFormat, Color, TextFormat, borders, Border, Borders,
        format_cell_range, set_frozen, NumberFormat,
        set_column_width, set_row_height, ConditionalFormatRule, BooleanRule,
        BooleanCondition, GradientRule, InterpolationPoint,
        get_conditional_format_rules,
        GridRange
    )
    HAS_FORMATTING = True
except ImportError as e:
    print(f"DEBUG: ImportError: {e}")
    HAS_FORMATTING = False

app = typer.Typer()

# --- Shared Colors ---
COLOR_NAVY = Color(0.10, 0.15, 0.27)  # #1a2744
COLOR_WHITE = Color(1, 1, 1)
COLOR_GREY_LIGHT = Color(0.97, 0.98, 0.98)  # #f8f9fa
COLOR_RED_DARK = Color(0.92, 0.26, 0.21)    # #ea4335
COLOR_RED_LIGHT = Color(0.99, 0.91, 0.90)   # #fce8e6
COLOR_GREEN_DARK = Color(0.20, 0.66, 0.33)  # #34a853
COLOR_GREEN_LIGHT = Color(0.85, 0.92, 0.83) # #d9ead3
COLOR_YELLOW_LIGHT = Color(1.0, 0.95, 0.80) # #fff2cc
COLOR_BLUE_LIGHT = Color(0.81, 0.89, 0.95)  # #cfe2f3
COLOR_ORANGE = Color(1.0, 0.60, 0.0)        # #ff9900
COLOR_GREEN_MUTED = Color(0.58, 0.77, 0.49) # #93c47d

def hide_cols(spreadsheet, sheet_id, start_index, end_index):
    """Helper to hide columns using batch_update."""
    spreadsheet.batch_update({
        "requests": [{
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": start_index,
                    "endIndex": end_index,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser"
            }
        }]
    })

def apply_alternating_banding(ws, start_row, end_row, last_col_index):
    """Applies alternating row banding."""
    rules = get_conditional_format_rules(ws)
    rules.append(ConditionalFormatRule(
        ranges=[GridRange.from_a1_range(f"A{start_row}:Z{end_row}", ws)],
        booleanRule=BooleanRule(
            condition=BooleanCondition("CUSTOM_FORMULA", [f"=ISEVEN(ROW())"]),
            format=CellFormat(backgroundColor=COLOR_GREY_LIGHT)
        )
    ))
    rules.save()

def format_agent_outputs(spreadsheet):
    """Tab 1: Agent_Outputs — Priority Review View"""
    tab_name = config.TAB_AGENT_OUTPUTS
    try:
        ws = spreadsheet.worksheet(tab_name)
        hide_cols(spreadsheet, ws.id, 0, 3)
        
        widths = {
            "D": 80, "E": 110, "F": 120, "G": 110, "H": 90,
            "I": 420, "J": 150, "K": 380
        }
        for col, width in widths.items():
            set_column_width(ws, col, width)
            
        set_frozen(ws, rows=1, cols=4)
        
        header_fmt = CellFormat(
            backgroundColor=COLOR_NAVY,
            textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10),
            wrapStrategy="CLIP",
            horizontalAlignment="CENTER"
        )
        format_cell_range(ws, "A1:K1", header_fmt)
        
        rules = get_conditional_format_rules(ws)
        signal_map = {"accumulate": COLOR_GREEN_LIGHT, "trim": COLOR_RED_LIGHT, "hold": COLOR_YELLOW_LIGHT, "monitor": COLOR_BLUE_LIGHT}
        for val, color in signal_map.items():
            rules.append(ConditionalFormatRule(
                ranges=[GridRange.from_a1_range("E2:E1000", ws)],
                booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", [val]), format=CellFormat(backgroundColor=color))
            ))
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("E2:E1000", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["exit"]), format=CellFormat(backgroundColor=COLOR_RED_DARK, textFormat=TextFormat(foregroundColor=COLOR_WHITE)))
        ))
        severity_map = {"high": (COLOR_RED_DARK, COLOR_WHITE), "medium": (COLOR_ORANGE, COLOR_WHITE), "low": (COLOR_GREEN_MUTED, COLOR_WHITE)}
        for val, (bg, fg) in severity_map.items():
            rules.append(ConditionalFormatRule(
                ranges=[GridRange.from_a1_range("H2:H1000", ws)],
                booleanRule=BooleanRule(condition=BooleanCondition("TEXT_CONTAINS", [val]), format=CellFormat(backgroundColor=bg, textFormat=TextFormat(foregroundColor=fg)))
            ))
        rules.save()
        
        set_row_height(ws, "2:1000", 80)
        wrap_fmt = CellFormat(wrapStrategy="WRAP", verticalAlignment="TOP")
        format_cell_range(ws, "I2:K1000", wrap_fmt)
        
        apply_alternating_banding(ws, 2, 1000, 11)
        border = Border("SOLID_THICK", COLOR_NAVY)
        format_cell_range(ws, "A1:K1", CellFormat(borders=Borders(bottom=border)))
        
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

def format_holdings_current(spreadsheet):
    """Tab 2: Holdings_Current — Daily P&L Review View"""
    tab_name = config.TAB_HOLDINGS_CURRENT
    try:
        ws = spreadsheet.worksheet(tab_name)
        # Ensure row 1 is available for KPI
        if ws.cell(1, 1).value != "📊 PORTFOLIO SNAPSHOT":
            ws.insert_row(["📊 PORTFOLIO SNAPSHOT"], 1)
            time.sleep(2)
            
        set_frozen(ws, rows=2, cols=0)
        # Hide B, D, I, N, O, P, R, S, T
        for idx in [1, 3, 8, 13, 14, 15, 17, 18, 19]:
            hide_cols(spreadsheet, ws.id, idx, idx+1)
            
        widths = {"A": 75, "C": 130, "E": 80, "F": 80, "G": 110, "H": 110, "J": 115, "K": 110, "L": 120, "M": 100, "Q": 75}
        for col, width in widths.items():
            set_column_width(ws, col, width)
            
        header_fmt = CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10), horizontalAlignment="CENTER")
        format_cell_range(ws, "A2:T2", header_fmt)
        
        # Percentage formatting for K (GL %), M (Yield), Q (Weight)
        pct_fmt = CellFormat(numberFormat=NumberFormat(type="PERCENT", pattern="0.00%"))
        format_cell_range(ws, "K3:K200", pct_fmt)
        format_cell_range(ws, "M3:M200", pct_fmt)
        format_cell_range(ws, "Q3:Q200", pct_fmt)
        
        # Currency formatting for G, H, J, L
        curr_fmt = CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0.00'))
        format_cell_range(ws, "G3:H200", curr_fmt)
        format_cell_range(ws, "J3:J200", curr_fmt)
        format_cell_range(ws, "L3:L200", curr_fmt)

        rules = get_conditional_format_rules(ws)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("J3:J200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_GREEN_DARK)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("J3:J200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_RED_DARK)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("K3:K200", ws)], gradientRule=GradientRule(
            minpoint=InterpolationPoint(color=COLOR_RED_DARK, type="NUMBER", value="-0.15"),
            midpoint=InterpolationPoint(color=COLOR_WHITE, type="NUMBER", value="0"),
            maxpoint=InterpolationPoint(color=COLOR_GREEN_DARK, type="NUMBER", value="0.20"))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("Q3:Q200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0.08"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT, textFormat=TextFormat(bold=True)))))
        rules.save()
        
        # KPI Row with LABELS
        ws.update(range_name="A1:L1", values=[[
            "📊 PORTFOLIO SNAPSHOT", "", 
            'Total Value: ', '=SUM(G3:G200)',
            'Unrealized G/L: ', '=SUM(J3:J200)',
            'G/L %: ', '=SUM(J3:J200)/SUM(H3:H200)',
            'Positions: ', '=COUNTA(A3:A200)-COUNTIF(P3:P200,TRUE)',
            'Cash: ', '=SUMIF(P3:P200,TRUE,G3:G200)'
        ]], value_input_option="USER_ENTERED")
        
        # Apply formatting to KPI numbers
        format_cell_range(ws, "D1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))
        format_cell_range(ws, "F1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))
        format_cell_range(ws, "H1", CellFormat(numberFormat=NumberFormat(type="PERCENT", pattern="0.0%"), textFormat=TextFormat(bold=True)))
        format_cell_range(ws, "L1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))

        kpi_style = CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(foregroundColor=COLOR_WHITE, fontSize=10), horizontalAlignment="RIGHT", verticalAlignment="MIDDLE")
        format_cell_range(ws, "A1:L1", kpi_style)
        ws.merge_cells("A1:B1")
        set_row_height(ws, "1", 40)
        
        apply_alternating_banding(ws, 3, 200, 19)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

def format_daily_snapshots(spreadsheet):
    """Tab 3: Daily_Snapshots — Portfolio Trend View"""
    tab_name = config.TAB_DAILY_SNAPSHOTS
    try:
        ws = spreadsheet.worksheet(tab_name)
        if "DAILY SNAPSHOT" not in str(ws.cell(1, 1).value):
            ws.insert_row(["📈 DAILY SNAPSHOT"], 1)
            time.sleep(2)
            
        set_frozen(ws, rows=2, cols=0)
        hide_cols(spreadsheet, ws.id, 9, 10)
        widths = {"A": 100, "B": 120, "C": 120, "D": 140, "E": 110, "F": 120, "G": 90, "H": 100, "I": 150}
        for col, width in widths.items():
            set_column_width(ws, col, width)
            
        format_cell_range(ws, "A2:I2", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE)))
        
        # Percentage formatting for H (Yield)
        format_cell_range(ws, "H3:H500", CellFormat(numberFormat=NumberFormat(type="PERCENT", pattern="0.00%")))
        # Currency for B, C, D, E, F
        curr_fmt = CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'))
        format_cell_range(ws, "B3:F500", curr_fmt)

        rules = get_conditional_format_rules(ws)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D3:D500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D3:D500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))))
        rules.save()
        
        spreadsheet.batch_update({"requests": [{"sortRange": {"range": {"sheetId": ws.id, "startRowIndex": 2, "endRowIndex": 500, "startColumnIndex": 0, "endColumnIndex": 9}, "sortSpecs": [{"dimensionIndex": 0, "sortOrder": "DESCENDING"}]}}]})
        
        ws.update(range_name="A1:E1", values=[[
            "📈 DAILY SNAPSHOT", "",
            'Trend (50d):', '=SPARKLINE(D3:D50,{"charttype","line";"color","#34a853"})',
            '=TEXT(D3,"$#,##0")'
        ]], value_input_option="USER_ENTERED")
        
        ws.merge_cells("A1:B1")
        format_cell_range(ws, "A1:E1", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=11), horizontalAlignment="CENTER", verticalAlignment="MIDDLE"))
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

def format_realized_gl(spreadsheet):
    """Tab 4: Realized_GL — Tax Intelligence View"""
    tab_name = config.TAB_REALIZED_GL
    try:
        ws = spreadsheet.worksheet(tab_name)
        if "REALIZED G/L" not in str(ws.cell(1, 1).value):
            ws.insert_row(["🧾 REALIZED G/L"], 1)
            time.sleep(2)
            
        set_frozen(ws, rows=2, cols=0)
        for idx in [1, 6, 7, 10, 20, 21]:
            hide_cols(spreadsheet, ws.id, idx, idx+1)
            
        widths = {"A": 75, "C": 110, "D": 110, "E": 90, "F": 75, "I": 110, "J": 110, "L": 110, "M": 100, "N": 110, "O": 110, "P": 80, "Q": 90, "R": 120, "S": 110}
        for col, width in widths.items():
            set_column_width(ws, col, width)
            
        # Percentage for M (Gain %)
        format_cell_range(ws, "M3:M500", CellFormat(numberFormat=NumberFormat(type="PERCENT", pattern="0.00%")))
        # Currency for G, H, I, J, L, N, O, R
        curr_fmt = CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'))
        format_cell_range(ws, "G3:J500", curr_fmt)
        format_cell_range(ws, "L3:L500", curr_fmt)
        format_cell_range(ws, "N3:O500", curr_fmt)
        format_cell_range(ws, "R3:R500", curr_fmt)

        rules = get_conditional_format_rules(ws)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("L3:L500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_GREEN_DARK)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("L3:L500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_RED_DARK)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("R3:R500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_NOT_BETWEEN", ["-0.01", "0.01"]), format=CellFormat(backgroundColor=COLOR_RED_DARK, textFormat=TextFormat(foregroundColor=COLOR_WHITE, bold=True)))))
        rules.save()
        
        ws.update(range_name="A1:L1", values=[[
            "🧾 REALIZED G/L", "",
            'Total G/L: ', '=SUM(L3:L500)',
            'LT Gain: ', '=SUMIF(O3:O500,">0",O3:O500)',
            'ST Loss: ', '=SUMIF(N3:N500,"<0",N3:N500)',
            'Disallowed: ', '=SUMIF(Q3:Q500,TRUE,R3:R500)', ""
        ]], value_input_option="USER_ENTERED")
        
        format_cell_range(ws, "D1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))
        format_cell_range(ws, "F1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))
        format_cell_range(ws, "H1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))
        format_cell_range(ws, "J1", CellFormat(numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0'), textFormat=TextFormat(bold=True)))

        ws.merge_cells("A1:B1")
        format_cell_range(ws, "A1:L1", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=11), horizontalAlignment="RIGHT", verticalAlignment="MIDDLE"))
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

@app.command()
def main(
    live: bool = typer.Option(False, "--live", help="Write formatting (default: dry run)"),
    tab: Optional[str] = typer.Option(None, "--tab", help="Format a specific tab only")
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
    
    if tab:
        if tab == config.TAB_AGENT_OUTPUTS:
            format_agent_outputs(spreadsheet)
        elif tab == config.TAB_HOLDINGS_CURRENT:
            format_holdings_current(spreadsheet)
        elif tab == config.TAB_DAILY_SNAPSHOTS:
            format_daily_snapshots(spreadsheet)
        elif tab == config.TAB_REALIZED_GL:
            format_realized_gl(spreadsheet)
        else:
            print(f"Unknown tab: {tab}")
    else:
        format_agent_outputs(spreadsheet)
        time.sleep(5)
        format_holdings_current(spreadsheet)
        time.sleep(5)
        format_daily_snapshots(spreadsheet)
        time.sleep(5)
        format_realized_gl(spreadsheet)
    
    typer.echo("✅ Formatting task complete.")

if __name__ == "__main__":
    app()
