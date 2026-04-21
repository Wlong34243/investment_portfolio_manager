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
import logging
from typing import List, Optional

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)

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
    logger.error(f"Import error in gspread_formatting: {e}")
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

def safe_execute(func, *args, **kwargs):
    """Wrapper with exponential backoff to handle Google API Quota limits."""
    retries = 5
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                wait = (i + 1) * 15
                print(f"  ! Quota exceeded (429), waiting {wait}s before retry {i+1}/{retries}...")
                time.sleep(wait)
            else:
                raise e

def hide_cols(spreadsheet, sheet_id, start_index, end_index):
    """Helper to hide columns using batch_update."""
    req = {
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
    }
    safe_execute(spreadsheet.batch_update, req)

def hide_tab(spreadsheet, tab_name: str):
    """Helper to hide a worksheet by name."""
    try:
        ws = spreadsheet.worksheet(tab_name)
        req = {
            "requests": [{
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws.id,
                        "hidden": True
                    },
                    "fields": "hidden"
                }
            }]
        }
        safe_execute(spreadsheet.batch_update, req)
        print(f"  ✓ hidden {tab_name}")
    except:
        pass

def apply_alternating_banding(ws, start_row, end_row):
    """Applies alternating row banding."""
    rules = get_conditional_format_rules(ws)
    rules.append(ConditionalFormatRule(
        ranges=[GridRange.from_a1_range(f"A{start_row}:Z{end_row}", ws)],
        booleanRule=BooleanRule(
            condition=BooleanCondition("CUSTOM_FORMULA", [f"=ISEVEN(ROW())"]),
            format=CellFormat(backgroundColor=COLOR_GREY_LIGHT)
        )
    ))
    safe_execute(rules.save)

def format_agent_outputs(spreadsheet):
    """Tab 1: Agent_Outputs — Priority Review View (Compact 10-col format)"""
    tab_name = config.TAB_AGENT_OUTPUTS
    try:
        ws = spreadsheet.worksheet(tab_name)
        hide_cols(spreadsheet, ws.id, 0, 3)
        time.sleep(1)
        
        # Visible: D: signal, E: ticker, F: action, G: narrative, H: scale_step, I: severity, J: score
        widths = {
            "D": 110, "E": 80, "F": 150, "G": 400, "H": 120, "I": 90, "J": 60
        }
        for col, width in widths.items():
            safe_execute(set_column_width, ws, col, width)
            
        try:
            safe_execute(set_frozen, ws, rows=1, cols=5)
        except Exception as _fe:
            print(f"  ! set_frozen skipped: {_fe}")

        header_fmt = CellFormat(
            backgroundColor=COLOR_NAVY,
            textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10),
            wrapStrategy="CLIP",
            horizontalAlignment="CENTER"
        )
        safe_execute(format_cell_range, ws, "A1:J1", header_fmt)
        
        rules = get_conditional_format_rules(ws)
        rules.clear() # Reset for clean apply
        
        # Signal Type (Col D)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D2:D1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["ADD"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D2:D1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["TRIM"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D2:D1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["HOLD"]), format=CellFormat(backgroundColor=COLOR_YELLOW_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D2:D1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["MONITOR"]), format=CellFormat(backgroundColor=COLOR_BLUE_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D2:D1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["EXIT"]), format=CellFormat(backgroundColor=COLOR_RED_DARK, textFormat=TextFormat(foregroundColor=COLOR_WHITE)))))
        
        # Severity (Col I)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("I2:I1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_CONTAINS", ["high"]), format=CellFormat(backgroundColor=COLOR_RED_DARK, textFormat=TextFormat(foregroundColor=COLOR_WHITE)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("I2:I1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_CONTAINS", ["medium"]), format=CellFormat(backgroundColor=COLOR_ORANGE, textFormat=TextFormat(foregroundColor=COLOR_WHITE)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("I2:I1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_CONTAINS", ["low"]), format=CellFormat(backgroundColor=COLOR_GREEN_MUTED))))
        
        safe_execute(rules.save)
        
        safe_execute(set_row_height, ws, "2:1000", 80)
        safe_execute(format_cell_range, ws, "F2:H1000", CellFormat(wrapStrategy="WRAP", verticalAlignment="TOP"))
        
        apply_alternating_banding(ws, 2, 1000)
        safe_execute(format_cell_range, ws, "A1:J1", CellFormat(borders=Borders(bottom=Border("SOLID_THICK", COLOR_NAVY))))
        
        print(f"  OK formatted {tab_name}")
    except Exception as e:
        print(f"  ! Failed to format {tab_name}: {e}")

