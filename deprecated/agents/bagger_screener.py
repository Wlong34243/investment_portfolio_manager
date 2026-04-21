"""
100-Bagger Screener Agent — Christopher Mayer Framework.

Phase 5-F port. Evaluates each portfolio position against the Christopher Mayer
quantitative gate for extreme compounder potential (100x over 15-25 years).
"""

import json
import logging
import math
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
from agents.schemas.bagger_schema import BaggerCandidate, BaggerScreenerResponse
from utils.fmp_client import get_fundamentals, get_income_statements_cached
from agents.utils.chunked_analysis import CHUNK_SIZE, INTER_CHUNK_SLEEP
import time as _time
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import archive_and_overwrite_agent_outputs
from utils.formatters import dicts_to_markdown_table

logger = logging.getLogger(__name__)

app = typer.Typer(help="100-Bagger Screener Agent — Christopher Mayer framework")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "bagger"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "bagger_screener_system.txt"
_FRAMEWORK_PATH = Path(__file__).parent.parent / "vault" / "frameworks" / "100_bagger_framework.json"

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]

_REC_TO_SEVERITY = {
    "STRONG_BUY": "action",
    "WATCHLIST":  "watch",
    "REJECT":     "info",
}

_REC_TO_ACTION = {
    "STRONG_BUY": "Evaluate staged entry — strong 100-bagger gate pass",
    "WATCHLIST":  "Monitor for entry — partial gate pass, track progress",
    "REJECT":     "Hold or evaluate — fails 100-bagger acorn/ROIC gate",
}

# Gate thresholds (mirrors vault/frameworks/100_bagger_framework.json)
_ACORN_HARD_CEILING_USD = 2_000_000_000     # $2B hard reject
_ROIC_THRESHOLD_PCT     = 18.0              # pass
_ROIC_MIN_PCT           = 15.0              # hard reject below this
_GROWTH_THRESHOLD_PCT   = 10.0
_MARGIN_THRESHOLD_PCT   = 50.0
_MARGIN_SOFT_PCT        = 30.0
_DIVIDEND_PENALTY_PCT   = 40.0             # not a hard reject


# ---------------------------------------------------------------------------
# Python pre-computation helpers
# ---------------------------------------------------------------------------

def _safe_pct(value) -> float | None:
    """Convert a raw fraction (0.22) to percentage (22.0). None if unavailable."""
    if value is None:
        return None
    try:
        f = float(value)
        return round(f * 100, 2) if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


