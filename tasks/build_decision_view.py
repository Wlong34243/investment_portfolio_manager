"""
tasks/build_decision_view.py — Builds the Decision_View tab: agent-signal rows only.

Decision_View no longer duplicates 0_DASHBOARD's full position table. It shows
only tickers with an active signal (ADD/TRIM/etc.) from the latest Agent_Outputs
run, with full untruncated rationale -- reusing the exact same Holdings_Current x
Valuation_Card x Agent signal join build_command_center.py uses for 0_DASHBOARD,
so the two views can never disagree on the underlying numbers.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import typer

import config
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import safe_execute
from utils.agent_signals import get_latest_agent_outputs
from tasks.build_command_center import _read_records, _build_position_table

app = typer.Typer()

_DEC_COLS = [
    "Ticker", "Signal", "Market Value", "Wt%", "Price", "Trim", "Add",
    "->Trim %", "->Add %", "Fwd P/E", "52w %", "Rationale",
]
_DATA_START_ROW = 3


def _pad(row: list, n: int = len(_DEC_COLS)) -> list:
    return (row + [""] * n)[:n]


def _run_header(df_agent) -> str:
    if df_agent.empty:
        return "AGENT SIGNALS — no agent run found"
    run_id = df_agent["run_id"].iloc[0] if "run_id" in df_agent.columns else "n/a"
    run_ts = df_agent["run_ts"].iloc[0] if "run_ts" in df_agent.columns else "n/a"
    return f"AGENT SIGNALS — run {run_id}  {run_ts}"


def _print_dry_run(header: str, signal_rows: list[dict]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(header)

    table = Table(show_header=True, header_style="bold")
    for col in _DEC_COLS:
        table.add_column(col, overflow="fold")
    for p in signal_rows:
        table.add_row(
            p["Ticker"], p["Signal"],
            f'${p["MV"]:,.0f}' if p["MV"] is not None else "—",
            f'{p["Wt%"]*100:.1f}%' if p["Wt%"] is not None else "—",
            f'${p["Price"]:,.2f}' if p["Price"] is not None else "—",
            f'${p["Trim"]:,.2f}' if p["Trim"] else "—",
            f'${p["Add"]:,.2f}' if p["Add"] else "—",
            f'{p["->Trim %"]*100:+.1f}%' if p["->Trim %"] is not None else "—",
            f'{p["->Add %"]*100:+.1f}%' if p["->Add %"] is not None else "—",
            f'{p["Fwd P/E"]:.1f}' if p["Fwd P/E"] else "—",
            f'{p["52w %"]*100:.0f}%' if p["52w %"] is not None else "—",
            p["Rationale"],
        )
    console.print(table)
    console.print(f"[dim]{len(signal_rows)} signal rows.[/]")
    console.print("[dim]DRY RUN — no Sheet writes. Re-run with --live to apply.[/]")


def _apply_formatting(ws, header: str, n_rows: int) -> None:
    try:
        from gspread_formatting import (
            CellFormat, Color, TextFormat, NumberFormat,
            format_cell_ranges, set_frozen, set_column_widths,
        )
    except ImportError:
        print("  ! gspread_formatting not installed, skipping visual styles.")
        return

    NAVY = Color(0.10, 0.15, 0.27)
    WHITE = Color(1, 1, 1)
    GREY_BG = Color(0.95, 0.95, 0.95)

    last_col = "L"
    data_end = _DATA_START_ROW - 1 + max(n_rows, 1)

    dollar_fmt = NumberFormat(type='CURRENCY', pattern='$#,##0.00')
    dollar0_fmt = NumberFormat(type='CURRENCY', pattern='$#,##0')
    pct_fmt = NumberFormat(type='PERCENT', pattern='0.0%')
    pct_signed_fmt = NumberFormat(type='PERCENT', pattern='+0.0%;-0.0%')
    float1_fmt = NumberFormat(type='NUMBER', pattern='0.0')

    ranges = [
        (f"A1:{last_col}1", CellFormat(backgroundColor=NAVY, textFormat=TextFormat(bold=True, fontSize=11, foregroundColor=WHITE))),
        (f"A2:{last_col}2", CellFormat(backgroundColor=GREY_BG, textFormat=TextFormat(bold=True))),
        (f"A{_DATA_START_ROW}:A{data_end}", CellFormat(textFormat=TextFormat(bold=True))),
        (f"C{_DATA_START_ROW}:C{data_end}", CellFormat(numberFormat=dollar0_fmt)),
        (f"D{_DATA_START_ROW}:D{data_end}", CellFormat(numberFormat=pct_fmt)),
        (f"E{_DATA_START_ROW}:E{data_end}", CellFormat(numberFormat=dollar_fmt)),
        (f"F{_DATA_START_ROW}:F{data_end}", CellFormat(numberFormat=dollar_fmt)),
        (f"G{_DATA_START_ROW}:G{data_end}", CellFormat(numberFormat=dollar_fmt)),
        (f"H{_DATA_START_ROW}:H{data_end}", CellFormat(numberFormat=pct_signed_fmt)),
        (f"I{_DATA_START_ROW}:I{data_end}", CellFormat(numberFormat=pct_signed_fmt)),
        (f"J{_DATA_START_ROW}:J{data_end}", CellFormat(numberFormat=float1_fmt)),
        (f"K{_DATA_START_ROW}:K{data_end}", CellFormat(numberFormat=pct_fmt)),
        (f"L{_DATA_START_ROW}:L{data_end}", CellFormat(wrapStrategy="WRAP", verticalAlignment="TOP")),
    ]
    try:
        format_cell_ranges(ws, ranges)
    except Exception as e:
        print(f"  ! Decision_View formatting failed: {e}")

    try:
        set_frozen(ws, rows=2, cols=1)
    except Exception as e:
        print(f"  ! Freeze failed: {e}")

    try:
        set_column_widths(ws, [
            ("A", 70), ("B", 70), ("C", 100), ("D", 70), ("E", 90),
            ("F", 90), ("G", 90), ("H", 90), ("I", 90), ("J", 70),
            ("K", 70), ("L", 500),
        ])
    except Exception as e:
        print(f"  ! Column widths failed: {e}")


@app.command()
def main(live: bool = typer.Option(False, "--live", help="Write to Google Sheets")):
    print(f"Building Decision View (Live={live})...")

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    holdings_rows = _read_records(ss, config.TAB_HOLDINGS_CURRENT)
    valuation_rows = _read_records(ss, "Valuation_Card")

    try:
        ws_agent = ss.worksheet(config.TAB_AGENT_OUTPUTS)
        df_agent = get_latest_agent_outputs(ws_agent)
    except Exception as e:
        print(f"Warning: Could not read {config.TAB_AGENT_OUTPUTS}: {e}")
        import pandas as pd
        df_agent = pd.DataFrame()

    header = _run_header(df_agent)
    positions = _build_position_table(holdings_rows, valuation_rows, df_agent)
    signal_rows = [p for p in positions if p.get("Signal")]

    if not live:
        _print_dry_run(header, signal_rows)
        return

    grid = [_pad([header]), _pad(_DEC_COLS)]
    for p in signal_rows:
        grid.append(_pad([
            p["Ticker"], p["Signal"], p["MV"], p["Wt%"], p["Price"],
            p["Trim"], p["Add"], p["->Trim %"], p["->Add %"],
            p["Fwd P/E"], p["52w %"], p["Rationale"],
        ]))
    grid = [["" if c is None else c for c in row] for row in grid]

    tab_name = "Decision_View"
    try:
        ws_dec = ss.worksheet(tab_name)
    except Exception:
        ws_dec = ss.add_worksheet(title=tab_name, rows=max(50, len(grid) + 5), cols=len(_DEC_COLS))

    safe_execute(ws_dec.clear)
    safe_execute(ws_dec.update, range_name="A1", values=grid, value_input_option="RAW")
    _apply_formatting(ws_dec, header, len(signal_rows))

    print(f"\nWrote {len(signal_rows)} signal rows to {tab_name}")


if __name__ == "__main__":
    app()
