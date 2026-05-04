import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from core.thesis_sync_data import gather_thesis_sync_data, TickerSyncPayload
from utils.thesis_utils import ThesisManager

console = Console()

def generate_thesis_report(payloads: Dict[str, TickerSyncPayload]) -> Table:
    """Generates a Rich table for the dry-run report."""
    table = Table(title="Thesis Sync Dry Run Report", show_header=True, header_style="bold magenta")
    table.add_column("Ticker", style="dim")
    table.add_column("Style", style="cyan")
    table.add_column("Allocation", justify="right")
    table.add_column("Ceiling", justify="right")
    table.add_column("Drift", justify="right")
    table.add_column("Cost Basis", justify="right")
    table.add_column("TX Count", justify="right")
    table.add_column("Status", justify="center")

    for ticker, p in payloads.items():
        drift_color = "red" if p.drift_pct > 0 else "green"
        status = "[green]OK[/green]" if p.drift_pct <= 0 else "[bold red]OVERWEIGHT[/bold red]"
        
        table.add_row(
            ticker,
            p.style or "N/A",
            f"{p.current_allocation_pct:.2f}%",
            f"{p.size_ceiling_pct:.2f}%",
            f"[{drift_color}]{p.drift_pct:+.2f}%[/{drift_color}]",
            f"${p.cost_basis:,.2f}",
            str(len(p.transactions)),
            status
        )
        
    return table

def format_realized_summary(realized_gl: List[dict]) -> str:
    if not realized_gl:
        return "No realized G/L history."
    
    total_gain = sum(item.get('Gain Loss $', 0) for item in realized_gl)
    total_proceeds = sum(item.get('Proceeds', 0) for item in realized_gl)
    count = len(realized_gl)
    
    return f"Total Realized G/L: ${total_gain:,.2f} over {count} closed lots. Total Proceeds: ${total_proceeds:,.2f}."

def format_transaction_log(transactions: List[dict]) -> str:
    if not transactions:
        return "No recent transactions found."
    
    lines = []
    for tx in transactions:
        date = tx.get('Trade Date', 'N/A')
        action = tx.get('Action', 'N/A')
        qty = tx.get('Quantity', 0)
        price = tx.get('Price', 0)
        lines.append(f"- {date}: {action} {qty} @ ${price:,.2f}")
    
    return "\n".join(lines)

import difflib

def write_thesis_updates(
    payloads: Dict[str, TickerSyncPayload], 
    dry_run: bool = True, 
    force_recreate_regions: bool = False,
    show_diff: bool = False
) -> dict:
    """
    Apply gathered data to thesis files.
    """
    report = {"processed": 0, "updated": 0, "skipped": 0, "errors": 0}
    
    if not payloads:
        return report

    if dry_run:
        console.print(generate_thesis_report(payloads))
        if not show_diff:
            console.print("\n[dim]Use --show-diff to see specific changes.[/]")

    for ticker, p in payloads.items():
        thesis_path = config.THESES_DIR / f"{ticker}_thesis.md"
        if not thesis_path.exists():
            report["skipped"] += 1
            continue
            
        try:
            mgr = ThesisManager(thesis_path)
            old_content = mgr.raw_content
            
            # 1. Update Frontmatter
            fm_updates = {
                "last_reviewed": p.last_reviewed,
                "cost_basis": p.cost_basis,
                "current_allocation": f"{p.current_allocation_pct:.2f}%"
            }
            if p.style:
                fm_updates["style"] = p.style
                
            mgr.update_frontmatter(fm_updates)
            
            # 2. Update Triggers block
            trig_updates = {
                "style_size_ceiling_pct": p.size_ceiling_pct,
                "current_weight_pct": p.current_allocation_pct
            }
            mgr.update_triggers(trig_updates)
            
            # 3. Update Regions
            # Position State
            state_content = f"**Current Allocation:** {p.current_allocation_pct:.2f}%\n"
            state_content += f"**Cost Basis:** ${p.cost_basis:,.2f}\n"
            mgr.replace_region("position_state", state_content)
            
            # Sizing
            sizing_content = f"**Style:** {p.style}\n"
            sizing_content += f"**Size Ceiling:** {p.size_ceiling_pct:.2f}%\n"
            sizing_content += f"**Drift:** {p.drift_pct:+.2f}%\n"
            mgr.replace_region("sizing", sizing_content)
            
            # Transaction Log
            mgr.replace_region("transaction_log", format_transaction_log(p.transactions))
            
            # Realized G/L
            mgr.replace_region("realized_gl", format_realized_summary(p.realized_gl))
            
            # Change Log (append)
            log_entry = f"{datetime.now().strftime('%Y-%m-%d %H:%M')}: Auto-sync allocation {p.current_allocation_pct:.2f}%, drift {p.drift_pct:+.2f}%"
            mgr.replace_region("change_log", log_entry)
            
            new_content = mgr.raw_content
            
            if old_content != new_content:
                report["updated"] += 1
                if show_diff:
                    diff = difflib.unified_diff(
                        old_content.splitlines(),
                        new_content.splitlines(),
                        fromfile=f"a/{ticker}_thesis.md",
                        tofile=f"b/{ticker}_thesis.md"
                    )
                    console.print(Panel("\n".join(diff), title=f"Diff: {ticker}_thesis.md", border_style="cyan"))
                
                if not dry_run:
                    mgr.save(backup=True)
            else:
                report["processed"] += 1
                
        except Exception as e:
            logging.error(f"Error updating {ticker}: {e}")
            report["errors"] += 1
            
    return report

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    payloads = gather_thesis_sync_data(datetime.now().strftime("%Y-%m-%d"), tickers=["UNH", "AMZN"])
    write_thesis_updates(payloads, dry_run=True)