def format_holdings_current(spreadsheet):
    """Tab 2: Holdings_Current — Daily P&L Review View"""
    tab_name = config.TAB_HOLDINGS_CURRENT
    try:
        ws = spreadsheet.worksheet(tab_name)
        
        # Insert KPI row 1 if missing
        try:
            first_cell = safe_execute(ws.cell, 1, 1).value
        except:
            first_cell = None
            
        if first_cell != "📊 PORTFOLIO SNAPSHOT":
            safe_execute(ws.insert_row, ["📊 PORTFOLIO SNAPSHOT"], 1)
            time.sleep(5)
            
        safe_execute(set_frozen, ws, rows=2)

        # Hide columns B, D, I, N, O, P, S, T (indices 1, 3, 8, 13, 14, 15, 18, 19)
        for idx in [1, 3, 8, 13, 14, 15, 18, 19]:
            hide_cols(spreadsheet, ws.id, idx, idx+1)
            
        # Set widths
        widths = {"A": 75, "C": 130, "E": 80, "F": 80, "G": 110, "H": 110, "J": 115, "K": 110, "L": 120, "M": 100, "R": 75}
        for col, width in widths.items():
            safe_execute(set_column_width, ws, col, width)
            
        # Header formatting (Row 2)
        header_fmt = CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10), horizontalAlignment="CENTER")
        safe_execute(format_cell_range, ws, "A2:T2", header_fmt)
        
        rules = get_conditional_format_rules(ws)
        rules.clear() # Reset
        # Unrealized G/L $ (Col J)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("J3:J200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_GREEN_DARK)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("J3:J200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_RED_DARK)))))
        # Unrealized G/L % Scale (Col K)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("K3:K200", ws)], gradientRule=GradientRule(
            minpoint=InterpolationPoint(color=COLOR_RED_DARK, type="NUMBER", value="-0.15"),
            midpoint=InterpolationPoint(color=COLOR_WHITE, type="NUMBER", value="0"),
            maxpoint=InterpolationPoint(color=COLOR_GREEN_DARK, type="NUMBER", value="0.20"))))
        # Weight Flag (Col R)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("R3:R200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0.08"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT, textFormat=TextFormat(bold=True)))))
        # Wash Sale (Col O)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("O3:O200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["TRUE"]), format=CellFormat(backgroundColor=COLOR_ORANGE))))
        safe_execute(rules.save)
        
        # Summary KPI row 1 with merged cells and formulas
        kpi_formulas = [
            "📊 PORTFOLIO SNAPSHOT", "", 
            '=TEXT(SUM(G3:G200),"$#,##0")', "",
            '=TEXT(SUM(J3:J200),"$#,##0")', "",
            '=TEXT(SUM(J3:J200)/SUM(H3:H200)*100,"0.0")&"%"', "",
            '=TEXT(SUMIF(P3:P200,TRUE,G3:G200),"$#,##0")', "",
            '=TEXT(COUNTA(A3:A200)-COUNTIF(P3:P200,TRUE),"0")&" positions"', ""
        ]
        safe_execute(ws.update, range_name="A1:L1", values=[kpi_formulas], value_input_option="USER_ENTERED")
        
        # Format KPI row
        kpi_fmt = CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=11), horizontalAlignment="CENTER", verticalAlignment="MIDDLE")
        safe_execute(format_cell_range, ws, "A1:L1", kpi_fmt)
        
        # Merging cells for labels/values pairs in row 1
        for merge_range in ["A1:B1", "C1:D1", "E1:F1", "G1:H1", "I1:J1", "K1:L1"]:
            try:
                ws.merge_cells(merge_range)
            except:
                pass # Already merged
        
        apply_alternating_banding(ws, 3, 200)
        print(f"  OK formatted {tab_name}")
    except Exception as e:
        print(f"  ! Failed to format {tab_name}: {e}")

def format_daily_snapshots(spreadsheet):
    """Tab 3: Daily_Snapshots — Portfolio Trend View"""
    tab_name = config.TAB_DAILY_SNAPSHOTS
    try:
        ws = spreadsheet.worksheet(tab_name)
        try:
            first_cell = safe_execute(ws.cell, 1, 1).value
        except:
            first_cell = None
            
        if "DAILY SNAPSHOT" not in str(first_cell):
            safe_execute(ws.insert_row, ["📈 DAILY SNAPSHOT"], 1)
            time.sleep(5)
            
        safe_execute(set_frozen, ws, rows=2)
        hide_cols(spreadsheet, ws.id, 9, 10) # Fingerprint J
        
        widths = {"A": 100, "B": 120, "C": 120, "D": 140, "E": 110, "F": 120, "G": 90, "H": 100, "I": 150}
        for col, width in widths.items():
            safe_execute(set_column_width, ws, col, width)
            
        safe_execute(format_cell_range, ws, "A2:I2", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE)))
        
        rules = get_conditional_format_rules(ws)
        rules.clear() # Reset
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D3:D500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("D3:D500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))))
        safe_execute(rules.save)
        
        # Sort newest first
        req = {"requests": [{"sortRange": {"range": {"sheetId": ws.id, "startRowIndex": 2, "endRowIndex": 500, "startColumnIndex": 0, "endColumnIndex": 9}, "sortSpecs": [{"dimensionIndex": 0, "sortOrder": "DESCENDING"}]}}]}
        safe_execute(spreadsheet.batch_update, req)
        
        # Row 1 Sparkline KPI
        safe_execute(ws.update, range_name="A1:E1", values=[[
            "📈 DAILY SNAPSHOT", "",
            '=SPARKLINE(D3:D50,{"charttype","line";"color","#34a853"})',
            '=TEXT(D3,"$#,##0")',
            '=TEXT(B3,"$#,##0")'
        ]], value_input_option="USER_ENTERED")
        
        ws.merge_cells("A1:B1")
        format_cell_range(ws, "A1:E1", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=11), horizontalAlignment="CENTER", verticalAlignment="MIDDLE"))
        format_cell_range(ws, "A3:I3", CellFormat(textFormat=TextFormat(bold=True))) # Bold most recent row
        
        print(f"  OK formatted {tab_name}")
    except Exception as e:
        print(f"  ! Failed to format {tab_name}: {e}")

