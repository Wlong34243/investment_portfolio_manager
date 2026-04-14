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
from agents.rebuy_analyst import app as rebuy_app
from agents.add_candidate_analyst import app as add_candidate_app
from agents.new_idea_screener import app as new_idea_app
from agents.tax_agent import app as tax_app
from agents.valuation_agent import app as valuation_app
from agents.concentration_hedger import app as concentration_app
from agents.macro_cycle_agent import app as macro_app
from agents.thesis_screener import app as thesis_app
from agents.bagger_screener import app as bagger_app

app = typer.Typer(help="Investment Portfolio Manager CLI", no_args_is_help=True)
console = Console()

# --- AGENT GROUP ---
agent_app = typer.Typer(help="AI agents — run over composite bundles.")
app.add_typer(agent_app, name="agent")
agent_app.add_typer(rebuy_app, name="rebuy")
agent_app.add_typer(add_candidate_app, name="add-candidate")
agent_app.add_typer(new_idea_app, name="new-idea")
agent_app.add_typer(tax_app, name="tax")
agent_app.add_typer(valuation_app, name="valuation")
agent_app.add_typer(concentration_app, name="concentration")
agent_app.add_typer(macro_app, name="macro")
agent_app.add_typer(thesis_app, name="thesis")
agent_app.add_typer(bagger_app, name="bagger")
# Usage: python manager.py agent rebuy analyze --bundle latest
# Usage: python manager.py agent tax analyze --bundle latest
# Usage: python manager.py agent valuation analyze --bundle latest
# Usage: python manager.py agent concentration analyze --bundle latest
# Usage: python manager.py agent macro analyze --bundle latest
# Usage: python manager.py agent thesis analyze --bundle latest
# Usage: python manager.py agent bagger analyze --bundle latest


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
        False, "--enrich-atr",
        help="After building the snapshot, find the latest composite bundle and inject ATR stops. "
             "Requires a composite bundle to already exist (run 'manager.py bundle composite' first).",
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

    # Enrichment errors — visible, not silent
    if getattr(bundle, "enrichment_errors", None):
        console.print(f"\n[yellow]⚠ {len(bundle.enrichment_errors)} enrichment warning(s):[/]")
        for err in bundle.enrichment_errors[:10]:
            console.print(f"  [yellow]•[/] {err}")

    # ATR enrichment — optional post-snapshot step
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

    template = f"""# {ticker.upper()} - Investment Thesis

## Style
[Growth | Value | Dividend | Speculative]

## Scaling State
next_step: [accumulate | hold | trim | exit]

## Rotation Priority
priority: [high | medium | low]

## Core Thesis
... why do we own this? ...

## Risks to Watch
... what would make us sell? ...
"""
    THESES_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(template)
    console.print(f"Created {target} — fill in the sections.")


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


@app.command("analyze-all")
def analyze_all(
    fresh_bundle: bool = typer.Option(
        False, "--fresh-bundle",
        help="Regenerate market + vault + composite bundles before running agents.",
    ),
    agents: str = typer.Option(
        "rebuy,tax,valuation,concentration,macro,thesis,bagger",
        "--agents",
        help="Comma-separated list of agents to run. Default: all.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write all agent outputs to Agent_Outputs in a single batch. Default: dry run.",
    ),
):
    """
    Run all portfolio agents in sequence and write outputs in one batch transaction.

    Agent execution is fault-tolerant — one agent failure does not abort the others.
    Rebuy agent is included in the manifest but uses a legacy write schema (not in
    the standard Agent_Outputs batch write).

    Run manifest is always written to bundles/runs/ regardless of --live.
    """
    from agents.analyze_all import run_analyze_all
    run_analyze_all(agents_str=agents, fresh_bundle=fresh_bundle, live=live)


if __name__ == "__main__":
    app()
