"""
Thesis Screener Agent — Gautam Baid Framework.

Phase 5-G port. Evaluates management quality, candor, and capital stewardship
from earnings transcripts and cross-references them against original theses.
"""

import json
import logging
import re
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root to path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from agents.schemas.thesis_screener_schema import ThesisScreenerResponse, ManagementEvaluation
from agents.framework_selector import parse_thesis_frontmatter
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import archive_and_overwrite_agent_outputs
from utils.formatters import dicts_to_markdown_table

logger = logging.getLogger(__name__)

app = typer.Typer(help="Thesis Screener Agent")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "thesis"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "thesis_screener_system.txt"
_FRAMEWORK_PATH = Path(__file__).parent.parent / "vault" / "frameworks" / "joys_of_compounding_framework.json"

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]

_REC_TO_SEVERITY = {
    "MAINTAIN_CONVICTION": "info",
    "WATCHLIST_DOWNGRADE": "watch",
    "THESIS_VIOLATED":    "action",
}

_STALE_THRESHOLD_DAYS = 90


# ---------------------------------------------------------------------------
# Python pre-computation helpers
# ---------------------------------------------------------------------------

def _extract_exit_conditions(thesis_text: str) -> str:
    """Extract the exit conditions section from thesis markdown (first 500 chars)."""
    match = re.search(
        r"##\s+(?:Hard\s+)?Exit\s+Conditions?\s*\n(.*?)(?=\n##|\Z)",
        thesis_text,
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip()[:500] if match else ""


def _parse_thesis_triggers(thesis_text: str) -> dict:
    """
    Extract the triggers: YAML block from the ## Quantitative Triggers section.
    Returns the triggers dict (may have null values). Returns {} if section missing.
    """
    import yaml as _yaml
    match = re.search(r"```yaml\s*\ntriggers:\s*\n(.*?)```", thesis_text, re.DOTALL)
    if not match:
        return {}
    try:
        data = _yaml.safe_load("triggers:\n" + match.group(1)) or {}
        return data.get("triggers") or {}
    except Exception:
        return {}


_TRIGGER_FIELDS = [
    "fwd_pe_add_below", "fwd_pe_trim_above", "fwd_pe_historical_median",
    "price_add_below", "price_trim_above", "discount_from_52w_high_add",
    "revenue_growth_floor_pct", "operating_margin_floor_pct",
    "style_size_ceiling_pct",
]


def _evaluate_triggers(triggers: dict, bundle_pos: dict) -> tuple[list[str], list[str]]:
    """
    Compare trigger values against current bundle data (price, fwd PE, weight).
    Returns (trigger_fired, trigger_missing).
    """
    fired: list[str] = []
    missing: list[str] = []

    price = float(bundle_pos.get("price") or 0.0)

    for field in _TRIGGER_FIELDS:
        val = triggers.get(field)
        if val is None:
            missing.append(field)
            continue
        try:
            threshold = float(val)
        except (TypeError, ValueError):
            missing.append(field)
            continue
        # Evaluate firing conditions
        if field == "price_add_below" and price > 0 and price < threshold:
            fired.append(f"{field}={threshold} (current={price:.2f})")
        elif field == "price_trim_above" and price > 0 and price > threshold:
            fired.append(f"{field}={threshold} (current={price:.2f})")
        elif field == "discount_from_52w_high_add":
            disc = float(bundle_pos.get("discount_from_52w_high_pct") or 0.0)
            if disc > threshold * 100:
                fired.append(f"{field}={threshold:.0%} (current={disc:.1f}%)")

    return fired, missing


def _is_stale_thesis(last_reviewed: str | None) -> bool:
    """True if last_reviewed is missing or older than _STALE_THRESHOLD_DAYS."""
    if not last_reviewed:
        return True
    try:
        reviewed = date.fromisoformat(str(last_reviewed))
        return (date.today() - reviewed).days > _STALE_THRESHOLD_DAYS
    except (ValueError, TypeError):
        return True


def _compute_thesis_facts(
    vault_bundle: dict,
    ticker_filter: set[str] | None = None,
    positions_by_ticker: dict | None = None,
) -> tuple[list[dict], list[str]]:
    """
    Match tickers with their theses and transcripts.
    Returns (facts, data_gaps).
    """
    facts = []
    data_gaps = []
    
    # Map by ticker
    thesis_map = {
        doc["ticker"]: doc for doc in vault_bundle["documents"]
        if doc.get("doc_type") == "thesis" and doc.get("thesis_present")
    }
    transcript_map = {
        doc["ticker"]: doc for doc in vault_bundle["documents"]
        if doc.get("doc_type") == "transcript"
    }

    # Current date for staleness check
    TODAY = date(2026, 4, 20)

    # Use all tickers present in either thesis or transcript map
    all_tickers = set(thesis_map.keys()) | set(transcript_map.keys())
    
    for ticker in sorted(all_tickers):
        if ticker_filter and ticker not in ticker_filter:
            continue

        th = thesis_map.get(ticker)
        tr = transcript_map.get(ticker)

        if not th and not tr:
            continue

        # Parse frontmatter and extract quantitative facts from thesis content
        has_thesis = th is not None
        thesis_content = th.get("content", "") if th else ""
        frontmatter = parse_thesis_frontmatter(thesis_content) if thesis_content else None
        last_reviewed = frontmatter.last_reviewed if frontmatter else None
        exit_conditions = frontmatter.exit_conditions if frontmatter and hasattr(frontmatter, 'exit_conditions') else []
        if not exit_conditions:
            # Fallback to text extraction if not in frontmatter
            exit_conditions_text = _extract_exit_conditions(thesis_content)
            exit_conditions = [exit_conditions_text] if exit_conditions_text else []

        stale_thesis = False
        if last_reviewed:
            try:
                rev_date = date.fromisoformat(str(last_reviewed))
                stale_thesis = (TODAY - rev_date).days > 90
            except (ValueError, TypeError):
                stale_thesis = True
        elif has_thesis:
            stale_thesis = True # No date means stale

        # Parse quantitative triggers and evaluate against current bundle data
        triggers = _parse_thesis_triggers(thesis_content) if thesis_content else {}
        bundle_pos = (positions_by_ticker or {}).get(ticker, {})
        trigger_fired, trigger_missing = _evaluate_triggers(triggers, bundle_pos)

        facts.append({
            "ticker": ticker,
            "has_thesis": has_thesis,
            "transcript_present": tr is not None,
            "transcript_date": tr.get("metadata", {}).get("date") if tr else "N/A",
            "last_reviewed": str(last_reviewed) if last_reviewed else "unknown",
            "stale_thesis": stale_thesis,
            "exit_conditions": exit_conditions,
            "trigger_fired": trigger_fired,
            "trigger_missing": trigger_missing,
        })

        if not th:
            data_gaps.append(f"{ticker}: missing original thesis")
        if not tr:
            data_gaps.append(f"{ticker}: missing latest transcript")

    return facts, data_gaps


def _result_to_sheet_rows(
    result: ThesisScreenerResponse,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for e in result.evaluations:
        action = e.final_recommendation.replace("_", " ").title()
        severity = _REC_TO_SEVERITY.get(e.final_recommendation, "info")
        rationale = f"{e.final_recommendation}: {e.thesis_alignment_warning}"
        
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "thesis_audit", e.ticker, action[:120],
            rationale[:800],
            e.final_recommendation, severity, dry_str,
        ])

    if result.portfolio_qualitative_summary:
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "portfolio_summary", "PORTFOLIO",
            "Thesis Audit Complete",
            result.portfolio_qualitative_summary[:800],
            "", "info", dry_str,
        ])

    return rows


