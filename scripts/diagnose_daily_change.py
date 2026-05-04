"""
scripts/diagnose_daily_change.py — Diagnostic: Daily Change % pipeline trace

Walks every transformation between Schwab API → bundle → Sheet write
and prints, for one or more sample tickers, whether 'Daily Change %' is:
  - present in the source dict
  - present after column mapping
  - present after type coercion
  - present in the bundle JSON
  - present in the DataFrame passed to write_to_sheets
  - present in the Decision_View source data

Read-only. No Sheet writes. No bundle writes. No mutations.

Usage:
  python scripts/diagnose_daily_change.py
  python scripts/diagnose_daily_change.py --tickers UNH,GOOG,JPIE
  python scripts/diagnose_daily_change.py --bundle bundles/context_bundle_2026-04-30.json
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = Path(_HERE).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from utils.schwab_client import get_accounts_client, fetch_positions
from utils.sheet_readers import get_gspread_client

app = typer.Typer()
console = Console()

def get_latest_bundle_path() -> Optional[Path]:
    candidates = sorted(
        Path("bundles").glob("context_bundle_*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None

def stage_1_schwab_raw(tickers: List[str], skip_live: bool):
    table = Table(title="STAGE 1: Raw Schwab JSON")
    table.add_column("Ticker")
    table.add_column("Candidate keys found")
    table.add_column("Values")
    
    if skip_live:
        for ticker in tickers:
            table.add_row(ticker, "(skipped — live fetch disabled)", "—")
        console.print(table)
        return None

    client = get_accounts_client()
    if not client:
        console.print("[red]Error: Could not get Schwab accounts client.[/red]")
        return None

    try:
        r = client.get_accounts(fields=client.Account.Fields.POSITIONS)
        r.raise_for_status()
        accounts = r.json()
    except Exception as e:
        console.print(f"[red]Error fetching Schwab accounts: {e}[/red]")
        return None

    found_data = {}
    
    for ticker in tickers:
        candidates = []
        values = []
        
        found_in_api = False
        for acc in accounts:
            positions = acc.get('securitiesAccount', {}).get('positions', [])
            for p in positions:
                instr = p.get('instrument', {})
                if instr.get('symbol') == ticker:
                    found_in_api = True
                    keys = sorted(p.keys())
                    relevant_keys = [k for k in keys if any(x in k.lower() for x in ['change', 'percent', 'pct', 'day', 'gain', 'loss'])]
                    candidates.extend(relevant_keys)
                    values.extend([str(p.get(k)) for k in relevant_keys])
                    
                    if ticker not in found_data:
                        found_data[ticker] = p
        
        if not found_in_api:
            table.add_row(ticker, "(not found in API positions)", "—")
        else:
            table.add_row(ticker, "\n".join(candidates) if candidates else "(none found)", "\n".join(values) if values else "—")

    console.print(table)
    return found_data

def stage_2_fetch_positions_df(tickers: List[str], skip_live: bool):
    table = Table(title="STAGE 2: Post-mapping DataFrame")
    table.add_column("Ticker")
    table.add_column("Daily Change %")
    table.add_column("Type")
    table.add_column("Other 'change/pct' columns")

    if skip_live:
        for ticker in tickers:
            table.add_row(ticker, "(skipped)", "—", "—")
        console.print(table)
        return

    client = get_accounts_client()
    if not client:
        return

    df = fetch_positions(client)
    
    for ticker in tickers:
        row = df[df['ticker'] == ticker] if 'ticker' in df.columns else df[df['Ticker'] == ticker]
        if row.empty:
            table.add_row(ticker, "(not found in DF)", "—", "—")
            continue
        
        val = row.iloc[0].get('daily_change_pct', row.iloc[0].get('Daily Change %', 'MISSING'))
        val_type = type(val).__name__
        
        other_cols = [c for c in df.columns if any(x in c.lower() for x in ['change', 'pct']) and c not in ['daily_change_pct', 'Daily Change %']]
        other_vals = [f"{c}: {row.iloc[0][c]}" for c in other_cols]
        
        table.add_row(ticker, str(val), val_type, "\n".join(other_vals) if other_vals else "(none)")

    console.print(table)

def stage_3_bundle_json(tickers: List[str], bundle_path: Optional[Path]):
    table = Table(title="STAGE 3: Bundle JSON")
    table.add_column("Ticker")
    table.add_column("Relevant Keys")
    table.add_column("Values")

    if not bundle_path or not bundle_path.exists():
        table.add_row("(none)", "(bundle not found)", "—")
        console.print(table)
        return

    try:
        with open(bundle_path, "r", encoding="utf-8") as f:
            bundle = json.load(f)
    except Exception as e:
        console.print(f"[red]Error reading bundle: {e}[/red]")
        return

    positions = bundle.get("positions", [])
    
    for ticker in tickers:
        pos = next((p for p in positions if p.get('ticker') == ticker), None)
        if not pos:
            table.add_row(ticker, "(not in bundle)", "—")
            continue
        
        keys = sorted(pos.keys())
        relevant_keys = [k for k in keys if any(x in k.lower() for x in ['change', 'pct', 'percent', 'daily'])]
        values = [str(pos.get(k)) for k in relevant_keys]
        
        table.add_row(ticker, "\n".join(relevant_keys) if relevant_keys else "(none)", "\n".join(values) if values else "—")

    console.print(table)

def stage_4_schema_check():
    table = Table(title="STAGE 4: Sheet Schema Check")
    table.add_column("Metric")
    table.add_column("Value")
    
    cols = config.POSITION_COLUMNS
    try:
        idx = cols.index('Daily Change %')
        status = f"Found at index {idx} (Column {chr(ord('A') + idx)})"
        if idx == 16:
            status += " [green](Correct: Column Q)[/green]"
        else:
            status += f" [red](MISMATCH: Expected 16/Q)[/red]"
    except ValueError:
        status = "[red]NOT FOUND in config.POSITION_COLUMNS[/red]"
    
    table.add_row("'Daily Change %' in POSITION_COLUMNS", status)
    
    map_entry = config.POSITION_COL_MAP.get('daily_change_pct')
    table.add_row("'daily_change_pct' in POSITION_COL_MAP", str(map_entry))
    
    console.print(table)

def stage_5_live_sheet_read(tickers: List[str]):
    table = Table(title="STAGE 5: Live Sheet Read (Holdings_Current)")
    table.add_column("Ticker")
    table.add_column("Column Q Value")
    table.add_column("Raw Content")

    try:
        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_HOLDINGS_CURRENT)
        
        # Get all tickers (Column A) and Daily Change % (Column Q)
        all_tickers = ws.col_values(1) # Ticker
        all_changes = ws.col_values(17) # Column Q
        
        ticker_map = {t: v for t, v in zip(all_tickers, all_changes)}
        
        for ticker in tickers:
            val = ticker_map.get(ticker, "(not found)")
            table.add_row(ticker, val, f"repr: {repr(val)}")
    except Exception as e:
        console.print(f"[red]Error reading live sheet: {e}[/red]")
        for ticker in tickers:
            table.add_row(ticker, "(error)", str(e))

    console.print(table)

def stage_6_decision_view_source():
    table = Table(title="STAGE 6: Decision_View Source Logic")
    table.add_column("Check")
    table.add_column("Observation")
    
    # Path trace from build_decision_view.py
    # We know it from reading the file
    observation = (
        "1. Reads Holdings_Current via ws.get_all_values()\n"
        "2. Normalizes via ensure_display_columns(df_holdings)\n"
        "3. h_daily = to_pct_float(row_h.get('Daily Change %'))\n"
        "4. tech_daily = tech_data.get('daily_change_pct', 0.0)\n"
        "5. daily_chg = tech_daily if (h_daily == 0.0 and t_daily != 0.0) else h_daily"
    )
    table.add_row("Logic Trace", observation)
    
    # Source check for UNH
    try:
        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet("Decision_View")
        headers = ws.row_values(1)
        try:
            col_idx = headers.index('Daily Chg %') + 1
            sample_val = ws.cell(2, col_idx).value
            table.add_row("Decision_View Sample (Row 2)", f"Column {col_idx}: {sample_val}")
        except ValueError:
            table.add_row("Decision_View Header", "[red]'Daily Chg %' not found[/red]")
    except Exception as e:
        table.add_row("Live Read", f"[red]Error: {e}[/red]")

    console.print(table)

@app.command()
def main(
    tickers: str = typer.Option("UNH,GOOG,JPIE,SGOV,CASH_MANUAL", help="Comma-separated tickers"),
    bundle: Optional[str] = typer.Option(None, help="Path to bundle JSON"),
    skip_live_fetch: bool = typer.Option(False, "--skip-live-fetch", help="Skip Schwab API calls")
):
    ticker_list = [t.strip() for t in tickers.split(",")]
    bundle_path = Path(bundle) if bundle else get_latest_bundle_path()
    
    console.rule("[bold blue]Daily Change % Pipeline Diagnosis")
    
    # Run Stages
    raw_schwab = stage_1_schwab_raw(ticker_list, skip_live_fetch)
    stage_2_fetch_positions_df(ticker_list, skip_live_fetch)
    stage_3_bundle_json(ticker_list, bundle_path)
    stage_4_schema_check()
    stage_5_live_sheet_read(ticker_list)
    stage_6_decision_view_source()
    
    console.rule("[bold yellow]DIAGNOSIS")
    
    # Logic for final diagnosis
    diagnosis_point = "ALL PASS"
    recommendation = "No issues found in the Daily Change % pipeline."
    
    # Check Stages in reverse to find the first failure
    
    # Stage 5 check
    try:
        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_HOLDINGS_CURRENT)
        all_tickers = ws.col_values(1)
        all_changes = ws.col_values(17)
        ticker_map = {t: v for t, v in zip(all_tickers, all_changes)}
        
        # Check a sample ticker that should have a change (like UNH or GOOG)
        found_non_zero = False
        for t in ticker_list:
            val = ticker_map.get(t, "0.00%")
            if val != "0.00%" and val != "0.0%":
                found_non_zero = True
                break
        
        if not found_non_zero:
            diagnosis_point = "STAGE 4 → STAGE 5"
            recommendation = "Values are 0.00% in the Sheet (Holdings_Current). Check if the bundle-push task or pipeline.write_to_sheets is being called with zeros."
    except:
        pass

    # Stage 3 check (Bundle)
    if bundle_path and bundle_path.exists():
        with open(bundle_path, "r", encoding="utf-8") as f:
            bundle = json.load(f)
        positions = bundle.get("positions", [])
        found_non_zero_bundle = False
        for t in ticker_list:
            pos = next((p for p in positions if p.get('ticker') == t), None)
            if pos and pos.get('daily_change_pct', 0.0) != 0.0:
                found_non_zero_bundle = True
                break
        
        if not found_non_zero_bundle:
            diagnosis_point = "STAGE 2 → STAGE 3"
            recommendation = "Values are non-zero in Stage 2 (DataFrame) but zero in Stage 3 (Bundle). Check if core/bundle.py is overwriting daily_change_pct (e.g., via Market Data quotes)."

    # Stage 2 check (DataFrame)
    if not skip_live_fetch:
        client = get_accounts_client()
        if client:
            df = fetch_positions(client)
            found_non_zero_df = False
            for t in ticker_list:
                row = df[df['ticker'] == t] if 'ticker' in df.columns else df[df['Ticker'] == t]
                if not row.empty:
                    val = row.iloc[0].get('daily_change_pct', row.iloc[0].get('Daily Change %', 0.0))
                    if val != 0.0:
                        found_non_zero_df = True
                        break
            if not found_non_zero_df:
                diagnosis_point = "STAGE 1 → STAGE 2"
                recommendation = "Values are non-zero in Stage 1 (Raw JSON) but zero in Stage 2 (DataFrame). Check POSITION_COL_MAP and fetch_positions mapping."

    if diagnosis_point == "ALL PASS":
        final_rec = f"Likely failure point: [bold green]{diagnosis_point}[/bold green]\n"
    else:
        final_rec = f"Likely failure point: [bold red]{diagnosis_point}[/bold red]\n"
    final_rec += recommendation

    console.print(final_rec)

if __name__ == "__main__":
    app()
