"""
Valuation Agent — per-position valuation signals and accumulation plans.

Reads the composite bundle (market + vault), pre-computes all valuation metrics
in Python via FMP, passes summarized facts to Gemini for signals and narrative,
and writes the structured result to Agent_Outputs Sheet tab (--live) or local
files (dry run).
"""

import json
import logging
import os
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
from agents.schemas.valuation_schema import ValuationAgentOutput
from agents.framework_selector import parse_thesis_frontmatter
from core.composite_bundle import load_composite_bundle, resolve_latest_bundles
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite
from utils.fmp_client import get_fmp_quote, get_earnings_surprises_cached
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import archive_and_overwrite_agent_outputs
from utils.formatters import dicts_to_markdown_table

logger = logging.getLogger(__name__)

app = typer.Typer(help="Valuation Agent — per-position valuation signals and accumulation plans")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "valuation"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "valuation_agent_system.txt"

# Column headers for Agent_Outputs tab (Appendix A schema)
_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]


# ---------------------------------------------------------------------------
# Python pre-computation helpers
# ---------------------------------------------------------------------------

def _safe_float(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0

def _safe_float_or_none(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None

def _compute_valuation_facts(
    positions: list[dict],
    thesis_map: dict[str, dict],
    ticker_filter: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """
    For each investable position, fetch FMP data and compute valuation metrics.
    Excludes ETFs, Funds, and fixed income as they lack meaningful P/E.

    Returns:
        (valuation_facts: list[dict], data_gaps: list[str])
    """
    facts: list[dict] = []
    data_gaps: list[str] = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_TICKERS or ticker in config.VALUATION_SKIP_TICKERS:
            continue
        if ticker_filter and ticker not in ticker_filter:
            continue

        asset_class = (pos.get("asset_class") or pos.get("Asset Class") or "").upper().replace(" ", "_")
        if asset_class in config.VALUATION_SKIP_ASSET_CLASSES:
            continue

        price = _safe_float(pos.get("price"))
        if price <= 0:
            data_gaps.append(f"{ticker}: zero/missing price in bundle")
            continue

        # Thesis style tag
        thesis_doc = thesis_map.get(ticker)
        thesis_text = thesis_doc.get("content", "") if thesis_doc else ""
        frontmatter = parse_thesis_frontmatter(thesis_text)
        style_tag = (frontmatter.style or "Unknown").title()

        # FMP data
        quote = get_fmp_quote(ticker)
        surprises = get_earnings_surprises_cached(ticker)

        if not quote:
            data_gaps.append(f"{ticker}: FMP quote unavailable")
            facts.append({
                "ticker": ticker,
                "price": price,
                "pe_trailing": None,
                "pe_fwd": None,
                "peg": None,
                "high_52w": None,
                "low_52w": None,
                "price_vs_52w_range": None,
                "discount_from_52w_high_pct": 0.0,
                "earnings_surprises": [],
                "style_tag": style_tag,
                "thesis_present": thesis_doc is not None,
                "current_weight_pct": round(_safe_float(pos.get("weight")) * 100, 2),
                "market_value": _safe_float(pos.get("market_value")),
            })
            continue

        pe_trailing = _safe_float_or_none(quote.get("pe"))
        pe_fwd = _safe_float_or_none(quote.get("forwardPE"))
        peg = None # Future: pull from key metrics

        # 52-week range
        high_52w = _safe_float_or_none(quote.get("yearHigh"))
        low_52w = _safe_float_or_none(quote.get("yearLow"))
        price_vs_52w = None
        disc_52w_high = 0.0

        if high_52w and low_52w and high_52w > low_52w:
            price_vs_52w = (price - low_52w) / (high_52w - low_52w)
            disc_52w_high = (high_52w - price) / high_52w * 100

        # Last 2 surprises
        surp_list = []
        if surprises:
            for s in surprises[:2]:
                surp_list.append({
                    "date": s.get("date"),
                    "pct": s.get("actualEpsSurprisePercentage")
                })

        facts.append({
            "ticker": ticker,
            "price": price,
            "pe_trailing": pe_trailing,
            "pe_fwd": pe_fwd,
            "peg": peg,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "price_vs_52w_range": round(price_vs_52w, 3) if price_vs_52w is not None else None,
            "discount_from_52w_high_pct": round(disc_52w_high, 2),
            "earnings_surprises": surp_list,
            "style_tag": style_tag,
            "thesis_present": thesis_doc is not None,
            "current_weight_pct": round(_safe_float(pos.get("weight")) * 100, 2),
            "market_value": _safe_float(pos.get("market_value")),
        })

    return facts, data_gaps


def _result_to_sheet_rows(
    result: ValuationAgentOutput,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    """Serialize ValuationAgentOutput to Agent_Outputs tab rows."""
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for p in result.positions:
        action = p.accumulation_plan if p.signal == "accumulate" else p.signal.title()
        severity = "action" if p.signal == "accumulate" else ("watch" if p.signal == "trim" else "info")
        scale_step = p.accumulation_plan if p.signal == "accumulate" else "No action"
        
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            p.signal, p.ticker, action[:120],
            p.rationale[:800],
            scale_step[:120], severity, dry_str,
        ])

    return rows


# ---------------------------------------------------------------------------
# Runner & CLI
# ---------------------------------------------------------------------------

def run_valuation_agent(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    ticker_filter: set[str] | None = None,
    dry_run: bool = True,
) -> tuple[ValuationAgentOutput, list[list]]:
    """
    Orchestrates the Valuation Agent analysis.
    Returns (result_object, list_of_sheet_rows).
    """
    # --- Load bundles ---
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))
    total_value = market.get("total_value", 0.0)

    investable = [
        p for p in market["positions"]
        if p.get("ticker") not in config.CASH_TICKERS
    ]

    # --- Build thesis map ---
    thesis_map = {
        doc["ticker"]: doc
        for doc in vault["documents"]
        if doc.get("doc_type") == "thesis" and doc.get("thesis_present")
    }

    # --- Pre-compute valuation facts ---
    with console.status("[cyan]Fetching FMP data..."):
        val_facts, data_gaps = _compute_valuation_facts(investable, thesis_map, ticker_filter)

    if not val_facts:
        raise RuntimeError("No positions to analyze after FMP fetch. Check FMP_API_KEY.")

    # --- Build user prompt ---
    system_prompt_text = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _SYSTEM_PROMPT_PATH.exists()
        else ""
    )
    
    # Markdown optimization for flat data
    valuation_table_str = dicts_to_markdown_table(val_facts)

    user_prompt = (
        f"Analyze the following {len(val_facts)} position(s) for valuation signals.\n\n"
        f"## Pre-Computed Valuation Metrics (use exact numbers — do NOT recalculate)\n"
        f"Portfolio total value: ${total_value:,.2f}\n\n"
        f"{valuation_table_str}\n\n"
        f"## Data Gaps (tickers with missing FMP data — assign signal='monitor', rationale='Insufficient data')\n"
        f"{json.dumps(data_gaps)}\n\n"
        f"## Instructions\n"
        "For each position in the valuation table:\n"
        "  - Assign a signal: 'accumulate', 'hold', 'trim', or 'monitor'.\n"
        "  - If signal='accumulate', write an accumulation_plan using staged language.\n"
        "  - Write a 2-3 sentence rationale.\n"
        "  - Set style_alignment from the 'style_tag' field in the table above.\n\n"
        "Set top_accumulation_candidates to tickers with signal='accumulate', "
        "ordered by highest conviction.\n"
        "Write a 3-5 sentence summary_narrative.\n"
        "Set data_gaps to the list provided above.\n\n"
        f"bundle_hash (MUST echo in your response): {composite['composite_hash']}\n\n"
        "Produce a ValuationAgentOutput JSON object."
    )

    # --- Call Gemini ---
    result: ValuationAgentOutput | None = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=ValuationAgentOutput,
        system_instruction=system_prompt_text,
        max_tokens=config.GEMINI_MAX_TOKENS_VALUATION,
    )

    if result is None:
        raise RuntimeError("Gemini returned no result.")

    sheet_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run)
    return result, sheet_rows


