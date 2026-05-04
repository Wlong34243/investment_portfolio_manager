"""
Concentration & Hedging Agent — Risk-based sizing and correlation-aware hedging.

Phase 5-E port. Analyzes portfolio concentration by single position and sector,
flags violations of config thresholds, and suggests hedges via high-correlation
pairs (from pre-computed correlation matrix in the composite bundle).
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
from agents.schemas.concentration_schema import ConcentrationAgentOutput, ConcentrationFlag, CorrelationPair
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import archive_and_overwrite_agent_outputs
from utils.formatters import dicts_to_markdown_table

logger = logging.getLogger(__name__)

app = typer.Typer(help="Concentration & Hedging Agent")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "concentration"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "concentration_hedger_system.txt"

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]


# ---------------------------------------------------------------------------
# Python pre-computation helpers
# ---------------------------------------------------------------------------

def _compute_concentration_flags(
    positions: list[dict],
    total_value: float,
) -> tuple[list[dict], list[dict]]:
    """
    Identify positions or sectors exceeding config thresholds.
    Returns (concentration_flags, data_quality_flags).

    Data quality check: if >10% of portfolio value has unclassified sector,
    sector analysis is unreliable and is skipped. The data_quality_flags list
    carries the issue for surfacing as a top-priority row in Agent_Outputs.
    """
    dq_flags: list[dict] = []
    flags: list[dict] = []

    # 0. Data quality guard — check sector coverage before running sector analysis
    unknown_mv = sum(
        (p.get("market_value") or 0)
        for p in positions
        if (p.get("sector") or "Unknown").lower() in ("unknown", "")
        and p.get("ticker") not in config.CASH_TICKERS
    )
    unknown_pct = unknown_mv / total_value if total_value > 0 else 0.0
    skip_sector = unknown_pct > 0.10
    if skip_sector:
        dq_flags.append({
            "issue": (
                f"{unknown_pct:.1%} of portfolio has unclassified sector/asset_class; "
                "sector concentration analysis skipped — backfill asset_class in bundle"
            ),
            "pct": round(unknown_pct * 100, 1),
        })
        logger.warning(
            "Sector analysis skipped: %.1f%% of portfolio market value has unclassified sector.",
            unknown_pct * 100,
        )

    # 1. Single Position Flags
    for p in positions:
        ticker = p.get("ticker", "")
        if ticker in config.CASH_TICKERS:
            continue
        weight = (p.get("market_value") or 0) / total_value
        if weight > config.CONCENTRATION_SINGLE_THRESHOLD:
            flags.append({
                "type": "SINGLE_POSITION",
                "target": ticker,
                "current_weight_pct": round(weight * 100, 2),
                "threshold_pct": round(config.CONCENTRATION_SINGLE_THRESHOLD * 100, 2),
                "status": "VIOLATION",
            })

    # 2. Sector Flags (skipped when data quality is too low)
    if not skip_sector:
        sector_mv: dict[str, float] = {}
        for p in positions:
            if p.get("ticker") in config.CASH_TICKERS:
                continue
            sector = p.get("sector") or "Unknown"
            sector_mv[sector] = sector_mv.get(sector, 0.0) + (p.get("market_value") or 0)

        for sector, mv in sector_mv.items():
            weight = mv / total_value
            if weight > config.CONCENTRATION_SECTOR_THRESHOLD:
                flags.append({
                    "type": "SECTOR",
                    "target": sector,
                    "current_weight_pct": round(weight * 100, 2),
                    "threshold_pct": round(config.CONCENTRATION_SECTOR_THRESHOLD * 100, 2),
                    "status": "VIOLATION",
                })

    return flags, dq_flags


def _extract_high_correlations(matrix: dict) -> list[dict]:
    """
    matrix: {ticker1: {ticker2: correlation, ...}, ...}
    Returns list of pairs where |r| > threshold.
    """
    pairs = []
    seen = set()
    threshold = config.CORRELATION_FLAG_THRESHOLD

    for t1, others in matrix.items():
        for t2, r in others.items():
            if t1 == t2: continue
            pair_key = tuple(sorted([t1, t2]))
            if pair_key in seen: continue
            seen.add(pair_key)
            
            if abs(r) >= threshold:
                pairs.append({
                    "ticker_a": t1,
                    "ticker_b": t2,
                    "correlation": round(r, 3)
                })
                
    # Sort by absolute correlation descending, limit to top 25
    return sorted(pairs, key=lambda x: abs(x["correlation"]), reverse=True)[:25]


def _result_to_sheet_rows(
    result: ConcentrationAgentOutput,
    run_id: str,
    run_ts: str,
    dry_run: bool,
    dq_flags: list[dict] | None = None,
) -> list[list]:
    """Serialize ConcentrationAgentOutput to Agent_Outputs tab rows.

    Data quality rows are prepended with severity='data_quality' so they sort
    to the top of Agent_Outputs (above action rows).
    """
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    # Data quality rows first — these are pipeline issues, not portfolio findings
    for dq in (dq_flags or []):
        issue_text = dq.get("issue", "Unknown data quality issue")
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "data_quality", "PORTFOLIO",
            _clean_action_headline(issue_text),
            issue_text,
            "Fix asset_class/sector enrichment in bundle", "data_quality", dry_str,
        ])

    for f in result.flags:
        action = f.hedge_suggestion or "Trim to threshold"
        severity = "action" if f.status == "VIOLATION" else "watch"
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            f"concentration_{f.type.lower()}", f.target,
            _clean_action_headline(action),
            f"Weight {f.current_weight_pct}% vs threshold {f.threshold_pct}%",
            f.scale_step, severity, dry_str,
        ])

    if result.summary_narrative:
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "portfolio_summary", "PORTFOLIO",
            "Concentration Audit Complete",
            result.summary_narrative[:800],
            "", "info", dry_str,
        ])

    return rows


def _clean_action_headline(text: str, max_len: int = 80) -> str:
    """Truncate action text on a word boundary, never mid-word."""
    text = str(text)
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return truncated + "…"


# ---------------------------------------------------------------------------
# Runner & CLI
# ---------------------------------------------------------------------------

def run_concentration_agent(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    dry_run: bool = True,
) -> tuple[ConcentrationAgentOutput, list[list]]:
    """
    Orchestrates the Concentration Agent analysis.
    Returns (result_object, list_of_sheet_rows).
    """
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))
    
    total_value = market.get("total_value", 0.0)
    portfolio_beta = composite.get("portfolio_beta", 1.0)
    matrix = composite.get("correlation_matrix", {})

    # --- Pre-computation ---
    flags, dq_flags = _compute_concentration_flags(market["positions"], total_value)
    correlations = _extract_high_correlations(matrix)

    # --- Build user prompt ---
    system_prompt_text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    
    # Markdown optimization for flat lists
    flags_table = dicts_to_markdown_table(flags)
    corr_table = dicts_to_markdown_table(correlations)

    user_prompt = (
        f"Analyze the following portfolio for concentration risk and hedging opportunities.\n\n"
        f"## Concentration Flags\n"
        f"Thresholds: Single={config.CONCENTRATION_SINGLE_THRESHOLD*100}%, Sector={config.CONCENTRATION_SECTOR_THRESHOLD*100}%\n"
        f"{flags_table}\n\n"
        f"## High-Correlation Pairs (|r| > {config.CORRELATION_FLAG_THRESHOLD})\n"
        f"{corr_table}\n\n"
        f"## Portfolio Context\n"
        f"Total value: ${total_value:,.2f}\n"
        f"Portfolio Beta: {portfolio_beta:.2f}\n"
        f"bundle_hash (echo it): {composite['composite_hash']}\n\n"
        "For each flag: assign a status (VIOLATION, WARNING) and suggest a hedge or trim action.\n"
        "Explain high-correlation clusters in the summary_narrative.\n"
        "Produce a ConcentrationAgentOutput JSON object."
    )

    # --- Call Gemini ---
    result: ConcentrationAgentOutput | None = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=ConcentrationAgentOutput,
        system_instruction=system_prompt_text,
        max_tokens=config.GEMINI_MAX_TOKENS_CONCENTRATION,
    )

    if result is None:
        raise RuntimeError("Gemini returned no result.")

    sheet_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run, dq_flags=dq_flags)
    return result, sheet_rows


@app.command("analyze")
def main(
    bundle: Optional[str] = typer.Option("latest", "--bundle", help="Composite bundle path or 'latest'."),
    live: bool = typer.Option(False, "--live", help="Write output to Agent_Outputs."),
):
    """Analyze concentration risk and correlation-aware hedging."""
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
        result, sheet_rows = run_concentration_agent(bundle_path, run_id, run_ts, dry_run=not live)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(1)

    # --- Rich Summary ---
    summary = Table(title="Concentration Agent — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Flags Raised", str(len(result.flags)))
    summary.add_row("Portfolio Beta", f"{result.portfolio_beta:.2f}")
    console.print(summary)

    if result.flags:
        table = Table(title="Risk Flags", show_header=True)
        table.add_column("Target")
        table.add_column("Type")
        table.add_column("Weight%")
        table.add_column("Status")
        for f in result.flags:
            color = "red" if f.status == "VIOLATION" else "yellow"
            table.add_row(f.target, f.type, f"{f.current_weight_pct}%", f"[{color}]{f.status}[/]")
        console.print(table)

    # --- Local audit file ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = Path("bundles/runs") / f"concentration_analysis_{run_ts.replace(':', '')}_{run_id}.json"
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
