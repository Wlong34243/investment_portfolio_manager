"""
Behavior Finance Auditor Agent — Bias detection and objective portfolio review.

Analyzes the worst-performing positions and recent trade rotations to detect 
behavioral biases (Disposition Effect, Sunk Cost, Action Bias, etc.) 
mapping to Morgan Housel's "Psychology of Money" principles.
"""

import json
import logging
import time
import uuid
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from agents.schemas.behavioral_schema import BehavioralAuditorResponse, BehavioralAudit
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import archive_and_overwrite_agent_outputs
from utils.formatters import dicts_to_markdown_table

logger = logging.getLogger(__name__)

app = typer.Typer(help="Behavioral Auditor Agent")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "behavioral"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "behavioral_auditor_system.txt"

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]


# ---------------------------------------------------------------------------
# Python pre-computation helpers
# ---------------------------------------------------------------------------

def _load_recent_trades(ss, days: int = 30) -> str:
    """Read recent Trade_Log entries from Sheets."""
    try:
        ws = ss.worksheet(config.TAB_TRADE_LOG)
        all_vals = ws.get_all_values()
        if len(all_vals) <= 1: return "No recent trades found."
        
        headers = all_vals[0]
        rows = all_vals[1:]
        # Take last 10
        recent = rows[-10:]
        return dicts_to_markdown_table([dict(zip(headers, r)) for r in recent])
    except Exception:
        return "Trade_Log unavailable."


def _result_to_sheet_rows(
    result: BehavioralAuditorResponse,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for a in result.audits:
        # Mapping BehavioralAudit to standard Agent_Outputs columns
        # Action analyzed might contain a ticker, try to extract it
        ticker = "PORTFOLIO"
        words = a.action_analyzed.split()
        if words:
            potential_ticker = words[0].strip(':,')
            if len(potential_ticker) <= 5 and potential_ticker.isupper():
                ticker = potential_ticker

        action = f"{a.final_verdict}: {a.housel_principle}"
        rationale = f"{a.housel_quote} | Compounding: {a.compounding_check}"
        
        severity = "info"
        if a.final_verdict == "IRRATIONAL": severity = "action"
        elif a.final_verdict == "CAUTION": severity = "watch"

        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "behavioral_audit", ticker, action[:120],
            rationale[:800],
            a.final_verdict, severity, dry_str,
        ])

    if result.summary_narrative:
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "behavioral_summary", "PORTFOLIO",
            result.overall_behavioral_score,
            f"{result.summary_narrative[:800]} | TOP RISK: {result.top_risk[:300]}",
            "", "info", dry_str,
        ])

    return rows


# ---------------------------------------------------------------------------
# Runner & CLI
# ---------------------------------------------------------------------------

def run_behavioral_agent(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    trade_days: int = 60,
    dry_run: bool = True,
) -> tuple[BehavioralAuditorResponse, list[list]]:
    """
    Orchestrates the Behavioral Auditor Agent analysis.
    """
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))
    
    # Pre-computation: top losers
    positions = market["positions"]
    worst_performers = sorted(
        [p for p in positions if p.get("ticker") not in config.CASH_TICKERS],
        key=lambda x: float(x.get("unrealized_gl_pct") or 0.0)
    )[:15]

    # --- Load Trade_Log Context ---
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    trade_context = _load_recent_trades(ss, trade_days)

    # --- Build user prompt ---
    system_prompt_text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    
    worst_table = dicts_to_markdown_table([{
        "ticker": p["ticker"],
        "unrealized_gl_pct": p.get("unrealized_gl_pct"),
        "weight_pct": p.get("weight_pct"),
        "sector": p.get("sector")
    } for p in worst_performers])

    user_prompt = (
        f"Audit the following portfolio for behavioral biases based on Morgan Housel's 'Psychology of Money'.\n\n"
        f"## Worst Performing Positions\n"
        f"{worst_table}\n\n"
        f"## Recent Trade History (last {trade_days} days)\n"
        f"{trade_context}\n\n"
        "## Instructions\n"
        "1. Conduct 3-7 behavioral audits. Each audit must address a specific position or pattern.\n"
        "2. For each audit, populate: action_analyzed, time_horizon_alignment, volatility_tolerance, "
        "compounding_check, margin_of_safety, final_verdict (REASONABLE, CAUTION, IRRATIONAL), "
        "housel_principle, and housel_quote.\n"
        "3. Provide an overall_behavioral_score (DISCIPLINED, MIXED, AT_RISK) and summary_narrative.\n"
        "4. bundle_hash (echo it): {composite['composite_hash']}\n"
        "Produce a BehavioralAuditorResponse JSON object."
    )

    # --- Call Gemini ---
    result: BehavioralAuditorResponse | None = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=BehavioralAuditorResponse,
        system_instruction=system_prompt_text,
        max_tokens=4000,
    )

    if result is None:
        raise RuntimeError("Gemini returned no result.")

    sheet_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run)
    return result, sheet_rows


@app.command("analyze")
def main(
    bundle: Optional[str] = typer.Option("latest", "--bundle", help="Composite bundle path or 'latest'."),
    trade_days: int = typer.Option(60, "--trade-days", help="Days of trade history to audit."),
    live: bool = typer.Option(False, "--live", help="Write output to Agent_Outputs."),
):
    """Audit portfolio for behavioral biases and objective decision-making."""
    run_id = str(uuid.uuid4())[:8]
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if bundle == "latest":
        candidates = sorted(Path("bundles").glob("composite_bundle_*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            console.print("[red]ERROR: No composite bundles found.[/]")
            raise typer.Exit(1)
        bundle_path = candidates[-1]
    else:
        bundle_path = Path(bundle)

    try:
        result, sheet_rows = run_behavioral_agent(bundle_path, run_id, run_ts, trade_days, dry_run=not live)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(1)

    # --- Rich Summary ---
    summary = Table(title="Behavioral Auditor — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Audits Performed", str(len(result.audits)))
    summary.add_row("Portfolio Score", result.overall_behavioral_score)
    console.print(summary)

    if result.audits:
        table = Table(title="Behavioral Audits", show_header=True)
        table.add_column("Action Analyzed")
        table.add_column("Verdict")
        table.add_column("Principle")
        for a in result.audits:
            color = "green" if a.final_verdict == "REASONABLE" else ("red" if a.final_verdict == "IRRATIONAL" else "yellow")
            table.add_row(a.action_analyzed[:40], f"[{color}]{a.final_verdict}[/]", a.housel_principle)
        console.print(table)

    # --- Audit files ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = Path("bundles/runs") / f"behavioral_analysis_{run_ts.replace(':', '')}_{run_id}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w") as f:
        f.write(result.model_dump_json(indent=2))

    if live:
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        archive_and_overwrite_agent_outputs(ss, sheet_rows, run_ts, _AGENT_OUTPUTS_HEADERS)
    
    console.print(f"[dim]Local audit file:[/] {json_path}")


if __name__ == "__main__":
    app()
