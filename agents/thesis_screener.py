"""
Thesis Screener Agent — Gautam Baid "Joys of Compounding" Framework.

Phase 5-E port. Evaluates corporate management quality against vault thesis files
and earnings transcript snippets. Detects thesis violations and management
character deterioration.

Pre-computation in Python (minimal — this is primarily a qualitative agent):
  - Vault thesis presence / absence per ticker → tickers_skipped
  - Thesis frontmatter parsing: core_thesis excerpt, exit_conditions, style tag
  - Earnings transcript snippets: pulled from vault bundle documents

Gemini writes: all scoring pillars, inner/outer scorecard, thesis alignment
warning, pre-mortem behavioral check, final_recommendation,
portfolio_qualitative_summary.

CLI:
    python manager.py agent thesis analyze
    python manager.py agent thesis analyze --ticker UNH
    python manager.py agent thesis analyze --bundle bundles/composite_20260413_....json
    python manager.py agent thesis analyze --live
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
from agents.schemas.thesis_screener_schema import ManagementEvaluation, ThesisScreenerResponse
from agents.utils.chunked_analysis import CHUNK_SIZE, INTER_CHUNK_SLEEP
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite

logger = logging.getLogger(__name__)

app = typer.Typer(help="Thesis Screener Agent — Gautam Baid management quality evaluation")
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
    "THESIS_VIOLATED":     "action",
}

_REC_TO_ACTION = {
    "MAINTAIN_CONVICTION": "Hold — thesis intact",
    "WATCHLIST_DOWNGRADE": "Monitor 1-2 quarters before acting",
    "THESIS_VIOLATED":     "Evaluate staged exit — thesis exit condition triggered",
}


# ---------------------------------------------------------------------------
# Vault parsing helpers
# ---------------------------------------------------------------------------

def _parse_thesis_frontmatter(content: str) -> dict:
    """
    Extract key fields from thesis markdown frontmatter + body.
    Returns dict with: style, next_step, priority, core_thesis_excerpt, exit_conditions
    """
    lines = content.splitlines()
    out = {
        "style": "Unknown",
        "next_step": "",
        "priority": "",
        "core_thesis_excerpt": "",
        "exit_conditions": "",
    }

    in_yaml = False
    yaml_done = False
    body_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---" and i == 0:
            in_yaml = True
            continue
        if stripped == "---" and in_yaml and not yaml_done:
            in_yaml = False
            yaml_done = True
            continue
        if in_yaml:
            if stripped.lower().startswith("style:"):
                out["style"] = stripped.split(":", 1)[1].strip()
            elif stripped.lower().startswith("next_step:"):
                out["next_step"] = stripped.split(":", 1)[1].strip()
            elif stripped.lower().startswith("priority:"):
                out["priority"] = stripped.split(":", 1)[1].strip()
        else:
            body_lines.append(line)

    body = "\n".join(body_lines)

    # Extract Core Thesis section (first 400 chars after heading)
    for heading in ["## Core Thesis", "# Core Thesis", "**Core Thesis**"]:
        idx = body.find(heading)
        if idx != -1:
            snippet = body[idx + len(heading):idx + len(heading) + 500].strip()
            out["core_thesis_excerpt"] = snippet[:400]
            break

    # Extract exit conditions
    for heading in ["## Exit Conditions", "## Risks to Watch", "## When to Sell"]:
        idx = body.find(heading)
        if idx != -1:
            snippet = body[idx + len(heading):idx + len(heading) + 500].strip()
            out["exit_conditions"] = snippet[:400]
            break

    return out


def _build_position_context(
    investable: list[dict],
    thesis_map: dict[str, dict],
    transcript_map: dict[str, str],
    ticker_filter: Optional[list[str]],
    total_value: float,
) -> tuple[list[dict], list[str]]:
    """
    Build per-position context dicts for the Gemini prompt.
    Returns (positions_context, tickers_skipped).
    """
    positions_context = []
    tickers_skipped = []

    for pos in investable:
        ticker = pos.get("ticker", "")
        if ticker_filter and ticker not in ticker_filter:
            continue

        if ticker not in thesis_map:
            tickers_skipped.append(ticker)
            continue

        thesis = thesis_map[ticker]
        weight_pct = round(
            float(pos.get("market_value", 0) or 0) / total_value * 100, 2
        ) if total_value > 0 else 0.0

        entry = {
            "ticker": ticker,
            "weight_pct": weight_pct,
            "asset_class": pos.get("asset_class", ""),
            "thesis_style": thesis.get("style", "Unknown"),
            "thesis_next_step": thesis.get("next_step", ""),
            "thesis_priority": thesis.get("priority", ""),
            "core_thesis_excerpt": thesis.get("core_thesis_excerpt", ""),
            "exit_conditions": thesis.get("exit_conditions", ""),
            "earnings_transcript_snippet": transcript_map.get(ticker, ""),
        }
        positions_context.append(entry)

    return positions_context, tickers_skipped


# ---------------------------------------------------------------------------
# Sheet write helpers
# ---------------------------------------------------------------------------

def _result_to_sheet_rows(
    result: ThesisScreenerResponse,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for ev in result.evaluations:
        action = _REC_TO_ACTION.get(ev.final_recommendation, ev.final_recommendation)
        severity = _REC_TO_SEVERITY.get(ev.final_recommendation, "info")
        flags_str = "; ".join(ev.red_flags_identified[:3]) if ev.red_flags_identified else "None"
        rationale = f"{ev.thesis_alignment_warning[:200]} | Flags: {flags_str}"
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "thesis_quality",
            ev.ticker,
            action,
            rationale[:300],
            action[:120],
            severity,
            dry_str,
        ])

    # Portfolio-level summary row
    violations_str = ", ".join(result.thesis_violations[:5]) or "none"
    rows.append([
        run_id, run_ts, composite_hash_short, AGENT_NAME,
        "portfolio_summary", "PORTFOLIO",
        f"Violations: {violations_str}",
        result.portfolio_qualitative_summary[:300],
        "", "info", dry_str,
    ])

    return rows


def _archive_and_overwrite(ss, new_rows: list[list], run_ts: str) -> None:
    existing_tabs = {ws.title for ws in ss.worksheets()}

    if config.TAB_AGENT_OUTPUTS not in existing_tabs:
        ws_out = ss.add_worksheet(
            title=config.TAB_AGENT_OUTPUTS, rows=2000, cols=len(_AGENT_OUTPUTS_HEADERS) + 1
        )
        time.sleep(1.0)
        existing_rows = []
    else:
        ws_out = ss.worksheet(config.TAB_AGENT_OUTPUTS)
        existing_rows = ws_out.get_all_values()

    if len(existing_rows) > 1:
        if config.TAB_AGENT_OUTPUTS_ARCHIVE not in existing_tabs:
            ws_arc = ss.add_worksheet(
                title=config.TAB_AGENT_OUTPUTS_ARCHIVE,
                rows=10000, cols=len(_AGENT_OUTPUTS_HEADERS) + 2,
            )
            time.sleep(1.0)
            ws_arc.update(
                range_name="A1",
                values=[["archived_at"] + existing_rows[0]],
                value_input_option="USER_ENTERED",
            )
            time.sleep(0.5)
        else:
            ws_arc = ss.worksheet(config.TAB_AGENT_OUTPUTS_ARCHIVE)

        archive_rows = [[run_ts] + row for row in existing_rows[1:]]
        if archive_rows:
            ws_arc.append_rows(archive_rows, value_input_option="USER_ENTERED")
            time.sleep(1.0)
        console.print(
            f"[dim]Archived {len(archive_rows)} row(s) to {config.TAB_AGENT_OUTPUTS_ARCHIVE}.[/]"
        )

    ws_out.clear()
    time.sleep(0.5)
    ws_out.update(
        range_name="A1",
        values=[_AGENT_OUTPUTS_HEADERS] + new_rows,
        value_input_option="USER_ENTERED",
    )
    time.sleep(1.0)
    console.print(
        f"[green]LIVE — wrote {len(new_rows)} row(s) to {config.TAB_AGENT_OUTPUTS} (single batch).[/]"
    )


# ---------------------------------------------------------------------------
# Chunked prompt builder
# ---------------------------------------------------------------------------

def _build_thesis_chunk_prompt(chunk: list[dict], ctx: dict) -> str:
    """Builds the user prompt for a single chunk of positions."""
    framework_context = ctx["framework_context"]
    composite_hash = ctx["composite_hash"]
    tickers_skipped = ctx["tickers_skipped"]
    return (
        f"Evaluate the management quality of {len(chunk)} portfolio position(s) "
        f"using the Gautam Baid 'Joys of Compounding' framework.\n\n"
        f"## Baid Scoring Framework Reference\n"
        f"{framework_context}\n\n"
        f"## Portfolio Positions — Thesis Files + Transcript Snippets\n"
        f"{json.dumps(chunk, indent=2, default=str)}\n\n"
        f"## Instructions\n"
        "For each position:\n"
        "  - Score linguistic_candor_score (HIGH / MODERATE / LOW + evidence)\n"
        "  - Score capital_stewardship_score (DISCIPLINED / ADEQUATE / QUESTIONABLE + evidence)\n"
        "  - Score alignment_score (STRONG / MODERATE / WEAK + evidence)\n"
        "  - List red_flags_identified (specific, evidence-based; empty list if none)\n"
        "  - Write inner_scorecard_assessment (one sentence: INNER or OUTER + reason)\n"
        "  - Write thesis_alignment_warning (does behavior invalidate core_thesis or exit_conditions?)\n"
        "  - Write pre_mortem_behavioral_check (run all 6 Baid guardrails by name)\n"
        "  - Assign final_recommendation: MAINTAIN_CONVICTION | WATCHLIST_DOWNGRADE | THESIS_VIOLATED\n\n"
        "If no earnings transcript snippet is provided, rely on the thesis file only "
        "and note the data gap in thesis_alignment_warning.\n\n"
        "Write portfolio_qualitative_summary (3-5 sentences on overall management quality).\n"
        "Return thesis_violations and watchlist_downgrades as ordered ticker lists.\n"
        f"tickers_skipped (no thesis file): {tickers_skipped}\n\n"
        f"bundle_hash (MUST echo in your response): {composite_hash}\n\n"
        "Produce a ThesisScreenerResponse JSON object."
    )


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@app.command()
def analyze(
    bundle: Optional[str] = typer.Option(
        "latest",
        "--bundle",
        help="Composite bundle path or 'latest' to use most recent.",
    ),
    ticker: Optional[str] = typer.Option(
        None, "--ticker",
        help="Evaluate a single ticker (e.g. UNH). Omit for all positions.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write output to Agent_Outputs Sheet tab. Default: dry run.",
    ),
):
    """
    Gautam Baid thesis screener — evaluate management quality against vault thesis files.

    Reads thesis files and transcript snippets from the composite bundle vault.
    Positions with no thesis file in the vault are logged in tickers_skipped.
    """

    # --- Banner ---
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

    # --- Resolve bundle ---
    if bundle == "latest":
        composite_candidates = sorted(
            Path("bundles").glob("composite_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not composite_candidates:
            console.print(
                "[red]ERROR: No composite bundles found. Run: python manager.py bundle composite[/]"
            )
            raise typer.Exit(1)
        bundle_path = composite_candidates[-1]
        console.print(f"[dim]Using latest composite bundle: {bundle_path.name}[/]")
    else:
        bundle_path = Path(bundle)
        if not bundle_path.exists():
            console.print(f"[red]ERROR: Bundle not found: {bundle_path}[/]")
            raise typer.Exit(1)

    # --- Load composite bundle ---
    composite = load_composite_bundle(bundle_path)
    console.print(f"[dim]Composite hash: {composite['composite_hash'][:16]}...[/]")

    # --- Load sub-bundles ---
    market = load_bundle(Path(composite["market_bundle_path"]))
    investable = [
        p for p in market["positions"]
        if p.get("ticker") not in config.CASH_TICKERS
    ]
    total_value = market.get("total_value", 0.0)

    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))

    console.print(f"[dim]{len(investable)} investable positions | portfolio ${total_value:,.0f}[/]")

    # --- Build thesis map (ticker → parsed frontmatter dict) ---
    thesis_map: dict[str, dict] = {}
    transcript_map: dict[str, str] = {}

    for doc in vault.get("documents", []):
        doc_ticker = doc.get("ticker", "")
        doc_type = doc.get("doc_type", "")
        content = doc.get("content", "")

        if doc_type == "thesis" and doc.get("thesis_present"):
            thesis_map[doc_ticker] = _parse_thesis_frontmatter(content)

        elif doc_type in ("transcript", "earnings_notes"):
            # Keep the first 600 chars as a snippet
            existing = transcript_map.get(doc_ticker, "")
            if not existing:
                transcript_map[doc_ticker] = content[:600]

    # --- Apply ticker filter ---
    ticker_filter: Optional[list[str]] = None
    if ticker:
        ticker_filter = [t.strip().upper() for t in ticker.split(",")]
        console.print(f"[dim]Ticker filter: {ticker_filter}[/]")

    # --- Build position context ---
    positions_context, tickers_skipped = _build_position_context(
        investable, thesis_map, transcript_map, ticker_filter, total_value
    )

    if not positions_context:
        console.print("[yellow]No positions with vault thesis files found. Run 'manager.py vault snapshot' first.[/]")
        raise typer.Exit(0)

    if tickers_skipped:
        console.print(f"[yellow]! {len(tickers_skipped)} position(s) have no thesis file: {tickers_skipped[:10]}[/]")

    console.print(f"[dim]Evaluating {len(positions_context)} position(s) with thesis files.[/]")

    # --- Load Baid framework JSON ---
    framework_context = ""
    if _FRAMEWORK_PATH.exists():
        try:
            framework_context = _FRAMEWORK_PATH.read_text(encoding="utf-8")
        except Exception:
            framework_context = ""
    else:
        console.print(
            "[yellow]! joys_of_compounding_framework.json not found in vault/frameworks/. "
            "Gemini will rely on system prompt rubric only.[/]"
        )

    # --- System prompt ---
    system_prompt_text = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _SYSTEM_PROMPT_PATH.exists()
        else ""
    )

    # --- Call Gemini — CHUNKED EXECUTION ---
    chunks = [
        positions_context[i : i + CHUNK_SIZE]
        for i in range(0, len(positions_context), CHUNK_SIZE)
    ]
    console.print(
        f"[cyan]Calling Gemini on {len(positions_context)} position(s) "
        f"(chunked, {CHUNK_SIZE} per batch)...[/]"
    )

    prompt_ctx = {
        "framework_context": framework_context,
        "composite_hash": composite["composite_hash"],
        "tickers_skipped": tickers_skipped,
    }

    all_evaluations: list = []
    all_thesis_violations: list = []
    all_watchlist_downgrades: list = []
    first_portfolio_summary: str | None = None
    chunk_errors: list[str] = []

    with console.status("[cyan]Evaluating management quality in chunks..."):
        for idx, chunk in enumerate(chunks):
            tickers_in_chunk = [p["ticker"] for p in chunk]
            logger.info("Chunk %d/%d: %s", idx + 1, len(chunks), tickers_in_chunk)
            try:
                chunk_prompt = _build_thesis_chunk_prompt(chunk, prompt_ctx)
                chunk_result: ThesisScreenerResponse | None = ask_gemini_composite(
                    prompt=chunk_prompt,
                    composite_bundle_path=bundle_path,
                    response_schema=ThesisScreenerResponse,
                    system_instruction=system_prompt_text,
                    max_tokens=8000,
                )
                if chunk_result is None:
                    msg = f"Chunk {idx + 1}/{len(chunks)} ({tickers_in_chunk}): Gemini returned None"
                    logger.warning(msg)
                    chunk_errors.append(msg)
                else:
                    all_evaluations.extend(chunk_result.evaluations)
                    all_thesis_violations.extend(chunk_result.thesis_violations)
                    all_watchlist_downgrades.extend(chunk_result.watchlist_downgrades)
                    if first_portfolio_summary is None and chunk_result.portfolio_qualitative_summary:
                        first_portfolio_summary = chunk_result.portfolio_qualitative_summary
            except Exception as e:
                msg = f"Chunk {idx + 1}/{len(chunks)} failed: {e}"
                logger.error(msg, exc_info=True)
                chunk_errors.append(msg)

            if idx < len(chunks) - 1:
                time.sleep(INTER_CHUNK_SLEEP)

    if not all_evaluations and chunk_errors:
        console.print("[red]ERROR: All chunks failed. Check API logs.[/]")
        for err in chunk_errors:
            console.print(f"  [red]• {err}[/]")
        raise typer.Exit(1)

    # Reconstruct result with ORIGINAL composite hash (never from a chunk response)
    result = ThesisScreenerResponse(
        bundle_hash=composite["composite_hash"],
        analysis_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        evaluations=all_evaluations,
        thesis_violations=list(dict.fromkeys(all_thesis_violations)),   # dedup, preserve order
        watchlist_downgrades=list(dict.fromkeys(all_watchlist_downgrades)),
        portfolio_qualitative_summary=(
            first_portfolio_summary or "See individual position evaluations."
        ),
        tickers_skipped=tickers_skipped,  # Python-computed — always authoritative
    )
    if chunk_errors:
        console.print(f"[yellow]! {len(chunk_errors)} chunk error(s): {chunk_errors}[/]")
    # --- END CHUNKED EXECUTION ---

    # Overwrite tickers_skipped with Python-computed list (LLM cannot know this from context)
    result.tickers_skipped = tickers_skipped

    # --- Rich summary ---
    summary = Table(title="Thesis Screener — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Analyzed At", result.analysis_timestamp_utc)
    summary.add_row("Positions Evaluated", str(len(result.evaluations)))
    summary.add_row("Thesis Violations", f"[bold red]{len(result.thesis_violations)}[/]" if result.thesis_violations else "0")
    summary.add_row("Watchlist Downgrades", f"[yellow]{len(result.watchlist_downgrades)}[/]" if result.watchlist_downgrades else "0")
    summary.add_row("Tickers Skipped", str(len(result.tickers_skipped)))
    console.print(summary)

    if result.evaluations:
        rec_colors = {
            "MAINTAIN_CONVICTION": "dim",
            "WATCHLIST_DOWNGRADE": "yellow",
            "THESIS_VIOLATED": "bold red",
        }
        eval_table = Table(title="Evaluation Results", show_header=True)
        eval_table.add_column("Ticker", style="bold")
        eval_table.add_column("Candor")
        eval_table.add_column("Stewardship")
        eval_table.add_column("Alignment")
        eval_table.add_column("Scorecard")
        eval_table.add_column("Recommendation")
        for ev in result.evaluations:
            color = rec_colors.get(ev.final_recommendation, "white")
            # Extract lead word only for table display
            candor_lead = ev.linguistic_candor_score.split()[0] if ev.linguistic_candor_score else "—"
            steward_lead = ev.capital_stewardship_score.split()[0] if ev.capital_stewardship_score else "—"
            align_lead = ev.alignment_score.split()[0] if ev.alignment_score else "—"
            scorecard_lead = "INNER" if "INNER" in ev.inner_scorecard_assessment.upper() else "OUTER"
            eval_table.add_row(
                ev.ticker,
                candor_lead,
                steward_lead,
                align_lead,
                scorecard_lead,
                f"[{color}]{ev.final_recommendation}[/]",
            )
        console.print(eval_table)

    if result.thesis_violations:
        console.print(f"\n[bold red]THESIS VIOLATIONS:[/] {', '.join(result.thesis_violations)}")
    if result.watchlist_downgrades:
        console.print(f"[yellow]WATCHLIST:[/] {', '.join(result.watchlist_downgrades)}")
    if result.portfolio_qualitative_summary:
        console.print(f"\n[dim]Portfolio summary:[/] {result.portfolio_qualitative_summary}")

    # --- Write local audit files ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = str(uuid.uuid4())

    json_path = AGENT_OUTPUT_DIR / f"thesis_output_{result.bundle_hash[:12]}.json"
    json_path.write_text(json.dumps(result.model_dump(), indent=2))

    if not live:
        console.print(f"\n[dim]DRY RUN — output written to:[/]")
        console.print(f"  {json_path}")
        return

    # --- Live: write to Agent_Outputs tab ---
    from utils.sheet_readers import get_gspread_client

    sheet_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run=False)
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    _archive_and_overwrite(ss, sheet_rows, run_ts)
    console.print(f"[dim]Local audit file:[/] {json_path}")


if __name__ == "__main__":
    app()
