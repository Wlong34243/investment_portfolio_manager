"""
Value Investing Screener Agent — Graham / Buffett / Browne Framework.

Phase 5-G port. Evaluates each portfolio position against the Benjamin Graham
defensive investor criteria and Warren Buffett quality overlay.

Pre-computation in Python (never delegated to LLM):
  - pe_ratio:           yfinance trailingPE → FMP key-metrics-ttm cache
  - pb_ratio:           yfinance priceToBook → FMP fallback
  - current_ratio:      yfinance currentRatio
  - roe_pct:            yfinance returnOnEquity (raw fraction → %) → FMP ROE
  - debt_to_equity:     yfinance debtToEquity / 100 (yfinance reports x100) → FMP
  - graham_number_prd:  pe_ratio * pb_ratio (Python — never LLM)
  - gate pass/fail per rule (pe_graham, pb_graham, graham_number, current_ratio,
                             roe_buffett, debt_equity)

Gemini receives pre-computed metrics + pass/fail flags and writes narrative only.

Strategy thresholds: agents/value_investing_strategy.json

CLI:
    python manager.py agent value analyze
    python manager.py agent value analyze --ticker AAPL,BA
    python manager.py agent value analyze --bundle bundles/composite_*.json
    python manager.py agent value analyze --live
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
from agents.schemas.value_investing_schema import ValueInvestingCandidate, ValueInvestingResponse
from agents.utils.chunked_analysis import CHUNK_SIZE, INTER_CHUNK_SLEEP
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from utils.gemini_client import ask_gemini_composite

logger = logging.getLogger(__name__)

app = typer.Typer(help="Value Investing Screener — Graham / Buffett / Browne framework")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "value"

_STRATEGY_PATH  = Path(__file__).parent / "value_investing_strategy.json"
_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "value_investing_system.txt"

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]

_REC_TO_SEVERITY = {
    "DEEP_VALUE":    "action",
    "VALUE_WATCH":   "watch",
    "FAIRLY_VALUED": "info",
    "REJECT":        "info",
}

_REC_TO_ACTION = {
    "DEEP_VALUE":    "Evaluate entry — margin of safety present on Graham + Buffett gates",
    "VALUE_WATCH":   "Monitor for better entry — approaching value territory",
    "FAIRLY_VALUED": "Hold — fairly priced, no meaningful discount to intrinsic value",
    "REJECT":        "Avoid adding — overvalued or fundamentally impaired at current price",
}


# ---------------------------------------------------------------------------
# Strategy loader
# ---------------------------------------------------------------------------

def _load_strategy() -> dict:
    if not _STRATEGY_PATH.exists():
        logger.warning("value_investing_strategy.json not found; using defaults.")
        return {
            "margin_of_safety_pct": 33.33,
            "graham_criteria": {
                "max_pe_ratio": 10.0,
                "max_pb_ratio": 0.66,
                "min_current_ratio": 2.0,
            },
            "buffett_criteria": {
                "min_roe_pct": 0.0,
                "max_debt_to_equity": 1.0,
            },
        }
    try:
        return json.loads(_STRATEGY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to load strategy JSON: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pct(value) -> float | None:
    """Convert raw fraction (0.15) to percentage (15.0). None if unavailable."""
    if value is None:
        return None
    try:
        f = float(value)
        return round(f * 100, 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------

def _evaluate_gates(
    pe_ratio: float | None,
    pb_ratio: float | None,
    current_ratio: float | None,
    roe_pct: float | None,
    de_ratio: float | None,
    strategy: dict,
) -> tuple[list[str], list[str]]:
    """
    Evaluate the 6 Graham / Buffett value gates.

    yfinance debtToEquity is reported as a percentage (e.g., 150.0 = 1.5x).
    de_ratio must already be normalized to a ratio (de_raw / 100) before calling.

    Returns (gates_passed, gates_failed).
    """
    graham = strategy.get("graham_criteria", {})
    buffett = strategy.get("buffett_criteria", {})

    max_pe = graham.get("max_pe_ratio", 10.0)
    max_pb = graham.get("max_pb_ratio", 0.66)
    min_cr = graham.get("min_current_ratio", 2.0)
    min_roe = max(buffett.get("min_roe_pct", 0.0), 10.0)  # floor at 10% for a meaningful quality gate
    max_de = buffett.get("max_debt_to_equity", 1.0)
    graham_number_ceiling = 22.5

    passed = []
    failed = []

    # PE Graham gate
    if pe_ratio is not None and pe_ratio > 0:
        (passed if pe_ratio <= max_pe else failed).append("pe_graham")

    # P/B Graham gate (strict Grahamian criterion)
    if pb_ratio is not None and pb_ratio > 0:
        (passed if pb_ratio <= max_pb else failed).append("pb_graham")

    # Graham Number product (PE × PB < 22.5) — more practical composite gate
    if pe_ratio is not None and pb_ratio is not None and pe_ratio > 0 and pb_ratio > 0:
        gn_product = pe_ratio * pb_ratio
        (passed if gn_product <= graham_number_ceiling else failed).append("graham_number")

    # Current ratio gate
    if current_ratio is not None:
        (passed if current_ratio >= min_cr else failed).append("current_ratio")

    # ROE Buffett gate
    if roe_pct is not None:
        (passed if roe_pct >= min_roe else failed).append("roe_buffett")

    # Debt / equity gate
    if de_ratio is not None:
        (passed if de_ratio <= max_de else failed).append("debt_equity")

    return passed, failed


# ---------------------------------------------------------------------------
# Pre-computation pipeline
# ---------------------------------------------------------------------------

def _compute_value_facts(
    positions: list[dict],
    ticker_filter: Optional[list[str]],
    strategy: dict,
) -> tuple[list[dict], list[str]]:
    """
    For each investable position (non-cash, optionally filtered), fetch
    Graham + Buffett metrics and evaluate gates.

    Data source priority (via utils.fmp_client.get_fundamentals):
      Tier 0 — Schwab bundle_quote (pe)
      Tier 1 — yfinance info (pe, pb, current_ratio, roe, de, gross_margin)
      Tier 2 — FMP key-metrics-ttm 7-day file cache (pe, roe, de fallback)

    Returns (positions_with_facts, data_gaps).
    """
    facts = []
    data_gaps = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        if not ticker:
            continue
        if ticker_filter and ticker not in ticker_filter:
            continue

        fundamentals = pos.get("fundamentals", {})

        pe_ratio     = fundamentals.get("trailing_pe")
        pb_ratio     = fundamentals.get("pb_ratio")
        current_ratio = fundamentals.get("current_ratio")

        # ROE: get_fundamentals returns it as a raw fraction (0.15 = 15%)
        roe_raw = fundamentals.get("roic")
        roe_pct = _safe_pct(roe_raw)

        # D/E: yfinance debtToEquity is x100 (e.g., 150 = 1.5x); normalize to ratio
        de_raw = fundamentals.get("debt_to_equity")
        de_ratio = round(de_raw / 100.0, 3) if de_raw is not None else None

        # Graham Number product (Python-computed)
        graham_number_product = None
        if pe_ratio is not None and pb_ratio is not None and pe_ratio > 0 and pb_ratio > 0:
            graham_number_product = round(pe_ratio * pb_ratio, 2)

        if all(v is None for v in [pe_ratio, pb_ratio, roe_pct, de_ratio]):
            data_gaps.append(ticker)

        gates_passed, gates_failed = _evaluate_gates(
            pe_ratio, pb_ratio, current_ratio, roe_pct, de_ratio, strategy
        )

        total_value = float(pos.get("_total_value", 1) or 1)
        weight_pct = round(
            float(pos.get("market_value", 0) or 0) / total_value * 100, 2
        )

        facts.append({
            "ticker":                ticker,
            "pe_ratio":              pe_ratio,
            "pb_ratio":              pb_ratio,
            "current_ratio":         current_ratio,
            "roe_pct":               roe_pct,
            "debt_to_equity_ratio":  de_ratio,
            "graham_number_product": graham_number_product,
            "weight_pct":            weight_pct,
            "sector":                fundamentals.get("sector", ""),
            "gates_passed":          gates_passed,
            "gates_failed":          gates_failed,
        })

    return facts, data_gaps


# ---------------------------------------------------------------------------
# Sheet write helpers
# ---------------------------------------------------------------------------

def _result_to_sheet_rows(
    result: ValueInvestingResponse,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for c in result.candidates_analyzed:
        action   = _REC_TO_ACTION.get(c.final_recommendation, c.final_recommendation)
        severity = _REC_TO_SEVERITY.get(c.final_recommendation, "info")
        rationale = f"{c.fundamental_reason[:200]} | {c.margin_of_safety_assessment[:100]}"
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "value_screen",
            c.ticker,
            action,
            rationale[:800],
            action[:120],
            severity,
            dry_str,
        ])

    rows.append([
        run_id, run_ts, composite_hash_short, AGENT_NAME,
        "portfolio_summary", "PORTFOLIO",
        f"Deep value: {', '.join(result.deep_value_candidates[:5]) or 'none'}",
        result.summary_narrative[:800],
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
# Prompt builder
# ---------------------------------------------------------------------------

def _build_value_chunk_prompt(chunk_facts: list[dict], ctx: dict) -> str:
    strategy_context = ctx["strategy_context"]
    composite_hash = ctx["composite_hash"]
    chunk_data_gaps = [f["ticker"] for f in chunk_facts
                       if f.get("pe_ratio") is None and f.get("pb_ratio") is None]
    return (
        f"Screen {len(chunk_facts)} portfolio position(s) against the Benjamin Graham "
        f"defensive investor framework and Warren Buffett quality overlay.\n\n"
        f"## Value Investing Strategy Reference\n"
        f"{strategy_context}\n\n"
        f"## Pre-Computed Quantitative Gate Results (Python — use exact values)\n"
        f"{json.dumps(chunk_facts, indent=2, default=str)}\n\n"
        f"## Instructions\n"
        "For each position, write the narrative evaluation fields. "
        "gates_passed and gates_failed are already computed — echo them exactly.\n\n"
        "Note: the pb_graham gate uses Graham's strict 0.66 ceiling. Most growth stocks "
        "and quality compounders will fail this gate. That is expected and informative — "
        "FAIRLY_VALUED ≠ 'bad investment'. REJECT is reserved for overvalued or impaired positions.\n\n"
        "Write summary_narrative (3-5 sentences) on portfolio-level value assessment: "
        "what fraction of holdings trade at a discount, which sectors offer the most value, "
        "and whether the portfolio leans toward value or growth at current prices.\n"
        "Return deep_value_candidates and value_watch_candidates as ordered ticker lists.\n"
        f"data_gaps (Python-detected, missing fundamental data): {chunk_data_gaps}\n\n"
        f"bundle_hash (MUST echo in your response): {composite_hash}\n\n"
        "Produce a ValueInvestingResponse JSON object."
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
        help="Screen specific tickers (comma-separated). Omit for all positions.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write output to Agent_Outputs Sheet tab. Default: dry run.",
    ),
):
    """
    Value screener — Graham + Buffett gates on all holdings.

    Pre-computes PE, P/B, current ratio, ROE, and D/E per position via yfinance/FMP.
    Gemini writes narrative rationale; Python determines gate pass/fail.

    Note: the strict Graham P/B gate (< 0.66) will reject most growth stocks —
    that is expected. The Graham Number (PE × PB < 22.5) is the more practical
    composite gate. Use DEEP_VALUE and VALUE_WATCH as actionable signals.
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

    # --- Load strategy thresholds ---
    strategy = _load_strategy()
    console.print(
        f"[dim]Strategy loaded: PE ≤ {strategy.get('graham_criteria', {}).get('max_pe_ratio', 10.0)}, "
        f"P/B ≤ {strategy.get('graham_criteria', {}).get('max_pb_ratio', 0.66)}, "
        f"CR ≥ {strategy.get('graham_criteria', {}).get('min_current_ratio', 2.0)}, "
        f"D/E ≤ {strategy.get('buffett_criteria', {}).get('max_debt_to_equity', 1.0)}[/]"
    )

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

    # --- Load composite and market sub-bundle ---
    composite = load_composite_bundle(bundle_path)
    console.print(f"[dim]Composite hash: {composite['composite_hash'][:16]}...[/]")

    market = load_bundle(Path(composite["market_bundle_path"]))
    investable = [
        p for p in market["positions"]
        if p.get("ticker") not in config.CASH_TICKERS
    ]
    total_value = market.get("total_value", 0.0)
    for p in investable:
        p["_total_value"] = total_value

    console.print(f"[dim]{len(investable)} investable positions | portfolio ${total_value:,.0f}[/]")

    # --- Apply ticker filter ---
    ticker_filter: Optional[list[str]] = None
    if ticker:
        ticker_filter = [t.strip().upper() for t in ticker.split(",")]
        console.print(f"[dim]Ticker filter: {ticker_filter}[/]")

    # --- Python pre-computation ---
    console.print("[cyan]Fetching fundamentals and evaluating Graham / Buffett gates...[/]")
    with console.status("[cyan]Computing PE, P/B, current ratio, ROE, D/E..."):
        positions_facts, data_gaps = _compute_value_facts(investable, ticker_filter, strategy)

    if not positions_facts:
        console.print("[yellow]No positions after filter / data fetch. Check --ticker or API key.[/]")
        raise typer.Exit(0)

    # Gate summary to console before Gemini call
    n_pe_pass  = sum(1 for p in positions_facts if "pe_graham"    in p["gates_passed"])
    n_gn_pass  = sum(1 for p in positions_facts if "graham_number" in p["gates_passed"])
    n_roe_pass = sum(1 for p in positions_facts if "roe_buffett"  in p["gates_passed"])
    console.print(
        f"[dim]Gate summary: {n_pe_pass}/{len(positions_facts)} pass PE "
        f"| {n_gn_pass}/{len(positions_facts)} pass Graham Number "
        f"| {n_roe_pass}/{len(positions_facts)} pass ROE[/]"
    )
    if data_gaps:
        console.print(f"[yellow]! Missing fundamental data for: {data_gaps[:10]}[/]")

    # --- Load system prompt and strategy context ---
    system_prompt_text = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _SYSTEM_PROMPT_PATH.exists()
        else ""
    )
    strategy_context = json.dumps(strategy, indent=2)

    # --- Chunked Gemini execution ---
    chunks = [
        positions_facts[i : i + CHUNK_SIZE]
        for i in range(0, len(positions_facts), CHUNK_SIZE)
    ]
    console.print(
        f"[cyan]Calling Gemini on {len(positions_facts)} position(s) "
        f"(chunked, {CHUNK_SIZE} per batch)...[/]"
    )

    prompt_ctx = {
        "strategy_context": strategy_context,
        "composite_hash": composite["composite_hash"],
    }

    all_candidates: list = []
    all_deep_value: list = []
    all_value_watch: list = []
    first_summary: str | None = None
    chunk_errors: list[str] = []

    with console.status("[cyan]Evaluating value gates in chunks..."):
        for idx, chunk in enumerate(chunks):
            tickers_in_chunk = [p["ticker"] for p in chunk]
            logger.info("Chunk %d/%d: %s", idx + 1, len(chunks), tickers_in_chunk)
            try:
                chunk_prompt = _build_value_chunk_prompt(chunk, prompt_ctx)
                chunk_result: ValueInvestingResponse | None = ask_gemini_composite(
                    prompt=chunk_prompt,
                    composite_bundle_path=bundle_path,
                    response_schema=ValueInvestingResponse,
                    system_instruction=system_prompt_text,
                    max_tokens=8000,
                )
                if chunk_result is None:
                    msg = f"Chunk {idx + 1}/{len(chunks)} ({tickers_in_chunk}): Gemini returned None"
                    logger.warning(msg)
                    chunk_errors.append(msg)
                else:
                    all_candidates.extend(chunk_result.candidates_analyzed)
                    all_deep_value.extend(chunk_result.deep_value_candidates)
                    all_value_watch.extend(chunk_result.value_watch_candidates)
                    if first_summary is None and chunk_result.summary_narrative:
                        first_summary = chunk_result.summary_narrative
            except Exception as e:
                msg = f"Chunk {idx + 1}/{len(chunks)} failed: {e}"
                logger.error(msg, exc_info=True)
                chunk_errors.append(msg)

            if idx < len(chunks) - 1:
                time.sleep(INTER_CHUNK_SLEEP)

    if not all_candidates and chunk_errors:
        console.print("[red]ERROR: All chunks failed. Check API logs.[/]")
        for err in chunk_errors:
            console.print(f"  [red]• {err}[/]")
        raise typer.Exit(1)

    # Reconstruct result using original composite hash (never a chunk hash)
    result = ValueInvestingResponse(
        bundle_hash=composite["composite_hash"],
        analysis_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        candidates_analyzed=all_candidates,
        deep_value_candidates=list(dict.fromkeys(all_deep_value)),
        value_watch_candidates=list(dict.fromkeys(all_value_watch)),
        summary_narrative=first_summary or "See individual position analyses.",
        data_gaps=data_gaps,
    )
    if chunk_errors:
        console.print(f"[yellow]! {len(chunk_errors)} chunk error(s): {chunk_errors}[/]")

    # Overwrite gates with Python-authoritative values
    facts_map = {f["ticker"]: f for f in positions_facts}
    for cand in result.candidates_analyzed:
        fact = facts_map.get(cand.ticker)
        if fact:
            cand.gates_passed = fact["gates_passed"]
            cand.gates_failed = fact["gates_failed"]

    # --- Rich summary table ---
    summary = Table(title="Value Investing Screener — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Analyzed At", result.analysis_timestamp_utc)
    summary.add_row("Positions Screened", str(len(result.candidates_analyzed)))
    summary.add_row(
        "Deep Value",
        f"[bold green]{len(result.deep_value_candidates)}[/]"
        if result.deep_value_candidates else "0",
    )
    summary.add_row(
        "Value Watch",
        f"[yellow]{len(result.value_watch_candidates)}[/]"
        if result.value_watch_candidates else "0",
    )
    summary.add_row("Data Gaps", str(len(result.data_gaps)))
    console.print(summary)

    if result.candidates_analyzed:
        rec_colors = {
            "DEEP_VALUE":    "bold green",
            "VALUE_WATCH":   "yellow",
            "FAIRLY_VALUED": "dim",
            "REJECT":        "red dim",
        }
        screen_table = Table(title="Gate Results", show_header=True)
        screen_table.add_column("Ticker", style="bold")
        screen_table.add_column("PE")
        screen_table.add_column("P/B")
        screen_table.add_column("GN Prod")
        screen_table.add_column("Curr Ratio")
        screen_table.add_column("ROE %")
        screen_table.add_column("D/E")
        screen_table.add_column("Gates")
        screen_table.add_column("Verdict")
        for cand in result.candidates_analyzed:
            fact = facts_map.get(cand.ticker, {})
            color = rec_colors.get(cand.final_recommendation, "white")
            screen_table.add_row(
                cand.ticker,
                f"{fact['pe_ratio']:.1f}"   if fact.get("pe_ratio")  else "N/A",
                f"{fact['pb_ratio']:.2f}"   if fact.get("pb_ratio")  else "N/A",
                f"{fact['graham_number_product']:.1f}" if fact.get("graham_number_product") else "N/A",
                f"{fact['current_ratio']:.1f}" if fact.get("current_ratio") else "N/A",
                f"{fact['roe_pct']:.1f}%"   if fact.get("roe_pct")   else "N/A",
                f"{fact['debt_to_equity_ratio']:.2f}" if fact.get("debt_to_equity_ratio") else "N/A",
                f"{len(cand.gates_passed)}/6",
                f"[{color}]{cand.final_recommendation}[/]",
            )
        console.print(screen_table)

    if result.deep_value_candidates:
        console.print(f"\n[bold green]DEEP VALUE:[/] {', '.join(result.deep_value_candidates)}")
    if result.value_watch_candidates:
        console.print(f"[yellow]VALUE WATCH:[/] {', '.join(result.value_watch_candidates)}")
    if result.summary_narrative:
        console.print(f"\n[dim]Portfolio summary:[/] {result.summary_narrative}")

    # --- Write local audit JSON ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = str(uuid.uuid4())

    json_path = AGENT_OUTPUT_DIR / f"value_output_{result.bundle_hash[:12]}.json"
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
