"""
tasks/format_sheets_dashboard_v2.py — Applies V2 formatting to all tabs.

Design Intent:
- Valuation/Decision: Standardize signals (green/red/yellow), apply strict percentage formatting based on CSV export.
- Agent Outputs: Support long, wrapped text for readability of LLM rationales.
- Holdings/Realized: Emphasize global KPIs, P&L gradients, and highlight wash sales.
"""

import time
import os
import sys
import typer
from typing import List, Optional, Any
from functools import wraps

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client

# Defensive gspread import for typing
try:
    from gspread import Worksheet
except ImportError:
    Worksheet = Any

try:
    from gspread_formatting import (
        CellFormat, Color, TextFormat, ConditionalFormatRule, BooleanRule,
        BooleanCondition, GradientRule, InterpolationPoint,
        format_cell_range, set_frozen, NumberFormat,
        set_column_widths, set_row_height, get_conditional_format_rules, GridRange
    )
    HAS_FORMATTING = True
except ImportError:
    HAS_FORMATTING = False

app = typer.Typer()

# --- Shared Colors ---
COLOR_NAVY = Color(0.10, 0.15, 0.27)         # #1a2744
COLOR_WHITE = Color(1, 1, 1)                 # #ffffff
COLOR_GREY_LIGHT = Color(0.95, 0.95, 0.95)   # #f3f3f3
COLOR_RED_DARK = Color(0.92, 0.26, 0.21)     # #ea4335
COLOR_RED_LIGHT = Color(0.99, 0.91, 0.90)    # #fce8e6
COLOR_GREEN_DARK = Color(0.20, 0.66, 0.33)   # #34a853
COLOR_GREEN_LIGHT = Color(0.85, 0.92, 0.83)  # #d9ead3
COLOR_YELLOW_LIGHT = Color(1.0, 0.95, 0.80)  # #fff2cc
COLOR_BLUE_LIGHT = Color(0.81, 0.89, 0.95)   # #cfe2f3
COLOR_ORANGE = Color(1.0, 0.60, 0.0)         # #ff9900

# --- Constants ---
MAX_DATA_ROWS = 200
MAX_DAILY_ROWS = 500
MAX_AGENT_ROWS = 1000

# ==========================================
# API Quota Helpers
# ==========================================

def require_formatting(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not HAS_FORMATTING:
            print(f"  ⚠ Skipping {func.__name__} (gspread_formatting not installed)")
            return
        return func(*args, **kwargs)
    return wrapper

def safe_api_call(func, *args, retries: int = 3, **kwargs) -> Any:
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

def safe_format(ws: Worksheet, range_name: str, fmt: 'CellFormat', retries: int = 3) -> None:
    """Applies formatting with retry logic for API quota limits."""
    safe_api_call(format_cell_range, ws, range_name, fmt, retries=retries)

def save_rules(ws: Worksheet, rules: Any) -> None:
    """Robustly saves conditional format rules to the worksheet."""
    try:
        safe_api_call(rules.save)
        # Heavy API call, sleep to respect quotas
        time.sleep(3)
    except Exception as e:
        if "429" in str(e):
            print("  ⚠ Quota exceeded on rules save, skipping.")
        else:
            raise e

# ==========================================
# Formatting Builders & Generators
# ==========================================

def build_header_format(font_size: int = 10) -> 'CellFormat':
    """Returns a standardized navy header format."""
    return CellFormat(
        backgroundColor=COLOR_NAVY,
        textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE, fontSize=font_size),
        horizontalAlignment="CENTER",
        verticalAlignment="MIDDLE"
    )

def build_boolean_rule(ws, range_a1, condition, values, bg_color=None, text_color=None, bold=False):
    """Helper to cleanly build standard boolean conditional formats."""
    text_fmt_args = {}
    if text_color: text_fmt_args['foregroundColor'] = text_color
    if bold: text_fmt_args['bold'] = True

    fmt_args = {}
    if bg_color: fmt_args['backgroundColor'] = bg_color
    if text_fmt_args: fmt_args['textFormat'] = TextFormat(**text_fmt_args)

    return ConditionalFormatRule(
        ranges=[GridRange.from_a1_range(range_a1, ws)],
        booleanRule=BooleanRule(
            condition=BooleanCondition(condition, values),
            format=CellFormat(**fmt_args) if fmt_args else CellFormat()
        )
    )

