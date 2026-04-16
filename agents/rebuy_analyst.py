"""
Re-buy Analyst — evaluates current holdings for scale-in candidates.

Reads the composite bundle (market + vault), filters to investable
positions, passes them with thesis context to Gemini, and writes
the structured result to a local markdown file (DRY RUN) or to the
Agent_Outputs Sheet tab (--live).
"""

import json
import logging
import sys
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
from agents.schemas.rebuy_schema import FrameworkValidation, RebuyAnalystResponse
from agents.utils.chunked_analysis import run_chunked_analysis, CHUNK_SIZE
from agents.framework_selector import (
    parse_thesis_frontmatter,
    select_framework,
    evaluate_framework_rules,
)
from core.composite_bundle import load_composite_bundle, resolve_latest_bundles
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.fmp_client import get_fundamentals
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)

app = typer.Typer(help="Re-buy Analyst — scale-in candidates from current holdings")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_OUTPUTS_TAB = "Agent_Outputs"

# Step colors for Rich display
_STEP_COLORS = {
    "scale_in": "bold green",
    "hold": "yellow",
    "watch": "dim",
    "exit_watch": "bold red",
}


def _build_rebuy_chunk_prompt(chunk: list[dict], ctx: dict) -> str:
    """Builds the user prompt for a single chunk of positions."""
    import json
    framework_section = ctx.get("framework_section", "")
    recent_rotations_str = ""
    if ctx.get("recent_rotations"):
        recent_rotations_str = f"\nRecent portfolio rotations (from Trade_Log):\n{json.dumps(ctx['recent_rotations'], default=str, indent=2)}\n"

    return (
        f"Analyze the following {len(chunk)} position(s) "
        f"for re-buy / add candidates.\n\n"
        f"Portfolio total value: ${ctx['total_value']:,.2f}\n"
        f"Cash (strategic dry powder): ${ctx['cash_manual']:,.2f}\n"
        f"Cash as % of portfolio: "
        f"{ctx['cash_manual'] / ctx['total_value'] * 100:.1f}%\n\n"
        f"{recent_rotations_str}"
        f"Positions:\n{json.dumps(chunk, default=str, indent=2)}\n\n"
        f"Thesis files present for: {ctx['thesis_map_keys']}\n"
        f"Thesis files missing for: {ctx['coverage_warnings']}\n"
        f"{framework_section}\n"
        "Evaluate each position against its thesis file (if present), "
        "recent rotations, and the four investment styles. "
        "Produce a RebuyAnalystResponse JSON object."
    )


