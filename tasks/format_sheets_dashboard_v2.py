"""
tasks/format_sheets_dashboard_v2.py — Applies V2 formatting to all tabs.
"""

import time
import os
import sys
import typer
from typing import List, Optional
from gspread.cell import Cell

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
        set_column_width, set_column_widths, set_row_height, set_row_heights,
        ConditionalFormatRule, BooleanRule,
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

def safe_api_call(func, *args, retries=3, **kwargs):
    """Generic wrapper for gspread/formatting calls with retry logic."""
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                wait = (i + 1) * 7
                print(f"  ⚠ Quota exceeded, waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise e

def safe_format(ws, range_name, fmt, retries=3):
    """Applies formatting with retry logic for API quota limits."""
    return safe_api_call(format_cell_range, ws, range_name, fmt, retries=retries)

def save_rules(ws, rules):
    """Robustly saves conditional format rules to the worksheet."""
    try:
        safe_api_call(rules.save)
        # Add a sleep after every rule update as it is a heavy API call
        time.sleep(3)
    except Exception as e:
        if "429" in str(e):
            print("  ⚠ Quota exceeded on rules save, skipping.")
        else:
            raise e

def apply_alternating_banding(ws, start_row, end_row):
    """Applies alternating row banding."""
    rules = safe_api_call(get_conditional_format_rules, ws)
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
        safe_api_call(set_frozen, ws, rows=1, cols=1)
        
        widths = [
            ("A", 70), ("B", 180), ("C", 110), ("D", 75), ("E", 95),
            ("F", 95), ("G", 70), ("H", 70), ("I", 80), ("J", 80),
            ("K", 110), ("L", 130), ("M", 90), ("N", 70), ("O", 70), ("P", 110)
        ]
        safe_api_call(set_column_widths, ws, widths)
            
        header_fmt = CellFormat(
            backgroundColor=COLOR_NAVY,
            textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10),
            horizontalAlignment="CENTER"
        )
        safe_format(ws, "A1:R1", header_fmt)
        
        rules = safe_api_call(get_conditional_format_rules, ws)
        rules.clear()
        
        # 52w Position % color scale: values are raw decimals 0.0–1.0 (build_valuation_card.py)
        # 0.0=red (at 52w low), 0.5=white (midpoint), 1.0=green (at 52w high)
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("K2:K200", ws)],
            gradientRule=GradientRule(
                minpoint=InterpolationPoint(color=COLOR_RED_DARK,   type="NUMBER", value="0"),
                midpoint=InterpolationPoint(color=COLOR_WHITE,      type="NUMBER", value="0.5"),
                maxpoint=InterpolationPoint(color=COLOR_GREEN_DARK, type="NUMBER", value="1.0")
            )
        ))
        # Discount from 52w High %: raw decimal (e.g. 0.20 = 20% below high)
        # >0.30 = meaningful discount → green; <0.10 = near high, no discount → red
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("L2:L200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0.30"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))
        ))
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("L2:L200", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0.10"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))
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
        safe_api_call(set_frozen, ws, rows=1, cols=1)
        
        widths = [
            ("A", 70), ("B", 70), ("C", 110), ("D", 100), ("E", 90),
            ("F", 80), ("G", 90), ("H", 100), ("I", 120), ("J", 200),
            ("K", 200), ("L", 90), ("M", 400)
        ]
        safe_api_call(set_column_widths, ws, widths)
            
        header_fmt = CellFormat(
            backgroundColor=COLOR_NAVY,
            textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10),
            horizontalAlignment="CENTER"
        )
        safe_format(ws, "A1:M1", header_fmt)
        
        safe_api_call(set_row_height, ws, "2:200", 60)
        wrap_fmt = CellFormat(wrapStrategy="WRAP", verticalAlignment="MIDDLE")
        safe_format(ws, "A2:M200", wrap_fmt)
        
        rules = safe_api_call(get_conditional_format_rules, ws)
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
        # 52w Pos % color scale: raw decimals 0.0–1.0 (low=green means near 52w low = cheaper)
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("G2:G200", ws)],
            gradientRule=GradientRule(
                minpoint=InterpolationPoint(color=COLOR_GREEN_DARK, type="NUMBER", value="0"),
                midpoint=InterpolationPoint(color=COLOR_WHITE,      type="NUMBER", value="0.5"),
                maxpoint=InterpolationPoint(color=COLOR_RED_DARK,   type="NUMBER", value="1.0")
            )
        ))
        save_rules(ws, rules)
        
        apply_alternating_banding(ws, 2, 200)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

