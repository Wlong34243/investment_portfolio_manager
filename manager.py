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
from datetime import datetime, date
from pathlib import Path

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
    #            Sell_Dates, Buy_Dates, Fingerprint
    # Trade_Log: Date, Sell_Ticker, Sell_Proceeds, Buy_Ticker, Buy_Amount,
    #            Implicit_Bet, Thesis_Brief, Rotation_Type, Trade_Log_ID, Fingerprint
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
            Path("bundles").glob("composite_bundle_*.json"),
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
            Path("bundles").glob("composite_bundle_*.json"),
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
    
    skip_style = "yellow" if bundle.vault_skip_log else "white"
    table.add_row("Skipped Files", f"[{skip_style}]{len(bundle.vault_skip_log)}[/]")
    
    table.add_row("Bundle Path", str(path))
    console.print(table)

    if bundle.vault_skip_log:
        console.print("\n[yellow]! Skipped files:[/]")
        for skip in bundle.vault_skip_log:
            console.print(f"  [yellow]•[/] {skip}")

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

        # Extract triggers YAML block
        trig_match = re.search(
            r"```yaml\s*\ntriggers:\s*\n(.*?)```",
            content,
            re.DOTALL,
        )
        if not trig_match:
            rows.append((ticker, style, 0, total_fields, "no_triggers_block"))
            continue

        try:
            trig_data = _yaml.safe_load("triggers:\n" + trig_match.group(1)) or {}
            triggers = trig_data.get("triggers", {}) or {}
        except Exception:
            rows.append((ticker, style, 0, total_fields, "parse_error"))
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
    
    missing_style = "yellow" if composite.theses_missing else "white"
    table.add_row("Theses Missing", f"[{missing_style}]{len(composite.theses_missing)}[/]")
    
    table.add_row("Bundle Path", str(path))
    console.print(table)

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
):
    """Sync Schwab transaction history to Google Sheets (merged archive-overwrite)."""
    from tasks.sync_transactions import sync_transactions
    success = sync_transactions(days=days, live=live, reconcile=reconcile)
    if not success:
        raise typer.Exit(code=1)


# --- DASHBOARD GROUP ---
dashboard_app = typer.Typer(help="Dashboard maintenance commands.")
app.add_typer(dashboard_app, name="dashboard")

@dashboard_app.command("refresh")
def dashboard_refresh(
    live: bool = typer.Option(False, "--live", help="Perform live update/formatting."),
    update: bool = typer.Option(False, "--update", help="Sync latest positions from Schwab before refreshing."),
    tx_days: int = typer.Option(90, "--tx-days", help="Days of transaction history to fetch with --update (use 365 for backfill)."),
):
    """Refreshes Valuation_Card, Decision_View, and all formatting."""
    from tasks.build_valuation_card import main as build_val
    from tasks.build_decision_view import main as build_dec
    from tasks.format_sheets_dashboard_v2 import main as format_v2

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
        
    console.print("\n[cyan]Step 3: Applying V2 Formatting...[/]")
    format_v2(live=live)
    
    console.print("\n[bold green]✅ Dashboard refresh complete.[/]")


if __name__ == "__main__":
    app()