def build_gradient_rule(ws, range_a1, min_color, mid_color, max_color):
    """Helper to build a 0.0 - 1.0 NUMBER gradient rule."""
    return ConditionalFormatRule(
        ranges=[GridRange.from_a1_range(range_a1, ws)],
        gradientRule=GradientRule(
            minpoint=InterpolationPoint(color=min_color, type="NUMBER", value="0"),
            midpoint=InterpolationPoint(color=mid_color, type="NUMBER", value="0.5"),
            maxpoint=InterpolationPoint(color=max_color, type="NUMBER", value="1.0")
        )
    )

def apply_alternating_banding(ws: Worksheet, start_row: int, end_row: int) -> None:
    """Applies alternating row banding, avoiding duplicate rules."""
    rules = safe_api_call(get_conditional_format_rules, ws)
    
    # Filter out existing banding to prevent accumulation
    new_rules = [r for r in rules if not (isinstance(r.booleanRule, BooleanRule) and "ISEVEN(ROW())" in str(r.booleanRule.condition.values))]
    
    rules.clear()
    for r in new_rules: rules.append(r)
    
    rules.append(build_boolean_rule(ws, f"A{start_row}:Z{end_row}", "CUSTOM_FORMULA", ["=ISEVEN(ROW())"], bg_color=COLOR_GREY_LIGHT))
    save_rules(ws, rules)

def format_standard_table(ws, header_range, header_row, data_start, data_end, freeze_cols=1):
    """Helper to set freeze panes, header format, and alternating row banding."""
    safe_api_call(set_frozen, ws, rows=header_row, cols=freeze_cols)
    safe_format(ws, header_range, build_header_format())
    apply_alternating_banding(ws, data_start, data_end)

# ==========================================
# Tab Specific Formatting Functions
# ==========================================

@require_formatting
def format_valuation_card(spreadsheet) -> None:
    """Part 1: Valuation_Card formatting (Uses Snippet 1's A-W columns based on CSV headers)"""
    tab_name = "Valuation_Card"
    try:
        ws = spreadsheet.worksheet(tab_name)
        
        # Post-2.3 layout (A–Y, 25 cols):
        # Ticker(A), Name(B), Sector(C), MarketCap(D), Price(E),
        # Trim Target(F), Add Target(G), TrailingPE(H), FwdPE_FMP(I), FwdPE_yf(J),
        # PB(K), PEG(L), GrossMargin(M), ROIC(N), DE(O), RevGrowth(P),
        # DivYield(Q), PayoutRatio(R), 52wLow(S), 52wHigh(T),
        # 52wPos%(U), Discount%(V), ValSignal(W), FMP_Avail(X), LastUpdated(Y)
        widths = [
            ("A", 70),  ("B", 180), ("C", 110), ("D", 90),  ("E", 80),
            ("F", 90),  ("G", 90),  ("H", 80),  ("I", 90),  ("J", 90),
            ("K", 70),  ("L", 70),  ("M", 90),  ("N", 90),  ("O", 70),
            ("P", 90),  ("Q", 80),  ("R", 80),  ("S", 80),  ("T", 80),
            ("U", 110), ("V", 110), ("W", 120), ("X", 80),  ("Y", 120),
        ]
        safe_api_call(set_column_widths, ws, widths)
        format_standard_table(ws, header_range="A1:Y1", header_row=1, data_start=2, data_end=MAX_DATA_ROWS)
        
        # Percentage columns — letters reflect post-2.3 layout
        # (Price=E, Trim=F, Add=G shifted H onward by 3 vs pre-2.3)
        # Gross Margin(M), ROIC(N), Rev Growth(P), Div Yield(Q), Payout Ratio(R), 52w Pos(U), Discount(V)
        pct_fmt = CellFormat(numberFormat=NumberFormat(type="PERCENT", pattern="0.00%"))
        for col in ["M", "N", "P", "Q", "R", "U", "V"]:
            safe_format(ws, f"{col}2:{col}{MAX_DATA_ROWS}", pct_fmt)

        rules = safe_api_call(get_conditional_format_rules, ws)
        rules.clear()
        
        # 52w Position % (Column U — shifted after Price/Trim/Add insertion in 2.3)
        rules.append(build_gradient_rule(ws, f"U2:U{MAX_DATA_ROWS}", COLOR_RED_DARK, COLOR_WHITE, COLOR_GREEN_DARK))

        # Discount from 52w High % (Column V)
        rules.append(build_boolean_rule(ws, f"V2:V{MAX_DATA_ROWS}", "NUMBER_GREATER", ["0.30"], bg_color=COLOR_GREEN_LIGHT))
        rules.append(build_boolean_rule(ws, f"V2:V{MAX_DATA_ROWS}", "NUMBER_LESS", ["0.10"], bg_color=COLOR_RED_LIGHT))

        # Trailing P/E (Column H — shifted)
        rules.append(build_boolean_rule(ws, f"H2:H{MAX_DATA_ROWS}", "NUMBER_GREATER", ["40"], bg_color=COLOR_RED_LIGHT))
        rules.append(build_boolean_rule(ws, f"H2:H{MAX_DATA_ROWS}", "NUMBER_LESS", ["15"], bg_color=COLOR_GREEN_LIGHT))

        # PEG (Column L — shifted)
        rules.append(build_boolean_rule(ws, f"L2:L{MAX_DATA_ROWS}", "NUMBER_GREATER", ["2"], bg_color=COLOR_RED_LIGHT))
        rules.append(build_boolean_rule(ws, f"L2:L{MAX_DATA_ROWS}", "NUMBER_LESS", ["1"], bg_color=COLOR_GREEN_LIGHT))

        # Phase 2.4 — Price trigger action zones (Price=E, Trim Target=F, Add Target=G)
        # Trim zone: price has reached or exceeded Bill's trim target → bold red
        rules.append(build_boolean_rule(
            ws, f"E2:E{MAX_DATA_ROWS}", "CUSTOM_FORMULA",
            [f"=AND(E2<>\"\",F2<>\"\",E2>=F2)"],
            bg_color=COLOR_RED_LIGHT, text_color=COLOR_RED_DARK, bold=True,
        ))
        # Add zone: price has dropped to or below Bill's add target → bold green
        rules.append(build_boolean_rule(
            ws, f"E2:E{MAX_DATA_ROWS}", "CUSTOM_FORMULA",
            [f"=AND(E2<>\"\",G2<>\"\",E2<=G2)"],
            bg_color=COLOR_GREEN_LIGHT, text_color=COLOR_GREEN_DARK, bold=True,
        ))

        save_rules(ws, rules)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