# ---------------------------------------------------------------------------
# Runner & CLI
# ---------------------------------------------------------------------------

from agents.utils.chunked_analysis import run_chunked_analysis

def _build_thesis_user_prompt(chunk: list[dict], context: dict) -> str:
    """Builds the prompt for a single chunk of positions."""
    facts_table = dicts_to_markdown_table(chunk)
    framework_text = context.get("framework_text", "")
    composite_hash = context.get("composite_hash", "")
    data_gaps = context.get("data_gaps", [])

    return (
        f"Analyze management candor and capital stewardship for the following {len(chunk)} positions.\n\n"
        f"## Gautam Baid Framework (Joys of Compounding)\n"
        f"{framework_text}\n\n"
        f"## Pre-Computed Facts (thesis coverage, exit conditions, trigger status, staleness)\n"
        f"{facts_table}\n\n"
        "## Verdict Hierarchy & Discipline (STRICT RULES)\n"
        "1. The Hard Stop (MONITOR): If has_thesis: false, the verdict MUST be MONITOR. Reasoning: 'Thesis file needs backfill before a verdict can be issued.'\n"
        "2. The Exit (EXIT): Triggered if any condition in the exit_conditions field of the thesis file is met.\n"
        "3. The Reduction (TRIM): Triggered if one exit condition is partially met, or if rotation_priority is High/Medium and thesis is weakening.\n"
        "4. The Accumulation (ADD): Only if thesis is INTACT AND you identify a specific asymmetric improvement.\n"
        "5. The Default (HOLD): Thesis is intact, and no exit conditions are triggered.\n\n"
        "## Reasoning Constraints\n"
        "- Your verdict_reasoning must explicitly cite the thesis file. Use 'Per the thesis file...' or 'The exit condition [X] is/is not triggered because...'\n"
        "- If stale_thesis: true, you MUST append: 'WARNING: Thesis is stale (>90 days). Re-verify assumptions.'\n\n"
        f"## Data Gaps (entire portfolio context)\n"
        f"{', '.join(data_gaps) if data_gaps else 'None'}\n\n"
        "## Instructions\n"
        "1. For each ticker: compare behavior to original thesis.\n"
        "2. Set 'verdict' as the FIRST field in the evaluation block.\n"
        "3. Provide concise 'verdict_reasoning' (max 600 chars).\n"
        f"4. bundle_hash (MUST echo): {composite_hash}\n"
        "Produce a ThesisScreenerResponse JSON object."
    )

