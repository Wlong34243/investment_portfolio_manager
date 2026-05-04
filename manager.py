"""
Investment Portfolio Manager — CLI entry point.

Headless, auditable, linear execution. Every run freezes its inputs to
an immutable bundle and exits. No reruns, no state leakage, no hidden
caches.

Usage:
    python manager.py snapshot --csv path/to/positions.csv --cash 10000
    python manager.py snapshot --csv path/to/positions.csv --cash 10000 --live
    python manager.py vault snapshot
    python manager.py bundle composite
"""

import json
import time
import sys
import os
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List

# Ensure project root is in sys.path to avoid shadowing by other projects' 'config.py'
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.bundle import build_bundle, write_bundle, load_bundle
from core.vault_bundle import (
    build_vault_bundle, write_vault_bundle, load_vault_bundle,
    THESES_DIR,
)
from core.composite_bundle import (
    build_composite_bundle, write_composite_bundle,
    load_composite_bundle, resolve_latest_bundles,
)

app = typer.Typer(help="Investment Portfolio Manager CLI", no_args_is_help=True)
console = Console()

# --- JOURNAL GROUP ---
journal_app = typer.Typer(help="Journaling commands — record manual decisions.")
app.add_typer(journal_app, name="journal")

# --- TRADE GROUP ---
trade_app = typer.Typer(help="Trade log review and decision tuning.")
app.add_typer(trade_app, name="trade")

@trade_app.command("review")
def trade_review(
    live: bool = typer.Option(False, "--live", help="Refresh attribution and write to Sheets. Default: DRY RUN.")
):
    """Refresh Rotation_Review with fresh attribution for all Trade_Log rows."""
    from tasks.compute_rotation_attribution import run_attribution
    run_attribution(live=live)

