"""
Hygiene & Cleanup Utilities
Shared logic for maintaining a clean filesystem.
"""

import os
import time
import logging
from pathlib import Path
from rich.console import Console

import config

console = Console()

def purge_obsolete_data(
    days_podcasts: int = config.PURGE_DEFAULT_DAYS_PODCASTS,
    days_bundles: int = config.PURGE_DEFAULT_DAYS_BUNDLES,
    days_exports: int = config.PURGE_DEFAULT_DAYS_EXPORTS,
    dry_run: bool = True
) -> dict:
    """
    Unified implementation for deleting old files across exports, podcasts, and bundles.
    """
    report = {
        "exports": {"deleted": 0, "bytes": 0},
        "podcasts": {"deleted": 0, "bytes": 0},
        "bundles": {"deleted": 0, "bytes": 0},
    }

    now = time.time()
    mode = "DRY RUN" if dry_run else "LIVE"
    
    # 1. Exports
    if config.EXPORTS_DIR.exists():
        cutoff = now - (days_exports * 86400)
        # Exports are directories (packages)
        for pkg in config.EXPORTS_DIR.iterdir():
            if pkg.is_dir() and pkg.stat().st_mtime < cutoff:
                size = sum(f.stat().st_size for f in pkg.rglob('*') if f.is_file())
                report["exports"]["deleted"] += 1
                report["exports"]["bytes"] += size
                if not dry_run:
                    import shutil
                    shutil.rmtree(pkg)
                    
    # 2. Podcasts (Transcripts)
    from tasks.podcast_fetcher import TRANSCRIPTS_DIR
    if TRANSCRIPTS_DIR.exists():
        cutoff = now - (days_podcasts * 86400)
        for f in TRANSCRIPTS_DIR.glob("*.txt"):
            if f.stat().st_mtime < cutoff:
                report["podcasts"]["deleted"] += 1
                report["podcasts"]["bytes"] += f.stat().st_size
                if not dry_run:
                    f.unlink()

    # 3. Bundles
    BUNDLE_DIR = Path("bundles")
    if BUNDLE_DIR.exists():
        cutoff = now - (days_bundles * 86400)
        # Market, Vault, Composite bundles
        for f in BUNDLE_DIR.glob("*.json"):
            if f.stat().st_mtime < cutoff:
                report["bundles"]["deleted"] += 1
                report["bundles"]["bytes"] += f.stat().st_size
                if not dry_run:
                    f.unlink()

    return report

def print_purge_report(report: dict, dry_run: bool):
    """Prints a summary of the purge operation."""
    mode = "[yellow]DRY RUN[/]" if dry_run else "[bold red]LIVE[/]"
    console.print(f"\n[bold cyan]Purge Report ({mode})[/]")
    
    total_files = 0
    total_bytes = 0
    
    for category, stats in report.items():
        if stats["deleted"] > 0:
            count = stats["deleted"]
            size_mb = stats["bytes"] / (1024 * 1024)
            console.print(f"  - {category.capitalize()}: {count} items ({size_mb:.1f} MB)")
            total_files += count
            total_bytes += stats["bytes"]
            
    if total_files == 0:
        console.print("  No obsolete data found.")
    else:
        total_mb = total_bytes / (1024 * 1024)
        console.print(f"\n[bold]Total: {total_files} items ({total_mb:.1f} MB)[/]")
        if dry_run:
            console.print("[dim]Use --live or the specific clean command to commit deletions.[/]")
