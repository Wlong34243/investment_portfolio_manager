"""
tasks/build_decision_view.py — Builds the Decision_View tab from Crosshairs.

Full ranked Crosshairs list (same producer as 0_DASHBOARD top 5). Facts only:
NEAR_TRIM / NEAR_ADD distances, DISLOCATION metrics, MISSING_LEVEL coverage gaps.
No Agent_Outputs. No buy/sell language.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import typer

import config
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import safe_execute
from tasks.build_command_center import _read_records
from tasks.build_crosshairs import CrosshairsResult, produce_crosshairs

app = typer.Typer(add_completion=False)

_DEC_COLS = [
    "Ticker", "Reason", "Market Value", "Wt%", "Price", "Trim", "Add",
    "->Trim %", "->Add %", "Rationale",
]
_DATA_START_ROW = 3


def _pad(row: list, n: int = len(_DEC_COLS)) -> list:
    return (row + [""] * n)[:n]


def _print_dry_run(header: str, items: list) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(header)

    table = Table(show_header=True, header_style="bold")
    for col in _DEC_COLS:
        table.add_column(col, overflow="fold")
    for item in items:
        table.add_row(
            item.ticker, item.reason_code,
            f"${item.mv:,.0f}" if item.mv is not None else "—",
            f"{item.wt * 100:.1f}%" if item.wt is not None else "—",
            f"${item.price:,.2f}" if item.price is not None else "—",
            f"${item.trim:,.2f}" if item.trim else "—",
            f"${item.add:,.2f}" if item.add else "—",
            f"{item.dist_trim * 100:+.1f}%" if item.dist_trim is not None else "—",
            f"{item.dist_add * 100:+.1f}%" if item.dist_add is not None else "—",
            item.rationale,
        )
    console.print(table)
    console.print(f"[dim]{len(items)} Crosshairs rows.[/]")
    console.print("[dim]DRY RUN — no Sheet writes. Re-run with --live to apply.[/]")


def _apply_formatting(ws, n_rows: int) -> None:
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

    last_col = "J"
    data_end = _DATA_START_ROW - 1 + max(n_rows, 1)

    dollar_fmt = NumberFormat(type='CURRENCY', pattern='$#,##0.00')
    dollar0_fmt = NumberFormat(type='CURRENCY', pattern='$#,##0')
    pct_fmt = NumberFormat(type='PERCENT', pattern='0.0%')
    pct_signed_fmt = NumberFormat(type='PERCENT', pattern='+0.0%;-0.0%')

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
        (f"J{_DATA_START_ROW}:J{data_end}", CellFormat(wrapStrategy="WRAP", verticalAlignment="TOP")),
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
            ("A", 70), ("B", 110), ("C", 100), ("D", 70), ("E", 90),
            ("F", 90), ("G", 90), ("H", 90), ("I", 90), ("J", 500),
        ])
    except Exception as e:
        print(f"  ! Column widths failed: {e}")


def main(live: bool = False, crosshairs: Optional[CrosshairsResult] = None) -> Optional[CrosshairsResult]:
    """Rebuild Decision_View from Crosshairs. Callable from manager.py and CLI."""
    print(f"Building Decision View (Live={live})...")

    if crosshairs is None:
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        holdings_rows = _read_records(ss, config.TAB_HOLDINGS_CURRENT)
        valuation_rows = _read_records(ss, "Valuation_Card")
        crosshairs = produce_crosshairs(
            holdings_rows=holdings_rows,
            valuation_rows=valuation_rows,
            read_sheets_if_needed=False,
        )

    header = crosshairs.header_line
    items = crosshairs.items

    if not live:
        _print_dry_run(header, items)
        return crosshairs

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    grid = [_pad([header]), _pad(_DEC_COLS)]
    for item in items:
        grid.append(_pad([
            item.ticker, item.reason_code, item.mv, item.wt, item.price,
            item.trim, item.add, item.dist_trim, item.dist_add, item.rationale,
        ]))
    grid = [["" if c is None else c for c in row] for row in grid]

    tab_name = "Decision_View"
    try:
        ws_dec = ss.worksheet(tab_name)
    except Exception:
        ws_dec = ss.add_worksheet(title=tab_name, rows=max(50, len(grid) + 5), cols=len(_DEC_COLS))

    safe_execute(ws_dec.clear)
    safe_execute(ws_dec.update, range_name="A1", values=grid, value_input_option="RAW")
    _apply_formatting(ws_dec, len(items))

    print(f"Decision_View refreshed. {len(items)} Crosshairs rows.")
    return crosshairs


@app.command()
def cli(live: bool = typer.Option(False, "--live", help="Write to Google Sheets")):
    main(live=live)


if __name__ == "__main__":
    # Preserve `python tasks/build_decision_view.py --live`
    if len(sys.argv) > 1 and sys.argv[1] not in ("cli", "--help", "-h"):
        main(live="--live" in sys.argv)
    else:
        app()