@journal_app.command("promote")
def journal_promote(
    live: bool = typer.Option(False, "--live", help="Write to live Sheets. Default: DRY RUN."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Promote approved staging rows from Trade_Log_Staging to Trade_Log."""
    import uuid
    import config
    from utils.sheet_readers import get_gspread_client

    # Column indices in staging sheet (0-based within header row)
    STAGING_COLS = config.TRADE_LOG_STAGING_COLUMNS  # ordered list

    def _col(row: list, name: str) -> str:
        """Return value from a staging data row by column name."""
        try:
            idx = STAGING_COLS.index(name)
            return row[idx] if idx < len(row) else ""
        except ValueError:
            return ""

    with console.status("[cyan]Reading Trade_Log_Staging..."):
        try:
            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            try:
                staging_ws = ss.worksheet(config.TAB_TRADE_LOG_STAGING)
            except Exception:
                console.print(f"[red]ERROR: Tab '{config.TAB_TRADE_LOG_STAGING}' not found. Run derive_rotations first.[/]")
                raise typer.Exit(code=1)

            all_rows = staging_ws.get_all_values()
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]ERROR reading staging: {e}[/]")
            raise typer.Exit(code=1)

    if len(all_rows) < 2:
        console.print("[yellow]Trade_Log_Staging is empty — nothing to promote.[/]")
        raise typer.Exit()

    header = all_rows[0]
    data_rows = all_rows[1:]  # 1-indexed row 2 onward in the sheet

    # Find Status column index in actual sheet header (may differ from config if sheet drifted)
    try:
        status_col_idx = header.index("Status")
    except ValueError:
        console.print("[red]ERROR: 'Status' column not found in Trade_Log_Staging header.[/]")
        raise typer.Exit(code=1)

    # Build list of (sheet_row_number, data_row) for approved rows
    approved: list[tuple[int, list]] = []
    for i, row in enumerate(data_rows):
        # Pad row to header length to avoid index errors
        padded = row + [""] * (len(header) - len(row))
        if padded[status_col_idx].strip().lower() == "approved":
            approved.append((i + 2, padded))  # sheet row = data index + 2 (1-based + header)

    if not approved:
        console.print("[yellow]No rows with Status='approved' found in Trade_Log_Staging.[/]")
        raise typer.Exit()

    # Preview table
    preview = Table(title=f"Rows to Promote ({len(approved)})", show_header=True)
    preview.add_column("Stage_ID[:8]", style="dim")
    preview.add_column("Date", style="cyan")
    preview.add_column("Sell_Tickers")
    preview.add_column("Buy_Tickers")
    preview.add_column("Rotation_Type", style="yellow")
    preview.add_column("Implicit_Bet")
    for _, row in approved:
        preview.add_row(
            _col(row, "Stage_ID")[:8],
            _col(row, "Date"),
            _col(row, "Sell_Tickers"),
            _col(row, "Buy_Tickers"),
            _col(row, "Rotation_Type"),
            _col(row, "Implicit_Bet") or "[dim]<blank>[/]",
        )
    console.print(preview)

    # Warn on blank Implicit_Bet
    blank_bets = [row for _, row in approved if not _col(row, "Implicit_Bet").strip()]
    if blank_bets:
        console.print(f"[yellow]! {len(blank_bets)} row(s) have a blank Implicit_Bet — fill them in the Sheet before promoting.[/]")
        if not yes and not live:
            console.print("[dim]Continuing in dry-run mode regardless.[/]")

    if not live:
        console.print(Panel.fit(
            f"[bold black on yellow] DRY RUN — Would promote {len(approved)} row(s). Use --live to write. [/]",
            border_style="yellow",
        ))
        return

    # Confirm (skip with --yes)
    if not yes:
        console.print(f"\n[bold]About to promote {len(approved)} row(s) to Trade_Log and mark them 'promoted' in staging.[/]")
        confirm = typer.confirm("Proceed?")
        if not confirm:
            console.print("[yellow]Aborted.[/]")
            raise typer.Exit()

    # Build Trade_Log rows
    # Staging:   Stage_ID, Date, Sell_Tickers, Sell_Proceeds, Buy_Tickers, Buy_Amount,
    #            Rotation_Type, Implicit_Bet, Thesis_Brief, Status, Cluster_Window_Days,
    #            Sell_Dates, Buy_Dates, Sell_RSI_At_Decision, ..., Fingerprint
    # Trade_Log: Date, Sell_Ticker, Sell_Proceeds, Buy_Ticker, Buy_Amount,
    #            Implicit_Bet, Thesis_Brief, Rotation_Type, Sell_RSI_At_Decision, ..., Trade_Log_ID, Fingerprint
    trade_log_rows = []
    for _, row in approved:
        trade_log_rows.append([
            _col(row, "Date"),
            _col(row, "Sell_Tickers"),   # Sell_Tickers -> Sell_Ticker
            _col(row, "Sell_Proceeds"),
            _col(row, "Buy_Tickers"),    # Buy_Tickers  -> Buy_Ticker
            _col(row, "Buy_Amount"),
            _col(row, "Implicit_Bet"),
            _col(row, "Thesis_Brief"),
            _col(row, "Rotation_Type"),
            _col(row, "Sell_RSI_At_Decision"),
            _col(row, "Sell_Trend_At_Decision"),
            _col(row, "Sell_Price_vs_MA200_At_Decision"),
            _col(row, "Buy_RSI_At_Decision"),
            _col(row, "Buy_Trend_At_Decision"),
            _col(row, "Buy_Price_vs_MA200_At_Decision"),
            _col(row, "Stage_ID"),       # Stage_ID -> Trade_Log_ID
            _col(row, "Fingerprint"),
        ])

    with console.status(f"[cyan]Writing {len(trade_log_rows)} row(s) to {config.TAB_TRADE_LOG}..."):
        try:
            try:
                trade_ws = ss.worksheet(config.TAB_TRADE_LOG)
            except Exception:
                console.print(f"[yellow]Creating {config.TAB_TRADE_LOG} tab...[/]")
                trade_ws = ss.add_worksheet(
                    title=config.TAB_TRADE_LOG,
                    rows="200",
                    cols=len(config.TRADE_LOG_COLUMNS),
                )
                trade_ws.insert_row(config.TRADE_LOG_COLUMNS, 1)
                trade_ws.freeze(rows=1)
                time.sleep(1)

            trade_ws.append_rows(trade_log_rows, value_input_option="USER_ENTERED")
        except Exception as e:
            console.print(f"[red]ERROR writing to {config.TAB_TRADE_LOG}: {e}[/]")
            raise typer.Exit(code=1)

    # Mark promoted rows in staging
    new_status_col = status_col_idx + 1  # gspread uses 1-based column numbers
    with console.status("[cyan]Marking staging rows as 'promoted'..."):
        try:
            for sheet_row_num, _ in approved:
                staging_ws.update_cell(sheet_row_num, new_status_col, "promoted")
                time.sleep(0.3)  # stay under Sheets API rate limit
        except Exception as e:
            console.print(f"[yellow]! WARNING: Could not update staging status: {e}[/]")
            console.print("[yellow]  Trade_Log rows were written — update staging manually.[/]")

    console.print(f"\n[bold green]SUCCESS:[/] Promoted {len(trade_log_rows)} row(s) to {config.TAB_TRADE_LOG}.")
    console.print(f"[dim]Staging rows marked 'promoted'. Run derive_rotations.py again to find new candidates.[/]")


@journal_app.command("rotation")
def journal_rotation(
    sold: str = typer.Option(..., "--sold", help="Comma-separated list of sell tickers."),
    bought: str = typer.Option(..., "--bought", help="Comma-separated list of buy tickers (or 'CASH')."),
    proceeds: float = typer.Option(..., "--proceeds", help="Total sell proceeds (USD)."),
    type: str = typer.Option(..., "--type", help="Rotation type: dry_powder | upgrade | rebalance | tax_loss."),
    bet: str = typer.Option(..., "--bet", help="Implicit bet / rationale for this rotation."),
    thesis: str = typer.Option("", "--thesis", help="Brief thesis note."),
    live: bool = typer.Option(False, "--live", help="Write to live Sheet. Default: DRY RUN."),
):
    """Record a portfolio rotation in the Trade_Log."""
    import uuid
    import config
    from utils.sheet_readers import get_gspread_client

    sell_tickers = [t.strip().upper() for t in sold.split(",")]
    buy_tickers = [t.strip().upper() for t in bought.split(",")]
    
    if type not in ["dry_powder", "upgrade", "rebalance", "tax_loss"]:
        console.print(f"[red]ERROR: Invalid type: {type}. Must be dry_powder | upgrade | rebalance | tax_loss[/]")
        raise typer.Exit(code=1)

    trade_id = str(uuid.uuid4())
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Calculate proceeds per sell ticker (simple average for log)
    # If we have multiple sell tickers, we split the proceeds for the log
    proceeds_per_ticker = proceeds / len(sell_tickers)
    
    rows = []
    for ticker in sell_tickers:
        fingerprint = f"{today}|{ticker}|{bought}|{proceeds_per_ticker:.2f}"
        rows.append([
            today,
            ticker,
            round(proceeds_per_ticker, 2),
            bought.upper(),
            0.0, # Buy amount unknown at this step if just recording rotation
            bet,
            thesis,
            type,
            trade_id,
            fingerprint
        ])

    if not live:
        console.print(Panel.fit(
            f"[bold black on yellow] DRY RUN — Would write {len(rows)} row(s) to {config.TAB_TRADE_LOG} [/]",
            border_style="yellow",
        ))
        for row in rows:
            console.print(f"Row: {row}")
        return

    # LIVE write
    with console.status(f"[cyan]Writing to {config.TAB_TRADE_LOG}..."):
        try:
            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            
            # Ensure tab exists
            try:
                ws = ss.worksheet(config.TAB_TRADE_LOG)
            except:
                console.print(f"[yellow]Creating {config.TAB_TRADE_LOG} tab...[/]")
                ws = ss.add_worksheet(title=config.TAB_TRADE_LOG, rows="100", cols=len(config.TRADE_LOG_COLUMNS))
                ws.insert_row(config.TRADE_LOG_COLUMNS, 1)
                ws.freeze(rows=1)
                time.sleep(1)

            ws.append_rows(rows, value_input_option="USER_ENTERED")
            console.print(f"[bold green]SUCCESS:[/] Wrote {len(rows)} row(s) to {config.TAB_TRADE_LOG} (ID: {trade_id[:8]})")
        except Exception as e:
            console.print(f"[red]ERROR: Failed to write to Sheet: {e}[/]")
            raise typer.Exit(code=1)

@app.command()
def health(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show expanded detail for each check."),
):
    """
    Run pipeline health checks — Schwab tokens, API connectivity, Sheet, bundle age,
    FMP cache coverage, yfinance, transactions freshness, thesis coverage.

    Exit codes:  0 = all green  |  1 = critical failure  |  2 = warnings only
    """
    from tasks.health import run_all_checks, exit_code, CRITICAL, WARNING, PASS, WARN, FAIL
    from rich.text import Text

    console.print()
    with console.status("[cyan]Running health checks in parallel…"):
        results = run_all_checks()

    # --- Build Rich table ---
    table = Table(
        title="Pipeline Health",
        show_header=True,
        header_style="bold cyan",
        box=None,
        padding=(0, 1),
    )
    table.add_column("Check",  style="cyan",  no_wrap=True, min_width=30)
    table.add_column("Status", justify="center", no_wrap=True, min_width=6)
    table.add_column("Detail", style="white")

    for r in results:
        if r.status == PASS:
            status_cell = Text("✓", style="bold green")
        elif r.status == WARN:
            status_cell = Text("⚠", style="bold yellow")
        else:
            status_cell = Text("✗", style="bold red")

        level_marker = "" if r.level == CRITICAL else "[dim](W)[/dim] "
        name_cell = f"{level_marker}[cyan]{r.name}[/cyan]"

        if r.status == FAIL and r.level == CRITICAL:
            detail_style = "red"
        elif r.status in (FAIL, WARN):
            detail_style = "yellow"
        else:
            detail_style = "white"

        table.add_row(name_cell, status_cell, f"[{detail_style}]{r.detail}[/{detail_style}]")

    console.print(table)

    # --- Verbose expansion ---
    if verbose:
        console.print()
        console.rule("[dim]Verbose Detail[/dim]")
        for r in results:
            if r.verbose:
                console.print(f"[cyan]{r.name}[/cyan]")
                for line in r.verbose.splitlines():
                    console.print(f"  [dim]{line}[/dim]")

    # --- Summary line ---
    n_pass  = sum(1 for r in results if r.status == PASS)
    n_warn  = sum(1 for r in results if r.status == WARN)
    n_fail  = sum(1 for r in results if r.status == FAIL)
    console.print()
    summary_parts = [f"[green]{n_pass} passed[/green]"]
    if n_warn:
        summary_parts.append(f"[yellow]{n_warn} warning(s)[/yellow]")
    if n_fail:
        summary_parts.append(f"[red]{n_fail} failed[/red]")
    console.print("  ".join(summary_parts))
    console.print()

    raise typer.Exit(code=exit_code(results))


@app.command()
def snapshot(
    source: str = typer.Option(
        "auto", "--source",
        help="Data source: 'schwab', 'csv', or 'auto' (default). "
             "'auto' tries Schwab first and falls back to CSV if --csv is provided."
    ),
    csv: Path | None = typer.Option(
        None, "--csv",
        help="Path to Schwab positions CSV. Required when --source=csv; used as fallback when --source=auto.",
        exists=True, file_okay=True, dir_okay=False,
        readable=True, resolve_path=True,
    ),
    cash: float = typer.Option(
        0.0, "--cash",
        help="Manual cash position (USD). Ignored on Schwab path if fetch_positions returns cash from account balances."
    ),
    enrich_atr: bool = typer.Option(
        True, "--enrich-atr/--no-enrich-atr",
        help="Inject ATR stops into the latest composite bundle (default: on). "
             "Requires a composite bundle to exist (run 'manager.py bundle composite' first).",
    ),
    enrich_technicals: bool = typer.Option(
        True, "--enrich-technicals/--no-enrich-technicals",
        help="Inject Murphy TA indicators into the latest composite bundle (default: on). "
             "Requires composite bundle to exist.",
    ),
    enrich_fmp: bool = typer.Option(
        True, "--enrich-fmp/--no-enrich-fmp",
        help="Bake FMP fundamentals into the market bundle (default: on). "
             "Disable with --no-enrich-fmp for offline testing.",
    ),
    enrich_styles: bool = typer.Option(
        True, "--enrich-styles/--no-enrich-styles",
        help="Stamp GARP/THEME/BORING/ETF style onto each position from data/ticker_strategies.json (default: on).",
    ),
    live: bool = typer.Option(False, "--live", help="Enable live mode. Default is DRY RUN."),
):
    """Freeze current market state to an immutable context bundle."""

    # 1. Validate source/csv combination
    if source == "csv" and csv is None:
        console.print("[red]ERROR: --source csv requires --csv PATH[/]")
        raise typer.Exit(code=1)
    if source not in {"schwab", "csv", "auto"}:
        console.print(f"[red]ERROR: Invalid --source: {source}[/]")
        raise typer.Exit(code=1)

    # Banner
    if live:
        console.print(Panel.fit(
            "[bold white on red] LIVE MODE — Sheet writes enabled in downstream commands [/]",
            border_style="red",
        ))
    else:
        console.print(Panel.fit(
            "[bold black on yellow] DRY RUN — No Sheet writes. Use --live to enable. [/]",
            border_style="yellow",
        ))

    # Build
    with console.status(f"[cyan]Freezing market state from {source}..."):
        try:
            bundle = build_bundle(
                source=source,
                csv_path=csv,
                cash_manual=cash,
            )
            path = write_bundle(bundle)
        except Exception as e:
            console.print(f"[red]ERROR: Snapshot failed: {e}[/]")
            raise typer.Exit(code=1)

    # 6. Fallback Warning
    if bundle.data_source == "csv" and source == "auto":
        console.print(Panel(
            "[bold yellow]⚠ Schwab API unavailable. Snapshot fell back to CSV file. [/]\n"
            "[dim]Check your tokens in GCS or run 'python scripts/schwab_manual_reauth.py'.[/]",
            border_style="yellow",
            title="Fallback Triggered"
        ))

    # Summary table
    table = Table(title="Context Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("Timestamp (UTC)", bundle.timestamp_utc)
    table.add_row("Bundle Hash", f"[bold green]{bundle.bundle_hash}[/]")
    table.add_row("Data Source", f"[bold green]{bundle.data_source}[/]")
    table.add_row("Source Fingerprint", bundle.data_source_fingerprint)
    table.add_row("Tax Treatment Available", "yes" if bundle.tax_treatment_available else "[yellow]no[/]")
    table.add_row("Positions", str(bundle.position_count))
    table.add_row("Total Value", f"${bundle.total_value:,.2f}")
    table.add_row("Cash (manual)", f"${bundle.cash_manual:,.2f}")
    table.add_row("Bundle Path", str(path))
    console.print(table)

    # 7. Post-snapshot enrichment
    from tasks.enrich_fundamentals import enrich_bundle_fundamentals
    with console.status("[cyan]Enriching with fundamentals (Tiered: Schwab -> yfinance -> FMP)..."):
        try:
            enriched = enrich_bundle_fundamentals(path)
            new_hash = enriched.get("bundle_hash", "")
            if new_hash and new_hash != bundle.bundle_hash:
                console.print(f"[green]Bundle enriched and re-hashed:[/] [bold green]{new_hash}[/]")
        except Exception as e:
            console.print(f"[red]Fundamental enrichment failed: {e}[/]")

    # Style enrichment (GARP/THEME/BORING/ETF) from data/ticker_strategies.json
    if enrich_styles:
        from tasks.enrich_styles import enrich_bundle_styles
        try:
            styles_result = enrich_bundle_styles(path)
            positions_with_styles = styles_result.get("positions", [])
            unknown = [p.get("ticker") for p in positions_with_styles if p.get("asset_strategy") == "UNKNOWN"]
            if unknown:
                console.print(f"[yellow]⚠ Style unknown for: {', '.join(unknown)} — add to data/ticker_strategies.json[/]")
            else:
                console.print(f"[green]Styles applied:[/] all {len(positions_with_styles)} positions classified.")
        except Exception as e:
            console.print(f"[red]Style enrichment failed: {e}[/]")

    # Enrichment errors — visible, not silent
    if getattr(bundle, "enrichment_errors", None):
        console.print(f"\n[yellow]⚠ {len(bundle.enrichment_errors)} enrichment warning(s):[/]")
        for err in bundle.enrichment_errors[:10]:
            console.print(f"  [yellow]•[/] {err}")

    # FMP fundamentals enrichment (default-on; disable with --no-enrich-fmp)
    if enrich_fmp:
        from tasks.enrich_fmp import enrich_bundle_fmp
        with console.status("[cyan]Enriching with FMP fundamentals (14-day cache)..."):
            try:
                fmp_result = enrich_bundle_fmp(path)
                fmp_positions = fmp_result.get("positions", [])
                fmp_ok    = sum(1 for p in fmp_positions if isinstance(p.get("fmp_fundamentals"), dict) and "error" not in p.get("fmp_fundamentals", {}))
                fmp_err   = sum(1 for p in fmp_positions if isinstance(p.get("fmp_fundamentals"), dict) and "error" in p.get("fmp_fundamentals", {}))
                console.print(
                    f"[green]FMP fundamentals baked into bundle:[/] "
                    f"{fmp_ok} enriched, {fmp_err} errors. "
                    f"Hash: [bold green]{fmp_result.get('bundle_hash', '')[:16]}…[/]"
                )
            except Exception as e:
                console.print(f"[red]FMP enrichment failed: {e}[/]")

    # ATR enrichment (default-on; disable with --no-enrich-atr)
    if enrich_atr:
        from tasks.enrich_atr import enrich_composite_bundle as _enrich_atr
        composite_candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not composite_candidates:
            console.print(
                "[yellow]! --enrich-atr: No composite bundles found. "
                "Run 'manager.py bundle composite' first, then re-run with --enrich-atr.[/]"
            )
        else:
            composite_path = composite_candidates[-1]
            console.print(f"\n[cyan]ATR Enrichment — {composite_path.name}[/]")
            with console.status("[cyan]Computing ATR stops (yfinance 1mo daily)..."):
                try:
                    enriched = _enrich_atr(composite_path)
                    stops = enriched.get("calculated_technical_stops", [])
                    triggered = [
                        s["ticker"] for s in stops
                        if s.get("current_price", 0) < s.get("stop_loss_level", 0)
                    ]
                    console.print(
                        f"[green]ATR stops computed for {len(stops)} position(s).[/]"
                    )
                    if triggered:
                        console.print(f"[bold red]! ATR TRIGGERED: {triggered}[/]")
                    else:
                        console.print("[dim]No ATR stops triggered.[/]")
                except Exception as e:
                    console.print(f"[red]ATR enrichment failed: {e}[/]")

    # Technical indicators enrichment — optional post-snapshot step
    if enrich_technicals:
        from tasks.enrich_technicals import enrich_composite_bundle as _enrich_technicals
        from collections import Counter
        composite_candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not composite_candidates:
            console.print(
                "[yellow]! --enrich-technicals: No composite bundles found. "
                "Run 'manager.py bundle composite' first, then re-run with --enrich-technicals.[/]"
            )
        else:
            composite_path = composite_candidates[-1]
            console.print(f"\n[cyan]Technical Indicators Enrichment — {composite_path.name}[/]")
            with console.status("[cyan]Computing Murphy TA indicators (MA/RSI/MACD/volume)..."):
                try:
                    enriched = _enrich_technicals(composite_path)
                    technicals = enriched.get("calculated_technicals", [])
                    data_gaps  = [e for e in technicals if e.get("data_gap")]
                    console.print(
                        f"[green]Technical indicators computed for {len(technicals)} position(s).[/]"
                    )
                    if data_gaps:
                        console.print(f"[yellow]⚠  Data gaps ({len(data_gaps)}):[/]")
                        for e in data_gaps:
                            console.print(f"  [yellow]{e['ticker']:8s} → {e['data_gap']}[/]")
                    dist = Counter(e.get("trend_label") for e in technicals if e.get("trend_label"))
                    for label in ["strong_uptrend", "uptrend", "neutral", "downtrend", "strong_downtrend"]:
                        if dist[label]:
                            console.print(f"  [dim]{label:<20}[/] {dist[label]}")
                except Exception as e:
                    console.print(f"[red]Technical enrichment failed: {e}[/]")

    # 8. Push to Sheets if --live
    if live:
        console.print("\n[cyan]Step 8: Pushing enriched bundle to Google Sheets...[/]")
        bundle_push(path=path, live=True)


# --- VAULT GROUP ---

vault_app = typer.Typer(help="Manage the vault bundle (thesis files, transcripts).")
app.add_typer(vault_app, name="vault")

@vault_app.command("snapshot")
def vault_snapshot(
    drive: bool = typer.Option(False, "--drive", help="Pull from Google Drive for missing files."),
    live: bool = typer.Option(False, "--live"),
):
    """Freeze vault documents (theses, transcripts) to an immutable vault bundle."""
    # Banner
    if live:
        console.print(Panel.fit(
            "[bold white on red] LIVE MODE — Vault snapshot enabled [/]",
            border_style="red",
        ))
    else:
        console.print(Panel.fit(
            "[bold black on yellow] DRY RUN — No writes. Use --live to enable. [/]",
            border_style="yellow",
        ))

    # Discover ticker list from latest market bundle
    tickers = None
    try:
        market_bundles = sorted(list(Path("bundles").glob("context_bundle_*.json")), key=lambda p: p.stat().st_mtime)
        if market_bundles:
            market_path = market_bundles[-1]
            market_data = load_bundle(market_path)
            tickers = [p["ticker"] for p in market_data["positions"] if not p.get("is_cash")]
            console.print(f"[dim]Resolved {len(tickers)} tickers from {market_path.name}[/]")
        else:
            console.print("[yellow]! No market bundles found. Continuing with local discovery only.[/]")
    except Exception as e:
        console.print(f"[yellow]! Could not resolve latest market bundle: {e}[/]")
        console.print("[yellow]Continuing with local discovery only.[/]")

    # Build
    with console.status("[cyan]Freezing vault..."):
        bundle = build_vault_bundle(ticker_list=tickers, include_drive=drive)
        path = write_vault_bundle(bundle)

    # Summary table
    table = Table(title="Vault Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("Timestamp (UTC)", bundle.timestamp_utc)
    table.add_row("Vault Hash", f"[bold green]{bundle.vault_hash}[/]")
    table.add_row("Vault Doc Count", str(bundle.vault_doc_count))
    
    present_str = f"{len(bundle.theses_present)} ({', '.join(bundle.theses_present[:5])}{'...' if len(bundle.theses_present) > 5 else ''})"
    table.add_row("Theses Present", present_str)
    
    missing_style = "yellow" if bundle.theses_missing else "white"
    missing_str = f"[{missing_style}]{len(bundle.theses_missing)} ({', '.join(bundle.theses_missing[:5])}{'...' if len(bundle.theses_missing) > 5 else ''})[/]"
    table.add_row("Theses Missing", missing_str)

    # Calculate triggers coverage for Prompt 2.1
    theses_with_triggers = 0
    total_theses = len(bundle.theses_present)
    for doc in bundle.documents:
        if doc.get("doc_type") == "thesis" and doc.get("thesis_present"):
            trigs = doc.get("triggers", {})
            if trigs.get("price_trim_above") is not None or trigs.get("price_add_below") is not None:
                theses_with_triggers += 1
    
    trigger_color = "green" if theses_with_triggers == total_theses and total_theses > 0 else ("yellow" if theses_with_triggers > 0 else "red")
    table.add_row("Price Triggers", f"[{trigger_color}]{theses_with_triggers} / {total_theses} theses populated[/]")
    
    skip_style = "yellow" if bundle.vault_skip_log else "white"
    table.add_row("Skipped Files", f"[{skip_style}]{len(bundle.vault_skip_log)}[/]")
    
    table.add_row("Bundle Path", str(path))
    console.print(table)

    if bundle.vault_skip_log:
        console.print("\n[yellow]! Skipped files:[/]")
        for skip in bundle.vault_skip_log:
            console.print(f"  [yellow]•[/] {skip}")


@vault_app.command("sync")
def vault_sync(
    ticker: str = typer.Option(None, "--ticker", help="Sync a specific ticker only."),
    live: bool = typer.Option(False, "--live", help="Commit changes to thesis files."),
    force: bool = typer.Option(False, "--force", help="Recreate missing managed regions."),
    show_diff: bool = typer.Option(False, "--show-diff", help="Print unified diffs of changes.")
):
    """Sync Sheets data (positions, trades, realized G/L) into thesis files."""
    from core.thesis_sync_data import gather_thesis_sync_data
    from tasks.write_thesis_updates import write_thesis_updates

    if live:
        console.print(Panel.fit("[bold white on red] LIVE MODE — Writing to disk enabled [/]", border_style="red"))
    else:
        console.print(Panel.fit("[bold black on yellow] DRY RUN — No writes. Use --live to enable. [/]", border_style="yellow"))

    with console.status("[cyan]Gathering sync data from Sheets..."):
        tickers = [ticker.upper()] if ticker else None
        payloads = gather_thesis_sync_data(tickers=tickers)

    if not payloads:
        console.print("[yellow]No data found for the specified tickers.[/]")
        return

    with console.status("[cyan]Updating thesis files..."):
        report = write_thesis_updates(
            payloads=payloads, 
            dry_run=not live, 
            force_recreate_regions=force,
            show_diff=show_diff
        )

    # Report Table
    table = Table(title="Thesis Sync Report")
    table.add_column("Status", style="cyan")
    table.add_column("Count", style="white")
    table.add_row("Processed (no change)", str(report["processed"]))
    table.add_row("Updated", f"[bold green]{report['updated']}[/]")
    table.add_row("Skipped (no file)", str(report["skipped"]))
    table.add_row("Errors", f"[bold red]{report['errors']}[/]")
    console.print(table)


@vault_app.command("sync-status")
def vault_sync_status():
    """Audit the staleness and drift of all thesis files."""
    from core.thesis_sync_data import gather_thesis_sync_data
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()

    with console.status("[cyan]Gathering data..."):
        payloads = gather_thesis_sync_data()

    table = Table(title="Thesis Sync Status")
    table.add_column("Ticker", style="cyan")
    table.add_column("Last Reviewed", style="white")
    table.add_column("Weight %", style="white")
    table.add_column("Ceiling %", style="white")
    table.add_column("Drift %", style="magenta")
    table.add_column("Status", style="white")

    for ticker, payload in payloads.items():
        path = Path(f"vault/theses/{ticker}_thesis.md")
        if not path.exists():
            continue

        try:
            content = path.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            last_reviewed = "N/A"
            if fm_match:
                fm_data = yaml.load(fm_match.group(1))
                last_reviewed = fm_data.get('last_reviewed', "N/A")

            weight = f"{payload.current_allocation_pct:,.2f}%" if payload.current_allocation_pct is not None else "N/A"
            ceiling = f"{payload.size_ceiling_pct:,.2f}%" if payload.size_ceiling_pct else "N/A"
            drift_str = "N/A"
            drift_val = 0.0
            if payload.current_allocation_pct is not None and payload.size_ceiling_pct:
                drift_val = payload.current_allocation_pct - payload.size_ceiling_pct
                color = "red" if drift_val > 0 else "green"
                drift_str = f"[{color}]{drift_val:+.2f}%[/]"

            status = "OK"
            if drift_val > 1.0: status = "[bold red]OVER[/]"
            elif drift_val < -5.0: status = "[yellow]UNDER[/]"

            table.add_row(ticker, str(last_reviewed), weight, ceiling, drift_str, status)
        except Exception:
            table.add_row(ticker, "ERR", "ERR", "ERR", "ERR", "ERR")

    console.print(table)


@vault_app.command("add-thesis")
def vault_add_thesis(
    ticker: str = typer.Argument(..., help="Ticker symbol (e.g. UNH)"),
):
    """Scaffold a new _thesis.md file from template for a given ticker."""
    target = THESES_DIR / f"{ticker.upper()}_thesis.md"
    if target.exists():
        console.print(f"[yellow]! Thesis for {ticker.upper()} already exists. Aborting.[/]")
        raise typer.Exit()

    _today = datetime.now().strftime("%Y-%m-%d")
    template = f"""---
ticker: {ticker.upper()}
style: GARP
framework_preference: lynch_garp_v1, joys_of_compounding, psychology_of_money
entry_date: {_today}
last_reviewed: {_today}
current_allocation: null
cost_basis: null
time_horizon: 3 to 5 years
---

# {ticker.upper()} — Investment Thesis

## Core Thesis
... why do we own this? What is the compounding engine? ...

## Valuation & Targets
... target P/E range, PEG ceiling, acceptable multiples ...

## Position Sizing & Action Zones
... add zone (price or % below cost basis), trim zone ...

## Behavioral Guardrails
... drawdown tolerance, patience mandate ...

## Exit Conditions
1. ...
2. ...

## Quantitative Triggers

<!-- Machine-readable triggers. Keep the YAML block EXACT — parsers depend on it.
     Use null for fields that don't apply to this position's style. -->

```yaml
triggers:
  # Valuation triggers (GARP, FUND)
  fwd_pe_add_below: null      # ADD if forward P/E drops below this
  fwd_pe_trim_above: null     # TRIM if forward P/E rises above this
  fwd_pe_historical_median: null  # the position's own 5-year median, for reference

  # Price/technical triggers (all styles)
  price_add_below: null       # ADD if price drops below this dollar level
  price_trim_above: null      # TRIM if price rises above this dollar level
  discount_from_52w_high_add: null   # ADD if % discount exceeds this (e.g., 0.15 for 15%)

  # Fundamental triggers (GARP, FUND)
  revenue_growth_floor_pct: null     # concern if YoY revenue growth drops below this
  operating_margin_floor_pct: null   # concern if operating margin drops below this

  # Position management
  style_size_ceiling_pct: null       # max weight for this position, per its style
  current_weight_pct: null           # auto-populated by weekly snapshot; do not edit
```
"""
    THESES_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(template)
    console.print(f"Created {target} — fill in the sections.")


@vault_app.command("thesis-audit")
def vault_thesis_audit():
    """
    Report quantitative trigger completeness across all thesis files.

    Reads all _thesis.md files in vault/theses/, parses the triggers: YAML block
    from each, and reports populated vs null fields. Sorted by completeness ascending
    so Bill sees the worst-backfilled positions first.

    Exits 0 regardless — this is reporting, not enforcement.
    """
    import re
    import yaml as _yaml

    _TRIGGER_FIELDS = [
        "fwd_pe_add_below",
        "fwd_pe_trim_above",
        "fwd_pe_historical_median",
        "price_add_below",
        "price_trim_above",
        "discount_from_52w_high_add",
        "revenue_growth_floor_pct",
        "operating_margin_floor_pct",
        "style_size_ceiling_pct",
        "current_weight_pct",
    ]
    total_fields = len(_TRIGGER_FIELDS)

    thesis_files = sorted(THESES_DIR.glob("*_thesis.md"))
    if not thesis_files:
        console.print(f"[yellow]No thesis files found in {THESES_DIR}[/]")
        raise typer.Exit()

    rows = []
    for tf in thesis_files:
        ticker = tf.stem.replace("_thesis", "").upper()
        content = tf.read_text(encoding="utf-8")

        # Extract style from frontmatter
        style = "unknown"
        fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            try:
                fm_data = _yaml.safe_load(fm_match.group(1)) or {}
                style = str(fm_data.get("style", "unknown"))[:10]
            except Exception:
                pass

        # Extract triggers — fenced block first, frontmatter fallback
        triggers = {}
        trig_match = re.search(
            r"```yaml\s*\ntriggers:\s*\n(.*?)```",
            content,
            re.DOTALL,
        )
        if trig_match:
            try:
                trig_data = _yaml.safe_load("triggers:\n" + trig_match.group(1)) or {}
                triggers = trig_data.get("triggers", {}) or {}
            except Exception:
                rows.append((ticker, style, 0, total_fields, "parse_error"))
                continue
        elif fm_match:
            try:
                fm_data = _yaml.safe_load(fm_match.group(1)) or {}
                triggers = fm_data.get("triggers", {}) or {}
            except Exception:
                rows.append((ticker, style, 0, total_fields, "parse_error"))
                continue

        if not triggers:
            rows.append((ticker, style, 0, total_fields, "no_triggers_block"))
            continue

        populated = sum(1 for f in _TRIGGER_FIELDS if triggers.get(f) is not None)
        status = "complete" if populated == total_fields else ("partial" if populated > 0 else "empty")
        rows.append((ticker, style, populated, total_fields, status))

    # Sort by populated ascending (worst-backfilled first)
    rows.sort(key=lambda r: r[2])

    table = Table(title="Thesis Quantitative Trigger Audit", show_header=True)
    table.add_column("Ticker", style="bold")
    table.add_column("Style")
    table.add_column("Populated")
    table.add_column("Total")
    table.add_column("Status")

    status_colors = {"complete": "green", "partial": "yellow", "empty": "red", "no_triggers_block": "dim", "parse_error": "red"}
    for ticker, style, populated, total, status in rows:
        color = status_colors.get(status, "white")
        table.add_row(
            ticker,
            style,
            str(populated),
            str(total),
            f"[{color}]{status}[/]",
        )

    console.print(table)
    console.print(
        f"\n[dim]{len(rows)} thesis file(s) scanned. "
        f"Complete: {sum(1 for r in rows if r[4] == 'complete')} | "
        f"Partial: {sum(1 for r in rows if r[4] == 'partial')} | "
        f"Empty/Missing: {sum(1 for r in rows if r[4] in ('empty', 'no_triggers_block', 'parse_error'))}[/]"
    )


# --- BUNDLE GROUP ---

bundle_app = typer.Typer(help="Build and inspect composite bundles.")
app.add_typer(bundle_app, name="bundle")

@bundle_app.command("composite")
def bundle_composite(
    market: Path | None = typer.Option(None, "--market", help="Explicit market bundle path."),
    vault: Path | None = typer.Option(None, "--vault", help="Explicit vault bundle path."),
    live: bool = typer.Option(False, "--live"),
):
    """Combine latest (or specified) market + vault bundles into a composite."""
    # Banner
    if live:
        console.print(Panel.fit(
            "[bold white on red] LIVE MODE — Composite bundle enabled [/]",
            border_style="red",
        ))
    else:
        console.print(Panel.fit(
            "[bold black on yellow] DRY RUN — No writes. Use --live to enable. [/]",
            border_style="yellow",
        ))

    # Resolve paths
    try:
        if market and vault:
            market_path, vault_path = market, vault
        else:
            market_path, vault_path = resolve_latest_bundles()
            console.print(f"[dim]Resolved latest: {market_path.name}, {vault_path.name}[/]")
    except Exception as e:
        console.print(f"[red]ERROR: Could not resolve bundles: {e}[/]")
        raise typer.Exit(code=1)

    # Build
    with console.status("[cyan]Building composite bundle..."):
        composite = build_composite_bundle(market_path, vault_path)
        path = write_composite_bundle(composite)

    # Summary table
    table = Table(title="Composite Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("Timestamp (UTC)", composite.timestamp_utc)
    table.add_row("Composite Hash", f"[bold green]{composite.composite_hash}[/]")
    table.add_row("Market Hash", composite.market_bundle_hash[:16] + "...")
    table.add_row("Vault Hash", composite.vault_bundle_hash[:16] + "...")
    table.add_row("Positions", str(composite.position_count))
    table.add_row("Vault Docs", str(composite.vault_doc_count))
    
    # Calculate triggers coverage
    from core.vault_bundle import load_vault_bundle
    vault_data = load_vault_bundle(Path(composite.vault_bundle_path))
    theses_with_triggers = 0
    total_theses = len(composite.theses_present)
    for doc in vault_data.get("documents", []):
        if doc.get("doc_type") == "thesis" and doc.get("thesis_present"):
            trigs = doc.get("triggers", {})
            if trigs.get("price_trim_above") is not None or trigs.get("price_add_below") is not None:
                theses_with_triggers += 1
    
    trigger_color = "green" if theses_with_triggers == total_theses and total_theses > 0 else ("yellow" if theses_with_triggers > 0 else "red")
    table.add_row("Price Triggers", f"[{trigger_color}]{theses_with_triggers} / {total_theses} theses populated[/]")

    missing_style = "yellow" if composite.theses_missing else "white"
    table.add_row("Theses Missing", f"[{missing_style}]{len(composite.theses_missing)}[/]")
    
    table.add_row("Bundle Path", str(path))
    console.print(table)

@bundle_app.command("push")
def bundle_push(
    path: Optional[Path] = typer.Option(None, "--path", help="Path to context bundle JSON. Defaults to latest."),
    live: bool = typer.Option(False, "--live", help="Perform live Sheet writes."),
):
    """
    Push a context bundle's position data to Google Sheets.
    Updates Holdings_Current, Holdings_History, and Daily_Snapshots.
    """
    from core.bundle import load_bundle
    import pipeline
    import pandas as pd

    if path is None:
        candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            console.print("[red]ERROR: No context bundles found in bundles/.[/]")
            raise typer.Exit(code=1)
        path = candidates[-1]

    console.print(f"[cyan]Pushing bundle to Sheets:[/] {path.name}")
    try:
        data = load_bundle(path)
        positions = data.get("positions", [])
        if not positions:
            console.print("[yellow]Warning: Bundle has no positions. Nothing to push.[/]")
            return

        df = pd.DataFrame(positions)
        
        # Ensure 'weight' column exists for pipeline (bundle uses 'weight_pct')
        if 'weight_pct' in df.columns and 'weight' not in df.columns:
            df['weight'] = df['weight_pct'] / 100.0
        
        # pipeline.write_to_sheets expects the DataFrame to have 'import_date'
        if 'import_date' not in df.columns:
            df['import_date'] = data.get('timestamp_utc', '')[:10]

        # Use pipeline's orchestration logic
        results = pipeline.write_to_sheets(
            df, 
            cash_amount=data.get('cash_manual', 0.0), 
            dry_run=not live
        )

        if live:
            console.print(f"[bold green]SUCCESS:[/] Pushed {results['holdings_written']} positions to Sheets.")
        else:
            console.print(f"[yellow]DRY RUN:[/] Would push {results['holdings_written']} positions to Sheets.")

    except Exception as e:
        console.print(f"[red]ERROR: Failed to push bundle: {e}[/]")
        raise typer.Exit(code=1)


@bundle_app.command("verify")
def bundle_verify(
    path: Path = typer.Argument(..., help="Path to any bundle file to verify."),
):
    """Verify the hash of a market, vault, or composite bundle."""
    if not path.exists():
        console.print(f"[red]ERROR: File not found: {path}[/]")
        raise typer.Exit(code=1)

    with open(path, "r") as f:
        data = json.load(f)

    try:
        if "composite_schema_version" in data:
            load_composite_bundle(path)
            label = "Composite"
        elif "vault_hash" in data:
            load_vault_bundle(path)
            label = "Vault"
        elif "bundle_hash" in data:
            load_bundle(path)
            label = "Market"
        else:
            console.print("[red]ERROR: Unknown bundle type.[/]")
            raise typer.Exit(code=1)
            
        console.print(f"[bold green]PASS[/] {label} hash verified: [bold green]{data.get('composite_hash') or data.get('vault_hash') or data.get('bundle_hash')}[/]")
    except ValueError as ve:
        console.print(f"[red]FAIL Hash verification failed: {ve}[/]")
        raise typer.Exit(code=1)


# --- SYNC GROUP ---
sync_app = typer.Typer(help="Sync data from external sources.")
app.add_typer(sync_app, name="sync")

@sync_app.command("transactions")
def sync_transactions_cmd(
    days: int = typer.Option(90, "--days", help="Number of days to sync."),
    live: bool = typer.Option(False, "--live", help="Perform live sheet write."),
    reconcile: bool = typer.Option(False, "--reconcile", help="Diff-only: compare Schwab vs Sheet, no writes."),
    clean: bool = typer.Option(False, "--clean", help="Remove CURRENCY_USD junk rows from the sheet."),
):
    """Sync Schwab transaction history to Google Sheets (merged archive-overwrite)."""
    if clean:
        from tasks.sync_transactions import clean_junk_tickers
        success = clean_junk_tickers(live=live)
    else:
        from tasks.sync_transactions import sync_transactions
        success = sync_transactions(days=days, live=live, reconcile=reconcile)
    if not success:
        raise typer.Exit(code=1)


@sync_app.command("realized-gl")
def sync_realized_gl_cmd(
    csv_path: Path = typer.Argument(..., help="Path to Schwab 'Realized Gain/Loss Lot Details' CSV export.", exists=True),
    live: bool = typer.Option(False, "--live", help="Write parsed lots to Realized_GL sheet."),
):
    """
    Import a Schwab Realized G/L Lot Details CSV into the Realized_GL sheet.

    Download from Schwab: Accounts → History → Realized Gain/Loss → Export.
    Runs fingerprint deduplication — safe to re-import the same file.
    """
    from utils.gl_parser import parse_realized_gl
    import config
    from utils.sheet_readers import get_gspread_client
    import pipeline

    console.print(f"[cyan]Parsing:[/] {csv_path.name}")
    try:
        df = parse_realized_gl(csv_path)
    except Exception as e:
        console.print(f"[red]ERROR parsing CSV: {e}[/]")
        raise typer.Exit(code=1)

    if df.empty:
        console.print("[yellow]No realized lots found in file — nothing to import.[/]")
        raise typer.Exit()

    console.print(f"  Parsed {len(df)} lots across {df['account'].nunique()} account(s).")

    # Add import_date
    from datetime import date as _date
    df['import_date'] = str(_date.today())

    # Sanitize for sheet write
    data_list = pipeline.sanitize_dataframe_for_sheets(df, config.GL_COLUMNS, config.GL_COL_MAP)

    if not live:
        console.print(Panel.fit(
            f"[bold black on yellow] DRY RUN — Would import {len(data_list)} lots. Use --live to write. [/]",
            border_style="yellow",
        ))
        # Preview first 5 rows
        for row in data_list[:5]:
            console.print(f"  {row[:6]}")
        return

    gc = get_gspread_client()
    ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = ss.worksheet(config.TAB_REALIZED_GL)

    # Fingerprint deduplication — only append rows not already present
    fp_col_idx = config.GL_COLUMNS.index('Fingerprint')
    existing_fps = set(ws.col_values(fp_col_idx + 1)[1:])  # 1-based, skip header
    new_rows = [r for r in data_list if str(r[fp_col_idx]) not in existing_fps]

    if not new_rows:
        console.print("[green]All lots already present in Realized_GL — nothing new to import.[/]")
        return

    # Write header if sheet is empty
    if not existing_fps:
        ws.update(range_name="A1", values=[config.GL_COLUMNS], value_input_option="USER_ENTERED")
        import time as _time; _time.sleep(1)

    ws.append_rows(new_rows, value_input_option="USER_ENTERED")
    console.print(f"[bold green]SUCCESS:[/] Imported {len(new_rows)} new lots → Realized_GL ({len(data_list) - len(new_rows)} already present, skipped).")


# --- TAX GROUP ---
tax_app = typer.Typer(help="Tax visibility and control.")
app.add_typer(tax_app, name="tax")

@tax_app.command("refresh")
def tax_refresh(live: bool = typer.Option(False, "--live", help="Compute YTD tax KPIs and refresh the Tax_Control tab.")):
    """Compute YTD tax KPIs and refresh the Tax_Control tab."""
    from tasks.build_tax_control import refresh_tax_control_sheet
    import config

    mode = "[bold red]LIVE[/]" if live else "[yellow]DRY RUN[/]"
    console.print(f"Refreshing Tax_Control in {mode} mode...")

    try:
        data = refresh_tax_control_sheet(live=live)
        if not data:
            console.print("[red]No data found to compute tax control.[/]")
            return

        metrics = data['metrics']
        lots_df = data['lots_df']

        # Show KPIs in a table
        table = Table(title="YTD Tax KPIs")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta", justify="right")

        for label in config.TAX_CONTROL_KPI_LABELS:
            val = metrics.get(label, 0)
            if isinstance(val, (int, float)):
                fmt_val = f"${val:,.2f}" if "Count" not in label else f"{val}"
            else:
                fmt_val = str(val)
            table.add_row(label, fmt_val)

        console.print(table)

        # Show top 10 lots
        if not lots_df.empty:
            lot_table = Table(title=f"Top {min(10, len(lots_df))} Tax-Relevant Lots (Wash Sales Pinned)")
            for col in lots_df.columns:
                lot_table.add_column(col)
            
            for _, row in lots_df.head(10).iterrows():
                row_vals = []
                for v in row.values:
                    if isinstance(v, pd.Timestamp):
                        row_vals.append(v.strftime('%Y-%m-%d'))
                    elif isinstance(v, (int, float)):
                        row_vals.append(f"{v:,.2f}")
                    else:
                        row_vals.append(str(v))
                lot_table.add_row(*row_vals)
            
            console.print(lot_table)

        if not live:
            console.print("\n[yellow]DRY RUN complete. Use --live to write to Google Sheets.[/]")
        else:
            console.print("\n[bold green]✅ Tax_Control refresh complete.[/]")

    except Exception as e:
        console.print(f"[red]ERROR refreshing tax control: {e}[/]")
        raise typer.Exit(code=1)


# --- DASHBOARD GROUP ---
dashboard_app = typer.Typer(help="Dashboard maintenance commands.")
app.add_typer(dashboard_app, name="dashboard")

@dashboard_app.command("refresh")
def dashboard_refresh(
    live: bool = typer.Option(False, "--live", help="Perform live update/formatting."),
    update: bool = typer.Option(False, "--update", help="Sync latest positions from Schwab before refreshing."),
    tx_days: int = typer.Option(90, "--tx-days", help="Days of transaction history to fetch with --update (use 365 for backfill)."),
    skip_tax: bool = typer.Option(False, "--skip-tax", help="Skip the Tax_Control refresh step."),
):
    """Refreshes Valuation_Card, Decision_View, Tax_Control and all formatting."""
    from tasks.build_valuation_card import main as build_val
    from tasks.build_decision_view import main as build_dec
    from tasks.format_sheets_dashboard_v2 import main as format_v2
    from tasks.build_tax_control import refresh_tax_control_sheet

    if update:
        console.print(f"[cyan]Step 0: Running Live Update from Schwab (tx_days={tx_days})...[/]")
        import scripts.live_update as live_up
        import config as cfg
        original_dry = cfg.DRY_RUN
        cfg.DRY_RUN = not live
        try:
            live_up.update_portfolio(tx_days=tx_days)
        finally:
            cfg.DRY_RUN = original_dry

        if live:
            time.sleep(2)

    console.print("\n[cyan]Step 1: Building Valuation Card...[/]")
    build_val(live=live)

    if live:
        time.sleep(2)

    console.print("\n[cyan]Step 2: Building Decision View...[/]")
    build_dec(live=live)

    if live:
        time.sleep(2)

    if not skip_tax:
        console.print("\n[cyan]Step 3: Refreshing Tax Control...[/]")
        refresh_tax_control_sheet(live=live)
        if live:
            time.sleep(2)
    else:
        console.print("\n[yellow]Step 3: Skipping Tax Control refresh.[/]")

    console.print("\n[cyan]Step 4: Applying V2 Formatting...[/]")
    format_v2(live=live)

    console.print("\n[bold green]✅ Dashboard refresh complete.[/]")

# --- EXPORT GROUP ---
export_app = typer.Typer(help="Export context packages for frontier LLM analysis.")
app.add_typer(export_app, name="export")

@export_app.command("list")
def export_list():
    """List available export scenarios grouped by category."""
    import config
    
    console.print("\n[bold cyan]Decision Support:[/]")
    table_ds = Table(box=None, show_header=False)
    table_ds.add_column("Scenario", style="magenta", width=20)
    table_ds.add_column("Description", style="white")
    table_ds.add_row("rotation", config.EXPORT_SCENARIOS["rotation"])
    table_ds.add_row("deep-dive", config.EXPORT_SCENARIOS["deep-dive"])
    table_ds.add_row("tax-rebalance", config.EXPORT_SCENARIOS["tax-rebalance"])
    table_ds.add_row("rotation-retrospective", "Pattern analysis on recent trade history")
    console.print(table_ds)

    console.print("\n[bold cyan]Portfolio Review:[/]")
    table_pr = Table(box=None, show_header=False)
    table_pr.add_column("Scenario", style="magenta", width=20)
    table_pr.add_column("Description", style="white")
    table_pr.add_row("technical-scan", config.EXPORT_SCENARIOS["technical-scan"])
    table_pr.add_row("macro-review", config.EXPORT_SCENARIOS["macro-review"])
    table_pr.add_row("concentration", config.EXPORT_SCENARIOS["concentration"])
    table_pr.add_row("thesis-health", config.EXPORT_SCENARIOS["thesis-health"])
    console.print(table_pr)
    console.print("")

@export_app.command("cleanup")
def export_cleanup(
    days: int = typer.Option(7, "--days", help="Delete packages older than this many days."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation.")
):
    """Delete old export packages from the exports/ directory."""
    import shutil
    import time
    import config
    
    if not config.EXPORTS_DIR.exists():
        console.print("[yellow]No exports directory found.[/]")
        return

    now = time.time()
    cutoff = now - (days * 86400)
    
    to_delete = []
    for pkg in config.EXPORTS_DIR.glob("*"):
        if pkg.is_dir() and pkg.stat().st_mtime < cutoff:
            to_delete.append(pkg)
            
    if not to_delete:
        console.print(f"[green]No packages older than {days} days found.[/]")
        return
        
    console.print(f"[yellow]Found {len(to_delete)} packages older than {days} days.[/]")
    
    if not force:
        confirm = typer.confirm("Are you sure you want to delete them?")
        if not confirm:
            console.print("[red]Aborted.[/]")
            return
            
    for pkg in to_delete:
        shutil.rmtree(pkg)
        console.print(f"  Deleted: {pkg.name}")
        
    console.print("[bold green]Cleanup complete.[/]")

@export_app.command("inspect")
def export_inspect(path: Path = typer.Argument(..., help="Path to the export package directory.")):
    """Print the structure of an export package (file sizes, hashes, preview)."""
    if not path.exists() or not path.is_dir():
        console.print(f"[red]ERROR: '{path}' is not a valid directory.[/]")
        raise typer.Exit(code=1)

    manifest_path = path / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[red]ERROR: No manifest.json found in '{path}'.[/]")
        raise typer.Exit(code=1)

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    table = Table(title=f"Package Inspection: {path.name}", box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Scenario", manifest.get("scenario"))
    table.add_row("Timestamp", manifest.get("timestamp"))
    table.add_row("Composite Hash", manifest.get("composite_hash"))
    table.add_row("Template Version", manifest.get("prompt_template_version"))
    
    console.print(table)

    # File list
    file_table = Table(title="File List")
    file_table.add_column("File", style="cyan")
    file_table.add_column("Size (bytes)", justify="right")

    for f in path.rglob("*"):
        if f.is_file():
            # Relative path to package root
            rel = f.relative_to(path)
            file_table.add_row(str(rel), f"{f.stat().st_size:,}")
    
    console.print(file_table)

    # Prompt preview
    prompt_path = path / "prompt.md"
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            preview = f.read(500)
            console.print(Panel(f"{preview}...", title="Prompt Preview (first 500 chars)"))

@export_app.command("tax-rebalance")
def export_tax_rebalance():
    """Package a tax-aware rebalancing snapshot for frontier LLM review."""
    import hashlib
    from datetime import datetime
    import config
    from core.composite_bundle import resolve_latest_bundles
    from tasks.build_tax_control import compute_tax_control_data
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme, 
        write_context_json, write_prompt_markdown
    )

    console.print("Preparing tax-rebalance export...")

    try:
        m_path, v_path = resolve_latest_bundles()
        from core.bundle import load_bundle
        market_data = load_bundle(m_path)
        comp_hash = hashlib.sha256(f"{market_data['bundle_hash']}".encode()).hexdigest()

        # 1. Tax Posture
        tax_res = compute_tax_control_data()
        metrics = tax_res.get("metrics", {})

        # 2. Unrealized Loss Candidates
        positions = market_data.get("positions", [])
        loss_candidates = [p for p in positions if p.get("unrealized_gl", 0) < -500]
        loss_candidates.sort(key=lambda x: x.get("unrealized_gl", 0))

        # 3. Thesis Drift Candidates (Qualitative rebalancing)
        from core.thesis_sync_data import gather_thesis_sync_data
        # We use today's date for drift check, but we care about the computed drift_pct
        drift_data = gather_thesis_sync_data()
        drift_candidates = []
        for ticker, payload in drift_data.items():
            if abs(payload.drift_pct) > 1.0: # 1% drift threshold
                drift_candidates.append(payload)
        
        drift_candidates.sort(key=lambda x: x.drift_pct, reverse=True)

        # Loss Candidates Table
        table_rows = ["| Ticker | Weight | Price | Cost Basis | Unrealized G/L | UGL % |"]
        table_rows.append("| :--- | ---: | ---: | ---: | ---: | ---: |")
        for p in loss_candidates:
            table_rows.append(
                f"| {p.get('ticker')} | {p.get('weight_pct', 0):.2f}% | ${p.get('price', 0):,.2f} | "
                f"${p.get('cost_basis', 0):,.2f} | ${p.get('unrealized_gl', 0):,.2f} | "
                f"{p.get('unrealized_gl_pct', 0)*100:.2f}% |"
            )
        markdown_table = "\n".join(table_rows)

        # Drift Candidates Table
        drift_rows = ["| Ticker | Style | Actual Weight | Size Ceiling | Drift % |"]
        drift_rows.append("| :--- | :--- | ---: | ---: | ---: |")
        for d in drift_candidates:
            drift_rows.append(
                f"| {d.ticker} | {d.style or 'N/A'} | {d.current_allocation_pct:.2f}% | "
                f"{d.size_ceiling_pct:.2f}% | {d.drift_pct:+.2f}% |"
            )
        drift_table = "\n".join(drift_rows)

        # 4. Assemble
        pkg_dir = create_package_dir("tax-rebalance")
        context = {
            "tax_posture": metrics, 
            "loss_candidates": loss_candidates,
            "drift_candidates": [d.model_dump() for d in drift_candidates]
        }
        write_context_json(pkg_dir, context)

        with open("tasks/templates/tax_rebalance_v1.md", "r", encoding="utf-8") as f:
            template = f.read()
        
        prompt_content = template.format(
            TIMESTAMP=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            YTD_NET_ST=f"${metrics.get('Net ST (YTD)', 0):,.2f}",
            YTD_NET_LT=f"${metrics.get('Net LT (YTD)', 0):,.2f}",
            WASH_DIS=f"${metrics.get('Disallowed Wash Loss (YTD)', 0):,.2f}",
            EST_TAX=f"${metrics.get('Est. Fed Cap Gains Tax', 0):,.2f}",
            OFFSET=f"${metrics.get('Tax Offset Capacity', 0):,.2f}",
            LOSS_CANDIDATES_TABLE=markdown_table,
            DRIFT_CANDIDATES_TABLE=drift_table
        )
        write_prompt_markdown(pkg_dir, prompt_content)
        write_manifest(pkg_dir, "tax-rebalance", comp_hash, config.PROMPT_TEMPLATE_VERSION_TAX_REBALANCE)
        write_readme(pkg_dir, "tax-rebalance", "Tax-loss harvesting candidates", "Paste prompt.md and context.json")

        console.print(f"\n[bold green]✅ Export Package Created:[/] {pkg_dir}")

    except Exception as e:
        console.print(f"[red]ERROR generating tax-rebalance export: {e}[/]")
        raise typer.Exit(code=1)

@export_app.command("macro-review")
def export_macro_review():
    """Package a macro-alignment snapshot for frontier LLM review."""
    import hashlib
    from datetime import datetime, timedelta
    import pandas as pd
    import config
    from core.composite_bundle import resolve_latest_bundles
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme, 
        write_context_json, write_prompt_markdown
    )

    console.print("Preparing macro-review export...")

    try:
        m_path, v_path = resolve_latest_bundles()
        from core.bundle import load_bundle
        market_data = load_bundle(m_path)
        comp_hash = hashlib.sha256(f"{market_data['bundle_hash']}".encode()).hexdigest()

        # 1. Weights
        positions = market_data.get("positions", [])
        cash_weight = sum(p.get("weight_pct", 0) for p in positions if p.get("is_cash") or p.get("ticker") in config.CASH_TICKERS)
        
        sorted_pos = sorted(positions, key=lambda x: x.get("weight_pct", 0), reverse=True)
        top_10_weight = sum(p.get("weight_pct", 0) for p in sorted_pos[:10])

        # Sector weights
        sectors = {}
        for p in positions:
            s = p.get("asset_class", "Other")
            sectors[s] = sectors.get(s, 0) + p.get("weight_pct", 0)
        
        sector_rows = ["| Sector | Weight |"]
        sector_rows.append("| :--- | ---: |")
        for s, w in sorted(sectors.items(), key=lambda x: x[1], reverse=True):
            sector_rows.append(f"| {s} | {w:.2f}% |")
        sector_table = "\n".join(sector_rows)

        # 2. Trade Log
        from utils.sheet_readers import get_trade_log
        try:
            trade_df = get_trade_log()
            ninety_days_ago = datetime.now() - timedelta(days=90)
            trade_df['Date'] = pd.to_datetime(trade_df['Date'], errors='coerce')
            recent_trades = trade_df[trade_df['Date'] > ninety_days_ago].sort_values("Date", ascending=False).head(15)
            trade_log_str = recent_trades[['Date', 'Sell_Ticker', 'Buy_Ticker', 'Implicit_Bet']].to_string(index=False)
        except:
            trade_log_str = "No recent trade log data."

        # 3. Assemble
        pkg_dir = create_package_dir("macro-review")
        context = {"sectors": sectors, "top_10_weight": top_10_weight, "cash_weight": cash_weight}
        write_context_json(pkg_dir, context)

        with open("tasks/templates/macro_review_v1.md", "r", encoding="utf-8") as f:
            template = f.read()
        
        prompt_content = template.format(
            TIMESTAMP=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            CASH_WEIGHT=f"{cash_weight:.2f}%",
            TOP_10_WEIGHT=f"{top_10_weight:.2f}",
            SECTOR_WEIGHTS_TABLE=sector_table,
            ALLOCATION_DRIFT_TABLE="See context.json for full sector drift",
            TRADE_LOG_CONTEXT=trade_log_str
        )
        write_prompt_markdown(pkg_dir, prompt_content)
        write_manifest(pkg_dir, "macro-review", comp_hash, config.PROMPT_TEMPLATE_VERSION_MACRO_REVIEW)
        write_readme(pkg_dir, "macro-review", "Portfolio macro alignment check", "Paste prompt.md and context.json")

        console.print(f"\n[bold green]✅ Export Package Created:[/] {pkg_dir}")

    except Exception as e:
        console.print(f"[red]ERROR generating macro-review export: {e}[/]")
        raise typer.Exit(code=1)

@export_app.command("concentration")
def export_concentration():
    """Package a concentration and correlation snapshot for frontier LLM review."""
    import hashlib
    from datetime import datetime
    import config
    from core.composite_bundle import resolve_latest_bundles
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme, 
        write_context_json, write_prompt_markdown
    )

    console.print("Preparing concentration export...")

    try:
        m_path, v_path = resolve_latest_bundles()
        from core.bundle import load_bundle
        market_data = load_bundle(m_path)
        comp_hash = hashlib.sha256(f"{market_data['bundle_hash']}".encode()).hexdigest()

        # 1. Structure
        positions = market_data.get("positions", [])
        styles = {}
        for p in positions:
            s = p.get("asset_strategy", "N/A")
            styles[s] = styles.get(s, 0) + p.get("weight_pct", 0)
        style_str = ", ".join([f"{s}: {w:.2f}%" for s, w in sorted(styles.items(), key=lambda x: x[1], reverse=True)])

        # Top 10
        sorted_pos = sorted(positions, key=lambda x: x.get("weight_pct", 0), reverse=True)
        top_10_rows = ["| Ticker | Style | Weight | Sector |"]
        top_10_rows.append("| :--- | :--- | ---: | :--- |")
        for p in sorted_pos[:10]:
            top_10_rows.append(f"| {p.get('ticker')} | {p.get('asset_strategy')} | {p.get('weight_pct', 0):.2f}% | {p.get('asset_class')} |")
        top_10_table = "\n".join(top_10_rows)

        # 2. Assemble
        pkg_dir = create_package_dir("concentration")
        context = {"styles": styles, "top_10": sorted_pos[:10]}
        write_context_json(pkg_dir, context)

        with open("tasks/templates/concentration_v1.md", "r", encoding="utf-8") as f:
            template = f.read()
        
        prompt_content = template.format(
            TIMESTAMP=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            STYLE_WEIGHTS=style_str,
            TOP_10_TABLE=top_10_table,
            SECTOR_TABLE="See macro-review or context.json for full sector breakdown"
        )
        write_prompt_markdown(pkg_dir, prompt_content)
        write_manifest(pkg_dir, "concentration", comp_hash, config.PROMPT_TEMPLATE_VERSION_CONCENTRATION)
        write_readme(pkg_dir, "concentration", "Hidden concentration and correlation check", "Paste prompt.md and context.json")

        console.print(f"\n[bold green]✅ Export Package Created:[/] {pkg_dir}")

    except Exception as e:
        console.print(f"[red]ERROR generating concentration export: {e}[/]")
        raise typer.Exit(code=1)

@export_app.command("thesis-health")
def export_thesis_health():
    """Package a thesis health and action zone audit for frontier LLM review."""
    import hashlib
    from datetime import datetime
    import config
    from core.composite_bundle import resolve_latest_bundles
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme, 
        copy_thesis_files, write_context_json, write_prompt_markdown
    )

    console.print("Preparing thesis-health export...")

    try:
        m_path, v_path = resolve_latest_bundles()
        from core.bundle import load_bundle
        from core.vault_bundle import load_vault_bundle
        market_data = load_bundle(m_path)
        vault_data = load_vault_bundle(v_path)
        comp_hash = hashlib.sha256(f"{market_data['bundle_hash']}{vault_data['vault_hash']}".encode()).hexdigest()

        # 1. Audit
        positions = market_data.get("positions", [])
        total_pos = len([p for p in positions if p.get("ticker") not in config.CASH_TICKERS])
        
        theses_present = vault_data.get("theses_present", [])
        missing_theses = [p.get("ticker") for p in positions if p.get("ticker") not in theses_present and p.get("ticker") not in config.CASH_TICKERS]
        
        # 2. Deviations
        trigger_map = {d.get("ticker"): d.get("triggers", {}) for d in vault_data.get("documents", []) if d.get("doc_type") == "thesis"}
        
        dev_rows = ["| Ticker | Price | Add Target | Trim Target | Status |"]
        dev_rows.append("| :--- | ---: | ---: | ---: | :--- |")
        
        for p in positions:
            ticker = p.get("ticker")
            if ticker in config.CASH_TICKERS: continue
            
            price = p.get("price", 0)
            trigs = trigger_map.get(ticker, {})
            add_t = trigs.get("price_add_below")
            trim_t = trigs.get("price_trim_above")
            
            status = "NEUTRAL"
            if trim_t and price >= trim_t: status = "ABOVE_TRIM"
            elif add_t and price <= add_t: status = "BELOW_ADD"
            
            if status != "NEUTRAL":
                dev_rows.append(f"| {ticker} | ${price:,.2f} | ${add_t if add_t else 0:,.2f} | ${trim_t if trim_t else 0:,.2f} | {status} |")
        
        dev_table = "\n".join(dev_rows)

        # 3. Assemble
        pkg_dir = create_package_dir("thesis-health")
        write_context_json(pkg_dir, {"audit": {"total": total_pos, "present": len(theses_present), "missing": missing_theses}})

        with open("tasks/templates/thesis_health_v1.md", "r", encoding="utf-8") as f:
            template = f.read()
        
        prompt_content = template.format(
            TIMESTAMP=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            TOTAL_POSITIONS=total_pos,
            THESIS_COUNT=len(theses_present),
            MISSING_THESIS_LIST=", ".join(missing_theses[:20]),
            DEVIATION_TABLE=dev_table
        )
        write_prompt_markdown(pkg_dir, prompt_content)
        
        # Copy top 10 tickers by weight that have theses
        top_tickers = [p.get("ticker") for p in sorted(positions, key=lambda x: x.get("weight_pct", 0), reverse=True)[:10]]
        copy_thesis_files(pkg_dir, top_tickers)
        
        write_manifest(pkg_dir, "thesis-health", comp_hash, config.PROMPT_TEMPLATE_VERSION_THESIS_HEALTH)
        write_readme(pkg_dir, "thesis-health", "Stale thesis and action zone audit", "Paste prompt.md and attach context.json + theses/")

        console.print(f"\n[bold green]✅ Export Package Created:[/] {pkg_dir}")

    except Exception as e:
        console.print(f"[red]ERROR generating thesis-health export: {e}[/]")
        raise typer.Exit(code=1)

@export_app.command("technical-scan")
def export_technical_scan(
    filter_style: str = typer.Option("", "--style", help="Filter to a specific style (GARP/FUND/THEME/ETF)."),
    min_weight: float = typer.Option(0.0, "--min-weight", help="Only include positions ≥ this weight %."),
    chunk_size: int = typer.Option(15, "--chunk-size", help="Split into parts with this many tickers per part.")
):
    """Package a portfolio-wide technical snapshot for frontier LLM review."""
    import hashlib
    from datetime import datetime
    import config
    from core.composite_bundle import resolve_latest_bundles, load_composite, CompositeBundle
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme, 
        write_context_json, write_prompt_markdown
    )

    console.print(f"Preparing technical-scan export (Style: {filter_style or 'All'}, Min Weight: {min_weight}%)...")

    try:
        # 1. Resolve Latest Bundles
        m_path, v_path = resolve_latest_bundles()
        from core.bundle import load_bundle
        from core.vault_bundle import load_vault_bundle
        market_data = load_bundle(m_path)
        vault_data = load_vault_bundle(v_path)
        comp_hash = hashlib.sha256(f"{market_data['bundle_hash']}{vault_data['vault_hash']}".encode()).hexdigest()

        # 2. Pull data for all positions
        positions = market_data.get("positions", [])
        technicals = market_data.get("calculated_technicals", [])
        
        # Build trigger map from vault
        trigger_map = {}
        for doc in vault_data.get("documents", []):
            if doc.get("doc_type") == "thesis":
                trigger_map[doc.get("ticker")] = doc.get("triggers", {})

        # 3. Filter and Build Table
        all_candidate_positions = []
        for pos in positions:
            ticker = pos.get("ticker")
            style = pos.get("asset_strategy", "N/A")
            weight = pos.get("weight_pct", 0)
            
            if ticker in config.CASH_TICKERS or pos.get("is_cash"):
                continue
            if filter_style and filter_style.upper() != style.upper():
                continue
            if weight < min_weight:
                continue
            
            all_candidate_positions.append(pos)

        # 4. Process in Chunks
        pkg_dir = create_package_dir("technical-scan")
        chunks = [all_candidate_positions[i:i + chunk_size] for i in range(0, len(all_candidate_positions), chunk_size)]
        
        for idx, chunk in enumerate(chunks):
            chunk_num = idx + 1
            table_rows = []
            filtered_positions = []
            
            for pos in chunk:
                ticker = pos.get("ticker")
                style = pos.get("asset_strategy", "N/A")
                weight = pos.get("weight_pct", 0)
                price = pos.get("price", 0)
                
                tech = next((t for t in technicals if t.get("ticker") == ticker), {})
                trigs = trigger_map.get(ticker, {})
                
                rsi = tech.get("rsi", "N/A")
                trend = tech.get("trend_label", "N/A")
                add_target = trigs.get("price_add_below", "N/A")
                trim_target = trigs.get("price_trim_above", "N/A")
                
                in_zone = "NEUTRAL"
                if isinstance(trim_target, (int, float)) and price >= trim_target:
                    in_zone = "TRIM"
                elif isinstance(add_target, (int, float)) and price <= add_target:
                    in_zone = "ADD"
                
                # Format for markdown table
                row = [
                    ticker, style, f"{weight:.2f}%", f"${price:,.2f}", 
                    f"{rsi:.1f}" if isinstance(rsi, (int, float)) else "N/A",
                    trend, 
                    f"${add_target:,.2f}" if isinstance(add_target, (int, float)) else "N/A",
                    f"${trim_target:,.2f}" if isinstance(trim_target, (int, float)) else "N/A",
                    in_zone
                ]
                table_rows.append(f"| {' | '.join(map(str, row))} |")
                
                filtered_positions.append({
                    "ticker": ticker,
                    "style": style,
                    "weight": weight,
                    "price": price,
                    "technicals": tech,
                    "triggers": trigs,
                    "zone_status": in_zone
                })

            table_header = "| Ticker | Style | Weight | Price | RSI | Trend Label | Add Target | Trim Target | In Zone? |"
            table_sep = "| :--- | :--- | ---: | ---: | ---: | :--- | ---: | ---: | :--- |"
            markdown_table = "\n".join([table_header, table_sep] + table_rows)

            # Assemble Part
            part_suffix = f"_part{chunk_num}" if len(chunks) > 1 else ""
            
            context = {
                "part": chunk_num,
                "total_parts": len(chunks),
                "filters": {"style": filter_style, "min_weight": min_weight},
                "positions_count": len(filtered_positions),
                "positions": filtered_positions
            }
            write_context_json(pkg_dir, context, filename=f"context{part_suffix}.json")

            with open("tasks/templates/technical_scan_v1.md", "r", encoding="utf-8") as f:
                template = f.read()
            
            prompt_content = template.format(
                TIMESTAMP=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                FILTER_STYLE_OR_ALL=filter_style or "ALL",
                MIN_WEIGHT=min_weight,
                TECHNICAL_TABLE=markdown_table
            )
            
            if len(chunks) > 1:
                prompt_content = f"### PART {chunk_num} OF {len(chunks)}\n\n" + prompt_content
                
            write_prompt_markdown(pkg_dir, prompt_content, filename=f"prompt{part_suffix}.md")

        write_manifest(pkg_dir, "technical-scan", comp_hash, config.PROMPT_TEMPLATE_VERSION_TECHNICAL_SCAN)
        write_readme(pkg_dir, "technical-scan", f"Technical scan for {filter_style or 'all'} styles", "Paste prompts in sequence and attach context files.")

        console.print(f"\n[bold green]✅ Export Package Created:[/] {pkg_dir} ({len(chunks)} parts)")
        console.print(f"Run: [cyan]python manager.py export inspect {pkg_dir}[/]")

    except Exception as e:
        console.print(f"[red]ERROR generating technical-scan export: {e}[/]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)

@export_app.command("deep-dive")
def export_deep_dive(
    ticker: str = typer.Argument(..., help="Ticker you want a deep dive on."),
    question: str = typer.Option(..., "--question", help="The specific question you want answered."),
):
    """Package a single-position deep dive for frontier LLM review."""
    import hashlib
    from datetime import datetime, timedelta
    import pandas as pd
    import config
    from core.composite_bundle import resolve_latest_bundles, load_composite, CompositeBundle
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme, 
        copy_thesis_files, write_context_json, write_prompt_markdown
    )

    console.print(f"Preparing deep-dive export for [bold cyan]{ticker}[/]...")

    try:
        # 1. Resolve Latest Bundles
        m_path, v_path = resolve_latest_bundles()
        from core.bundle import load_bundle
        from core.vault_bundle import load_vault_bundle
        market_data = load_bundle(m_path)
        vault_data = load_vault_bundle(v_path)
        comp_hash = hashlib.sha256(f"{market_data['bundle_hash']}{vault_data['vault_hash']}".encode()).hexdigest()

        # 2. Extract Ticker Data
        ticker = ticker.upper()
        pos = next((p for p in market_data.get("positions", []) if p.get("ticker") == ticker), {})
        tech = next((t for t in market_data.get("calculated_technicals", []) if t.get("ticker") == ticker), {})
        fund = next((f for f in market_data.get("calculated_fundamentals", []) if f.get("ticker") == ticker), {})
        
        # Thesis and Triggers
        thesis_doc = next((d for d in vault_data.get("documents", []) if d.get("doc_type") == "thesis" and d.get("ticker") == ticker), {})
        trigs = thesis_doc.get("triggers", {})
        style_ceiling = thesis_doc.get("meta", {}).get("style_size_ceiling_pct", "N/A")

        # 3. Drift and Status
        current_price = pos.get("price", 0)
        trim_above = trigs.get("price_trim_above")
        add_below = trigs.get("price_add_below")
        
        zone_status = "NEUTRAL"
        if trim_above and current_price >= trim_above:
            zone_status = "IN_TRIM_ZONE"
        elif add_below and current_price <= add_below:
            zone_status = "IN_ADD_ZONE"

        # 3b. Van Tharp Sizing (R-Multiple Risk Units)
        from utils.risk import compute_van_tharp_sizing
        atr_14 = tech.get("atr_14", 0)
        total_equity = market_data.get("total_value", 0)
        
        # Risk 1% of equity per trade, using 3.0x ATR for 1R unit
        sizing = compute_van_tharp_sizing(
            atr_14=atr_14,
            entry_price=current_price,
            portfolio_equity=total_equity,
            risk_pct=0.01,
            atr_multiplier=3.0
        )

        # 4. Tax/Trade History (last year)
        from utils.sheet_readers import get_realized_gl, get_trade_log
        
        # Realized G/L YTD for this ticker
        try:
            gl_df = get_realized_gl()
            current_year = datetime.now().year
            gl_df['Closed Date'] = pd.to_datetime(gl_df['Closed Date'], errors='coerce')
            ticker_gl = gl_df[(gl_df['Ticker'] == ticker) & (gl_df['Closed Date'].dt.year == current_year)]
            realized_gl_ytd = ticker_gl['Gain Loss $'].sum() if not ticker_gl.empty else 0
        except:
            realized_gl_ytd = 0

        # Trade Log Count (last 365 days)
        try:
            trade_df = get_trade_log()
            one_year_ago = datetime.now() - timedelta(days=365)
            trade_df['Date'] = pd.to_datetime(trade_df['Date'], errors='coerce')
            ticker_trades = trade_df[
                ((trade_df['Sell_Ticker'] == ticker) | (trade_df['Buy_Ticker'] == ticker)) & 
                (trade_df['Date'] > one_year_ago)
            ]
            rotation_count = len(ticker_trades)
            trade_history = ticker_trades[['Date', 'Sell_Ticker', 'Buy_Ticker', 'Implicit_Bet']].to_dict(orient="records")
        except:
            rotation_count = 0
            trade_history = []

        # 5. Assemble Package
        pkg_dir = create_package_dir("deep-dive")
        
        context = {
            "ticker": ticker,
            "question": question,
            "position": pos,
            "technicals": tech,
            "fundamentals": fund,
            "triggers": trigs,
            "style_ceiling": style_ceiling,
            "zone_status": zone_status,
            "van_tharp_sizing": sizing,
            "realized_gl_ytd": realized_gl_ytd,
            "rotation_count_1y": rotation_count,
            "trade_history_1y": trade_history
        }
        write_context_json(pkg_dir, context)

        # Prompt generation
        with open("tasks/templates/deep_dive_v1.md", "r", encoding="utf-8") as f:
            template = f.read()
        
        # Format Sizing Narrative
        if sizing.get("sizing_valid"):
            sizing_fmt = (
                f"1R unit = {sizing['position_size_units']} shares "
                f"(${sizing['position_size_usd']:,.2f} at current price). "
                f"Risk per share: ${sizing['per_share_risk_1r']:.2f}. "
                f"Stop Loss: ${sizing['stop_loss_price']:,.2f}."
            )
        else:
            sizing_fmt = "Insufficient ATR/Price data for Van Tharp sizing."

        prompt_content = template.format(
            TICKER=ticker,
            USER_QUESTION=question,
            COMPOSITE_HASH_SHORT=comp_hash[:12],
            CURRENT_PRICE=f"${current_price:,.2f}" if current_price else "N/A",
            CURRENT_WEIGHT=f"{pos.get('weight_pct', 0):.2f}%" if pos else "N/A",
            STYLE_CEILING=f"{style_ceiling}%" if style_ceiling != "N/A" else "N/A",
            VAN_THARP_1R=sizing_fmt,
            COST_BASIS=f"${pos.get('cost_basis', 0):,.2f}" if pos else "N/A",
            UGL=f"${pos.get('unrealized_gl', 0):,.2f} ({pos.get('unrealized_gl_pct', 0)*100:.2f}%)" if pos else "N/A",
            TECHNICALS=str(tech) if tech else "N/A",
            TREND_LABEL=tech.get("trend_label", "N/A"),
            TREND_SCORE=tech.get("trend_score", "N/A"),
            HIGH_52W=f"${pos.get('fundamentals', {}).get('52w_high', 0):,.2f}",
            LOW_52W=f"${pos.get('fundamentals', {}).get('52w_low', 0):,.2f}",
            FUNDAMENTALS=str(fund) if fund else "N/A",
            FMP_FUNDAMENTALS=str(pos.get("fmp_fundamentals", {})) if pos else "N/A",
            PRICE_TRIM_ABOVE=f"${trim_above:,.2f}" if trim_above else "N/A",
            PRICE_ADD_BELOW=f"${add_below:,.2f}" if add_below else "N/A",
            ZONE_STATUS=zone_status,
            ROTATION_COUNT=rotation_count,
            REALIZED_GL_YTD=f"${realized_gl_ytd:,.2f}"
        )
        write_prompt_markdown(pkg_dir, prompt_content)
        
        copy_thesis_files(pkg_dir, [ticker])
        write_manifest(pkg_dir, "deep-dive", comp_hash, config.PROMPT_TEMPLATE_VERSION_DEEP_DIVE)
        write_readme(pkg_dir, "deep-dive", f"Deep dive analysis for {ticker}", f"Question: {question}")

        console.print(f"\n[bold green]✅ Export Package Created:[/] {pkg_dir}")
        console.print(f"Run: [cyan]python manager.py export inspect {pkg_dir}[/]")

    except Exception as e:
        console.print(f"[red]ERROR generating deep-dive export: {e}[/]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)

@export_app.command("rotation")
def export_rotation(
    sell: str = typer.Option(..., "--sell", help="Ticker you're considering selling."),
    buy: str = typer.Option(..., "--buy", help="Ticker you're considering buying (or 'CASH')."),
    size: str = typer.Option("partial", "--size", help="partial | full"),
    notes: str = typer.Option("", "--notes", help="Free-text context to include in the prompt."),
):
    """Package a rotation analysis for frontier LLM review."""
    import hashlib
    from datetime import timedelta
    import pandas as pd
    import config
    from core.composite_bundle import resolve_latest_bundles, load_composite, CompositeBundle
    from tasks.build_tax_control import compute_tax_control_data
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme, 
        copy_thesis_files, write_context_json, write_prompt_markdown
    )

    console.print(f"Preparing rotation export: [bold cyan]{sell}[/] → [bold green]{buy}[/]...")

    try:
        # 1. Resolve Latest Composite Bundle
        m_path, v_path = resolve_latest_bundles()
        # For simplicity, we can just load the market and vault bundles directly or use build_composite if we want a fresh one.
        # But Phase 4.1 says "Resolves the latest composite bundle". 
        # Since composite_bundle.py doesn't have a 'get latest' helper yet, we'll find the latest context_bundle and vault_bundle.
        from core.bundle import load_bundle
        from core.vault_bundle import load_vault_bundle
        market_data = load_bundle(m_path)
        vault_data = load_vault_bundle(v_path)
        
        comp_hash = hashlib.sha256(f"{market_data['bundle_hash']}{vault_data['vault_hash']}".encode()).hexdigest()

        # 2. Extract Ticker Data
        def get_ticker_info(ticker: str):
            if ticker.upper() == "CASH":
                return {
                    "price": "N/A", "weight": "N/A", "cost_basis": "N/A", "ugl": "N/A",
                    "technicals": "N/A", "fundamentals": "N/A", "trim": "N/A", "add": "N/A"
                }
            
            pos = next((p for p in market_data.get("positions", []) if p.get("ticker") == ticker.upper()), {})
            tech = next((t for t in market_data.get("calculated_technicals", []) if t.get("ticker") == ticker.upper()), {})
            fund = next((f for f in market_data.get("calculated_fundamentals", []) if f.get("ticker") == ticker.upper()), {})
            
            # Triggers from vault
            thesis = next((d for d in vault_data.get("documents", []) if d.get("doc_type") == "thesis" and d.get("ticker") == ticker.upper()), {})
            trigs = thesis.get("triggers", {})

            return {
                "price": f"${pos.get('price', 0):,.2f}" if pos else "N/A",
                "weight": f"{pos.get('weight_pct', 0):.2f}%" if pos else "N/A",
                "cost_basis": f"${pos.get('cost_basis', 0):,.2f}" if pos else "N/A",
                "ugl": f"${pos.get('unrealized_gl', 0):,.2f} ({pos.get('unrealized_gl_pct', 0)*100:.2f}%)" if pos else "N/A",
                "technicals": str(tech) if tech else "N/A",
                "fundamentals": str(fund) if fund else "N/A",
                "trim": trigs.get("price_trim_above", "N/A"),
                "add": trigs.get("price_add_below", "N/A")
            }

        sell_info = get_ticker_info(sell)
        buy_info = get_ticker_info(buy)

        # 3. Tax Data
        tax_res = compute_tax_control_data()
        metrics = tax_res.get("metrics", {})
        
        # Sell-side tax impact estimate
        sell_pos = next((p for p in market_data.get("positions", []) if p.get("ticker") == sell.upper()), {})
        est_gl = 0
        term = "N/A"
        if sell_pos:
            # Simple estimate: proportional G/L if partial, full if full
            full_gl = sell_pos.get("unrealized_gl", 0)
            est_gl = full_gl if size == "full" else full_gl * 0.5 # Default 50% for partial if not specified
            # We don't have lot-level dates here easily without re-parsing CSV, 
            # so we look at the 'term' if enriched or just mark as 'Verify in context.json'
            term = "Check lots in context.json"

        # 4. Trade Log Context (last 90 days)
        from utils.sheet_readers import get_trade_log
        try:
            trade_df = get_trade_log()
            # Filter last 90 days
            ninety_days_ago = datetime.now() - timedelta(days=90)
            trade_df['Date'] = pd.to_datetime(trade_df['Date'])
            recent_trades = trade_df[trade_df['Date'] > ninety_days_ago].sort_values("Date", ascending=False).head(10)
            trade_log_str = recent_trades[['Date', 'Sell_Ticker', 'Buy_Ticker', 'Implicit_Bet']].to_string(index=False)
        except:
            trade_log_str = "No recent trade log data available."

        # 5. Assemble Package
        pkg_dir = create_package_dir("rotation")
        
        # -- FIX: Sanitize Pandas and NumPy types for JSON serialization --
        import json as _json
        
        # 1. Use Pandas' built-in JSON encoder to safely handle Timestamps and int64s
        if 'recent_trades' in locals() and not recent_trades.empty:
            safe_rotations = _json.loads(recent_trades.to_json(orient="records", date_format="iso"))
        else:
            safe_rotations = []
        
        # 2. Extract native Python types from Numpy wrappers in the metrics dict
        safe_metrics = {}
        for k, v in metrics.items():
            if hasattr(v, 'item'):  # Safely converts np.int64/np.float64 to native int/float
                safe_metrics[k] = v.item()
            else:
                safe_metrics[k] = v
                
        context = {
            "sell_ticker": sell.upper(),
            "buy_ticker": buy.upper(),
            "size": size,
            "user_notes": notes,
            "sell_side": sell_info,
            "buy_side": buy_info,
            "tax_posture": safe_metrics,
            "sell_tax_estimate": {"gain_loss": float(est_gl), "term": term},
            "recent_rotations": safe_rotations
        }
        write_context_json(pkg_dir, context)
        
        # Prompt generation
        with open("tasks/templates/rotation_v1.md", "r", encoding="utf-8") as f:
            template = f.read()
        
        prompt_content = template.format(
            SELL_TICKER=sell.upper(),
            BUY_TICKER=buy.upper(),
            SELL_SIZE=size,
            SELL_DOLLAR_AMOUNT="See context.json",
            BUY_DOLLAR_AMOUNT="See context.json",
            USER_NOTES=notes,
            COMPOSITE_HASH_SHORT=comp_hash[:12],
            SELL_PRICE=sell_info['price'],
            SELL_WEIGHT=sell_info['weight'],
            SELL_COST_BASIS=sell_info['cost_basis'],
            SELL_UGL=sell_info['ugl'],
            SELL_TECHNICALS=sell_info['technicals'],
            SELL_FUNDAMENTALS=sell_info['fundamentals'],
            SELL_TRIM=sell_info['trim'],
            SELL_ADD=sell_info['add'],
            BUY_PRICE=buy_info['price'],
            BUY_WEIGHT=buy_info['weight'],
            BUY_COST_BASIS=buy_info['cost_basis'],
            BUY_UGL=buy_info['ugl'],
            BUY_TECHNICALS=buy_info['technicals'],
            BUY_FUNDAMENTALS=buy_info['fundamentals'],
            BUY_TRIM=buy_info['trim'],
            BUY_ADD=buy_info['add'],
            ESTIMATED_REALIZED_GL=f"${est_gl:,.2f}",
            ST_OR_LT=term,
            YTD_NET_ST=f"${metrics.get('Net ST (YTD)', 0):,.2f}",
            YTD_NET_LT=f"${metrics.get('Net LT (YTD)', 0):,.2f}",
            WASH_DIS=f"${metrics.get('Disallowed Wash Loss (YTD)', 0):,.2f}",
            EST_TAX=f"${metrics.get('Est. Fed Cap Gains Tax', 0):,.2f}",
            OFFSET=f"${metrics.get('Tax Offset Capacity', 0):,.2f}",
            TRADE_LOG_CONTEXT=trade_log_str
        )
        write_prompt_markdown(pkg_dir, prompt_content)
        
        copy_thesis_files(pkg_dir, [sell, buy])
        write_manifest(pkg_dir, "rotation", comp_hash, config.PROMPT_TEMPLATE_VERSION_ROTATION)
        write_readme(pkg_dir, "rotation", f"Rotation analysis for {sell} -> {buy}", "Paste prompt.md and attach context.json + theses/")

        console.print(f"\n[bold green]✅ Export Package Created:[/] {pkg_dir}")
        console.print(f"Run: [cyan]python manager.py export inspect {pkg_dir}[/]")

    except Exception as e:
        console.print(f"[red]ERROR generating rotation export: {e}[/]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)


@export_app.command("rotation-retrospective")
def export_rotation_retrospective(
    last_n: int = typer.Option(20, "--last-n", help="Number of most recent rotations to include."),
    by_type: str = typer.Option("", "--type", help="Filter to one rotation type."),
):
    """Package the last N rotations with attribution for frontier LLM pattern analysis."""
    import config
    from utils.sheet_readers import get_gspread_client
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme, 
        write_context_json, write_prompt_markdown
    )

    with console.status("[cyan]Reading Rotation_Review data..."):
        try:
            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            try:
                ws = ss.worksheet(config.TAB_ROTATION_REVIEW)
                rows = ws.get_all_values()
            except Exception:
                console.print(f"[red]ERROR: Tab '{config.TAB_ROTATION_REVIEW}' not found. Run 'manager.py trade review' first.[/]")
                raise typer.Exit(code=1)

            if len(rows) < 2:
                console.print("[yellow]Rotation_Review is empty. Nothing to retrospective.[/]")
                return

            headers = rows[0]
            data = [dict(zip(headers, r)) for r in rows[1:]]
        except Exception as e:
            console.print(f"[red]ERROR reading Rotation_Review: {e}[/]")
            raise typer.Exit(code=1)

    # Filter
    if by_type:
        data = [r for r in data if r.get("Rotation_Type", "").lower() == by_type.lower()]
    
    # Sort by date desc (most recent first) and take last N
    data.sort(key=lambda x: x.get("Date", ""), reverse=True)
    subset = data[:last_n]

    if not subset:
        console.print("[yellow]No rotations found matching filters.[/]")
        return

    # Pre-compute stats
    total = len(subset)
    types = {}
    for r in subset:
        t = r.get("Rotation_Type", "unknown")
        types[t] = types.get(t, 0) + 1
    type_breakdown = ", ".join([f"{k}: {v}" for k, v in types.items()])

    # Median 90d return
    returns_90d = []
    for r in subset:
        val = r.get("Pair_Return_90d", "")
        if val and val != "":
            try:
                # Sheets might have % or float string
                clean_val = float(str(val).replace("%", "").strip()) / (100.0 if "%" in str(val) else 1.0)
                returns_90d.append(clean_val)
            except: pass
    
    returns_90d.sort()
    median_90d = 0
    if returns_90d:
        mid = len(returns_90d) // 2
        median_90d = returns_90d[mid] if len(returns_90d) % 2 != 0 else (returns_90d[mid-1] + returns_90d[mid]) / 2

    pos_90d = len([v for v in returns_90d if v > 0])
    pos_90d_pct = f"{(pos_90d / len(returns_90d) * 100):.1f}%" if returns_90d else "N/A"

    # Positive 180d
    returns_180d = []
    for r in subset:
        val = r.get("Pair_Return_180d", "")
        if val and val != "":
            try:
                clean_val = float(str(val).replace("%", "").strip()) / (100.0 if "%" in str(val) else 1.0)
                returns_180d.append(clean_val)
            except: pass
    pos_180d = len([v for v in returns_180d if v > 0])
    pos_180d_pct = f"{(pos_180d / len(returns_180d) * 100):.1f}%" if returns_180d else "N/A"

    # Build Markdown Table
    table_rows = []
    for r in subset:
        # Date | Sell | Buy | Type | Sell RSI | Buy RSI | Pair 30d | Pair 90d | Pair 180d | Implicit Bet
        table_rows.append(
            f"| {r.get('Date')} | {r.get('Sell_Ticker')} | {r.get('Buy_Ticker')} | {r.get('Rotation_Type')} | "
            f"{r.get('Sell_RSI_At_Decision')} | {r.get('Buy_RSI_At_Decision')} | "
            f"{r.get('Pair_Return_30d')} | {r.get('Pair_Return_90d')} | {r.get('Pair_Return_180d')} | "
            f"{r.get('Implicit_Bet')} |"
        )
    rotation_table_md = "\n".join(table_rows)

    # Package
    pkg_dir = create_package_dir("rotation_retrospective")
    write_context_json(pkg_dir, {"rotations": subset, "stats": {
        "total": total, "type_breakdown": types, "median_90d": median_90d, "positive_90d_pct": pos_90d_pct
    }})

    template_path = Path("tasks/templates/rotation_retrospective_v1.md")
    if template_path.exists():
        with open(template_path, "r") as f:
            template = f.read()
        prompt_content = template.format(
            N=total,
            ROTATION_TABLE=rotation_table_md,
            TYPE_BREAKDOWN=type_breakdown,
            MEDIAN_90D=f"{median_90d:.1%}",
            POSITIVE_90D_PCT=pos_90d_pct,
            POSITIVE_180D_PCT=pos_180d_pct
        )
        write_prompt_markdown(pkg_dir, prompt_content)
        
        write_manifest(pkg_dir, "rotation-retrospective", "N/A", "1.0.0")
        write_readme(pkg_dir, "rotation-retrospective", f"Retrospective on last {total} rotations", "Paste prompt.md and attach context.json")

        console.print(f"\n[bold green]✅ Retrospective Package Created:[/] {pkg_dir}")
        console.print(f"Contains last {total} rotations.")
    else:
        console.print("[red]ERROR: Template tasks/templates/rotation_retrospective_v1.md not found.[/]")


# --- PODCAST GROUP ---
podcast_app = typer.Typer(help="Podcast transcript collection and optional AI analysis.")
app.add_typer(podcast_app, name="podcast")


@podcast_app.command("fetch")
def podcast_fetch(
    video_id: str = typer.Argument(..., help="YouTube video ID (the part after v=)."),
    source_name: str = typer.Option("Manual", "--source-name", "-s", help="Friendly source label written into the filename."),
):
    """Download a single transcript to data/podcast_transcripts/. No AI, no Sheet writes."""
    from tasks.podcast_fetcher import fetch_transcript_to_file

    console.print(f"Fetching transcript for [cyan]{video_id}[/]...")
    try:
        save_path = fetch_transcript_to_file(video_id, source_name=source_name)
    except Exception as e:
        console.print(f"[red]ERROR: Could not download transcript: {e}[/]")
        raise typer.Exit(code=1)

    word_count = len(save_path.read_text(encoding="utf-8").split())
    console.print(f"  Words:  [green]{word_count:,}[/]")
    console.print(f"  Saved:  [green]{save_path}[/]")


@podcast_app.command("batch")
def podcast_batch(
    analyze: bool = typer.Option(False, "--analyze", help="Also run Gemini analysis and write to AI_Suggested_Allocation. Default: transcripts only."),
    live: bool = typer.Option(False, "--live", help="Required for Sheet writes when --analyze is set. Also updates the dedup log."),
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Process only one named channel from PODCAST_CHANNELS. Default: all."),
):
    """Scan configured channels for new episodes via YouTube RSS. Downloads transcripts for new episodes.

    With --analyze: also run Gemini analysis (dry-run print by default; --live writes to AI_Suggested_Allocation).
    Dedup log is only updated with --live, so dry-run batches are safe to repeat.
    """
    from tasks.batch_podcast_sync import (
        PODCAST_CHANNELS, TITLE_FILTERS,
        get_latest_video, load_processed_videos, save_processed_videos,
    )
    from tasks.podcast_fetcher import fetch_transcript_to_file, TRANSCRIPTS_DIR

    mode = "LIVE" if live else "DRY RUN"
    console.print(f"\n[bold cyan]=== Podcast Batch — {mode} ===[/]")

    # Channel filter
    channels = PODCAST_CHANNELS
    if channel:
        if channel not in PODCAST_CHANNELS:
            console.print(f"[red]ERROR: '{channel}' not in PODCAST_CHANNELS. Known channels: {list(PODCAST_CHANNELS.keys())}[/]")
            raise typer.Exit(code=1)
        channels = {channel: PODCAST_CHANNELS[channel]}

    processed = load_processed_videos()
    results: dict[str, list[str]] = {"fetched": [], "skipped": [], "failed": []}

    for ch_name, ch_id in channels.items():
        console.print(f"\n[bold]Checking:[/] {ch_name}")
        title_filter = TITLE_FILTERS.get(ch_name)
        video_id, title = get_latest_video(ch_id, title_filter=title_filter)

        if video_id is None:
            console.print(f"  [yellow]Could not fetch latest video (RSS or filter issue)[/]")
            results["failed"].append(ch_name)
            continue

        console.print(f"  Latest: [cyan]{title}[/] (ID: {video_id})")

        if video_id in processed:
            console.print(f"  [dim]SKIP — already processed on {processed[video_id]['processed_at'][:10]}[/]")
            results["skipped"].append(ch_name)
            continue

        # Always fetch transcript to disk
        source_label = f"{ch_name}: {title}"
        try:
            save_path = fetch_transcript_to_file(video_id, source_name=source_label)
            word_count = len(save_path.read_text(encoding="utf-8").split())
            console.print(f"  Transcript: [green]{word_count:,} words -> {save_path.name}[/]")
        except Exception as e:
            console.print(f"  [red]FAILED transcript download: {e}[/]")
            results["failed"].append(ch_name)
            continue

        # Optional Gemini analysis path
        if analyze:
            from utils.agents.podcast_analyst import analyze_podcast
            transcript_text = save_path.read_text(encoding="utf-8")
            console.print(f"  Running Gemini analysis...")
            strategy = analyze_podcast(transcript_text, source_name=source_label)
            if strategy is None:
                console.print(f"  [red]Gemini analysis failed — transcript saved but not analyzed[/]")
                results["failed"].append(ch_name)
                continue

            import json as _json
            console.print(_json.dumps(strategy, indent=2))

            if live:
                import time as _time
                import config as _config
                from utils.sheet_readers import get_gspread_client
                from datetime import datetime as _dt

                targets = strategy.get("target_allocations", [])
                exec_summary = strategy.get("executive_summary", "")
                today = _dt.now().strftime("%Y-%m-%d")

                client = get_gspread_client()
                ss = client.open_by_key(_config.PORTFOLIO_SHEET_ID)
                ws = ss.worksheet(_config.TAB_AI_SUGGESTED_ALLOCATION)

                existing = ws.get_all_values()
                header = existing[0] if existing else []
                other_rows = [r for r in existing[1:] if len(r) > 1 and r[1] != source_label]

                new_rows = []
                for sector in targets:
                    asset_class    = str(sector.get("asset_class", "Other"))
                    asset_strategy = str(sector.get("asset_strategy", "N/A"))
                    target_pct     = float(sector.get("target_pct", 0.0))
                    min_pct        = float(sector.get("min_pct", target_pct - 5.0))
                    max_pct        = float(sector.get("max_pct", target_pct + 5.0))
                    confidence     = str(sector.get("confidence", "Medium"))
                    notes          = str(sector.get("notes", ""))
                    fingerprint    = f"{today}|{source_label}|{asset_class}"
                    new_rows.append([
                        today, source_label, asset_class, asset_strategy,
                        target_pct, min_pct, max_pct, confidence,
                        notes, str(exec_summary), fingerprint,
                    ])

                all_rows = [header] + other_rows + new_rows
                ws.batch_clear(["A1:K1000"])
                _time.sleep(0.5)
                ws.update(range_name="A1", values=all_rows, value_input_option="USER_ENTERED")
                _time.sleep(1.0)
                console.print(f"  [green]Sheet: wrote {len(new_rows)} rows for '{source_label}'[/]")

                try:
                    from utils.podcast_digest import write_summaries_from_sheet, purge_old_summaries
                    purge_old_summaries()
                    written = write_summaries_from_sheet()
                    for p in written:
                        console.print(f"  Summary: {p}")
                except Exception as digest_e:
                    console.print(f"  [yellow]WARNING: Could not write podcast summaries: {digest_e}[/]")
            else:
                console.print("\n[dim]--- DRY RUN COMPLETE --- Use --live to write to Sheet.[/]")
        else:
            if not live:
                console.print(f"  [dim]DRY RUN — transcript saved, dedup log not updated[/]")

        # Record in dedup only on --live
        if live:
            processed[video_id] = {
                "channel": ch_name,
                "title": title,
                "processed_at": datetime.now().isoformat(),
            }
        results["fetched"].append(ch_name)

    if live:
        save_processed_videos(processed)

    # Summary table
    table = Table(title="Batch Summary", box=None)
    table.add_column("Status", style="cyan", width=12)
    table.add_column("Channels")
    table.add_row("Fetched", ", ".join(results["fetched"]) or "none")
    table.add_row("Skipped", ", ".join(results["skipped"]) or "none")
    table.add_row("Failed", ", ".join(results["failed"]) or "none")
    console.print(table)

    # Auto-clean transcripts older than 30 days on every --live run
    if live:
        import time as _time
        from tasks.podcast_fetcher import TRANSCRIPTS_DIR
        if TRANSCRIPTS_DIR.exists():
            cutoff = _time.time() - (30 * 86400)
            stale = [f for f in TRANSCRIPTS_DIR.glob("*.txt") if f.stat().st_mtime < cutoff]
            if stale:
                for f in stale:
                    f.unlink()
                console.print(f"[dim]Auto-cleaned {len(stale)} transcript(s) older than 30 days.[/]")


@podcast_app.command("list")
def podcast_list():
    """Show configured channels and recently fetched transcripts."""
    from tasks.batch_podcast_sync import PODCAST_CHANNELS
    from tasks.podcast_fetcher import TRANSCRIPTS_DIR

    # Channels
    ch_table = Table(title="Configured Channels", box=None)
    ch_table.add_column("Name", style="cyan", width=20)
    ch_table.add_column("Channel ID", style="dim")
    for name, cid in PODCAST_CHANNELS.items():
        ch_table.add_row(name, cid)
    console.print(ch_table)

    # Transcripts
    if not TRANSCRIPTS_DIR.exists() or not any(TRANSCRIPTS_DIR.glob("*.txt")):
        console.print("\n[dim]No transcripts in data/podcast_transcripts/ yet.[/]")
        return

    files = sorted(TRANSCRIPTS_DIR.glob("*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
    total_bytes = sum(f.stat().st_size for f in files)

    t_table = Table(title=f"Transcripts ({len(files)} files, {total_bytes / 1024:.0f} KB total)", box=None)
    t_table.add_column("Date", style="dim", width=12)
    t_table.add_column("Filename", style="cyan")
    t_table.add_column("Size", justify="right", style="dim", width=10)
    for f in files:
        date_str = f.name[:10] if len(f.name) >= 10 else "unknown"
        size_kb = f"{f.stat().st_size / 1024:.1f} KB"
        t_table.add_row(date_str, f.name, size_kb)
    console.print(t_table)


@podcast_app.command("clean")
def podcast_clean(
    days: int = typer.Option(30, "--days", help="Delete transcripts older than N days."),
    force: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    """Delete old transcript files from data/podcast_transcripts/."""
    import time as _time
    from tasks.podcast_fetcher import TRANSCRIPTS_DIR

    if not TRANSCRIPTS_DIR.exists():
        console.print("[yellow]No transcript directory found.[/]")
        return

    cutoff = _time.time() - (days * 86400)
    to_delete = [f for f in TRANSCRIPTS_DIR.glob("*.txt") if f.stat().st_mtime < cutoff]

    if not to_delete:
        console.print(f"[green]No transcripts older than {days} days.[/]")
        return

    console.print(f"[yellow]Found {len(to_delete)} transcript(s) older than {days} days.[/]")

    if not force:
        confirm = typer.confirm("Delete them?")
        if not confirm:
            console.print("[red]Aborted.[/]")
            return

    for f in to_delete:
        f.unlink()
        console.print(f"  Deleted: {f.name}")

    console.print("[bold green]Done.[/]")


PODCAST_ANALYSIS_PROMPT = """\
You are reviewing recent macro/markets podcast transcripts on behalf of an active discretionary investor with a ~$550K portfolio split across individual equities, sector/thematic ETFs, and strategic cash. The investor follows four codified styles (GARP-by-intuition, Thematic Specialists, Boring Fundamentals + dip-buying, Sector/Thematic ETFs as macro expressions) and prefers small-step scaling over binary entries.

For each transcript below, extract:
1. The core 6-12 month macro thesis
2. Sector rotation views (which sectors the speakers are leaning toward / away from, with reasoning)
3. Specific tickers mentioned with rationale, if any
4. Risk factors and contrarian framings worth weighing

Then synthesize across all transcripts:
- Where do the speakers agree?
- Where do they meaningfully disagree?
- What 2-3 actionable considerations emerge for an investor already holding the typical mix above?

Avoid price targets, market timing predictions, and recommendations to abandon the investor's existing process. Flag anything that looks promotional, sponsored, or short-term-trade-focused so the investor can discount it.\
"""

PODCAST_BUNDLES_DIR = Path("data/podcast_bundles")


@podcast_app.command("bundle")
def podcast_bundle(
    last_n: Optional[int] = typer.Option(None, "--last-n", "-n", help="Number of most recent transcripts to include. Default: 5."),
    since_days: Optional[int] = typer.Option(None, "--since-days", help="Include all transcripts from the last N days. Overrides --last-n."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path. Default: data/podcast_bundles/bundle_YYYY-MM-DD_HHMM.md"),
    include_prompt: bool = typer.Option(True, "--prompt/--no-prompt", help="Prepend a ready-to-use analysis prompt for the receiving LLM."),
):
    """Concatenate recent transcripts into a single markdown file ready to paste into Claude or ChatGPT."""
    import time as _time
    from tasks.podcast_fetcher import TRANSCRIPTS_DIR

    if not TRANSCRIPTS_DIR.exists() or not any(TRANSCRIPTS_DIR.glob("*.txt")):
        console.print("[yellow]No transcripts found in data/podcast_transcripts/. Run 'pm podcast batch' first.[/]")
        raise typer.Exit(code=1)

    all_files = sorted(TRANSCRIPTS_DIR.glob("*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)

    # Select files
    if since_days is not None:
        if last_n is not None:
            console.print("[yellow]Both --last-n and --since-days set; --since-days takes precedence.[/]")
        cutoff = _time.time() - (since_days * 86400)
        selected = [f for f in all_files if f.stat().st_mtime >= cutoff]
        if not selected:
            console.print(f"[yellow]No transcripts from the last {since_days} days.[/]")
            raise typer.Exit(code=1)
    else:
        selected = all_files[: last_n if last_n is not None else 5]
        if not selected:
            console.print("[yellow]No transcripts found.[/]")
            raise typer.Exit(code=1)

    # Parse metadata from filenames (YYYY-MM-DD_SOURCE_..._VIDEOID.txt)
    episodes = []
    source_counts: dict[str, int] = {}
    dates = []
    for f in selected:
        parts = f.stem.split("_")
        date_str = parts[0] if parts else "unknown"
        # Source token: everything between the date and the last token (video ID)
        source_raw = "_".join(parts[1:-1]) if len(parts) > 2 else "_".join(parts[1:])
        source_label = source_raw.replace("_", " ").strip() or "Unknown"
        # Infer short channel name from known prefixes
        if source_label.startswith("Forward Guidance"):
            channel = "Forward Guidance"
        elif source_label.startswith("The Compound"):
            channel = "The Compound"
        elif source_label.startswith("Risk Reversal"):
            channel = "Risk Reversal"
        else:
            channel = source_label.split(":")[0].strip() if ":" in source_label else source_label[:30]
        source_counts[channel] = source_counts.get(channel, 0) + 1
        dates.append(date_str)
        episodes.append((date_str, channel, source_label, f))

    date_range = f"{min(dates)} to {max(dates)}" if len(set(dates)) > 1 else dates[0]
    sources_summary = ", ".join(f"{ch} ({n})" for ch, n in sorted(source_counts.items()))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build markdown
    lines = [
        "# Podcast Transcript Bundle",
        "",
        f"**Generated:** {generated_at}",
        f"**Episodes:** {len(episodes)}",
        f"**Sources:** {sources_summary}",
        f"**Date range:** {date_range}",
        "",
        "---",
    ]

    if include_prompt:
        lines += [
            "",
            "## Suggested analysis prompt",
            "",
            PODCAST_ANALYSIS_PROMPT,
            "",
            "---",
        ]

    for i, (date_str, channel, source_label, f) in enumerate(episodes, start=1):
        lines += [
            "",
            f"## Episode {i} -- {channel} -- {date_str}",
            "",
            f.read_text(encoding="utf-8"),
            "",
            "---",
        ]

    content = "\n".join(lines)

    # Resolve output path
    if output is None:
        PODCAST_BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M")
        out_path = PODCAST_BUNDLES_DIR / f"bundle_{ts}.md"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        out_path = output

    out_path.write_text(content, encoding="utf-8")

    word_count = len(content.split())
    console.print(f"[bold green]Bundle written:[/] {out_path.resolve()}")
    console.print(f"  Episodes:   {len(episodes)}")
    console.print(f"  Word count: {word_count:,}")


def _morning_summary(
    console: Console,
    mode_label: str,
    step_results: list,
    tx_ok: bool,
    snapshot_ok: bool,
    tax_refreshed: bool,
    skip_tax: bool,
    start_time: float,
) -> None:
    elapsed = time.time() - start_time
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)
    elapsed_str = f"{h:02d}:{m:02d}:{s:02d}"

    icons = {"pass": "[bold green]OK[/]", "warn": "[bold yellow]WARN[/]", "fail": "[bold red]FAIL[/]", "skip": "[dim]SKIP[/dim]"}

    lines = [f"[bold]Mode:[/] {'[bold green]LIVE[/]' if mode_label == 'LIVE' else '[bold yellow]DRY RUN[/]'}"]
    lines.append("")
    lines.append("[bold]Steps:[/]")
    for name, status in step_results:
        lines.append(f"  {icons.get(status, '-')} {name}")
    lines.append("")
    lines.append(f"[bold]Snapshot written:[/]      {'[green]yes[/]' if snapshot_ok else '[red]no[/]'}")
    lines.append(f"[bold]Transactions synced:[/]   {'[green]yes[/]' if tx_ok else '[yellow]see above[/]'}")
    lines.append(f"[bold]Tax_Control refreshed:[/] {'[green]yes[/]' if tax_refreshed else ('[dim]skipped[/dim]' if skip_tax else '[yellow]no[/]')}")
    lines.append("")
    lines.append(f"[bold]Total elapsed:[/] {elapsed_str}")

    console.print()
    console.print(Panel("\n".join(lines), title="[bold]Morning Pipeline Summary[/]", border_style="cyan"))


@app.command("morning")
def morning(
    live: bool = typer.Option(False, "--live", help="Write to Google Sheets. Without this, runs as a dry-run preview."),
    skip_health: bool = typer.Option(False, "--skip-health", help="Skip the upfront health check (not recommended)."),
    skip_transactions: bool = typer.Option(False, "--skip-transactions", help="Skip transaction sync. Use if Schwab transaction endpoint is misbehaving."),
    skip_tax: bool = typer.Option(False, "--skip-tax", help="Skip the Tax_Control refresh."),
    tx_days: int = typer.Option(7, "--tx-days", help="Days of transactions to sync. Default 7 for daily run."),
    continue_on_warning: bool = typer.Option(True, "--continue-on-warning/--strict", help="Continue past health warnings. Use --strict to halt on any non-green check."),
):
    """Run the full market-open pipeline: health check -> Schwab sync -> snapshot -> dashboard refresh.

    Designed to be run once at market open. Default is dry-run; pass --live to write to the Sheet.
    """
    from tasks.health import run_all_checks, exit_code as health_exit_code, CRITICAL, FAIL, WARN, PASS
    from tasks.build_valuation_card import main as build_val
    from tasks.build_decision_view import main as build_dec
    from tasks.format_sheets_dashboard_v2 import main as format_v2
    from tasks.build_tax_control import refresh_tax_control_sheet
    from rich.text import Text
    import scripts.live_update as live_up
    import config as cfg

    start_time = time.time()
    mode_label = "LIVE" if live else "DRY RUN"
    step_results: list = []
    snapshot_ok = False
    tx_ok = False
    tax_refreshed = False

    MORNING_CRITICAL = {"schwab_token_accounts", "schwab_token_market", "schwab_api_positions", "sheet_reachable"}

    # ── STEP 0 - Health Check ─────────────────────────────────────────
    if not skip_health:
        console.print()
        console.print("[bold cyan]STEP 0 - Health Check[/]")
        with console.status("[cyan]Running health checks in parallel..."):
            health_results = run_all_checks()

        table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
        table.add_column("Check", style="cyan", no_wrap=True, min_width=30)
        table.add_column("Status", justify="center", no_wrap=True, min_width=6)
        table.add_column("Detail", style="white")
        for r in health_results:
            if r.status == PASS:
                status_cell = Text("✓", style="bold green")
            elif r.status == WARN:
                status_cell = Text("⚠", style="bold yellow")
            else:
                status_cell = Text("✗", style="bold red")
            level_marker = "" if r.level == CRITICAL else "[dim](W)[/dim] "
            detail_style = "red" if (r.status == FAIL and r.level == CRITICAL) else ("yellow" if r.status in (FAIL, WARN) else "white")
            table.add_row(
                f"{level_marker}[cyan]{r.name}[/cyan]",
                status_cell,
                f"[{detail_style}]{r.detail}[/{detail_style}]",
            )
        console.print(table)

        morning_critical_fails = [r for r in health_results if r.name in MORNING_CRITICAL and r.status == FAIL]
        h_code = health_exit_code(health_results)

        if morning_critical_fails or h_code == 1:
            console.print()
            console.print(Panel(
                "[bold red]Cannot proceed — Schwab or Sheet access broken. Run `pm health -v` for detail.[/]",
                style="red",
            ))
            step_results.append(("Health", "fail"))
            _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
            raise typer.Exit(code=1)

        if h_code == 2 and not continue_on_warning:
            console.print()
            console.print(Panel("[bold yellow]Health warnings detected — halting (--strict mode).[/]", style="yellow"))
            step_results.append(("Health", "warn"))
            _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
            raise typer.Exit(code=2)

        step_results.append(("Health", "warn" if h_code == 2 else "pass"))
    else:
        console.print("[dim]STEP 0 - Health Check skipped.[/]")
        step_results.append(("Health", "skip"))

    # ── STEP 1 - Transaction Sync ─────────────────────────────────────
    if not skip_transactions:
        console.print()
        console.print(f"[bold cyan]STEP 1 - Transaction Sync (last {tx_days} days)[/]")
        try:
            from tasks.sync_transactions import sync_transactions
            result = sync_transactions(days=tx_days, live=live, reconcile=False)
            if result is False:
                console.print("[yellow]Transaction sync returned failure — continuing.[/]")
                step_results.append(("Transactions", "warn"))
            else:
                tx_ok = True
                step_results.append(("Transactions", "pass"))
        except Exception as e:
            console.print(f"[yellow]Transaction sync raised exception: {e} — continuing.[/]")
            step_results.append(("Transactions", "warn"))
        if live:
            time.sleep(2)
    else:
        console.print("[dim]STEP 1 - Transaction Sync skipped.[/]")
        step_results.append(("Transactions", "skip"))

    # ── STEP 2 — Snapshot ─────────────────────────────────────────────
    console.print()
    console.print("[bold cyan]STEP 2 - Snapshot / Position Sync[/]")
    try:
        original_dry = cfg.DRY_RUN
        cfg.DRY_RUN = not live
        try:
            snap_result = live_up.update_portfolio(tx_days=tx_days)
        finally:
            cfg.DRY_RUN = original_dry

        if snap_result is False:
            console.print()
            console.print(Panel(
                "[bold red]Snapshot failed — cannot build dashboard from stale data. Aborting.[/]",
                style="red",
            ))
            step_results.append(("Snapshot", "fail"))
            _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
            raise typer.Exit(code=1)

        snapshot_ok = True
        step_results.append(("Snapshot", "pass"))

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Snapshot raised exception: {e}[/]")
        console.print(Panel(
            "[bold red]Snapshot failed — cannot build dashboard from stale data. Aborting.[/]",
            style="red",
        ))
        step_results.append(("Snapshot", "fail"))
        _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
        raise typer.Exit(code=1)

    if live:
        time.sleep(2)

    # ── STEP 3 - Dashboard Refresh ────────────────────────────────────
    console.print()
    console.print("[bold cyan]STEP 3 - Dashboard Refresh[/]")
    try:
        console.print("[cyan]  Building Valuation Card...[/]")
        build_val(live=live)
        if live:
            time.sleep(2)

        console.print("[cyan]  Building Decision View...[/]")
        build_dec(live=live)
        if live:
            time.sleep(2)

        if not skip_tax:
            console.print("[cyan]  Refreshing Tax Control...[/]")
            refresh_tax_control_sheet(live=live)
            tax_refreshed = True
            if live:
                time.sleep(2)
        else:
            console.print("[dim]  Tax Control refresh skipped.[/]")

        console.print("[cyan]  Applying V2 Formatting...[/]")
        format_v2(live=live)

        step_results.append(("Dashboard", "pass"))

    except Exception as e:
        console.print(f"[red]Dashboard refresh error: {e}[/]")
        step_results.append(("Dashboard", "fail"))

    # ── STEP 4 — Summary ──────────────────────────────────────────────
    _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)

    worst = "pass"
    for _, status in step_results:
        if status == "fail":
            worst = "fail"
            break
        if status == "warn":
            worst = "warn"

    if worst == "fail":
        raise typer.Exit(code=1)
    if worst == "warn":
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
