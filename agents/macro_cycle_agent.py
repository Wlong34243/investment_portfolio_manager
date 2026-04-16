"""
Macro-Cycle Rotation Agent — Carlota Perez framework + ATR stop-loss triggers.

Phase 5-D port. The yfinance ATR violation has been moved to tasks/enrich_atr.py.
This agent reads pre-computed `calculated_technical_stops` from the composite bundle.

Pre-computation in Python (never delegated to LLM):
  - ATR stop-loss levels: from tasks/enrich_atr.py → composite["calculated_technical_stops"]
  - pct_from_stop: (current_price - stop_loss) / current_price
  - is_triggered: current_price < stop_loss_level (passed as context fact, not a field in schema)

Gemini writes: paradigm_phase, maturity_signals, final_recommendation,
fundamental_reason_to_sell, technical_trigger_summary, portfolio_cycle_summary,
rotation_targets.

CLI:
    python manager.py agent macro analyze
    python manager.py agent macro analyze --bundle bundles/composite_20260413_....json
    python manager.py agent macro analyze --live

Pre-port fix to run first:
    python tasks/enrich_atr.py          # or: python manager.py snapshot --enrich-atr
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

logger = logging.getLogger(__name__)

app = typer.Typer(help="Macro-Cycle Rotation Agent — Carlota Perez framework + ATR stops")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "macro"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "macro_cycle_system.txt"

# Carlota Perez framework — loaded from agents dir as context for the LLM
_FRAMEWORK_PATH = Path(__file__).parent / "macro_super_cycle.json"

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]

# Map recommendation to scale_step language for the Agent_Outputs tab
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
# Sheet write helpers
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
        rationale = p.fundamental_reason_to_sell[:300]
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "macro_cycle",
            p.ticker,
            action,
            rationale,
            action[:120],
            severity,
            dry_str,
        ])

    # Portfolio-level summary row
    rows.append([
        run_id, run_ts, composite_hash_short, AGENT_NAME,
        "portfolio_summary", "PORTFOLIO",
        f"Rotation targets: {', '.join(result.rotation_targets[:3])}",
        result.portfolio_cycle_summary[:300],
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

def _build_macro_chunk_prompt(chunk_positions_context: list[dict], ctx: dict) -> str:
    """Builds the user prompt for a single chunk of positions."""
    atr_status = ctx["atr_status"]
    framework_context = ctx["framework_context"]
    composite_hash = ctx["composite_hash"]
    return (
        f"Evaluate {len(chunk_positions_context)} portfolio positions through the Carlota Perez "
        f"techno-economic super-cycle framework.\n\n"
        f"## Carlota Perez Framework Reference\n"
        f"{framework_context}\n\n"
        f"## Pre-Computed ATR Stops Status\n"
        f"{atr_status}\n\n"
        f"## Portfolio Positions + ATR Context (pre-computed — use exact numbers)\n"
        f"{json.dumps(chunk_positions_context, indent=2, default=str)}\n\n"
        f"## Instructions\n"
        "For each position:\n"
        "  - Assign paradigm_phase: installation | frenzy | synergy | maturity | unknown\n"
        "  - List maturity_signals observed (from the framework's sell triggers list)\n"
        "  - Assign final_recommendation: HOLD | TRIM_25PCT | TRIM_50PCT | EXIT | MONITOR\n"
        "    Use TRIM_25PCT/TRIM_50PCT for partial exits — never raw 'trim' or 'sell'\n"
        "  - Set rotation_priority: high | medium | low\n"
        "  - Write fundamental_reason_to_sell (2-3 sentences; use 'N/A — continue holding' if no sell signals)\n"
        "  - Write technical_trigger_summary based on atr_stop.is_triggered\n"
        "  - If atr_stop is not null, the stop_loss field in your output MUST use the pre-computed values\n\n"
        "Write portfolio_cycle_summary (3-5 sentences) on overall paradigm positioning.\n"
        "Return rotation_targets: 3-5 tickers or ETFs for capital redeployment.\n\n"
        f"bundle_hash (MUST echo in your response): {composite_hash}\n\n"
        "Produce a MacroCycleResponse JSON object."
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
        None,
        "--ticker",
        help="Comma-separated list of tickers to analyze (e.g. UNH,GOOG). Default: all.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write output to Agent_Outputs Sheet tab. Default: dry run.",
    ),
):
    """
    Carlota Perez macro-cycle analysis per position, using pre-computed ATR stops.

    Run `python tasks/enrich_atr.py` first to inject ATR stops into the composite bundle.
    Without enrichment, the agent runs without technical stop data (Gemini notified).
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

    # --- Load market sub-bundle ---
    market = load_bundle(Path(composite["market_bundle_path"]))
    investable = [
        p for p in market["positions"]
        if p.get("ticker") not in config.CASH_TICKERS
    ]
    
    # Filter investable if ticker subset requested
    if ticker:
        ticker_list = [t.strip().upper() for t in ticker.split(",")]
        investable = [p for p in investable if p.get("ticker") in ticker_list]
        console.print(f"[dim]Ticker subset mode: {ticker_list}[/]")

    total_value = market.get("total_value", 0.0)

    console.print(f"[dim]{len(investable)} investable positions | portfolio ${total_value:,.0f}[/]")

    # --- Read pre-computed ATR stops ---
    atr_stops_raw: list[dict] = composite.get("calculated_technical_stops", [])
    atr_enriched = bool(atr_stops_raw)

    if not atr_enriched:
        console.print(
            "[yellow]! No ATR stops found in composite bundle. "
            "Run `python tasks/enrich_atr.py` first for technical stop data. "
            "Agent will reason from fundamentals only.[/]"
        )
    else:
        console.print(f"[dim]{len(atr_stops_raw)} ATR stop(s) loaded from bundle.[/]")
        # Flag triggered positions (current_price < stop_loss_level)
        triggered = [
            s["ticker"] for s in atr_stops_raw
            if s.get("current_price", 0) < s.get("stop_loss_level", 0)
        ]
        if triggered:
            console.print(f"[bold red]! ATR TRIGGERED: {triggered}[/]")

    # Build ATR map keyed by ticker for prompt assembly
    atr_map: dict[str, dict] = {s["ticker"]: s for s in atr_stops_raw}

    # --- Load Carlota Perez framework JSON ---
    framework_context = ""
    if _FRAMEWORK_PATH.exists():
        try:
            framework_context = _FRAMEWORK_PATH.read_text(encoding="utf-8")
        except Exception:
            framework_context = ""

    # --- Load thesis snippets for each investable position ---
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))
    thesis_map = {
        doc["ticker"]: doc.get("content", "")[:300]
        for doc in vault["documents"]
        if doc.get("doc_type") == "thesis" and doc.get("thesis_present")
    }

    # --- Build position context for prompt ---
    positions_context = []
    for pos in investable:
        ticker = pos.get("ticker", "")
        entry = {
            "ticker": ticker,
            "price": pos.get("price"),
            "market_value": pos.get("market_value"),
            "asset_class": pos.get("asset_class"),
            "weight_pct": round(
                float(pos.get("market_value", 0) or 0) / total_value * 100, 2
            ) if total_value > 0 else 0.0,
            "thesis_snippet": thesis_map.get(ticker, ""),
        }
        if ticker in atr_map:
            s = atr_map[ticker]
            entry["atr_stop"] = {
                "atr_14": s["atr_14"],
                "stop_loss_level": s["stop_loss_level"],
                "pct_from_stop": s["pct_from_stop"],
                "is_triggered": s["current_price"] < s["stop_loss_level"],
            }
        else:
            entry["atr_stop"] = None
        positions_context.append(entry)

    # --- System prompt ---
    system_prompt_text = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _SYSTEM_PROMPT_PATH.exists()
        else ""
    )

    # --- ATR status string for prompt ---
    atr_status = (
        f"{len(atr_stops_raw)} ATR stops pre-computed (Python). "
        f"is_triggered = current_price < stop_loss_level."
        if atr_enriched
        else "ATR enrichment was NOT run. Set technical_trigger_summary to 'No ATR data available' for all positions."
    )

    # --- Call Gemini — CHUNKED EXECUTION ---
    chunks = [
        positions_context[i : i + CHUNK_SIZE]
        for i in range(0, len(positions_context), CHUNK_SIZE)
    ]
    console.print(
        f"[cyan]Calling Gemini on {len(investable)} positions "
        f"(chunked, {CHUNK_SIZE} per batch)...[/]"
    )

    portfolio_context_for_prompt = {
        "atr_status": atr_status,
        "framework_context": framework_context,
        "composite_hash": composite["composite_hash"],
    }

    all_positions_analyzed: list = []
    all_rotation_targets: list = []
    first_portfolio_summary: str | None = None
    chunk_errors: list[str] = []

    with console.status("[cyan]Analyzing in chunks..."):
        for idx, chunk in enumerate(chunks):
            tickers_in_chunk = [p["ticker"] for p in chunk]
            logger.info("Chunk %d/%d: %s", idx + 1, len(chunks), tickers_in_chunk)
            try:
                chunk_prompt = _build_macro_chunk_prompt(chunk, portfolio_context_for_prompt)
                chunk_result: MacroCycleResponse | None = ask_gemini_composite(
                    prompt=chunk_prompt,
                    composite_bundle_path=bundle_path,
                    response_schema=MacroCycleResponse,
                    system_instruction=system_prompt_text,
                    max_tokens=config.GEMINI_MAX_TOKENS_MACRO,
                )
                if chunk_result is None:
                    msg = f"Chunk {idx + 1}/{len(chunks)} ({tickers_in_chunk}): Gemini returned None"
                    logger.warning(msg)
                    chunk_errors.append(msg)
                else:
                    all_positions_analyzed.extend(chunk_result.positions_analyzed)
                    all_rotation_targets.extend(chunk_result.rotation_targets)
                    if first_portfolio_summary is None and chunk_result.portfolio_cycle_summary:
                        first_portfolio_summary = chunk_result.portfolio_cycle_summary
            except Exception as e:
                msg = f"Chunk {idx + 1}/{len(chunks)} failed: {e}"
                logger.error(msg, exc_info=True)
                chunk_errors.append(msg)

            if idx < len(chunks) - 1:
                time.sleep(INTER_CHUNK_SLEEP)

    if not all_positions_analyzed and chunk_errors:
        console.print("[red]ERROR: All chunks failed. Check API logs.[/]")
        for err in chunk_errors:
            console.print(f"  [red]• {err}[/]")
        raise typer.Exit(1)

    # Reconstruct result with ORIGINAL composite hash (never from a chunk response)
    result = MacroCycleResponse(
        bundle_hash=composite["composite_hash"],
        analysis_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        positions_analyzed=all_positions_analyzed,
        rotation_targets=list(set(all_rotation_targets)),
        portfolio_cycle_summary=(
            first_portfolio_summary or "See individual position analyses."
        ),
    )
    if chunk_errors:
        console.print(f"[yellow]! {len(chunk_errors)} chunk error(s): {chunk_errors}[/]")
    # --- END CHUNKED EXECUTION ---

    # --- Overwrite ATRStopLoss fields with pre-computed Python values ---
    # LLM may reconstruct stop_loss values from context; overwrite to guarantee accuracy.
    for pos_analysis in result.positions_analyzed:
        ticker = pos_analysis.ticker
        if ticker in atr_map:
            s = atr_map[ticker]
            pos_analysis.stop_loss = ATRStopLoss(
                ticker=ticker,
                atr_14=s["atr_14"],
                stop_loss_level=s["stop_loss_level"],
                current_price=s["current_price"],
                pct_from_stop=s["pct_from_stop"],
            )
        else:
            pos_analysis.stop_loss = None

    # --- Rich summary ---
    summary = Table(title="Macro-Cycle Agent — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Analyzed At", result.analysis_timestamp_utc)
    summary.add_row("Positions Analyzed", str(len(result.positions_analyzed)))
    summary.add_row("ATR Enriched", "yes" if atr_enriched else "[yellow]no[/]")
    summary.add_row("Rotation Targets", ", ".join(result.rotation_targets[:5]))
    console.print(summary)

    if result.positions_analyzed:
        rec_colors = {
            "HOLD": "dim", "MONITOR": "dim",
            "TRIM_25PCT": "yellow", "TRIM_50PCT": "bold yellow",
            "EXIT": "bold red",
        }
        phase_table = Table(title="Position Analysis", show_header=True)
        phase_table.add_column("Ticker", style="bold")
        phase_table.add_column("Phase")
        phase_table.add_column("ATR Stop")
        phase_table.add_column("Triggered?")
        phase_table.add_column("Recommendation")
        phase_table.add_column("Priority")
        for p in result.positions_analyzed:
            atr_s = atr_map.get(p.ticker, {})
            stop_str = f"${atr_s.get('stop_loss_level', 0):.2f}" if atr_s else "—"
            trig_str = "[bold red]YES[/]" if (
                atr_s and atr_s.get("current_price", 0) < atr_s.get("stop_loss_level", 0)
            ) else "no"
            color = rec_colors.get(p.final_recommendation, "white")
            phase_table.add_row(
                p.ticker,
                p.paradigm_phase,
                stop_str,
                trig_str,
                f"[{color}]{p.final_recommendation}[/]",
                p.rotation_priority,
            )
        console.print(phase_table)

    if result.portfolio_cycle_summary:
        console.print(f"\n[dim]Cycle summary:[/] {result.portfolio_cycle_summary}")

    # --- Write local audit files ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = str(uuid.uuid4())

    json_path = AGENT_OUTPUT_DIR / f"macro_output_{result.bundle_hash[:12]}.json"
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