def format_agent_outputs_v2(spreadsheet):
    """Part 3: Agent_Outputs revised formatting with READABILITY focus"""
    tab_name = config.TAB_AGENT_OUTPUTS
    try:
        ws = spreadsheet.worksheet(tab_name)
        all_values = ws.get_all_values()
        
        # Ensure frozen summary row exists
        first_cell = all_values[0][0] if all_values and all_values[0] else None
        if first_cell and "Accumulate:" not in str(first_cell):
            safe_api_call(ws.insert_row, [""], 1)
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
        col_signal_let, col_signal_idx = get_col_letter('signal') # Note: Check for 'signal' or 'signal_type'
        if not col_signal_let: col_signal_let, col_signal_idx = get_col_letter('signal_type')
        
        col_action_let, col_action_idx = get_col_letter('action')
        col_narrative_let, col_narrative_idx = get_col_letter('narrative')
        if not col_narrative_let: col_narrative_let, col_narrative_idx = get_col_letter('rationale')
        
        # Default fallback indices if detection fails
        col_agent_let = col_agent_let or 'C'
        col_signal_let = col_signal_let or 'D'
        col_action_let = col_action_let or 'F'
        col_narrative_let = col_narrative_let or 'G'
        
        # --- READABILITY FIXES START ---
        # 1. Column Widths (Surgical Control)
        # Assuming compact format: A:Date, B:ID, C:Agent, D:Signal, E:Ticker, F:Action, G:Narrative, H:Scale, I:Severity, J:Score
        widths = [
            ("A", 100), ("B", 70),  ("C", 90),  ("D", 80),  ("E", 80),
            ("F", 350), # action (Narrative-heavy)
            ("G", 550), # narrative (LLM reasoning)
            ("H", 120), ("I", 100), ("J", 80)
        ]
        safe_api_call(set_column_widths, ws, widths)

        # 2. Row heights and global alignment
        safe_api_call(set_row_height, ws, "3:1000", 60)
        content_fmt = CellFormat(
            wrapStrategy="WRAP",
            verticalAlignment="TOP",
            horizontalAlignment="LEFT",
            textFormat=TextFormat(fontSize=10)
        )
        safe_format(ws, "A3:K1000", content_fmt)
        # --- READABILITY FIXES END ---

        # Summary Row (Row 1)
        summary_formula = (
            f'="Accumulate: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"ADD")&'
            f'" | Trim: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"TRIM")&'
            f'" | Hold: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"HOLD")&'
            f'" | Exit: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"EXIT")&'
            f'" | Monitor: "&COUNTIF({col_signal_let}3:{col_signal_let}1000,"MONITOR")'
        )
        safe_api_call(ws.update, [[summary_formula]], 'A1', value_input_option="USER_ENTERED")
        
        # Split merge to avoid "You can't merge frozen and non-frozen columns" error
        # Freezing cols A-E (indices 1-5). A-E are frozen, F-K are NOT.
        try:
            safe_api_call(ws.merge_cells, "A1:E1") # All frozen
            safe_api_call(ws.merge_cells, "F1:K1") # All non-frozen
        except Exception as _me:
            print(f"  ! merge_cells skipped (already merged?): {_me}")
            
        safe_format(ws, "A1:K1", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=12), horizontalAlignment="CENTER"))
        
        safe_format(ws, "A2:K2", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE), horizontalAlignment="CENTER"))
        safe_api_call(set_frozen, ws, rows=2, cols=5) # Freeze up to Ticker
        
        rules = safe_api_call(get_conditional_format_rules, ws)
        rules.clear()
        
        # Signal Type Colors
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range(f"{col_signal_let}3:{col_signal_let}1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["ADD"]), format=CellFormat(backgroundColor=COLOR_GREEN_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range(f"{col_signal_let}3:{col_signal_let}1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["TRIM"]), format=CellFormat(backgroundColor=COLOR_RED_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range(f"{col_signal_let}3:{col_signal_let}1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["HOLD"]), format=CellFormat(backgroundColor=COLOR_YELLOW_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range(f"{col_signal_let}3:{col_signal_let}1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["MONITOR"]), format=CellFormat(backgroundColor=COLOR_BLUE_LIGHT))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range(f"{col_signal_let}3:{col_signal_let}1000", ws)], booleanRule=BooleanRule(condition=BooleanCondition("TEXT_EQ", ["EXIT"]), format=CellFormat(backgroundColor=COLOR_RED_DARK, textFormat=TextFormat(foregroundColor=COLOR_WHITE)))))
        
        save_rules(ws, rules)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