def run_thesis_agent(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    ticker_filter: set[str] | None = None,
    dry_run: bool = True,
) -> tuple[ThesisScreenerResponse, list[list]]:
    """
    Orchestrates the Thesis Screener Agent analysis using chunked execution.
    """
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))
    composite_hash = composite["composite_hash"]

    # Build positions lookup for trigger evaluation
    positions_by_ticker = {p["ticker"]: p for p in market.get("positions", [])}

    # --- Pre-computation ---
    facts, data_gaps = _compute_thesis_facts(vault, ticker_filter, positions_by_ticker)

    if not facts:
        raise RuntimeError("No positions with thesis/transcript data to analyze.")

    # --- Run Chunked Analysis ---
    framework_text = _FRAMEWORK_PATH.read_text(encoding="utf-8")
    system_instruction = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    
    portfolio_context = {
        "framework_text": framework_text,
        "composite_hash": composite_hash,
        "data_gaps": data_gaps
    }

    all_evals, excluded, coverage_warns, errors = run_chunked_analysis(
        investable=facts,
        bundle_path=bundle_path,
        composite_hash=composite_hash,
        build_user_prompt_fn=_build_thesis_user_prompt,
        response_schema=ThesisScreenerResponse,
        system_instruction=system_instruction,
        portfolio_context=portfolio_context,
        ask_gemini_fn=ask_gemini_composite,
        max_tokens=config.GEMINI_MAX_TOKENS_THESIS,
        result_field="evaluations",
    )

    if not all_evals:
        raise RuntimeError(f"Thesis analysis failed for all chunks. Errors: {errors}")

    # Map back to Pydantic
    final_evals = []
    violations = []
    watchlists = []
    for e in all_evals:
        if isinstance(e, dict):
            obj = ManagementEvaluation(**e)
        else:
            obj = e
        final_evals.append(obj)
        if obj.final_recommendation == "THESIS_VIOLATED":
            violations.append(obj.ticker)
        elif obj.final_recommendation == "WATCHLIST_DOWNGRADE":
            watchlists.append(obj.ticker)

    result = ThesisScreenerResponse(
        bundle_hash=composite_hash,
        analysis_timestamp_utc=run_ts,
        evaluations=final_evals,
        thesis_violations=violations,
        watchlist_downgrades=watchlists,
        portfolio_qualitative_summary="Thesis management audit complete via chunked execution.",
    )

    sheet_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run)
    return result, sheet_rows


@app.command("analyze")
def main(
    bundle: Optional[str] = typer.Option("latest", "--bundle", help="Composite bundle path or 'latest'."),
    tickers: Optional[str] = typer.Option(None, "--tickers", help="Comma-separated tickers."),
    live: bool = typer.Option(False, "--live", help="Write output to Agent_Outputs."),
):
    """Analyze management candor and thesis alignment."""
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

    ticker_filter = {t.strip().upper() for t in tickers.split(",")} if tickers else None

    try:
        result, sheet_rows = run_thesis_agent(bundle_path, run_id, run_ts, ticker_filter, dry_run=not live)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(1)

    # --- Rich Summary ---
    summary = Table(title="Thesis Screener — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Evaluations", str(len(result.evaluations)))
    console.print(summary)

    if result.evaluations:
        table = Table(title="Management Evaluations", show_header=True)
        table.add_column("Ticker")
        table.add_column("Rec")
        table.add_column("Alignment Warning")
        for e in result.evaluations:
            color = "green" if e.final_recommendation == "MAINTAIN_CONVICTION" else ("red" if e.final_recommendation == "THESIS_VIOLATED" else "yellow")
            table.add_row(e.ticker, f"[{color}]{e.final_recommendation}[/]", e.thesis_alignment_warning[:60])
        console.print(table)

    # --- Local audit file ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = Path("bundles/runs") / f"thesis_analysis_{run_ts.replace(':', '')}_{run_id}.json"
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
