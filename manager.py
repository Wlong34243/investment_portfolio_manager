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
import subprocess
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

# Windows consoles default to cp1252; unencodable chars (arrows, emoji) must
# degrade to '?' rather than crash the command mid-output.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

import pandas as pd
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
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

# --- REFRESH GROUP (New) ---
refresh_app = typer.Typer(help="Unified command for rebuilding computed Sheet views.")
app.add_typer(refresh_app, name="refresh")

# --- CLEAN GROUP (New) ---
clean_app = typer.Typer(help="Unified command for filesystem hygiene.")
app.add_typer(clean_app, name="clean")

# --- INGEST GROUP (New) ---
ingest_app = typer.Typer(help="Unified data ingestion (transactions, realized-gl, podcasts).")
app.add_typer(ingest_app, name="ingest")

# --- CORE/LEGACY GROUPS (Many now aliased/hidden) ---
journal_app = typer.Typer(help="Journaling commands — record manual decisions.")
app.add_typer(journal_app, name="journal")

trade_app = typer.Typer(help="Trade log review and decision tuning. (Deprecated: use 'refresh rotations')")
app.add_typer(trade_app, name="trade", hidden=True)

vault_app = typer.Typer(help="Manage the vault bundle (thesis files, transcripts).")
app.add_typer(vault_app, name="vault")

bundle_app = typer.Typer(help="Build and inspect composite bundles.")
app.add_typer(bundle_app, name="bundle")

sync_app = typer.Typer(help="Sync data from external sources. (Deprecated: use 'ingest')")
app.add_typer(sync_app, name="sync", hidden=True)

tax_app = typer.Typer(help="Tax visibility and control. (Deprecated: use 'refresh tax')")
app.add_typer(tax_app, name="tax", hidden=True)

dashboard_app = typer.Typer(help="Dashboard maintenance commands. (Deprecated: use 'refresh dashboard')")
app.add_typer(dashboard_app, name="dashboard", hidden=True)

export_app = typer.Typer(help="Export context packages for frontier LLM analysis.")
app.add_typer(export_app, name="export")

podcast_app = typer.Typer(help="Podcast transcript collection and optional AI analysis.")
app.add_typer(podcast_app, name="podcast")

# --- AGENT GROUP ---
agent_app = typer.Typer(help="AI agents that consume the composite bundle and produce local output.")
app.add_typer(agent_app, name="agent")

# --- TOP LEVEL COMMANDS ---