@app.command("analyze")
def main(
    bundle: Optional[str] = typer.Option(
        "latest",
        "--bundle",
        help="Composite bundle path or 'latest' to use most recent.",
    ),
    tickers: Optional[str] = typer.Option(
        None,
        "--tickers",
        help="Comma-separated subset of tickers to analyze. Omit to analyze all positions.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write output to Agent_Outputs Sheet tab. Default: dry run.",
    ),
):
    """Pre-compute valuation metrics per position; Gemini assigns signals and plans."""
    run_id = str(uuid.uuid4())[:8]
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # --- Banner ---
    if live:
        console.print(Panel.fit("[bold white on red] LIVE MODE — Sheet writes enabled [/]", border_style="red"))
    else:
        console.print(Panel.fit("[bold black on yellow] DRY RUN — No Sheet writes. [/]", border_style="yellow"))

    # --- Resolve bundle path ---
    if bundle == "latest":
        composite_candidates = sorted(Path("bundles").glob("composite_bundle_*.json"), key=lambda p: p.stat().st_mtime)
        if not composite_candidates:
            console.print("[red]ERROR: No composite bundles found.[/]")
            raise typer.Exit(1)
        bundle_path = composite_candidates[-1]
    else:
        bundle_path = Path(bundle)
        if not bundle_path.exists():
            console.print(f"[red]ERROR: Bundle not found: {bundle_path}[/]")
            raise typer.Exit(1)

    ticker_filter = {t.strip().upper() for t in tickers.split(",") if t.strip()} if tickers else None

    console.print(f"[bold]Valuation Agent[/] | Run ID: {run_id} | Live: {live}")
    console.print(f"[dim]Bundle: {bundle_path.name}[/]")

    try:
        result, sheet_rows = run_valuation_agent(bundle_path, run_id, run_ts, ticker_filter, dry_run=not live)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(1)

    # --- Rich summary table ---
    summary = Table(title="Valuation Agent — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Generated At", result.generated_at)
    summary.add_row("Positions Analyzed", str(len(result.positions)))
    summary.add_row("Data Gaps", str(len(result.data_gaps)))
    summary.add_row("Accumulate Candidates", str(len(result.top_accumulation_candidates)))
    console.print(summary)

    # --- Local audit file ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = Path("bundles/runs") / f"valuation_analysis_{run_ts.replace(':', '')}_{run_id}.json"
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