@require_formatting
def format_decision_view(spreadsheet) -> None:
    """Part 2: Decision_View formatting (Uses Snippet 1's 10-column layout)"""
    tab_name = "Decision_View"
    try:
        ws = spreadsheet.worksheet(tab_name)
        
        # Post-2.3 layout (13 cols):
        # Ticker(A), Weight%(B), MV(C), UGL%(D), DayChg%(E),
        # Price(F), Trim Target(G), Add Target(H), FwdPE(I),
        # 52wPos%(J), Disc%(K), ValSignal(L), Rationale(M)
        widths = [
            ("A", 70), ("B", 70), ("C", 110), ("D", 100), ("E", 90),
            ("F", 90), ("G", 100), ("H", 100), ("I", 80),
            ("J", 100), ("K", 110), ("L", 120), ("M", 400),
        ]
        safe_api_call(set_column_widths, ws, widths)
        format_standard_table(ws, header_range="A1:M1", header_row=1, data_start=2, data_end=MAX_DATA_ROWS)

        safe_api_call(set_row_height, ws, f"2:{MAX_DATA_ROWS}", 60)
        safe_format(ws, f"A2:M{MAX_DATA_ROWS}", CellFormat(wrapStrategy="WRAP", verticalAlignment="MIDDLE"))

        # Percentage formats — Weight%(B), UGL%(D), DayChg%(E), 52wPos%(J), Disc%(K)
        pct_fmt = CellFormat(wrapStrategy="WRAP", verticalAlignment="MIDDLE", numberFormat=NumberFormat(type="PERCENT", pattern="0.00%"))
        for col in ["B", "D", "E", "J", "K"]:
            safe_format(ws, f"{col}2:{col}{MAX_DATA_ROWS}", pct_fmt)

        rules = safe_api_call(get_conditional_format_rules, ws)
        rules.clear()
        
        # Valuation Signals (Column I)
        signal_map = {"accumulate": COLOR_GREEN_LIGHT, "trim": COLOR_RED_LIGHT, "hold": COLOR_YELLOW_LIGHT, "monitor": COLOR_BLUE_LIGHT, "add": COLOR_GREEN_LIGHT}
        for val, color in signal_map.items():
            rules.append(build_boolean_rule(ws, f"I2:I{MAX_DATA_ROWS}", "TEXT_EQ", [val], bg_color=color))
            
        # Unreal G/L % (Column D)
        rules.append(build_boolean_rule(ws, f"D2:D{MAX_DATA_ROWS}", "NUMBER_GREATER", ["0"], text_color=COLOR_GREEN_DARK))
        rules.append(build_boolean_rule(ws, f"D2:D{MAX_DATA_ROWS}", "NUMBER_LESS", ["0"], text_color=COLOR_RED_DARK))

        # 52w Pos % (Column J — post-2.3 layout)
        rules.append(build_gradient_rule(ws, f"J2:J{MAX_DATA_ROWS}", COLOR_GREEN_DARK, COLOR_WHITE, COLOR_RED_DARK))

        # Phase 2.4 — Price trigger action zones (Price=F, Trim Target=G, Add Target=H)
        # Trim zone: price has reached or exceeded Bill's trim target → bold red
        rules.append(build_boolean_rule(
            ws, f"F2:F{MAX_DATA_ROWS}", "CUSTOM_FORMULA",
            [f"=AND(F2<>\"\",G2<>\"\",F2>=G2)"],
            bg_color=COLOR_RED_LIGHT, text_color=COLOR_RED_DARK, bold=True,
        ))
        # Add zone: price has dropped to or below Bill's add target → bold green
        rules.append(build_boolean_rule(
            ws, f"F2:F{MAX_DATA_ROWS}", "CUSTOM_FORMULA",
            [f"=AND(F2<>\"\",H2<>\"\",F2<=H2)"],
            bg_color=COLOR_GREEN_LIGHT, text_color=COLOR_GREEN_DARK, bold=True,
        ))

        save_rules(ws, rules)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