def format_holdings_current_v2(spreadsheet):
    """Part 4: Holdings_Current KPI and Readability Fix"""
    tab_name = config.TAB_HOLDINGS_CURRENT
    try:
        ws = spreadsheet.worksheet(tab_name)
        
        # 1. ULTIMATE UNMERGE (Must happen before any read/write to avoid gspread bugs)
        for merge_range in ["A1:B1", "C1:D1", "E1:F1", "G1:H1", "I1:J1", "K1:L1"]:
            try:
                ws.unmerge_cells(merge_range)
            except Exception:
                pass 
        time.sleep(5)

        all_values = ws.get_all_values()
        
        # 2. Ensure KPI row exists without overwriting headers
        first_cell = all_values[0][0] if all_values and all_values[0] else None
        if first_cell and "PORTFOLIO SNAPSHOT" not in str(first_cell):
            safe_api_call(ws.insert_row, [""], 1)
            time.sleep(2)
            all_values = ws.get_all_values()
            
        header_row_idx = 1 
        headers = all_values[header_row_idx]
        data_start_row = 3 
        
        if 'Ticker' not in [str(h).strip() for h in headers]:
            for i, row in enumerate(all_values[:5]):
                if 'Ticker' in row or 'ticker' in [str(h).strip().lower() for h in row]:
                    header_row_idx = i
                    break
            if header_row_idx != -1:
                headers = all_values[header_row_idx]
                data_start_row = header_row_idx + 2

        def get_col_letter(name):
            try:
                idx = next(i for i, h in enumerate(headers) if h.strip().lower() == name.lower())
                return chr(ord('A') + idx)
            except StopIteration:
                return None

        col_ticker = get_col_letter('Ticker') or 'A'
        col_mv = get_col_letter('Market Value') or 'G'
        col_cb = get_col_letter('Cost Basis') or 'H'
        col_ugl = get_col_letter('Unrealized G/L') or 'J'
        
        # Core conditional rules
        rules = safe_api_call(get_conditional_format_rules, ws)
        rules.clear()
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range(f"{col_ugl}{data_start_row}:{col_ugl}200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_GREEN_DARK)))))
        rules.append(ConditionalFormatRule(ranges=[GridRange.from_a1_range(f"{col_ugl}{data_start_row}:{col_ugl}200", ws)], booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=COLOR_RED_DARK)))))
        save_rules(ws, rules)
        
        # Formatting
        safe_api_call(set_frozen, ws, rows=2, cols=0)
        header_range = f"A{header_row_idx+1}:T{header_row_idx+1}" 
        safe_format(ws, header_range, CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=10), horizontalAlignment="CENTER"))
        apply_alternating_banding(ws, data_start_row, 200)

        # --- FINAL KPI WRITE (Combined Label + Formula in one cell to survive merging) ---
        # 1. Prepare Combined Formulas (Label + Value using TEXT for formatting)
        # Using SUMIF(TickerRange, "*", ValueRange) to ignore ghost rows with blank tickers.
        kpi_formulas = [
            ("A1", "📊 PORTFOLIO SNAPSHOT"),
            ("C1", f'="Total Value: "&TEXT(SUMIF({col_ticker}{data_start_row}:{col_ticker}200, "*", {col_mv}{data_start_row}:{col_mv}200), "$#,##0")'),
            ("E1", f'="Dry Powder: "&TEXT(SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"CASH_MANUAL",{col_mv}{data_start_row}:{col_mv}200)+SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"SGOV",{col_mv}{data_start_row}:{col_mv}200), "$#,##0")'),
            ("G1", f'="Cash + SGOV: "&TEXT(SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"CASH_MANUAL",{col_mv}{data_start_row}:{col_mv}200)+SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"SGOV",{col_mv}{data_start_row}:{col_mv}200)+SUMIF({col_ticker}{data_start_row}:{col_ticker}200,"QACDS",{col_mv}{data_start_row}:{col_mv}200), "$#,##0")'),
            ("I1", f'="G/L %: "&TEXT(IF(SUMIF({col_ticker}{data_start_row}:{col_ticker}200, "*", {col_cb}{data_start_row}:{col_cb}200)=0, 0, SUMIF({col_ticker}{data_start_row}:{col_ticker}200, "*", {col_ugl}{data_start_row}:{col_ugl}200)/SUMIF({col_ticker}{data_start_row}:{col_ticker}200, "*", {col_cb}{data_start_row}:{col_cb}200)), "0.00%")'),
            ("K1", f'="Positions: "&(COUNTA({col_ticker}{data_start_row}:{col_ticker}200)-COUNTIF({col_ticker}{data_start_row}:{col_ticker}200,"CASH_MANUAL")-COUNTIF({col_ticker}{data_start_row}:{col_ticker}200,"QACDS"))')
        ]

        # Clear Row 1 to avoid conflicts
        ws.update("A1:T1", [["" for _ in range(20)]])
        time.sleep(2)

        # Write combined formulas
        for cell, val in kpi_formulas:
            ws.update_acell(cell, val)
        time.sleep(3)

        # 3. Final KPI Row Formatting (Centered)
        safe_format(ws, "A1:L1", CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=11), verticalAlignment="MIDDLE", horizontalAlignment="CENTER"))

        # 4. Merging
        for merge_range in ["A1:B1", "C1:D1", "E1:F1", "G1:H1", "I1:J1", "K1:L1"]:
            try:
                ws.merge_cells(merge_range)
            except Exception:
                pass 

        print(f"  ✓ updated KPI and formatting for {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to update KPI for {tab_name}: {e}")

