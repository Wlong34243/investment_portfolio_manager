"""
Re-buy Analyst — evaluates current holdings for scale-in candidates.

Reads the composite bundle (market + vault), filters to investable
positions, passes them with thesis context to Gemini, and writes
the structured result to a local markdown file (DRY RUN) or to the
Agent_Outputs Sheet tab (--live).

This is the first agent on the bundle spine. Its correct operation
validates the Phase 01-02 infrastructure end-to-end.
"""

import json
import logging
import sys
import time
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


@app.command()
def analyze(
    bundle: Optional[str] = typer.Option(
        "latest",
        "--bundle",
        help="Composite bundle path or 'latest' to use most recent.",
    ),
    ticker: Optional[str] = typer.Option(
        None,
        "--ticker",
        help="Analyze a single ticker only. Omit to analyze all positions.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write output to Agent_Outputs Sheet tab. Default: dry run.",
    ),
):
    """Evaluate current holdings for scale-in candidates."""

    # 1. Banner
    if live:
        console.print(Panel.fit(
            "[bold white on red] LIVE MODE — Sheet writes enabled [/]",
            border_style="red",
        ))
    else:
        console.print(Panel.fit(
            "[bold black on yellow] DRY RUN — No Sheet writes. Use --live to enable. [/]",
            border_style="yellow",
        ))

    # 2. Resolve bundle path
    if bundle == "latest":
        try:
            _market_path, _vault_path = resolve_latest_bundles()
            # Find the latest composite bundle
            composite_candidates = sorted(
                Path("bundles").glob("composite_bundle_*.json"),
                key=lambda p: p.stat().st_mtime,
            )
            if not composite_candidates:
                console.print("[red]ERROR: No composite bundles found in bundles/. Run: python manager.py bundle composite[/]")
                raise typer.Exit(1)
            bundle_path = composite_candidates[-1]
            console.print(f"[dim]Using latest composite bundle: {bundle_path.name}[/]")
        except FileNotFoundError as e:
            console.print(f"[red]ERROR: {e}[/]")
            raise typer.Exit(1)
    else:
        bundle_path = Path(bundle)
        if not bundle_path.exists():
            console.print(f"[red]ERROR: Bundle not found: {bundle_path}[/]")
            raise typer.Exit(1)

    # 3. Load composite bundle
    composite = load_composite_bundle(bundle_path)
    console.print(f"[dim]Loaded composite bundle: {composite['composite_hash'][:16]}...[/]")

    # 4. Load sub-bundles
    market = load_bundle(Path(composite["market_bundle_path"]))
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))

    # 5. Build investable positions list
    investable = [
        p for p in market["positions"]
        if p["ticker"] not in config.CASH_TICKERS
    ]

    if ticker:
        ticker_upper = ticker.upper()
        investable = [p for p in investable if p["ticker"] == ticker_upper]
        if not investable:
            console.print(f"[yellow]! Ticker {ticker_upper} not found in bundle positions.[/]")
            raise typer.Exit(0)

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

    # 7. Coverage warnings — investable positions with no thesis
    coverage_warnings = [
        p["ticker"] for p in investable
        if p["ticker"] not in thesis_map
    ]

    # 7b. Recent rotations context from Trade_Log (baked into composite bundle)
    recent_rotations = composite.get("recent_rotations", [])

    # 8. Read system prompt
    system_prompt_path = Path(__file__).parent / "prompts" / "rebuy_analyst_system.txt"
    system_prompt_text = system_prompt_path.read_text(encoding="utf-8")

    # 8b. Framework pipeline — deterministic pre-computation before LLM call
    frameworks = vault.get("frameworks", [])
    framework_validations: dict[str, dict] = {}  # keyed by ticker

    # Bundle quotes: Schwab /marketdata/v1/quotes data, if present in composite.
    # Populated when data_source='schwab_api'; empty dict for CSV-sourced bundles.
    # Passed as tier-1 source to get_fundamentals() to reduce FMP API calls.
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
            try:
                fundamentals = get_fundamentals(t, bundle_quote=bundle_quotes.get(t)) or {}
            except Exception as e:
                logger.warning("Failed to fetch fundamentals for %s: %s", t, e)
                fundamentals = {}
            fw_validation = evaluate_framework_rules(
                position=pos,
                fundamentals=fundamentals,
                framework=selected_fw,
            )
            framework_validations[t] = fw_validation
            logger.info(
                "Framework %s evaluated for %s: %s",
                selected_fw["framework_id"], t,
                fw_validation.get("framework_score_display"),
            )
        else:
            logger.info("No reviewed framework applies to %s — thesis-only reasoning", t)

    # 9. Van Tharp position sizing — pre-computed, never LLM-derived
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
                logger.info(
                    "Van Tharp sizing for %s: %s units, 1R=$%.2f",
                    t, sizing.get("position_size_units"), sizing.get("per_share_risk_1r", 0),
                )
            else:
                logger.debug("Van Tharp sizing invalid for %s: %s", t, sizing.get("note"))
        else:
            logger.debug("Van Tharp: no ATR data for %s — run tasks/enrich_atr.py", t)

    # Inject Van Tharp sizing into each position dict for LLM context
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
            if fv["insufficient_data_rules"]:
                lines.append(f"  Insufficient data: {fv['insufficient_data_rules']}")
            lines.append("")
        lines.append(
            "For each ticker with a framework evaluation, you MUST fill in "
            "framework_influence_notes explaining how the score shaped your recommendation. "
            "The framework score is INFORMATIONAL — you may still recommend scale_in on a "
            "partial pass, but you must justify it explicitly.\n"
        )
        framework_section = "\n".join(lines)
    else:
        framework_section = (
            "\n## Framework Evaluation\n\n"
            "No reviewed framework matches any position's asset class and style. "
            "Reason from thesis alone. Set framework_validation to null and "
            "framework_influence_notes to empty string for all candidates.\n"
        )

    # 10. Call LLM — CHUNKED EXECUTION
    console.print(f"[cyan]Calling Gemini on {len(investable)} positions "
                  f"(chunked, {CHUNK_SIZE} per batch)...[/]")

    portfolio_context = {
        "total_value": market["total_value"],
        "cash_manual": market["cash_manual"],
        "thesis_map_keys": list(thesis_map.keys()),
        "coverage_warnings": coverage_warnings,
        "framework_section": framework_section,
        "recent_rotations": recent_rotations,
    }

    with console.status("[cyan]Analyzing in chunks..."):
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

    if not all_candidates and chunk_errors:
        console.print("[red]ERROR: All chunks failed. Check API logs.[/]")
        for err in chunk_errors:
            console.print(f"  [red]• {err}[/]")
        raise typer.Exit(1)

    # Reconstruct result with ORIGINAL composite hash (never from a chunk response)
    result = RebuyAnalystResponse(
        bundle_hash=composite["composite_hash"],
        analysis_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        candidates=all_candidates,
        excluded_tickers=list(set(excluded_tickers + all_excluded)),
        coverage_warnings=list(set(coverage_warnings + all_warnings)),
        analyst_notes=(
            f"Chunked: {len(investable)} positions across "
            f"{-(-len(investable) // CHUNK_SIZE)} batch(es). "
            f"Errors: {', '.join(chunk_errors) if chunk_errors else 'none'}"
        ),
    )
    # --- END CHUNKED EXECUTION ---

    # 11a. Overwrite van_tharp_sizing_map with Python-computed values.
    #      Never from a chunk response — sizing is pure Python, not LLM-derived.
    result.van_tharp_sizing_map = van_tharp_sizing
    if van_tharp_sizing:
        console.print(
            f"[dim]Van Tharp sizing computed for {len(van_tharp_sizing)} position(s).[/]"
        )
    else:
        console.print(
            "[dim]Van Tharp: no ATR data in bundle — run tasks/enrich_atr.py to populate.[/]"
        )

    # 11b. Overwrite framework_validation on each candidate with pre-computed Python results.
    #      Trust the deterministic computation, not the LLM's reconstruction.
    for candidate in result.candidates:
        fv_dict = framework_validations.get(candidate.ticker)
        if fv_dict is not None:
            try:
                candidate.framework_validation = FrameworkValidation(**fv_dict)
            except Exception as e:
                logger.warning("Could not coerce framework_validation for %s: %s", candidate.ticker, e)
                candidate.framework_validation = None
        else:
            candidate.framework_validation = None

    # 12. Rich summary table
    summary = Table(title="Re-buy Analyst Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Analysis Time", result.analysis_timestamp_utc)
    summary.add_row("Candidates", str(len(result.candidates)))
    summary.add_row("Excluded", str(len(result.excluded_tickers)))
    summary.add_row("Coverage Warnings", str(len(result.coverage_warnings)))
    console.print(summary)

    if result.candidates:
        cand_table = Table(title="Candidates", show_header=True)
        cand_table.add_column("Ticker", style="bold")
        cand_table.add_column("Style")
        cand_table.add_column("Next Step")
        cand_table.add_column("Confidence")
        for c in result.candidates:
            color = _STEP_COLORS.get(c.proposed_next_step, "white")
            cand_table.add_row(
                c.ticker,
                c.style,
                f"[{color}]{c.proposed_next_step}[/]",
                c.confidence,
            )
        console.print(cand_table)

    if result.analyst_notes:
        console.print(f"\n[dim]Analyst notes:[/] {result.analyst_notes}")

    # 13 & 14. Write local files (always, regardless of --live)
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = AGENT_OUTPUT_DIR / f"rebuy_output_{result.bundle_hash[:12]}.json"
    md_path = AGENT_OUTPUT_DIR / f"rebuy_output_{result.bundle_hash[:12]}.md"

    json_path.write_text(json.dumps(result.model_dump(), indent=2))

    # Build markdown
    sections = {"scale_in": [], "hold": [], "watch": [], "exit_watch": []}
    for c in result.candidates:
        sections.get(c.proposed_next_step, sections["watch"]).append(c)

    md_lines = [
        "# Re-buy Analyst Output",
        f"**Bundle hash:** {result.bundle_hash}",
        f"**Run at:** {result.analysis_timestamp_utc}",
        "",
    ]

    def _render_section(title: str, candidates: list) -> list[str]:
        if not candidates:
            return []
        lines = [f"## {title}", ""]
        for c in candidates:
            lines += [
                f"### {c.ticker} - {c.style}",
                f"- Scaling state: {c.current_scaling_state}",
                f"- Proposed next step: {c.proposed_next_step}",
                f"- Confidence: {c.confidence}",
                f"- Rationale: {c.scaling_rationale}",
            ]
            if c.notes:
                lines.append(f"- Notes: {c.notes}")
            lines.append("")
        return lines

    md_lines += _render_section("Scale-in Candidates", sections["scale_in"])
    md_lines += _render_section("Hold / Watch", sections["hold"] + sections["watch"])
    md_lines += _render_section("Exit Watch", sections["exit_watch"])

    if result.coverage_warnings:
        md_lines += ["## Coverage Warnings", ""]
        for w in result.coverage_warnings:
            md_lines.append(f"- {w}")
        md_lines.append("")

    if result.analyst_notes:
        md_lines += ["## Analyst Notes", "", result.analyst_notes, ""]

    md_path.write_text("\n".join(md_lines))

    if not live:
        console.print(f"\n[dim]DRY RUN — output written to:[/]")
        console.print(f"  {json_path}")
        console.print(f"  {md_path}")
        return

    # 14. Live — write to Sheet
    from utils.sheet_readers import get_gspread_client

    headers = [
        "Run Timestamp", "Agent", "Bundle Hash", "Ticker",
        "Style", "Thesis Present", "Scaling State",
        "Proposed Step", "Rotation Priority", "Confidence",
        "Rationale", "Notes", "Fingerprint",
    ]

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    existing_tabs = [ws.title for ws in ss.worksheets()]

    if AGENT_OUTPUTS_TAB not in existing_tabs:
        ws = ss.add_worksheet(title=AGENT_OUTPUTS_TAB, rows=1000, cols=15)
        ws.update(range_name="A1", values=[headers], value_input_option="USER_ENTERED")
        time.sleep(1.0)
        existing_fps = set()
    else:
        ws = ss.worksheet(AGENT_OUTPUTS_TAB)
        all_vals = ws.get_all_values()
        if len(all_vals) <= 1:
            existing_fps = set()
        else:
            fp_col_idx = len(headers) - 1  # Fingerprint is last column
            existing_fps = {row[fp_col_idx] for row in all_vals[1:] if len(row) > fp_col_idx}

    new_rows = []
    for c in result.candidates:
        fp = f"{result.bundle_hash[:12]}|{c.ticker}|{c.proposed_next_step}"
        if fp in existing_fps:
            continue
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

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        time.sleep(1.0)
        console.print(f"[green]LIVE — wrote {len(new_rows)} rows to {AGENT_OUTPUTS_TAB} tab.[/]")
    else:
        console.print(f"[yellow]LIVE — all {len(result.candidates)} rows already present (fingerprint dedup).[/]")

    console.print(f"[dim]Local audit files:[/] {json_path}, {md_path}")


if __name__ == "__main__":
    app()