@require_formatting
def format_agent_outputs_v2(spreadsheet):
    """Part 3: Agent_Outputs revised formatting with READABILITY focus"""
    tab_name = getattr(config, 'TAB_AGENT_OUTPUTS', 'Agent_Outputs')
    try:
        ws = spreadsheet.worksheet(tab_name)
        all_values = ws.get_all_values()
        
        # Ensure frozen summary row exists
        first_cell = all_values[0][0] if all_values and all_values[0] else None
        if first_cell and "Accumulate:" not in str(first_cell):
            safe_api_call(ws.insert_row, [""], 1)
            time.sleep(1)
            all_values = ws.get_all_values()
            
        headers = all_values[1] # Usually Row 2 now
        
        def get_col(name: str, fallback_let: str) -> str:
            try:
                idx = next(i for i, h in enumerate(headers) if h.strip().lower() in name.lower().split('|'))
                return chr(ord('A') + idx)
            except StopIteration:
                return fallback_let

        col_signal = get_col('signal|signal_type', 'D')
        
        # 1. Column Widths (Surgical Control)
        widths = [
            ("A", 100), ("B", 70), ("C", 90), ("D", 80), ("E", 80),
            ("F", 350), ("G", 550), ("H", 120), ("I", 100), ("J", 80)
        ]
        safe_api_call(set_column_widths, ws, widths)

        # 2. Row heights and global alignment
        safe_api_call(set_row_height, ws, f"3:{MAX_AGENT_ROWS}", 60)
        content_fmt = CellFormat(wrapStrategy="WRAP", verticalAlignment="TOP", horizontalAlignment="LEFT", textFormat=TextFormat(fontSize=10))
        safe_format(ws, f"A3:K{MAX_AGENT_ROWS}", content_fmt)

        # Summary Row (Row 1)
        summary_formula = (
            f'="Accumulate: "&COUNTIF({col_signal}3:{col_signal}{MAX_AGENT_ROWS},"ADD")&'
            f'" | Trim: "&COUNTIF({col_signal}3:{col_signal}{MAX_AGENT_ROWS},"TRIM")&'
            f'" | Hold: "&COUNTIF({col_signal}3:{col_signal}{MAX_AGENT_ROWS},"HOLD")&'
            f'" | Exit: "&COUNTIF({col_signal}3:{col_signal}{MAX_AGENT_ROWS},"EXIT")&'
            f'" | Monitor: "&COUNTIF({col_signal}3:{col_signal}{MAX_AGENT_ROWS},"MONITOR")'
        )
        safe_api_call(ws.update, [[summary_formula]], 'A1', value_input_option="USER_ENTERED")
        
        # Split merge to avoid "You can't merge frozen and non-frozen columns" error
        try:
            safe_api_call(ws.merge_cells, "A1:E1")
            safe_api_call(ws.merge_cells, "F1:K1")
        except Exception as _me:
            pass
            
        safe_format(ws, "A1:K1", build_header_format(font_size=12))
        safe_format(ws, "A2:K2", build_header_format())
        safe_api_call(set_frozen, ws, rows=2, cols=5) 
        
        rules = safe_api_call(get_conditional_format_rules, ws)
        rules.clear()
        
        # Signal Type Colors
        sig_range = f"{col_signal}3:{col_signal}{MAX_AGENT_ROWS}"
        rules.append(build_boolean_rule(ws, sig_range, "TEXT_EQ", ["ADD"], bg_color=COLOR_GREEN_LIGHT))
        rules.append(build_boolean_rule(ws, sig_range, "TEXT_EQ", ["TRIM"], bg_color=COLOR_RED_LIGHT))
        rules.append(build_boolean_rule(ws, sig_range, "TEXT_EQ", ["HOLD"], bg_color=COLOR_YELLOW_LIGHT))
        rules.append(build_boolean_rule(ws, sig_range, "TEXT_EQ", ["MONITOR"], bg_color=COLOR_BLUE_LIGHT))
        rules.append(build_boolean_rule(ws, sig_range, "TEXT_EQ", ["EXIT"], bg_color=COLOR_RED_DARK, text_color=COLOR_WHITE))
        
        save_rules(ws, rules)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