def format_realized_gl_v2(spreadsheet):
    """Part 5: Realized_GL Wash Sale UI"""
    tab_name = config.TAB_REALIZED_GL
    try:
        ws = spreadsheet.worksheet(tab_name)
        
        # Ensure second KPI row
        row2_val = safe_api_call(ws.cell, 2, 1).value
        if row2_val and "WASH SALE RISK" not in str(row2_val):
            safe_api_call(ws.insert_row, [""], 2)
            time.sleep(1)
            
        # Row 1 formatting update for Disallowed Loss
        # Assuming Disallowed Loss Label is in I1 and Value in J1 (based on previous format_realized_gl)
        safe_format(ws, "J1", CellFormat(textFormat=TextFormat(bold=True, foregroundColor=COLOR_RED_DARK, fontSize=12), numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0')))
        
        # Row 2 Wash Sale Warning
        safe_api_call(ws.update, [["⚠️ WASH SALE RISK: Review before year-end. Disallowed losses cannot offset gains."]], "A2", value_input_option="USER_ENTERED")
        safe_api_call(ws.merge_cells, "A2:S2")
        safe_format(ws, "A2:S2", CellFormat(backgroundColor=COLOR_ORANGE, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE), horizontalAlignment="CENTER"))
        
        # Row 3 is now Header, Data starts at Row 4
        safe_api_call(set_frozen, ws, rows=3, cols=0)
        
        rules = safe_api_call(get_conditional_format_rules, ws)
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

def format_daily_snapshots_v2(spreadsheet):
    """Part 6: Daily_Snapshots formatting"""
    tab_name = config.TAB_DAILY_SNAPSHOTS
    try:
        ws = spreadsheet.worksheet(tab_name)
        try:
            safe_api_call(set_frozen, ws, rows=2)
        except Exception as _fe:
            print(f"  ! set_frozen skipped: {_fe}")
            
        widths = [
            ("A", 100), ("B", 120), ("C", 120), ("D", 140), ("E", 110),
            ("F", 120), ("G", 90), ("H", 100), ("I", 150)
        ]
        safe_api_call(set_column_widths, ws, widths)
            
        header_fmt = CellFormat(backgroundColor=COLOR_NAVY, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE), horizontalAlignment="CENTER")
        safe_format(ws, "A2:I2", header_fmt)
        
        apply_alternating_banding(ws, 3, 500)
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
    print("  ... Resting 30s for quota reset ...")
    time.sleep(30)
    
    format_decision_view(spreadsheet)
    print("  ... Resting 30s for quota reset ...")
    time.sleep(30)
    
    format_agent_outputs_v2(spreadsheet)
    print("  ... Resting 30s for quota reset ...")
    time.sleep(30)
    
    format_holdings_current_v2(spreadsheet)
    print("  ... Resting 30s for quota reset ...")
    time.sleep(30)
    
    format_realized_gl_v2(spreadsheet)
    print("  ... Resting 30s for quota reset ...")
    time.sleep(30)
    
    format_daily_snapshots_v2(spreadsheet)
    
    typer.echo("✅ V2 Formatting task complete.")

if __name__ == "__main__":
    app()
