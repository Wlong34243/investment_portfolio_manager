"""
Macro-Cycle Rotation Agent — Carlota Perez framework + ATR stop-loss triggers.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from agents.schemas.macro_cycle_schema import MacroCycleResponse, ATRStopLoss, PositionCycleAnalysis
from agents.utils.chunked_analysis import CHUNK_SIZE, INTER_CHUNK_SLEEP
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import archive_and_overwrite_agent_outputs
from utils.formatters import dicts_to_markdown_table

logger = logging.getLogger(__name__)

app = typer.Typer(help="Macro-Cycle Rotation Agent")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "macro"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "macro_cycle_system.txt"
_FRAMEWORK_PATH = Path(__file__).parent / "macro_super_cycle.json"

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]

_REC_TO_SCALE = {
    "HOLD":       "Hold — no action",
    "TRIM_25PCT": "Trim 25% over 2 sessions",
    "TRIM_50PCT": "Trim 50% in two tranches over 2-3 weeks",
    "EXIT":       "Exit position in 3-4 staged tranches",
    "MONITOR":    "Monitor — no action yet",
}

_REC_TO_SEVERITY = {
    "HOLD":       "info",
    "TRIM_25PCT": "watch",
    "TRIM_50PCT": "action",
    "EXIT":       "action",
    "MONITOR":    "watch",
}


# ---------------------------------------------------------------------------
# Python pre-computation helpers
# ---------------------------------------------------------------------------

def _result_to_sheet_rows(
    result: MacroCycleResponse,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for p in result.positions_analyzed:
        action = _REC_TO_SCALE.get(p.final_recommendation, p.final_recommendation)
        severity = _REC_TO_SEVERITY.get(p.final_recommendation, "info")
        rationale = p.fundamental_reason_to_sell[:800]
        
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "macro_rotation", p.ticker, action[:120],
            rationale,
            p.final_recommendation, severity, dry_str,
        ])

    if result.portfolio_cycle_summary:
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "portfolio_summary", "PORTFOLIO",
            f"Phase: {result.paradigm_phase}",
            result.portfolio_cycle_summary[:800],
            "", "info", dry_str,
        ])

    return rows


# ---------------------------------------------------------------------------
# Runner & CLI
# ---------------------------------------------------------------------------

def run_macro_agent(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    dry_run: bool = True,
) -> tuple[MacroCycleResponse, list[list]]:
    """
    Orchestrates the Macro-Cycle Agent analysis.
    """
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))
    
    positions = [p for p in market["positions"] if p.get("ticker") not in config.CASH_TICKERS]

    # enrich_atr.py writes a list-of-dicts; normalize to dict keyed by ticker
    _atr_raw = composite.get("calculated_technical_stops", [])
    if isinstance(_atr_raw, list):
        atr_stops = {s["ticker"]: s for s in _atr_raw if isinstance(s, dict) and "ticker" in s}
    elif isinstance(_atr_raw, dict):
        atr_stops = _atr_raw
    else:
        logger.warning("calculated_technical_stops has unexpected shape — running in fundamentals-only mode")
        atr_stops = {}

    # --- Pre-computation facts ---
    macro_facts = []
    for p in positions:
        ticker = p["ticker"]
        stop_data = atr_stops.get(ticker, {})
        stop_level = stop_data.get("stop_loss_level")
        price = p.get("price", 0.0)
        
        is_triggered = False
        pct_from_stop = None
        if stop_level and price > 0:
            is_triggered = price < stop_level
            pct_from_stop = round((price - stop_level) / price * 100, 2)

        macro_facts.append({
            "ticker": ticker,
            "sector": p.get("sector", "Unknown"),
            "price": price,
            "stop_loss_level": stop_level,
            "pct_from_stop": pct_from_stop,
            "is_triggered": is_triggered,
            "weight_pct": round(p.get("weight_pct", 0.0), 2)
        })

    # --- Build user prompt ---
    system_prompt_text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    framework_text = _FRAMEWORK_PATH.read_text(encoding="utf-8")
    
    # Markdown optimization
    facts_table = dicts_to_markdown_table(macro_facts)

    user_prompt = (
        f"Analyze the following portfolio against the Carlota Perez Macro-Cycle Framework.\n\n"
        f"## Pre-Computed Macro Facts (Technical Stops + Weights)\n"
        f"{facts_table}\n\n"
        f"## Carlota Perez Framework Context\n"
        f"{framework_text}\n\n"
        "## Instructions\n"
        "1. Identify the current paradigm_phase (Installation, Deployment, Turning Point).\n"
        "2. For each triggered stop-loss: decide if this is a fundamental EXIT or a 'noise' dip.\n"
        "3. Provide final_recommendation (HOLD, TRIM_25PCT, TRIM_50PCT, EXIT, MONITOR).\n"
        "4. bundle_hash (echo it): {composite['composite_hash']}\n"
        "Produce a MacroCycleResponse JSON object."
    )

    # --- Call Gemini ---
    result: MacroCycleResponse | None = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=MacroCycleResponse,
        system_instruction=system_prompt_text,
        max_tokens=config.GEMINI_MAX_TOKENS_MACRO,
    )

    if result is None:
        raise RuntimeError("Gemini returned no result.")

    sheet_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run)
    return result, sheet_rows


@app.command("analyze")
def main(
    bundle: Optional[str] = typer.Option("latest", "--bundle", help="Composite bundle path or 'latest'."),
    live: bool = typer.Option(False, "--live", help="Write output to Agent_Outputs."),
):
    """Analyze macro-cycle rotation and technical stop-losses."""
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
        result, sheet_rows = run_macro_agent(bundle_path, run_id, run_ts, dry_run=not live)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(1)

    # --- Rich Summary ---
    summary = Table(title="Macro-Cycle Agent — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Paradigm Phase", result.paradigm_phase)
    summary.add_row("Positions Analyzed", str(len(result.positions_analyzed)))
    console.print(summary)

    if result.positions_analyzed:
        table = Table(title="Rotation Signals", show_header=True)
        table.add_column("Ticker")
        table.add_column("Rec")
        table.add_column("Stop Level")
        for p in result.positions_analyzed:
            color = "red" if "TRIM" in p.final_recommendation or "EXIT" in p.final_recommendation else "white"
            table.add_row(p.ticker, f"[{color}]{p.final_recommendation}[/]", str(p.technical_trigger_summary[:40]))
        console.print(table)

    # --- Local audit file ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = Path("bundles/runs") / f"macro_analysis_{run_ts.replace(':', '')}_{run_id}.json"
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