@refresh_app.command("rotations")
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
    trade_log_rows = []
    for _, row in approved:
        trade_log_rows.append([
            _col(row, "Date"),
            _col(row, "Sell_Tickers"),
            _col(row, "Sell_Proceeds"),
            _col(row, "Buy_Tickers"),
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
            _col(row, "Stage_ID"),
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
    new_status_col = status_col_idx + 1
    with console.status("[cyan]Marking staging rows as 'promoted'..."):
        try:
            for sheet_row_num, _ in approved:
                staging_ws.update_cell(sheet_row_num, new_status_col, "promoted")
                time.sleep(0.3)
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
    
    if type not in ["dry_powder", "upgrade", "rebalance", "tax_loss"]:
        console.print(f"[red]ERROR: Invalid type: {type}. Must be dry_powder | upgrade | rebalance | tax_loss[/]")
        raise typer.Exit(code=1)

    trade_id = str(uuid.uuid4())
    today = datetime.now().strftime("%Y-%m-%d")
    proceeds_per_ticker = proceeds / len(sell_tickers)
    
    rows = []
    for ticker in sell_tickers:
        fingerprint = f"{today}|{ticker}|{bought}|{proceeds_per_ticker:.2f}"
        rows.append([
            today,
            ticker,
            round(proceeds_per_ticker, 2),
            bought.upper(),
            0.0,
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

    with console.status(f"[cyan]Writing to {config.TAB_TRADE_LOG}..."):
        try:
            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
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

def run_health_report(verbose: bool = False):
    """Execution logic for health checks, returns exit code."""
    from tasks.health import run_all_checks, exit_code, CRITICAL, WARNING, PASS, WARN, FAIL
    from rich.text import Text

    console.print()
    with console.status("[cyan]Running health checks in parallel…"):
        results = run_all_checks()

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
            status_cell = Text("PASS", style="bold green")
        elif r.status == WARN:
            status_cell = Text("WARN", style="bold yellow")
        else:
            status_cell = Text("FAIL", style="bold red")

        level_marker = "" if r.level == CRITICAL else "[dim](W)[/dim] "
        name_cell = f"{level_marker}[cyan]{r.name}[/cyan]"
        detail_style = "red" if (r.status == FAIL and r.level == CRITICAL) else ("yellow" if r.status in (FAIL, WARN) else "white")
        table.add_row(name_cell, status_cell, f"[{detail_style}]{r.detail}[/{detail_style}]")

    console.print(table)

    if verbose:
        console.print()
        console.rule("[dim]Verbose Detail[/dim]")
        for r in results:
            if r.verbose:
                console.print(f"[cyan]{r.name}[/cyan]")
                for line in r.verbose.splitlines():
                    console.print(f"  [dim]{line}[/dim]")

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
    return exit_code(results)


@app.command()
def health(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show expanded detail for each check."),
):
    """
    Run pipeline health checks — Schwab tokens, API connectivity, Sheet, bundle age,
    FMP cache coverage, yfinance, transactions freshness, thesis coverage.
    """
    code = run_health_report(verbose=verbose)
    raise typer.Exit(code=code)


@app.command()
def snapshot(
    source: str = typer.Option("auto", "--source"),
    csv: Path | None = typer.Option(None, "--csv", exists=True),
    cash: float = typer.Option(0.0, "--cash"),
    enrich_atr: bool = typer.Option(True, "--enrich-atr/--no-enrich-atr"),
    enrich_technicals: bool = typer.Option(True, "--enrich-technicals/--no-enrich-technicals"),
    enrich_fmp: bool = typer.Option(True, "--enrich-fmp/--no-enrich-fmp"),
    enrich_styles: bool = typer.Option(True, "--enrich-styles/--no-enrich-styles"),
    live: bool = typer.Option(False, "--live"),
):
    """Freeze current market state to an immutable context bundle."""
    if source == "csv" and csv is None:
        console.print("[red]ERROR: --source csv requires --csv PATH[/]")
        raise typer.Exit(code=1)

    if live:
        console.print(Panel.fit("[bold white on red] LIVE MODE — Sheet writes enabled [/]", border_style="red"))
    else:
        console.print(Panel.fit("[bold black on yellow] DRY RUN — No Sheet writes. [/]", border_style="yellow"))

    with console.status(f"[cyan]Freezing market state from {source}..."):
        try:
            bundle = build_bundle(source=source, csv_path=csv, cash_manual=cash)
            path = write_bundle(bundle)
        except Exception as e:
            console.print(f"[red]ERROR: Snapshot failed: {e}[/]")
            raise typer.Exit(code=1)

    table = Table(title="Context Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Timestamp (UTC)", bundle.timestamp_utc)
    table.add_row("Bundle Hash", f"[bold green]{bundle.bundle_hash}[/]")
    table.add_row("Data Source", bundle.data_source)
    table.add_row("Positions", str(bundle.position_count))
    table.add_row("Total Value", f"${bundle.total_value:,.2f}")
    table.add_row("Bundle Path", str(path))
    console.print(table)

    from tasks.enrich_fundamentals import enrich_bundle_fundamentals
    with console.status("[cyan]Enriching with fundamentals..."):
        try:
            enrich_bundle_fundamentals(path)
        except Exception as e:
            console.print(f"[red]Fundamental enrichment failed: {e}[/]")

    if enrich_styles:
        from tasks.enrich_styles import enrich_bundle_styles
        try:
            enrich_bundle_styles(path)
        except Exception as e:
            console.print(f"[red]Style enrichment failed: {e}[/]")

    if enrich_fmp:
        from tasks.enrich_fmp import enrich_bundle_fmp
        with console.status("[cyan]Enriching with FMP..."):
            try:
                enrich_bundle_fmp(path)
            except Exception as e:
                console.print(f"[red]FMP enrichment failed: {e}[/]")

    if live:
        bundle_push(path=path, live=True)


# --- VAULT GROUP ---

@vault_app.command("snapshot")
def vault_snapshot(
    drive: bool = typer.Option(False, "--drive"),
    live: bool = typer.Option(False, "--live"),
):
    """Freeze vault documents (theses, transcripts) to an immutable vault bundle."""
    tickers = None
    try:
        market_bundles = sorted(list(Path("bundles").glob("context_bundle_*.json")), key=lambda p: p.stat().st_mtime)
        if market_bundles:
            market_data = load_bundle(market_bundles[-1])
            tickers = [p["ticker"] for p in market_data["positions"] if not p.get("is_cash")]
    except: pass

    with console.status("[cyan]Freezing vault..."):
        bundle = build_vault_bundle(ticker_list=tickers, include_drive=drive)
        path = write_vault_bundle(bundle)

    table = Table(title="Vault Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Vault Hash", f"[bold green]{bundle.vault_hash}[/]")
    table.add_row("Vault Doc Count", str(bundle.vault_doc_count))
    table.add_row("Bundle Path", str(path))
    console.print(table)


@vault_app.command("sync")
def vault_sync(
    ticker: str = typer.Option(None, "--ticker"),
    live: bool = typer.Option(False, "--live"),
    force: bool = typer.Option(False, "--force"),
    show_diff: bool = typer.Option(False, "--show-diff")
):
    """Sync Sheets data into thesis files."""
    from core.thesis_sync_data import gather_thesis_sync_data
    from tasks.write_thesis_updates import write_thesis_updates

    with console.status("[cyan]Gathering sync data..."):
        tickers = [ticker.upper()] if ticker else None
        payloads = gather_thesis_sync_data(tickers=tickers)

    if not payloads:
        console.print("[yellow]No data found.[/]")
        return

    with console.status("[cyan]Updating thesis files..."):
        report = write_thesis_updates(payloads=payloads, dry_run=not live, force_recreate_regions=force, show_diff=show_diff)

    table = Table(title="Thesis Sync Report")
    table.add_column("Status", style="cyan")
    table.add_column("Count", style="white")
    table.add_row("Updated", str(report['updated']))
    table.add_row("Errors", str(report['errors']))
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
        if not path.exists(): continue
        try:
            content = path.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            last_reviewed = "N/A"
            if fm_match:
                fm_data = yaml.load(fm_match.group(1))
                last_reviewed = fm_data.get('last_reviewed', "N/A")
            weight = f"{payload.current_allocation_pct:,.2f}%" if payload.current_allocation_pct is not None else "N/A"
            ceiling = f"{payload.size_ceiling_pct:,.2f}%" if payload.size_ceiling_pct else "N/A"
            drift_val = (payload.current_allocation_pct or 0) - (payload.size_ceiling_pct or 0)
            drift_str = f"{drift_val:+.2f}%"
            status = "OK"
            if drift_val > 1.0: status = "[bold red]OVER[/]"
            elif drift_val < -5.0: status = "[yellow]UNDER[/]"
            table.add_row(ticker, str(last_reviewed), weight, ceiling, drift_str, status)
        except:
            table.add_row(ticker, "ERR", "ERR", "ERR", "ERR", "ERR")
    console.print(table)


@vault_app.command("add-thesis")
def vault_add_thesis(ticker: str = typer.Argument(...)):
    """Scaffold a new _thesis.md file."""
    target = THESES_DIR / f"{ticker.upper()}_thesis.md"
    if target.exists():
        console.print(f"[yellow]! Thesis for {ticker.upper()} already exists.[/]")
        raise typer.Exit()
    _today = datetime.now().strftime("%Y-%m-%d")
    template = f"---\nticker: {ticker.upper()}\nstyle: GARP\nentry_date: {_today}\nlast_reviewed: {_today}\n---\n\n# {ticker.upper()} — Thesis\n"
    THESES_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(template)
    console.print(f"Created {target}")


@vault_app.command("thesis-audit")
def vault_thesis_audit():
    """Report quantitative trigger completeness."""
    thesis_files = sorted(THESES_DIR.glob("*_thesis.md"))
    table = Table(title="Thesis Audit")
    table.add_column("Ticker")
    table.add_column("File Size")
    for tf in thesis_files:
        table.add_row(tf.stem, f"{tf.stat().st_size} bytes")
    console.print(table)


# --- BUNDLE GROUP ---

@bundle_app.command("composite")
def bundle_composite(
    market: Path | None = typer.Option(None, "--market"),
    vault: Path | None = typer.Option(None, "--vault"),
    live: bool = typer.Option(False, "--live"),
):
    """Combine latest market + vault bundles into a composite."""
    try:
        if market and vault: market_path, vault_path = market, vault
        else: market_path, vault_path = resolve_latest_bundles()
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(code=1)

    with console.status("[cyan]Building composite bundle..."):
        composite = build_composite_bundle(market_path, vault_path)
        path = write_composite_bundle(composite)

    table = Table(title="Composite Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Composite Hash", f"[bold green]{composite.composite_hash}[/]")
    table.add_row("Bundle Path", str(path))
    console.print(table)

@bundle_app.command("push")
def bundle_push(
    path: Optional[Path] = typer.Option(None, "--path"),
    live: bool = typer.Option(False, "--live"),
):
    """Push bundle data to Sheets."""
    import pipeline
    if path is None:
        candidates = sorted(Path("bundles").glob("context_bundle_*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates: raise typer.Exit(code=1)
        path = candidates[-1]

    data = load_bundle(path)
    df = pd.DataFrame(data.get("positions", []))
    if 'weight_pct' in df.columns:
        # core/bundle.py only ever populates weight_pct (from market_value /
        # total_value); some enrichment steps add a 'weight' key that defaults
        # to 0.0 and is never actually filled in. Always prefer weight_pct
        # here -- checking "weight not in df.columns" let a bogus all-zero
        # 'weight' column silently win whenever both keys were present.
        df['weight'] = df['weight_pct'] / 100.0
    if 'import_date' not in df.columns:
        df['import_date'] = data.get('timestamp_utc', '')[:10]
    pipeline.write_to_sheets(df, cash_amount=data.get('cash_manual', 0.0), dry_run=not live)
    console.print("[green]Done.[/]")


@bundle_app.command("verify")
def bundle_verify(path: Path = typer.Argument(...)):
    """Verify bundle hash."""
    with open(path, "r") as f: data = json.load(f)
    try:
        if "composite_hash" in data: load_composite_bundle(path)
        elif "vault_hash" in data: load_vault_bundle(path)
        else: load_bundle(path)
        console.print(f"[bold green]PASS[/] Hash verified.")
    except Exception as e:
        console.print(f"[red]FAIL: {e}[/]")
        raise typer.Exit(code=1)


# --- SYNC GROUP ---

@ingest_app.command("transactions")
@sync_app.command("transactions")
def sync_transactions_cmd(
    days: int = typer.Option(90, "--days"),
    live: bool = typer.Option(False, "--live"),
    reconcile: bool = typer.Option(False, "--reconcile"),
    clean: bool = typer.Option(False, "--clean"),
    purge: bool = typer.Option(False, "--purge"),
):
    """Sync Schwab transaction history."""
    if clean:
        from tasks.sync_transactions import clean_junk_tickers
        success = clean_junk_tickers(live=live)
    else:
        from tasks.sync_transactions import sync_transactions
        success = sync_transactions(days=days, live=live, reconcile=reconcile)
    
    if success and purge:
        from utils.hygiene import purge_obsolete_data, print_purge_report
        report = purge_obsolete_data(dry_run=not live)
        print_purge_report(report, dry_run=not live)


@ingest_app.command("realized-gl")
@sync_app.command("realized-gl")
def sync_realized_gl_cmd(
    csv_path: Path = typer.Argument(..., exists=True),
    live: bool = typer.Option(False, "--live"),
    purge: bool = typer.Option(False, "--purge"),
):
    """Import Realized G/L CSV."""
    from utils.gl_parser import parse_realized_gl
    from utils.sheet_readers import get_gspread_client
    import pipeline

    df = parse_realized_gl(csv_path)
    if df.empty: return
    df['import_date'] = str(date.today())
    data_list = pipeline.sanitize_dataframe_for_sheets(df, config.GL_COLUMNS, config.GL_COL_MAP)

    if live:
        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_REALIZED_GL)
        ws.append_rows(data_list, value_input_option="USER_ENTERED")
        console.print("[green]Imported lots.[/]")
    else:
        console.print(f"[yellow]DRY RUN: Would import {len(data_list)} lots.[/]")

    if purge:
        from utils.hygiene import purge_obsolete_data, print_purge_report
        report = purge_obsolete_data(dry_run=not live)
        print_purge_report(report, dry_run=not live)


@ingest_app.command("podcasts")
def ingest_podcasts_cmd(
    analyze: bool = typer.Option(False, "--analyze"),
    live: bool = typer.Option(False, "--live"),
    purge: bool = typer.Option(False, "--purge"),
):
    """Ingest podcast transcripts."""
    podcast_batch(analyze=analyze, live=live)
    if purge:
        from utils.hygiene import purge_obsolete_data, print_purge_report
        report = purge_obsolete_data(dry_run=not live)
        print_purge_report(report, dry_run=not live)


@ingest_app.command("all")
def ingest_all(
    live: bool = typer.Option(False, "--live"),
    days: int = typer.Option(90, "--days"),
    purge: bool = typer.Option(False, "--purge"),
):
    """Ingest Transactions + Podcasts."""
    sync_transactions_cmd(days=days, live=live)
    ingest_podcasts_cmd(live=live)
    if purge:
        from utils.hygiene import purge_obsolete_data, print_purge_report
        report = purge_obsolete_data(dry_run=not live)
        print_purge_report(report, dry_run=not live)


# --- TAX GROUP ---

@refresh_app.command("tax")
@tax_app.command("refresh")
def tax_refresh(live: bool = typer.Option(False, "--live")):
    """Refresh Tax_Control tab."""
    from tasks.build_tax_control import refresh_tax_control_sheet
    refresh_tax_control_sheet(live=live)
    console.print("[green]Tax refresh complete.[/]")


# --- DASHBOARD GROUP ---

@refresh_app.command("dashboard")
@dashboard_app.command("refresh")
def dashboard_refresh(
    live: bool = typer.Option(False, "--live"),
    update: bool = typer.Option(False, "--update"),
    tx_days: int = typer.Option(90, "--tx-days"),
):
    """Refreshes Dashboard views."""
    from tasks.build_valuation_card import main as build_val
    from tasks.build_decision_view import main as build_dec
    from tasks.build_command_center import main as build_cc
    from tasks.format_sheets_dashboard_v2 import main as format_v2
    import scripts.live_update as live_up

    if update: live_up.update_portfolio(tx_days=tx_days)
    build_val(live=live)
    build_dec(live=live)
    build_cc(live=live)
    format_v2(live=live)
    console.print("[green]Dashboard refresh complete (Valuation_Card, Decision_View, 0_DASHBOARD).[/]")


# --- EXPORT GROUP ---

@export_app.command("list")
def export_list():
    """List scenarios."""
    for s, d in config.EXPORT_SCENARIOS.items():
        console.print(f"  {s:15s} {d}")


@export_app.command("run")
def export_run(
    scenario: str = typer.Argument(..., help="Scenario name (see 'pm export list')"),
):
    """Build a context package for the given scenario and save to exports/."""
    if scenario not in config.EXPORT_SCENARIOS:
        console.print(f"[red]Unknown scenario '{scenario}'. Run 'pm export list' to see options.[/]")
        raise typer.Exit(1)

    if scenario == "tax-rebalance":
        _export_tax_rebalance()
    else:
        console.print(f"[yellow]Scenario '{scenario}' is listed but not yet implemented.[/]")
        raise typer.Exit(1)


def _export_tax_rebalance():
    """Build a tax-rebalance context package from live Sheet data."""
    import pandas as pd
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme,
        write_context_json, write_prompt_markdown,
    )
    from utils.sheet_readers import get_gspread_client, read_gsheet_robust

    with console.status("[cyan]Reading Sheet data..."):
        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)

        # Tax_Control KPI strip (row 2 = labels, row 3 = values)
        tax_raw = ss.worksheet(config.TAB_TAX_CONTROL).get_all_values()
        tax_kpis = {}
        if len(tax_raw) >= 3:
            labels = tax_raw[1]
            values = tax_raw[2]
            for i, label in enumerate(labels):
                if label and i < len(values):
                    tax_kpis[label] = values[i]

        # Holdings — unrealized positions for TLH candidates
        df_h = read_gsheet_robust(ss.worksheet(config.TAB_HOLDINGS_CURRENT))
        df_h["Market Value"] = pd.to_numeric(df_h.get("Market Value", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df_h["Unrealized G/L"] = pd.to_numeric(df_h.get("Unrealized G/L", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df_h["Unrealized G/L %"] = pd.to_numeric(df_h.get("Unrealized G/L %", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df_h["Weight"] = pd.to_numeric(df_h.get("Weight", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df_h = df_h[~df_h["Ticker"].astype(str).isin(config.CASH_TICKERS)]

        # Normalize weight to percentage if stored as decimal
        if df_h["Weight"].max() <= 1.5:
            df_h["Weight"] = df_h["Weight"] * 100

        tlh_candidates = df_h[df_h["Unrealized G/L"] < config.TLH_LOSS_THRESHOLD_USD].sort_values("Unrealized G/L")
        gains_at_risk = df_h[df_h["Unrealized G/L"] > 0].sort_values("Unrealized G/L", ascending=False).head(15)

        # Realized G/L — wash sale lots + recent lots
        try:
            df_gl = read_gsheet_robust(ss.worksheet(config.TAB_REALIZED_GL))
            df_gl["Gain Loss $"] = pd.to_numeric(df_gl.get("Gain Loss $", pd.Series(dtype=float)), errors="coerce").fillna(0)
            wash_lots = df_gl[df_gl.get("Wash Sale", pd.Series(dtype=str)).astype(str).str.upper() == "TRUE"]
        except Exception:
            df_gl = pd.DataFrame()
            wash_lots = pd.DataFrame()

    # Build context dict
    context = {
        "generated_at": datetime.now().isoformat(),
        "tax_posture_ytd": tax_kpis,
        "tlh_candidates": tlh_candidates[["Ticker", "Market Value", "Unrealized G/L", "Unrealized G/L %", "Weight"]].to_dict("records"),
        "largest_unrealized_gains": gains_at_risk[["Ticker", "Market Value", "Unrealized G/L", "Unrealized G/L %", "Weight"]].to_dict("records"),
        "wash_sale_lots": wash_lots[["Ticker", "Closed Date", "Gain Loss $", "Disallowed Loss"]].to_dict("records") if not wash_lots.empty else [],
        "tlh_threshold_usd": config.TLH_LOSS_THRESHOLD_USD,
    }

    prompt = f"""# Tax-Rebalance Analysis — {datetime.now().strftime("%Y-%m-%d")}

You are a tax-efficient portfolio advisor. The attached context.json contains:
- YTD realized gain/loss posture (Net ST, Net LT, wash sale count, estimated tax liability)
- Tax-loss harvesting (TLH) candidates: unrealized losses exceeding ${abs(config.TLH_LOSS_THRESHOLD_USD):,.0f}
- Largest unrealized gains at risk of triggering a tax event
- Active wash sale lots requiring 30-day replacement discipline

## Instructions

1. **Posture Assessment** — Summarize the current YTD tax position. Is the portfolio net-positive (tax bill likely) or net-negative (harvesting capacity)?

2. **TLH Recommendations** — For each TLH candidate, recommend whether to harvest, hold, or wait. Flag any 30-day wash sale window risks from recent realized lots in the same ticker.

3. **Gains Protection** — For the top unrealized gainers, flag which have held long-term (>1 year) vs. short-term. Note which are approaching a calendar-year trigger.

4. **Rebalance Pairing** — Suggest any loss-harvest / replacement-buy pairs that reduce concentration risk while respecting wash sale rules.

5. **Priority Action List** — Rank the top 3 actions by tax impact. Be specific: ticker, action, rationale.

## Context

See attached context.json.
"""

    with console.status("[cyan]Writing package..."):
        pkg_dir = create_package_dir("tax-rebalance")
        write_context_json(pkg_dir, context)
        write_prompt_markdown(pkg_dir, prompt)
        write_manifest(pkg_dir, "tax-rebalance", "n/a", "1.0.0", {
            "tlh_candidates": len(context["tlh_candidates"]),
            "wash_lots": len(context["wash_sale_lots"]),
        })
        write_readme(pkg_dir, "tax-rebalance",
            "YTD tax posture, TLH candidates, and gain/loss pairing analysis.",
            "Paste prompt.md into your LLM, then attach or paste context.json.")

    console.print(f"[green]Package ready:[/] {pkg_dir}")
    console.print(f"  TLH candidates : {len(context['tlh_candidates'])}")
    console.print(f"  Unrealized gains: {len(context['largest_unrealized_gains'])}")
    console.print(f"  Wash sale lots : {len(context['wash_sale_lots'])}")
    console.print(f"\nNext: paste [bold]prompt.md[/] into your LLM, attach [bold]context.json[/].")


@clean_app.command("exports")
@export_app.command("cleanup")
def export_cleanup(
    days: int = typer.Option(config.PURGE_DEFAULT_DAYS_EXPORTS, "--days"),
    live: bool = typer.Option(False, "--live"),
):
    """Clean old exports."""
    from utils.hygiene import purge_obsolete_data, print_purge_report
    report = purge_obsolete_data(days_exports=days, dry_run=not live)
    print_purge_report({"exports": report["exports"]}, dry_run=not live)

@clean_app.command("podcasts")
@podcast_app.command("clean")
def podcast_clean(
    days: int = typer.Option(config.PURGE_DEFAULT_DAYS_PODCASTS, "--days"),
    live: bool = typer.Option(False, "--live"),
):
    """Clean old podcasts."""
    from utils.hygiene import purge_obsolete_data, print_purge_report
    report = purge_obsolete_data(days_podcasts=days, dry_run=not live)
    print_purge_report({"podcasts": report["podcasts"]}, dry_run=not live)

@clean_app.command("bundles")
def clean_bundles(
    days: int = typer.Option(config.PURGE_DEFAULT_DAYS_BUNDLES, "--days"),
    live: bool = typer.Option(False, "--live"),
):
    """Clean old bundles."""
    from utils.hygiene import purge_obsolete_data, print_purge_report
    report = purge_obsolete_data(days_bundles=days, dry_run=not live)
    print_purge_report({"bundles": report["bundles"]}, dry_run=not live)

@clean_app.command("all")
def clean_all(live: bool = typer.Option(False, "--live")):
    """Clean everything."""
    from utils.hygiene import purge_obsolete_data, print_purge_report
    report = purge_obsolete_data(dry_run=not live)
    print_purge_report(report, dry_run=not live)


@export_app.command("inspect")
def export_inspect(path: Path = typer.Argument(...)):
    """Inspect package."""
    console.print(f"Inspecting {path}")

@podcast_app.command("fetch")
def podcast_fetch(video_id: str = typer.Argument(...), source_name: str = "Manual"):
    """Fetch transcript."""
    from tasks.podcast_fetcher import fetch_transcript_to_file
    fetch_transcript_to_file(video_id, source_name=source_name)
    console.print("[green]Done.[/]")


@podcast_app.command("batch")
def podcast_batch(
    analyze: bool = typer.Option(False, "--analyze", help="Run Gemini macro analysis after fetching."),
    live: bool = typer.Option(False, "--live", help="Save dedup log and run Sheet writes. Default: DRY RUN."),
):
    """Fetch latest episode transcripts for all tracked podcast channels."""
    from tasks.batch_podcast_sync import (
        get_latest_video, load_processed_videos, save_processed_videos,
        PODCAST_CHANNELS,
    )
    from tasks.podcast_fetcher import fetch_transcript_to_file

    mode = "LIVE" if live else "DRY RUN"
    console.print(f"[bold cyan]Batch Podcast Sync — {mode}[/]")

    processed = load_processed_videos()
    counts = {"fetched": 0, "skipped": 0, "failed": 0}

    for channel_name, cfg in PODCAST_CHANNELS.items():
        channel_id = cfg["channel_id"]
        title_filter = cfg.get("title_filter")
        console.print(f"\nChecking [cyan]{channel_name}[/]...")
        video_id, title = get_latest_video(channel_id, title_filter=title_filter)

        if video_id is None:
            console.print(f"  [red]Could not fetch latest video[/]")
            counts["failed"] += 1
            continue

        console.print(f"  Latest: [dim]{title}[/] ({video_id})")

        if video_id in processed:
            console.print(f"  [yellow]SKIP[/] — already processed on {processed[video_id]['processed_at'][:10]}")
            counts["skipped"] += 1
            continue

        try:
            save_path = fetch_transcript_to_file(video_id, source_name=f"{channel_name}: {title}")
            word_count = len(save_path.read_text(encoding="utf-8").split())
            console.print(f"  [green]Fetched[/] {word_count:,} words -> {save_path.name}")
            processed[video_id] = {
                "channel": channel_name,
                "title": title,
                "processed_at": datetime.now().isoformat(),
            }
            counts["fetched"] += 1
        except Exception as e:
            console.print(f"  [red]FAILED:[/] {e}")
            counts["failed"] += 1
            continue

        if analyze:
            try:
                from utils.agents.podcast_analyst import analyze_podcast
                text = save_path.read_text(encoding="utf-8")
                result = analyze_podcast(text, source_name=f"{channel_name}: {title}")
                if result:
                    console.print(f"  [dim]Analysis: {result.get('executive_summary', '')[:80]}[/]")
            except Exception as e:
                console.print(f"  [yellow]Analysis failed:[/] {e}")

    if live:
        save_processed_videos(processed)
        console.print("\n[dim]Dedup log saved.[/]")
    else:
        console.print("\n[bold yellow]DRY RUN — dedup log not saved. Use --live to persist.[/]")

    console.print(
        f"\n[bold]Done:[/] {counts['fetched']} fetched, "
        f"{counts['skipped']} skipped, {counts['failed']} failed"
    )


@podcast_app.command("bundle")
def podcast_bundle(last_n: int = typer.Option(10, "--last-n", help="Number of most recent transcripts to include")):
    """Concatenate the N most recent transcripts into a single Markdown file for LLM use."""
    from tasks.podcast_fetcher import TRANSCRIPTS_DIR
    from datetime import datetime as _dt

    transcript_files = sorted(TRANSCRIPTS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    selected = transcript_files[:last_n]

    if not selected:
        console.print("[red]No transcripts found. Run 'pm podcast fetch' or 'pm podcast batch' first.[/]")
        raise typer.Exit(1)

    bundle_dir = Path("data/podcast_bundles")
    bundle_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.now().strftime("%Y-%m-%d_%H%M")
    out_path = bundle_dir / f"bundle_{ts}.md"

    lines = [f"# Podcast Bundle — {ts}", f"_Includes {len(selected)} transcript(s)_", ""]
    for tf in reversed(selected):  # chronological order
        lines += [f"---", f"## {tf.stem}", ""]
        lines.append(tf.read_text(encoding="utf-8"))
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    size_kb = out_path.stat().st_size // 1024
    console.print(f"[green]Bundle written:[/] {out_path}  ({size_kb} KB, {len(selected)} transcripts)")


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
    skip_transactions: bool = typer.Option(False, "--skip-transactions", help="Skip transaction sync."),
    skip_podcasts: bool = typer.Option(False, "--skip-podcasts", help="Skip the podcast batch sync step."),
    skip_tax: bool = typer.Option(False, "--skip-tax", help="Skip the Tax_Control refresh."),
    tx_days: int = typer.Option(7, "--tx-days", help="Days of transactions to sync. Default 7."),
    continue_on_warning: bool = typer.Option(True, "--continue-on-warning/--strict", help="Continue past health warnings."),
    skip_vault_sync: bool = typer.Option(False, "--skip-vault-sync", help="Skip vault sync to markdown theses."),
    skip_composite: bool = typer.Option(False, "--skip-composite", help="Skip building composite bundle."),
):
    """
    Run the full market-open pipeline: health -> Schwab sync -> snapshot -> podcast sync -> dashboard refresh -> vault sync -> composite bundle.
    """
    from tasks.health import run_all_checks, exit_code as health_exit_code, CRITICAL, FAIL, WARN, PASS
    from tasks.build_valuation_card import main as build_val
    from tasks.build_decision_view import main as build_dec
    from tasks.build_command_center import main as build_cc
    from tasks.format_sheets_dashboard_v2 import main as format_v2
    from tasks.build_tax_control import refresh_tax_control_sheet
    import scripts.live_update as live_up
    
    start_time = time.time()
    mode_label = "LIVE" if live else "DRY RUN"
    step_results = []
    snapshot_ok = False
    tx_ok = False
    tax_refreshed = False

    # 1. Health Check
    if not skip_health:
        console.print("\n[bold cyan]STEP 0 - Health Check[/]")
        code = run_health_report()
        
        # Determine worst status from the report
        if code == 1:
            step_results.append(("Health", "fail"))
            console.print(Panel("[bold red]Cannot proceed — Critical health failures detected.[/]", style="red"))
            from rich.prompt import Confirm
            if Confirm.ask("Would you like to run the Schwab reauthentication script now?"):
                subprocess.run([sys.executable, "scripts/schwab_manual_reauth.py"])
                console.print("[yellow]Reauthentication complete. Please run `pm morning` again.[/]")
            _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
            raise typer.Exit(code=1)
        elif code == 2:
            step_results.append(("Health", "warn"))
            if not continue_on_warning:
                console.print(Panel("[bold yellow]Health warnings detected — halting (--strict mode).[/]", style="yellow"))
                _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
                raise typer.Exit(code=2)
        else:
            step_results.append(("Health", "pass"))
    else:
        step_results.append(("Health", "skip"))

    # 2. Sync Transactions & Positions (Writes to Sheets)
    if not skip_transactions:
        console.print("\n[bold cyan]STEP 1 - Syncing Schwab Transactions & Positions...[/]")
        try:
            from tasks.sync_transactions import sync_transactions
            success = sync_transactions(days=tx_days, live=live)
            if success:
                tx_ok = True
                step_results.append(("Transactions", "pass"))
            else:
                step_results.append(("Transactions", "warn"))
        except Exception as e:
            console.print(f"[yellow]Transaction sync failed: {e}[/]")
            step_results.append(("Transactions", "fail"))
    else:
        step_results.append(("Transactions", "skip"))

    # 3. Live Update (Fetches fresh prices and writes to Sheets if live)
    console.print("\n[bold cyan]STEP 2 - Updating Portfolio State...[/]")
    try:
        live_up.update_portfolio(tx_days=tx_days, dry_run=not live)
        step_results.append(("Live Update", "pass"))
    except Exception as e:
        console.print(f"[red]Portfolio update failed: {e}[/]")
        step_results.append(("Live Update", "fail"))

    # 4. Snapshot (Freeze Sheets state to Bundle)
    console.print("\n[bold cyan]STEP 3 - Freezing Context Bundle...[/]")
    try:
        bundle = build_bundle(source="auto", cash_manual=0.0)
        path = write_bundle(bundle)
        console.print(f"[green]Snapshot frozen:[/] {path.name} ({bundle.bundle_hash[:8]})")
        snapshot_ok = True
        step_results.append(("Snapshot", "pass"))
    except Exception as e:
        console.print(f"[red]Snapshot failed: {e}[/]")
        step_results.append(("Snapshot", "fail"))

    # 5. Batch Podcast Sync (non-fatal; always continues regardless of result or --strict)
    #    batch_podcast_sync.main() uses argparse so we can't call it in-process cleanly;
    #    we shell out via subprocess — the same decoupled pattern the batch script uses
    #    when it shells out to weekly_podcast_sync.py.
    if not skip_podcasts:
        console.print("\n[bold cyan]STEP 4 - Batch Podcast Sync...[/]")
        try:
            script_path = Path(__file__).parent / "tasks" / "batch_podcast_sync.py"
            cmd = [sys.executable, str(script_path)]
            if live:
                cmd.append("--live")
            # 600s, not 180s: each new episode found costs a transcript
            # download + a Gemini call over the full transcript, sequentially,
            # on top of up to 10 RSS checks -- a morning with several new
            # episodes queued across channels routinely exceeded 180s.
            pod_result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            # Logger writes to stderr; parse summary lines from there
            output = pod_result.stderr
            n_processed = 0
            n_failed = 0
            pm = re.search(r"Processed: \[(.+?)\]", output)
            if pm:
                n_processed = len([x for x in pm.group(1).split(",") if x.strip()])
            fm = re.search(r"Failed: \[(.+?)\]", output)
            if fm:
                n_failed = len([x for x in fm.group(1).split(",") if x.strip()])

            for line in output.strip().splitlines()[-6:]:
                if line.strip():
                    console.print(f"  [dim]{line}[/dim]")

            label = f"Podcasts ({n_processed} new)" if n_processed else "Podcasts"
            if n_failed > 0:
                console.print(f"  [yellow]! {n_failed} channel(s) failed to fetch[/]")
                step_results.append((label, "warn"))
            else:
                step_results.append((label, "pass"))
        except Exception as e:
            console.print(f"[yellow]Podcast sync error: {e}[/]")
            step_results.append(("Podcasts", "warn"))
    else:
        step_results.append(("Podcasts", "skip"))

    # 6. Refresh Dashboard (Rebuild Views from Bundle)
    console.print("\n[bold cyan]STEP 5 - Refreshing Dashboard...[/]")
    try:
        build_val(live=live, include_all=True)
        build_dec(live=live)
        if not skip_tax:
            refresh_tax_control_sheet(live=live)
            tax_refreshed = True
        build_cc(live=live)
        format_v2(live=live)
        step_results.append(("Dashboard", "pass"))
    except Exception as e:
        console.print(f"[red]Dashboard refresh failed: {e}[/]")
        step_results.append(("Dashboard", "fail"))

    # 7. Vault Sync (sync Sheets data back to local thesis files)
    if not skip_vault_sync:
        console.print("\n[bold cyan]STEP 6 - Syncing Sheets to Local Thesis Files...[/]")
        try:
            from core.thesis_sync_data import gather_thesis_sync_data
            from tasks.write_thesis_updates import write_thesis_updates
            
            payloads = gather_thesis_sync_data()
            if payloads:
                report = write_thesis_updates(payloads=payloads, dry_run=not live, force_recreate_regions=False, show_diff=False)
                if report.get('errors', 0) > 0:
                    console.print(f"[yellow]Vault sync completed with {report['errors']} errors.[/]")
                    step_results.append(("Vault Sync", "warn"))
                else:
                    console.print(f"[green]Vault sync completed successfully. Updated {report['updated']} file(s).[/]")
                    step_results.append(("Vault Sync", "pass"))
            else:
                console.print("[yellow]No vault sync data found.[/]")
                step_results.append(("Vault Sync", "pass"))
        except Exception as e:
            console.print(f"[red]Vault sync failed: {e}[/]")
            step_results.append(("Vault Sync", "fail"))
    else:
        step_results.append(("Vault Sync", "skip"))

    # 8. Vault Snapshot (rebuild local vault bundle)
    if not skip_composite:
        console.print("\n[bold cyan]STEP 7 - Freezing Vault Snapshot...[/]")
        try:
            tickers = None
            try:
                if 'bundle' in locals() and bundle:
                    tickers = [p["ticker"] for p in bundle.positions if not p.get("is_cash")]
                else:
                    market_bundles = sorted(list(Path("bundles").glob("context_bundle_*.json")), key=lambda p: p.stat().st_mtime)
                    if market_bundles:
                        market_data = load_bundle(market_bundles[-1])
                        tickers = [p["ticker"] for p in market_data["positions"] if not p.get("is_cash")]
            except Exception as e:
                console.print(f"[dim]Failed to resolve tickers for vault snapshot: {e}[/dim]")

            vault_bundle = build_vault_bundle(ticker_list=tickers, include_drive=False)
            vault_path = write_vault_bundle(vault_bundle)
            console.print(f"[green]Vault snapshot frozen:[/] {vault_path.name} ({vault_bundle.vault_hash[:8]})")
            step_results.append(("Vault Snapshot", "pass"))
        except Exception as e:
            console.print(f"[red]Vault snapshot failed: {e}[/]")
            step_results.append(("Vault Snapshot", "fail"))
    else:
        step_results.append(("Vault Snapshot", "skip"))

    # 9. Build Composite Bundle
    if not skip_composite:
        console.print("\n[bold cyan]STEP 8 - Building Composite Bundle...[/]")
        try:
            market_path = None
            if 'path' in locals() and path:
                market_path = path
            
            vault_path_resolved = None
            if 'vault_path' in locals() and vault_path:
                vault_path_resolved = vault_path
            else:
                vault_bundles = sorted(list(Path("bundles").glob("vault_bundle_*.json")), key=lambda p: p.stat().st_mtime)
                if vault_bundles:
                    vault_path_resolved = vault_bundles[-1]

            if not market_path or not vault_path_resolved:
                market_path, vault_path_resolved = resolve_latest_bundles()

            composite = build_composite_bundle(market_path, vault_path_resolved)
            comp_path = write_composite_bundle(composite)
            console.print(f"[green]Composite bundle built:[/] {comp_path.name} ({composite.composite_hash[:8]})")
            step_results.append(("Composite Bundle", "pass"))
        except Exception as e:
            console.print(f"[red]Composite bundle failed: {e}[/]")
            step_results.append(("Composite Bundle", "fail"))
    else:
        step_results.append(("Composite Bundle", "skip"))

    _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)

    # Exit with code based on worst step
    worst = "pass"
    for _, status in step_results:
        if status == "fail": worst = "fail"
        elif status == "warn" and worst != "fail": worst = "warn"
    
    if worst == "fail": raise typer.Exit(code=1)
    if worst == "warn": raise typer.Exit(code=2)
    raise typer.Exit(code=0)


@app.command("login")
def login():
    """
    Run the Schwab OAuth manual reauthentication script to update credentials.
    """
    from scripts.schwab_manual_reauth import run_reauth
    run_reauth()


@app.command("backup")
def backup(
    name: Optional[str] = typer.Option(None, help="Name of the zip file in Drive."),
    folder_id: Optional[str] = typer.Option(None, help="ID of the Drive folder to upload to.")
):
    """
    Archive the project (excluding credentials/venv/caches) and upload to Google Drive.
    """
    from scripts.backup_to_drive import backup as run_backup
    run_backup(name=name, folder_id=folder_id)


# --- AGENT GROUP ---

@agent_app.command("ideas")
def agent_ideas(
    since_days: int = typer.Option(7, "--since-days", help="Look back N days for transcripts."),
    bundle_path: Optional[Path] = typer.Option(None, "--bundle-path", help="Path to composite bundle. Auto-detects latest if omitted."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print report to stdout instead of writing to disk."),
    skip_ingest: bool = typer.Option(False, "--skip-ingest", help="Skip podcast ingestion and use transcripts already on disk."),
):
    """
    Generate investment candidates from recent podcast transcripts.

    Fetches new podcast transcripts first, then runs the idea generator.
    Consumes the composite bundle + data/podcast_transcripts/ and writes a markdown
    report to agent_outputs/ideas/. Use --dry-run to print to stdout.
    """
    import time as _time
    from utils.agents.idea_generator import run_idea_generator, write_idea_report

    if not skip_ingest:
        console.print("[bold cyan]Step 1/2 — Ingesting new podcast transcripts...[/]")
        try:
            podcast_batch(analyze=False, live=True)
        except Exception as e:
            console.print(f"[yellow]Podcast ingestion failed: {e} — continuing with existing transcripts.[/]")
        console.print()

    console.print("[bold cyan]Step 2/2 — Running idea generator...[/]" if not skip_ingest else "[bold cyan]Running idea generator...[/]")

    bundle_path_str = str(bundle_path) if bundle_path else None

    with console.status("[cyan]Running idea generator..."):
        t0 = _time.time()
        try:
            output = run_idea_generator(
                composite_bundle_path=bundle_path_str,
                since_days=since_days,
            )
        except FileNotFoundError as e:
            console.print(f"[red]ERROR: {e}[/]")
            raise typer.Exit(code=1)
        elapsed = _time.time() - t0

    if dry_run:
        report_text = write_idea_report(output, dry_run=True)
        console.print(report_text)
        console.print(f"\n[dim]Generated in {elapsed:.1f}s | {len(output.candidates)} candidate(s) | {len(output.transcripts_analyzed)} transcript(s)[/]")
        return

    report_path = write_idea_report(output)
    console.print(f"\n[bold green]Report written:[/] {report_path}")
    console.print(
        f"[cyan]{len(output.candidates)} candidate(s)[/] across "
        f"[cyan]{len(output.transcripts_analyzed)} transcript(s)[/] "
        f"in {elapsed:.1f}s"
    )
    if output.notes:
        console.print(f"[dim]Notes: {output.notes[:120]}{'...' if len(output.notes) > 120 else ''}[/]")


if __name__ == "__main__":
    app()