def _revenue_cagr_3yr(income_stmts: list[dict]) -> float | None:
    """
    Compute 3-year revenue CAGR from annual income statements (newest-first).
    Needs at least 4 periods (year 0 and year 3).
    """
    if len(income_stmts) < 4:
        return None
    try:
        rev_latest = float(income_stmts[0].get("revenue") or 0)
        rev_3yr_ago = float(income_stmts[3].get("revenue") or 0)
        if rev_latest <= 0 or rev_3yr_ago <= 0:
            return None
        cagr = (rev_latest / rev_3yr_ago) ** (1 / 3) - 1
        return round(cagr * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _gross_margin_latest(income_stmts: list[dict]) -> float | None:
    """Latest annual gross margin %."""
    if not income_stmts:
        return None
    try:
        stmt = income_stmts[0]
        gp  = float(stmt.get("grossProfit") or 0)
        rev = float(stmt.get("revenue") or 0)
        if rev <= 0:
            return None
        return round(gp / rev * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _evaluate_gates(
    market_cap_usd: float | None,
    roic_pct: float | None,
    revenue_growth_3yr_cagr_pct: float | None,
    gross_margin_pct: float | None,
    dividend_payout_ratio_pct: float | None,
) -> dict:
    """Return dict of pass/fail flags for each 100-bagger rule."""
    flags = {
        "is_acorn": False,
        "is_roic_pass": False,
        "is_growth_pass": False,
        "is_margin_pass": False,
        "is_dividend_pass": True, # default pass
        "is_hard_reject": False
    }

    if market_cap_usd and market_cap_usd < _ACORN_HARD_CEILING_USD:
        flags["is_acorn"] = True
    elif market_cap_usd and market_cap_usd > _ACORN_HARD_CEILING_USD * 10:
        flags["is_hard_reject"] = True # too big to 100x

    if roic_pct:
        if roic_pct >= _ROIC_THRESHOLD_PCT:
            flags["is_roic_pass"] = True
        elif roic_pct < _ROIC_MIN_PCT:
            flags["is_hard_reject"] = True

    if revenue_growth_3yr_cagr_pct and revenue_growth_3yr_cagr_pct >= _GROWTH_THRESHOLD_PCT:
        flags["is_growth_pass"] = True

    if gross_margin_pct and gross_margin_pct >= _MARGIN_THRESHOLD_PCT:
        flags["is_margin_pass"] = True

    if dividend_payout_ratio_pct and dividend_payout_ratio_pct > _DIVIDEND_PENALTY_PCT:
        flags["is_dividend_pass"] = False

    return flags


def _compute_bagger_facts(
    positions: list[dict],
    ticker_filter: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """
    For each position, compute 100-bagger gate facts.
    """
    facts = []
    data_gaps = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        # Use VALUATION_SKIP (canonical list) — VALUATION_SKIP_TICKERS is legacy/truncated
        _skip_tickers = set(config.CASH_TICKERS) | set(config.VALUATION_SKIP)
        if ticker in _skip_tickers:
            continue
        if ticker_filter and ticker not in ticker_filter:
            continue

        # Secondary guard: skip ETF/fund asset classes (no 100-bagger potential)
        asset_class = (pos.get("asset_class") or pos.get("Asset Class") or "").upper().replace(" ", "_")
        if asset_class in config.VALUATION_SKIP_ASSET_CLASSES:
            continue

        # Fetch pre-computed metrics
        fundamentals = get_fundamentals(ticker)
        income_stmts = get_income_statements_cached(ticker)

        if not fundamentals:
            data_gaps.append(f"{ticker}: fundamentals unavailable")
            continue

        # 3yr CAGR and gross margin fallback to income statements if fundamentals missing them
        roic = _safe_pct(fundamentals.get("returnOnEquity")) # ROE proxy
        rev_growth = _safe_pct(fundamentals.get("revenueGrowth"))
        if rev_growth is None and income_stmts:
             rev_growth = _revenue_cagr_3yr(income_stmts)
        
        gm = _safe_pct(fundamentals.get("grossMargin"))
        if gm is None and income_stmts:
            gm = _gross_margin_latest(income_stmts)

        payout = _safe_pct(fundamentals.get("payoutRatio"))
        mkt_cap = fundamentals.get("marketCap")

        gates = _evaluate_gates(mkt_cap, roic, rev_growth, gm, payout)

        facts.append({
            "ticker": ticker,
            "market_cap_usd": mkt_cap,
            "roic_pct": roic,
            "revenue_growth_3yr_pct": rev_growth,
            "gross_margin_pct": gm,
            "dividend_payout_pct": payout,
            "is_acorn": gates["is_acorn"],
            "is_roic_pass": gates["is_roic_pass"],
            "is_growth_pass": gates["is_growth_pass"],
            "is_margin_pass": gates["is_margin_pass"],
            "is_dividend_pass": gates["is_dividend_pass"],
            "is_hard_reject": gates["is_hard_reject"],
        })

    return facts, data_gaps


def _result_to_sheet_rows(
    result: BaggerScreenerResponse,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    """Serialize BaggerScreenerResponse to Agent_Outputs tab rows."""
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for c in result.candidates_analyzed:
        action = _REC_TO_ACTION.get(c.final_recommendation, c.final_recommendation)
        severity = _REC_TO_SEVERITY.get(c.final_recommendation, "info")
        rationale = f"{c.final_recommendation}: {c.fundamental_reason}"
        
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "bagger_signal", c.ticker, action[:120],
            rationale[:800],
            c.final_recommendation, severity, dry_str,
        ])

    if result.summary_narrative:
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "portfolio_summary", "PORTFOLIO",
            f"Strong buys: {', '.join(result.strong_buy_candidates[:5]) or 'none'}",
            result.summary_narrative[:800],
            "", "info", dry_str,
        ])

    return rows


# ---------------------------------------------------------------------------
# Runner & CLI
# ---------------------------------------------------------------------------