@require_formatting
def format_holdings_current_v2(spreadsheet):
    """Part 4: Holdings_Current KPI and Readability Fix"""
    tab_name = getattr(config, 'TAB_HOLDINGS_CURRENT', 'Holdings_Current')
    try:
        ws = spreadsheet.worksheet(tab_name)
        
        # ULTIMATE UNMERGE (Must happen before any read/write to avoid gspread bugs)
        for merge_range in ["A1:B1", "C1:D1", "E1:F1", "G1:H1", "I1:J1", "K1:L1"]:
            try:
                ws.unmerge_cells(merge_range)
            except Exception:
                pass 
        time.sleep(5)

        all_values = ws.get_all_values()
        
        # Ensure KPI row exists without overwriting headers
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
                    headers = all_values[header_row_idx]
                    data_start_row = header_row_idx + 2
                    break

        def get_col(name: str, fallback: str) -> str:
            try:
                idx = next(i for i, h in enumerate(headers) if h.strip().lower() == name.lower())
                return chr(ord('A') + idx)
            except StopIteration:
                return fallback

        col_ticker = get_col('Ticker', 'A')
        col_mv = get_col('Market Value', 'G')
        col_cb = get_col('Cost Basis', 'H')
        col_ugl = get_col('Unrealized G/L', 'J')
        
        rules = safe_api_call(get_conditional_format_rules, ws)
        rules.clear()
        
        ugl_range = f"{col_ugl}{data_start_row}:{col_ugl}{MAX_DATA_ROWS}"
        rules.append(build_boolean_rule(ws, ugl_range, "NUMBER_GREATER", ["0"], text_color=COLOR_GREEN_DARK))
        rules.append(build_boolean_rule(ws, ugl_range, "NUMBER_LESS", ["0"], text_color=COLOR_RED_DARK))
        save_rules(ws, rules)
        
        # Formatting
        safe_api_call(set_frozen, ws, rows=2, cols=0)
        safe_format(ws, f"A{header_row_idx+1}:T{header_row_idx+1}", build_header_format())
        apply_alternating_banding(ws, data_start_row, MAX_DATA_ROWS)

        # FINAL KPI WRITE
        drange = f"{data_start_row}:{MAX_DATA_ROWS}" # e.g. "3:200"
        kpi_formulas = [
            ("A1", "📊 PORTFOLIO SNAPSHOT"),
            ("C1", f'="Total Value: "&TEXT(SUMIF({col_ticker}{drange}, "*", {col_mv}{drange}), "$#,##0")'),
            ("E1", f'="Dry Powder: "&TEXT(SUMIF({col_ticker}{drange},"CASH_MANUAL",{col_mv}{drange})+SUMIF({col_ticker}{drange},"SGOV",{col_mv}{drange}), "$#,##0")'),
            ("G1", f'="Cash + SGOV: "&TEXT(SUMIF({col_ticker}{drange},"CASH_MANUAL",{col_mv}{drange})+SUMIF({col_ticker}{drange},"SGOV",{col_mv}{drange})+SUMIF({col_ticker}{drange},"QACDS",{col_mv}{drange}), "$#,##0")'),
            ("I1", f'="G/L %: "&TEXT(IF(SUMIF({col_ticker}{drange}, "*", {col_cb}{drange})=0, 0, SUMIF({col_ticker}{drange}, "*", {col_ugl}{drange})/SUMIF({col_ticker}{drange}, "*", {col_cb}{drange})), "0.00%")'),
            ("K1", f'="Positions: "&(COUNTA({col_ticker}{drange})-COUNTIF({col_ticker}{drange},"CASH_MANUAL")-COUNTIF({col_ticker}{drange},"QACDS"))')
        ]

        ws.update(range_name="A1:T1", values=[["" for _ in range(20)]])
        time.sleep(2)

        for cell, val in kpi_formulas:
            ws.update_acell(cell, val)
        time.sleep(3)

        safe_format(ws, "A1:L1", build_header_format(font_size=11))

        # Re-merge
        for merge_range in ["A1:B1", "C1:D1", "E1:F1", "G1:H1", "I1:J1", "K1:L1"]:
            try:
                ws.merge_cells(merge_range)
            except Exception:
                pass 

        print(f"  ✓ updated KPI and formatting for {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to update KPI for {tab_name}: {e}")

