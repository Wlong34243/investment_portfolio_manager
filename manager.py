"""
Investment Portfolio Manager — CLI entry point.

Headless, auditable, linear execution. Every run freezes its inputs to
an immutable bundle and exits. No reruns, no state leakage, no hidden
caches.

Usage:
    python manager.py snapshot --csv path/to/positions.csv --cash 10000
    python manager.py snapshot --csv path/to/positions.csv --cash 10000 --live

Default is DRY RUN. --live is required for any downstream Sheet writes.
The snapshot subcommand itself never writes to Sheets — it only produces
the bundle. --live is plumbed through for future subcommands that do.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.bundle import build_bundle, write_bundle

app = typer.Typer(help="Investment Portfolio Manager CLI", no_args_is_help=True)
console = Console()


@app.command()
def snapshot(
    csv: Path = typer.Option(
        ...,
        "--csv",
        help="Path to Schwab positions CSV",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    cash: float = typer.Option(0.0, "--cash", help="Manual cash position (USD)"),
    live: bool = typer.Option(False, "--live", help="Enable live mode. Default is DRY RUN."),
):
    """Freeze current market state to an immutable context bundle."""

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
    with console.status("[cyan]Freezing market state..."):
        bundle = build_bundle(csv_path=csv, cash_manual=cash)
        path = write_bundle(bundle)

    # Summary table
    table = Table(title="Context Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("Timestamp (UTC)", bundle.timestamp_utc)
    table.add_row("Bundle Hash", f"[bold green]{bundle.bundle_hash}[/]")
    table.add_row("Positions", str(bundle.position_count))
    table.add_row("Total Value", f"${bundle.total_value:,.2f}")
    table.add_row("Cash (manual)", f"${bundle.cash_manual:,.2f}")
    table.add_row("Source CSV", str(csv.name))
    table.add_row("Source SHA256", bundle.source_csv_sha256[:16] + "...")
    table.add_row("Bundle Path", str(path))
    console.print(table)

    # Enrichment errors — visible, not silent
    if getattr(bundle, "enrichment_errors", None):
        console.print(f"\n[yellow]⚠ {len(bundle.enrichment_errors)} enrichment warning(s):[/]")
        for err in bundle.enrichment_errors[:10]:
            console.print(f"  [yellow]•[/] {err}")


if __name__ == "__main__":
    app()