def run_bagger_agent(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    ticker_filter: set[str] | None = None,
    dry_run: bool = True,
) -> tuple[BaggerScreenerResponse, list[list]]:
    """
    Orchestrates the 100-Bagger Screener analysis.
    Returns (result_object, list_of_sheet_rows).
    """
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))

    # --- Pre-computation ---
    with console.status("[cyan]Computing 100-bagger gates..."):
        bagger_facts, data_gaps = _compute_bagger_facts(market["positions"], ticker_filter)

    if not bagger_facts:
        raise RuntimeError("No positions to analyze. Check FMP API and tickers.")

    # --- Build per-chunk prompt helper ---
    system_prompt_text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    framework_text = _FRAMEWORK_PATH.read_text(encoding="utf-8")
    composite_hash = composite["composite_hash"]

    def _build_bagger_prompt(chunk: list[dict]) -> str:
        chunk_table = dicts_to_markdown_table(chunk)
        return (
            f"Evaluate the following {len(chunk)} position(s) against the 100-Bagger Framework.\n\n"
            f"## Christopher Mayer 100-Bagger Framework\n"
            f"{framework_text}\n\n"
            f"## Pre-Computed Gate Facts\n"
            f"{chunk_table}\n\n"
            f"## Instructions\n"
            "1. For each ticker: analyze ROIC, Moat (Gross Margin), Growth, and Size (Acorn).\n"
            "2. Keep each narrative field under 200 characters — concise evaluation, not paragraphs.\n"
            "3. Provide a one-sentence 'fundamental_reason' and a 'final_recommendation'.\n"
            "4. Write a brief summary_narrative covering this chunk only.\n"
            f"5. bundle_hash (MUST echo): {composite_hash}\n"
            "Produce a BaggerScreenerResponse JSON object."
        )

    # --- Manual chunked loop ---
    # BaggerScreenerResponse.candidates_analyzed does not match run_chunked_analysis's
    # result.candidates interface, so we chunk manually like the macro agent.
    chunks = [bagger_facts[i:i + CHUNK_SIZE] for i in range(0, len(bagger_facts), CHUNK_SIZE)]

    all_candidates: list[BaggerCandidate] = []
    all_summaries: list[str] = []
    chunk_errors: list[str] = []

    for idx, chunk in enumerate(chunks):
        tickers_in_chunk = [p["ticker"] for p in chunk]
        logger.info("Bagger chunk %d/%d: %s", idx + 1, len(chunks), tickers_in_chunk)
        try:
            user_prompt = _build_bagger_prompt(chunk)
            chunk_result: BaggerScreenerResponse | None = ask_gemini_composite(
                prompt=user_prompt,
                composite_bundle_path=bundle_path,
                response_schema=BaggerScreenerResponse,
                system_instruction=system_prompt_text,
                max_tokens=config.GEMINI_MAX_TOKENS_BAGGER,
                include_vault_context=False,  # facts pre-computed; vault docs not needed
            )
            if chunk_result is None:
                msg = f"Chunk {idx + 1}/{len(chunks)} ({tickers_in_chunk}): Gemini returned None"
                logger.warning(msg)
                chunk_errors.append(msg)
            else:
                all_candidates.extend(chunk_result.candidates_analyzed)
                if chunk_result.summary_narrative:
                    all_summaries.append(chunk_result.summary_narrative)
        except Exception as e:
            msg = f"Chunk {idx + 1}/{len(chunks)} failed: {e}"
            logger.error(msg, exc_info=True)
            chunk_errors.append(msg)

        if idx < len(chunks) - 1:
            _time.sleep(INTER_CHUNK_SLEEP)

    if not all_candidates:
        raise RuntimeError(f"Bagger analysis failed for all chunks. Errors: {chunk_errors}")

    if chunk_errors:
        logger.warning("Some bagger chunks failed (%d/%d): %s", len(chunk_errors), len(chunks), chunk_errors)

    strong_buys = [c.ticker for c in all_candidates if c.final_recommendation == "STRONG_BUY"]
    watchlist = [c.ticker for c in all_candidates if c.final_recommendation == "WATCHLIST"]
    summary = " | ".join(all_summaries[:2]) if all_summaries else f"Bagger analysis complete across {len(all_candidates)} positions."

    result = BaggerScreenerResponse(
        bundle_hash=composite_hash,
        analysis_timestamp_utc=run_ts,
        candidates_analyzed=all_candidates,
        strong_buy_candidates=strong_buys,
        watchlist_candidates=watchlist,
        summary_narrative=summary,
        data_gaps=data_gaps,
    )

    sheet_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run)
    return result, sheet_rows


@app.command("analyze")
def main(
    bundle: Optional[str] = typer.Option("latest", "--bundle", help="Composite bundle path or 'latest'."),
    tickers: Optional[str] = typer.Option(None, "--tickers", help="Comma-separated tickers."),
    live: bool = typer.Option(False, "--live", help="Write output to Agent_Outputs."),
):
    """Evaluate portfolio positions against the 100-bagger framework."""
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
        result, sheet_rows = run_bagger_agent(bundle_path, run_id, run_ts, ticker_filter, dry_run=not live)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(1)

    # --- Rich Summary ---
    summary = Table(title="100-Bagger Screener — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Candidates", str(len(result.candidates_analyzed)))
    summary.add_row("Strong Buys", str(len(result.strong_buy_candidates)))
    console.print(summary)

    if result.candidates_analyzed:
        colors = {"STRONG_BUY": "bold green", "WATCHLIST": "yellow", "REJECT": "dim red"}
        table = Table(title="Bagger Candidates", show_header=True)
        table.add_column("Ticker")
        table.add_column("Rec")
        table.add_column("Reason")
        for c in result.candidates_analyzed:
            table.add_row(c.ticker, f"[{colors.get(c.final_recommendation)}]{c.final_recommendation}[/]", c.fundamental_reason[:80])
        console.print(table)

    # --- Audit files ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = Path("bundles/runs") / f"bagger_analysis_{run_ts.replace(':', '')}_{run_id}.json"
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