def format_realized_gl(spreadsheet):
    """Tab 4: Realized_GL — Tax Intelligence View"""
    tab_name = config.TAB_REALIZED_GL
    try:
        ws = spreadsheet.worksheet(tab_name)
        try:
            first_cell = safe_execute(ws.cell, 1, 1).value
        except:
            first_cell = None
            
        if "REALIZED G/L" not in str(first_cell):
            safe_execute(ws.insert_row, ["🧾 REALIZED G/L"], 1)
            time.sleep(5)
            
        safe_execute(set_frozen, ws, rows=2)
        # Hide audit columns (indices 1, 6, 7, 10, 20, 21)
        for idx in [1, 6, 7, 10, 20, 21]:
            hide_cols(spreadsheet, ws.id, idx, idx+1)
            
        widths = {"A": 75, "C": 110, "D": 110, "E": 90, "F": 75, "I": 110, "J": 110, "L": 110, "M": 100, "N": 110, "O": 110, "P": 80, "Q": 90, "R": 120, "S": 110}
        for col, width in widths.items():
            safe_execute(set_column_width, ws, col, width)
            
        rules = get_conditional_format_rules(ws)
        rules.clear() # Reset
        # Gain Loss $ (Col L)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("L3:L500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_GREEN_DARK)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("L3:L500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_RED_DARK)))))
        # Disallowed Loss (Col R) - High Priority Red Bold White
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("R3:R500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_NOT_BETWEEN", ["-0.01", "0.01"]), format=CellFormat(backgroundColor=COLOR_RED_DARK, textFormat=TextFormat(foregroundColor=COLOR_WHITE, bold=True)))))
        # Wash Sale entire row background (Col Q)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("A3:S500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("CUSTOM_FORMULA", ["=$Q3=TRUE"]), format=CellFormat(backgroundColor=COLOR_YELLOW_LIGHT))))
        # Term ST/LT (Col P)
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("P3:P500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_CONTAINS", ["ST"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range("P3:P500", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_CONTAINS", ["LT"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))))
        safe_execute(rules.save)
        
        # Row 1 KPI
        # LT Gain (N>0), LT Loss (N<0), ST Gain (O>0), Disallowed (Q=TRUE, R)
        kpis = [
            "🧾 REALIZED G/L", "",
            '=TEXT(SUM(L3:L500),"$#,##0")', "",
            '=TEXT(SUMIF(N3:N500,">0",N3:N500),"$#,##0")', "",
            '=TEXT(SUMIF(N3:N500,"<0",N3:N500),"$#,##0")', "",
            '=TEXT(SUMIF(O3:O500,">0",O3:O500),"$#,##0")', "",
            '=TEXT(SUMIF(Q3:Q500,TRUE,R3:R500),"$#,##0")', ""
        ]
        safe_execute(ws.update, range_name="A1:L1", values=[kpis], value_input_option="USER_ENTERED")
        
        ws.merge_cells("A1:B1")
        format_cell_range(ws, "A1:L1", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=11), horizontalAlignment="CENTER", verticalAlignment="MIDDLE"))
        print(f"  OK formatted {tab_name}")
    except Exception as e:
        print(f"  ! Failed to format {tab_name}: {e}")

@app.command()
def main(
    live: bool = typer.Option(False, "--live", help="Write formatting (default: dry run)"),
    tab: Optional[str] = typer.Option(None, "--tab", help="Format a specific tab only")
):
    if not HAS_FORMATTING:
        typer.echo("ERROR: Import failed. Please verify gspread-formatting is installed correctly.")
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
        # Hide deprecated tabs
        hide_tab(spreadsheet, "Trade_Log_Staging")
        hide_tab(spreadsheet, "Agent_Outputs_Archive")
        hide_tab(spreadsheet, "Logs")

        format_agent_outputs(spreadsheet)
        print("  ... Resting 30s for quota reset ...")
        time.sleep(30)
        format_holdings_current(spreadsheet)
        print("  ... Resting 30s for quota reset ...")
        time.sleep(30)
        format_daily_snapshots(spreadsheet)
        print("  ... Resting 30s for quota reset ...")
        time.sleep(30)
        format_realized_gl(spreadsheet)
    
    typer.echo("Formatting task complete.")

if __name__ == "__main__":
    app()