@require_formatting
def format_realized_gl_v2(spreadsheet):
    """Part 5: Realized_GL Wash Sale UI"""
    tab_name = getattr(config, 'TAB_REALIZED_GL', 'Realized_GL')
    try:
        ws = spreadsheet.worksheet(tab_name)
        
        row2_val = safe_api_call(ws.cell, 2, 1).value
        if row2_val and "WASH SALE RISK" not in str(row2_val):
            safe_api_call(ws.insert_row, [""], 2)
            time.sleep(1)
            
        safe_format(ws, "J1", CellFormat(
            textFormat=TextFormat(bold=True, foregroundColor=COLOR_RED_DARK, fontSize=12), 
            numberFormat=NumberFormat(type="CURRENCY", pattern='"$"#,##0')
        ))
        
        # Row 2 Wash Sale Warning
        safe_api_call(ws.update, [["⚠️ WASH SALE RISK: Review before year-end. Disallowed losses cannot offset gains."]], "A2", value_input_option="USER_ENTERED")
        safe_api_call(ws.merge_cells, "A2:S2")
        safe_format(ws, "A2:S2", CellFormat(backgroundColor=COLOR_ORANGE, textFormat=TextFormat(bold=True, foregroundColor=COLOR_WHITE), horizontalAlignment="CENTER"))
        
        safe_api_call(set_frozen, ws, rows=3, cols=0)
        
        rules = safe_api_call(get_conditional_format_rules, ws)
        rules.clear()
        
        # Disallowed Loss Highlighting
        rules.append(build_boolean_rule(ws, f"A4:S{MAX_DAILY_ROWS}", "CUSTOM_FORMULA", ["=$R4>0"], bg_color=COLOR_YELLOW_LIGHT))
        rules.append(build_boolean_rule(ws, f"R4:R{MAX_DAILY_ROWS}", "NUMBER_GREATER", ["0"], bg_color=COLOR_RED_LIGHT, text_color=COLOR_RED_DARK, bold=True))
        
        save_rules(ws, rules)
        print(f"  ✓ formatted {tab_name}")
    except Exception as e:
        print(f"  ⚠ Failed to format {tab_name}: {e}")

@require_formatting
def format_daily_snapshots_v2(spreadsheet):
    """Part 6: Daily_Snapshots formatting"""
    tab_name = getattr(config, 'TAB_DAILY_SNAPSHOTS', 'Daily_Snapshots')
    try:
        ws = spreadsheet.worksheet(tab_name)
        try:
            safe_api_call(set_frozen, ws, rows=2)
        except Exception:
            pass
            
        widths = [
            ("A", 100), ("B", 120), ("C", 120), ("D", 140), ("E", 110),
            ("F", 120), ("G", 90), ("H", 100), ("I", 150)
        ]
        safe_api_call(set_column_widths, ws, widths)
        safe_format(ws, "A2:I2", build_header_format())
        
        apply_alternating_banding(ws, 3, MAX_DAILY_ROWS)
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
    
    # Run formatting and sleep between tabs to respect strict Sheets API quotas
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