def run_rebuy_analyst(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    ticker_filter: set[str] | None = None,
    dry_run: bool = True,
) -> tuple[RebuyAnalystResponse, list[list]]:
    """
    Orchestrates the Re-buy Analyst analysis.
    Returns (result_object, list_of_sheet_rows).
    """
    # 3. Load composite bundle
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))

    # 5. Build investable positions list
    investable = [
        p for p in market["positions"]
        if p["ticker"] not in config.CASH_TICKERS
    ]

    if ticker_filter:
        investable = [p for p in investable if p["ticker"] in ticker_filter]

    excluded_tickers = [
        p["ticker"] for p in market["positions"]
        if p["ticker"] in config.CASH_TICKERS
    ]

    # 6. Build thesis map
    thesis_map = {
        doc["ticker"]: doc
        for doc in vault["documents"]
        if doc.get("doc_type") == "thesis" and doc.get("thesis_present")
    }

    # 7. Coverage warnings
    coverage_warnings = [
        p["ticker"] for p in investable
        if p["ticker"] not in thesis_map
    ]

    recent_rotations = composite.get("recent_rotations", [])

    # 8. Read system prompt
    system_prompt_path = Path(__file__).parent / "prompts" / "rebuy_analyst_system.txt"
    system_prompt_text = system_prompt_path.read_text(encoding="utf-8")

    # 8b. Framework pipeline
    frameworks = vault.get("frameworks", [])
    framework_validations: dict[str, dict] = {}

    bundle_quotes: dict[str, dict] = {
        q["ticker"]: q
        for q in composite.get("market_data", {}).get("quotes", [])
        if isinstance(q, dict) and q.get("ticker")
    }

    for pos in investable:
        t = pos["ticker"]
        thesis_doc = thesis_map.get(t)
        thesis_text = thesis_doc.get("content", "") if thesis_doc else ""
        thesis_frontmatter = parse_thesis_frontmatter(thesis_text or "")

        selected_fw = select_framework(
            ticker=t,
            position=pos,
            thesis_frontmatter=thesis_frontmatter,
            frameworks=frameworks,
        )

        if selected_fw is not None:
            fundamentals = {}
            try:
                fundamentals = get_fundamentals(t, bundle_quote=bundle_quotes.get(t)) or {}
            except Exception as e:
                logger.warning("Failed to fetch fundamentals for %s: %s", t, e)
            
            fw_validation = evaluate_framework_rules(
                position=pos,
                fundamentals=fundamentals,
                framework=selected_fw,
            )
            framework_validations[t] = fw_validation

    # 9. Van Tharp position sizing
    from agents.framework_selector import compute_van_tharp_sizing
    van_tharp_stops: dict[str, dict] = {
        s["ticker"]: s
        for s in composite.get("calculated_technical_stops", [])
        if isinstance(s, dict) and s.get("ticker")
    }
    van_tharp_sizing: dict[str, dict] = {}

    for pos in investable:
        t = pos["ticker"]
        atr_data = van_tharp_stops.get(t)
        if atr_data and atr_data.get("atr_14") and float(atr_data["atr_14"]) > 0:
            sizing = compute_van_tharp_sizing(
                entry_price=float(pos.get("price", 0.0)),
                atr_14=float(atr_data["atr_14"]),
                portfolio_equity=market["total_value"],
            )
            if sizing.get("sizing_valid"):
                van_tharp_sizing[t] = sizing

    for pos in investable:
        if pos["ticker"] in van_tharp_sizing:
            pos["van_tharp_sizing"] = van_tharp_sizing[pos["ticker"]]

    # 10. Build user prompt
    framework_section = ""
    if framework_validations:
        lines = ["\n## Pre-Computed Framework Evaluations (use as-is — do not re-derive)\n"]
        for t, fv in framework_validations.items():
            lines.append(f"### {t} — {fv['framework_id']} v{fv['framework_version']}")
            lines.append(f"Score: {fv['framework_score_display']} | Passes: {fv['passes_framework']}")
            for rule in fv["rules_evaluated"]:
                status = "PASS" if rule["passed"] is True else ("FAIL" if rule["passed"] is False else "N/A")
                lines.append(f"  [{rule['severity'].upper()}] {rule['rule_id']}: {status} — {rule['rationale']}")
            lines.append("")
        framework_section = "\n".join(lines)
    else:
        framework_section = "\n## Framework Evaluation\n\nNo frameworks applied.\n"

    portfolio_context = {
        "total_value": market["total_value"],
        "cash_manual": market["cash_manual"],
        "thesis_map_keys": list(thesis_map.keys()),
        "coverage_warnings": coverage_warnings,
        "framework_section": framework_section,
        "recent_rotations": recent_rotations,
    }

    all_candidates, all_excluded, all_warnings, chunk_errors = run_chunked_analysis(
        investable=investable,
        bundle_path=bundle_path,
        composite_hash=composite["composite_hash"],
        build_user_prompt_fn=_build_rebuy_chunk_prompt,
        response_schema=RebuyAnalystResponse,
        system_instruction=system_prompt_text,
        portfolio_context=portfolio_context,
        ask_gemini_fn=ask_gemini_composite,
        max_tokens=config.GEMINI_MAX_TOKENS_REBUY,
    )

    result = RebuyAnalystResponse(
        bundle_hash=composite["composite_hash"],
        analysis_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        candidates=all_candidates,
        excluded_tickers=list(set(excluded_tickers + all_excluded)),
        coverage_warnings=list(set(coverage_warnings + all_warnings)),
        analyst_notes=f"Chunked: {len(investable)} positions. Errors: {', '.join(chunk_errors) if chunk_errors else 'none'}",
    )
    result.van_tharp_sizing_map = van_tharp_sizing

    for candidate in result.candidates:
        fv_dict = framework_validations.get(candidate.ticker)
        if fv_dict:
            candidate.framework_validation = FrameworkValidation(**fv_dict)

    # Legacy Write logic for rebuy
    headers = [
        "Run Timestamp", "Agent", "Bundle Hash", "Ticker",
        "Style", "Thesis Present", "Scaling State",
        "Proposed Step", "Rotation Priority", "Confidence",
        "Rationale", "Notes", "Fingerprint",
    ]
    
    new_rows = []
    for c in result.candidates:
        fp = f"{result.bundle_hash[:12]}|{c.ticker}|{c.proposed_next_step}"
        new_rows.append([
            result.analysis_timestamp_utc,
            "rebuy_analyst",
            result.bundle_hash,
            c.ticker,
            c.style,
            str(c.thesis_present),
            c.current_scaling_state,
            c.proposed_next_step,
            c.rotation_priority,
            c.confidence,
            c.scaling_rationale,
            c.notes,
            fp,
        ])

    return result, new_rows


@app.command("analyze")
def main(
    bundle: Optional[str] = typer.Option("latest", "--bundle", help="Composite bundle path or 'latest'."),
    ticker: Optional[str] = typer.Option(None, "--ticker", help="Single ticker subset."),
    live: bool = typer.Option(False, "--live", help="Write output to Sheet."),
):
    """Evaluate current holdings for scale-in candidates."""
    run_id = str(uuid.uuid4())[:8]
    run_ts = datetime.now(timezone.utc).isoformat()

    if bundle == "latest":
        composite_candidates = sorted(Path("bundles").glob("composite_bundle_*.json"), key=lambda p: p.stat().st_mtime)
        if not composite_candidates:
            console.print("[red]ERROR: No composite bundles found.[/]")
            raise typer.Exit(1)
        bundle_path = composite_candidates[-1]
    else:
        bundle_path = Path(bundle)

    ticker_filter = {ticker.upper()} if ticker else None

    try:
        result, sheet_rows = run_rebuy_analyst(bundle_path, run_id, run_ts, ticker_filter, dry_run=not live)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(1)

    # --- Rich Summary ---
    summary = Table(title="Re-buy Analyst Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Candidates", str(len(result.candidates)))
    console.print(summary)

    # ... Local audit file ...
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = AGENT_OUTPUT_DIR / f"rebuy_output_{result.bundle_hash[:12]}.json"
    json_path.write_text(json.dumps(result.model_dump(), indent=2))

    if live:
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        # Rebuy uses append-only pattern, not archive-and-overwrite
        ws = ss.worksheet(AGENT_OUTPUTS_TAB)
        ws.append_rows(sheet_rows, value_input_option="USER_ENTERED")
        console.print(f"[green]LIVE — appended {len(sheet_rows)} rows to {AGENT_OUTPUTS_TAB}.[/]")
    
    console.print(f"[dim]Local audit file:[/] {json_path}")


if __name__ == "__main__":
    app()
