"""
100-Bagger Screener Agent — Christopher Mayer Framework.

Phase 5-F port. Evaluates each portfolio position against the Christopher Mayer
quantitative gate for extreme compounder potential (100x over 15-25 years).

Pre-computation in Python (never delegated to LLM):
  - market_cap_usd: FMP /profile endpoint
  - roic_pct: FMP /key-metrics-ttm (returnOnInvestedCapitalTTM; falls back to ROE)
  - revenue_growth_3yr_cagr_pct: FMP /income-statement?limit=4 (3yr CAGR)
  - gross_margin_pct: FMP /income-statement?limit=1 (grossProfit / revenue)
  - dividend_payout_ratio_pct: FMP /key-metrics-ttm (payoutRatioTTM)
  - gate pass/fail per rule (acorn, roic, revenue_growth, gross_margin, dividend_payout)

Gemini receives pre-computed metrics + pass/fail flags and writes narrative only.

CLI:
    python manager.py agent bagger analyze
    python manager.py agent bagger analyze --ticker CORZ,IREN
    python manager.py agent bagger analyze --bundle bundles/composite_20260413_....json
    python manager.py agent bagger analyze --live
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

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from agents.schemas.bagger_schema import BaggerCandidate, BaggerScreenerResponse
from agents.utils.chunked_analysis import CHUNK_SIZE, INTER_CHUNK_SLEEP
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite

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
# FMP fetch helpers
# ---------------------------------------------------------------------------

def _get_fmp_api_key() -> str:
    return getattr(config, "FMP_API_KEY", os.environ.get("FMP_API_KEY", ""))


def _fmp_get(url: str) -> list | dict:
    """Raw FMP GET with 402 guard. Returns [] or {} on failure."""
    api_key = _get_fmp_api_key()
    if not api_key:
        return []
    try:
        resp = requests.get(url, timeout=12)
        if resp.status_code == 402:
            logger.warning("FMP 402 (subscription limit): %s", url)
            return []
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("FMP fetch failed (%s): %s", url, e)
        return []


def _fetch_fmp_profile(ticker: str) -> dict:
    """FMP /profile — returns market_cap_usd, sector, beta."""
    api_key = _get_fmp_api_key()
    data = _fmp_get(
        f"https://financialmodelingprep.com/stable/profile?symbol={ticker}&apikey={api_key}"
    )
    if data and isinstance(data, list) and len(data) > 0:
        p = data[0]
        return {
            "market_cap_usd": float(p.get("mktCap") or 0.0),
            "sector": p.get("sector", ""),
        }
    return {}


def _fetch_fmp_key_metrics_ttm(ticker: str) -> dict:
    """FMP /key-metrics-ttm — returns roic, roe, payoutRatio."""
    api_key = _get_fmp_api_key()
    data = _fmp_get(
        f"https://financialmodelingprep.com/stable/key-metrics-ttm?symbol={ticker}&apikey={api_key}"
    )
    if data and isinstance(data, list) and len(data) > 0:
        m = data[0]
        roic_raw = m.get("returnOnInvestedCapitalTTM")
        roe_raw  = m.get("returnOnEquityTTM")
        payout   = m.get("payoutRatioTTM")
        return {
            "roic_raw": roic_raw,     # fraction (0.22 = 22%)
            "roe_raw":  roe_raw,
            "payout_ratio_raw": payout,
        }
    return {}


def _fetch_fmp_income_statements(ticker: str, limit: int = 4) -> list[dict]:
    """FMP /income-statement — annual, limit years. Returns list newest-first."""
    api_key = _get_fmp_api_key()
    data = _fmp_get(
        f"https://financialmodelingprep.com/stable/income-statement"
        f"?symbol={ticker}&period=annual&limit={limit}&apikey={api_key}"
    )
    if data and isinstance(data, list):
        return data
    return []


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


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------

def _evaluate_gates(
    market_cap_usd: float | None,
    roic_pct: float | None,
    revenue_growth_pct: float | None,
    gross_margin_pct: float | None,
    dividend_payout_pct: float | None,
    sector: str,
) -> tuple[list[str], list[str]]:
    """
    Evaluate the 5 Christopher Mayer gates.
    Returns (gates_passed, gates_failed).
    """
    passed = []
    failed = []

    # Acorn
    if market_cap_usd is not None:
        if market_cap_usd < _ACORN_HARD_CEILING_USD:
            passed.append("acorn")
        else:
            failed.append("acorn")

    # ROIC
    if roic_pct is not None:
        if roic_pct >= _ROIC_THRESHOLD_PCT:
            passed.append("roic")
        elif roic_pct >= _ROIC_MIN_PCT:
            passed.append("roic")   # soft pass — Gemini notes "marginal"
        else:
            failed.append("roic")

    # Revenue growth
    if revenue_growth_pct is not None:
        if revenue_growth_pct >= _GROWTH_THRESHOLD_PCT:
            passed.append("revenue_growth")
        else:
            failed.append("revenue_growth")

    # Gross margin — capital-intensive sectors use soft threshold
    capital_intensive = any(
        s.lower() in (sector or "").lower()
        for s in ["energy", "mining", "utilities", "industrial", "material"]
    )
    margin_threshold = _MARGIN_SOFT_PCT if capital_intensive else _MARGIN_THRESHOLD_PCT
    if gross_margin_pct is not None:
        if gross_margin_pct >= margin_threshold:
            passed.append("gross_margin")
        else:
            failed.append("gross_margin")

    # Dividend payout (soft penalty only)
    if dividend_payout_pct is not None:
        if dividend_payout_pct <= 20.0:
            passed.append("dividend_payout")
        else:
            passed.append("dividend_payout")   # penalted not hard-failed; Gemini flags narrative

    return passed, failed


# ---------------------------------------------------------------------------
# Pre-computation pipeline
# ---------------------------------------------------------------------------

def _compute_bagger_facts(
    positions: list[dict],
    ticker_filter: Optional[list[str]],
) -> tuple[list[dict], list[str]]:
    """
    For each investable position (non-cash, optionally filtered), fetch FMP data
    and compute the 5 Mayer gate metrics.

    Returns (positions_with_facts, data_gaps).
    """
    facts = []
    data_gaps = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker_filter and ticker not in ticker_filter:
            continue

        # Fetch FMP data
        profile  = _fetch_fmp_profile(ticker)
        km       = _fetch_fmp_key_metrics_ttm(ticker)
        income   = _fetch_fmp_income_statements(ticker, limit=4)

        market_cap = profile.get("market_cap_usd")
        sector     = profile.get("sector", "")

        # ROIC: prefer ROIC, fall back to ROE
        roic_raw = km.get("roic_raw")
        roe_raw  = km.get("roe_raw")
        roic_pct = _safe_pct(roic_raw)
        roe_pct  = _safe_pct(roe_raw)
        roic_source = "ROIC"
        if roic_pct is None and roe_pct is not None:
            roic_pct = roe_pct
            roic_source = "ROE (proxy)"

        revenue_growth_pct  = _revenue_cagr_3yr(income)
        gross_margin_pct    = _gross_margin_latest(income)
        payout_pct          = _safe_pct(km.get("payout_ratio_raw"))

        # If we have nothing useful, mark as data gap
        if all(v is None for v in [market_cap, roic_pct, revenue_growth_pct, gross_margin_pct]):
            data_gaps.append(ticker)

        gates_passed, gates_failed = _evaluate_gates(
            market_cap, roic_pct, revenue_growth_pct, gross_margin_pct, payout_pct, sector
        )

        facts.append({
            "ticker":                    ticker,
            "market_cap_usd":            round(market_cap, 0) if market_cap else None,
            "market_cap_label":          (
                f"${market_cap / 1e9:.1f}B" if market_cap and market_cap >= 1e9
                else (f"${market_cap / 1e6:.0f}M" if market_cap else "N/A")
            ),
            "roic_pct":                  roic_pct,
            "roic_source":               roic_source,
            "revenue_growth_3yr_cagr_pct": revenue_growth_pct,
            "gross_margin_pct":          gross_margin_pct,
            "dividend_payout_ratio_pct": payout_pct,
            "sector":                    sector,
            "weight_pct":                round(
                float(pos.get("market_value", 0) or 0) /
                float(pos.get("_total_value", 1) or 1) * 100, 2
            ),
            "gates_passed":              gates_passed,
            "gates_failed":              gates_failed,
        })

    return facts, data_gaps


# ---------------------------------------------------------------------------
# Sheet write helpers
# ---------------------------------------------------------------------------

def _result_to_sheet_rows(
    result: BaggerScreenerResponse,
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
        rationale = f"{c.fundamental_reason[:200]} | {c.roic_evaluation[:100]}"
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "bagger_screen",
            c.ticker,
            action,
            rationale[:300],
            action[:120],
            severity,
            dry_str,
        ])

    rows.append([
        run_id, run_ts, composite_hash_short, AGENT_NAME,
        "portfolio_summary", "PORTFOLIO",
        f"Strong buys: {', '.join(result.strong_buy_candidates[:5]) or 'none'}",
        result.summary_narrative[:300],
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

def _build_bagger_chunk_prompt(chunk_facts: list[dict], ctx: dict) -> str:
    """Builds the user prompt for a single chunk of pre-computed bagger facts."""
    framework_context = ctx["framework_context"]
    composite_hash = ctx["composite_hash"]
    chunk_data_gaps = [f["ticker"] for f in chunk_facts if f.get("roic_pct") is None
                       and f.get("revenue_growth_3yr_cagr_pct") is None]
    return (
        f"Screen {len(chunk_facts)} portfolio position(s) against Christopher Mayer's "
        f"100-Bagger quantitative gate framework.\n\n"
        f"## Christopher Mayer Framework Reference\n"
        f"{framework_context}\n\n"
        f"## Pre-Computed Quantitative Gate Results (Python — use exact values)\n"
        f"{json.dumps(chunk_facts, indent=2, default=str)}\n\n"
        f"## Instructions\n"
        "For each position, write the narrative evaluation fields. "
        "gates_passed and gates_failed are already computed — echo them exactly.\n\n"
        "Key rule: most large-cap holdings will REJECT on the Acorn gate. "
        "That is expected. Be clear but not dismissive — REJECT ≠ 'bad investment'.\n\n"
        "Write summary_narrative (3-5 sentences) on portfolio-level 100-bagger potential.\n"
        "Return strong_buy_candidates and watchlist_candidates as ordered ticker lists.\n"
        f"data_gaps (Python-detected, missing FMP data): {chunk_data_gaps}\n\n"
        f"bundle_hash (MUST echo in your response): {composite_hash}\n\n"
        "Produce a BaggerScreenerResponse JSON object."
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
    100-Bagger screener — Christopher Mayer quantitative gate on all holdings.

    Pre-computes ROIC, revenue CAGR, gross margin, and market cap per position
    via FMP. Gemini writes narrative rationale; Python determines gate pass/fail.

    Note: most large-cap holdings will REJECT on the Acorn gate — that is expected
    and informative. The screener surfaces which positions still have 100x math.
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
    total_value = market.get("total_value", 0.0)

    # Inject total_value into each pos so _compute_bagger_facts can compute weight_pct
    for p in investable:
        p["_total_value"] = total_value

    console.print(f"[dim]{len(investable)} investable positions | portfolio ${total_value:,.0f}[/]")

    # --- Apply ticker filter ---
    ticker_filter: Optional[list[str]] = None
    if ticker:
        ticker_filter = [t.strip().upper() for t in ticker.split(",")]
        console.print(f"[dim]Ticker filter: {ticker_filter}[/]")

    # --- Python pre-computation: FMP data + gate evaluation ---
    console.print("[cyan]Fetching FMP data and evaluating Mayer quantitative gates...[/]")
    with console.status("[cyan]Computing ROIC, revenue CAGR, gross margin, market cap..."):
        positions_facts, data_gaps = _compute_bagger_facts(investable, ticker_filter)

    if not positions_facts:
        console.print("[yellow]No positions after filter / FMP fetch. Check --ticker or FMP key.[/]")
        raise typer.Exit(0)

    # Quick gate summary to console before Gemini call
    n_acorn_pass  = sum(1 for p in positions_facts if "acorn" in p["gates_passed"])
    n_roic_pass   = sum(1 for p in positions_facts if "roic" in p["gates_passed"])
    console.print(
        f"[dim]Gate summary: {n_acorn_pass}/{len(positions_facts)} pass Acorn "
        f"| {n_roic_pass}/{len(positions_facts)} pass ROIC[/]"
    )
    if data_gaps:
        console.print(f"[yellow]! FMP data unavailable for: {data_gaps[:10]}[/]")

    # --- Load Mayer framework JSON ---
    framework_context = ""
    if _FRAMEWORK_PATH.exists():
        try:
            framework_context = _FRAMEWORK_PATH.read_text(encoding="utf-8")
        except Exception:
            pass

    # --- System prompt ---
    system_prompt_text = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _SYSTEM_PROMPT_PATH.exists()
        else ""
    )

    # --- Call Gemini — CHUNKED EXECUTION ---
    chunks = [
        positions_facts[i : i + CHUNK_SIZE]
        for i in range(0, len(positions_facts), CHUNK_SIZE)
    ]
    console.print(
        f"[cyan]Calling Gemini on {len(positions_facts)} position(s) "
        f"(chunked, {CHUNK_SIZE} per batch)...[/]"
    )

    prompt_ctx = {
        "framework_context": framework_context,
        "composite_hash": composite["composite_hash"],
    }

    all_candidates_analyzed: list = []
    all_strong_buys: list = []
    all_watchlist: list = []
    first_summary_narrative: str | None = None
    chunk_errors: list[str] = []

    with console.status("[cyan]Evaluating 100-bagger potential in chunks..."):
        for idx, chunk in enumerate(chunks):
            tickers_in_chunk = [p["ticker"] for p in chunk]
            logger.info("Chunk %d/%d: %s", idx + 1, len(chunks), tickers_in_chunk)
            try:
                chunk_prompt = _build_bagger_chunk_prompt(chunk, prompt_ctx)
                chunk_result: BaggerScreenerResponse | None = ask_gemini_composite(
                    prompt=chunk_prompt,
                    composite_bundle_path=bundle_path,
                    response_schema=BaggerScreenerResponse,
                    system_instruction=system_prompt_text,
                    max_tokens=8000,
                )
                if chunk_result is None:
                    msg = f"Chunk {idx + 1}/{len(chunks)} ({tickers_in_chunk}): Gemini returned None"
                    logger.warning(msg)
                    chunk_errors.append(msg)
                else:
                    all_candidates_analyzed.extend(chunk_result.candidates_analyzed)
                    all_strong_buys.extend(chunk_result.strong_buy_candidates)
                    all_watchlist.extend(chunk_result.watchlist_candidates)
                    if first_summary_narrative is None and chunk_result.summary_narrative:
                        first_summary_narrative = chunk_result.summary_narrative
            except Exception as e:
                msg = f"Chunk {idx + 1}/{len(chunks)} failed: {e}"
                logger.error(msg, exc_info=True)
                chunk_errors.append(msg)

            if idx < len(chunks) - 1:
                time.sleep(INTER_CHUNK_SLEEP)

    if not all_candidates_analyzed and chunk_errors:
        console.print("[red]ERROR: All chunks failed. Check API logs.[/]")
        for err in chunk_errors:
            console.print(f"  [red]• {err}[/]")
        raise typer.Exit(1)

    # Reconstruct result with ORIGINAL composite hash (never from a chunk response)
    result = BaggerScreenerResponse(
        bundle_hash=composite["composite_hash"],
        analysis_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        candidates_analyzed=all_candidates_analyzed,
        strong_buy_candidates=list(dict.fromkeys(all_strong_buys)),
        watchlist_candidates=list(dict.fromkeys(all_watchlist)),
        summary_narrative=first_summary_narrative or "See individual position analyses.",
        data_gaps=data_gaps,  # Python-computed — always authoritative
    )
    if chunk_errors:
        console.print(f"[yellow]! {len(chunk_errors)} chunk error(s): {chunk_errors}[/]")
    # --- END CHUNKED EXECUTION ---

    # Overwrite data_gaps with Python-computed list (authoritative)
    result.data_gaps = data_gaps

    # Overwrite gates_passed / gates_failed on each candidate with Python truth
    facts_map = {f["ticker"]: f for f in positions_facts}
    for cand in result.candidates_analyzed:
        fact = facts_map.get(cand.ticker)
        if fact:
            cand.gates_passed = fact["gates_passed"]
            cand.gates_failed = fact["gates_failed"]

    # --- Rich summary ---
    summary = Table(title="100-Bagger Screener — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Analyzed At", result.analysis_timestamp_utc)
    summary.add_row("Positions Screened", str(len(result.candidates_analyzed)))
    summary.add_row("Strong Buys", f"[bold green]{len(result.strong_buy_candidates)}[/]" if result.strong_buy_candidates else "0")
    summary.add_row("Watchlist", f"[yellow]{len(result.watchlist_candidates)}[/]" if result.watchlist_candidates else "0")
    summary.add_row("Data Gaps", str(len(result.data_gaps)))
    console.print(summary)

    if result.candidates_analyzed:
        rec_colors = {
            "STRONG_BUY": "bold green",
            "WATCHLIST":  "yellow",
            "REJECT":     "dim",
        }
        screen_table = Table(title="Gate Results", show_header=True)
        screen_table.add_column("Ticker", style="bold")
        screen_table.add_column("Mkt Cap")
        screen_table.add_column("ROIC %")
        screen_table.add_column("Rev CAGR %")
        screen_table.add_column("Gross Margin %")
        screen_table.add_column("Gates Passed")
        screen_table.add_column("Verdict")
        for cand in result.candidates_analyzed:
            fact = facts_map.get(cand.ticker, {})
            color = rec_colors.get(cand.final_recommendation, "white")
            screen_table.add_row(
                cand.ticker,
                fact.get("market_cap_label", "N/A"),
                f"{fact.get('roic_pct', 0) or 0:.1f}%" if fact.get("roic_pct") else "N/A",
                f"{fact.get('revenue_growth_3yr_cagr_pct', 0) or 0:.1f}%" if fact.get("revenue_growth_3yr_cagr_pct") else "N/A",
                f"{fact.get('gross_margin_pct', 0) or 0:.1f}%" if fact.get("gross_margin_pct") else "N/A",
                f"{len(cand.gates_passed)}/5",
                f"[{color}]{cand.final_recommendation}[/]",
            )
        console.print(screen_table)

    if result.strong_buy_candidates:
        console.print(f"\n[bold green]STRONG BUY:[/] {', '.join(result.strong_buy_candidates)}")
    if result.watchlist_candidates:
        console.print(f"[yellow]WATCHLIST:[/] {', '.join(result.watchlist_candidates)}")
    if result.summary_narrative:
        console.print(f"\n[dim]Portfolio summary:[/] {result.summary_narrative}")

    # --- Write local audit files ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = str(uuid.uuid4())

    json_path = AGENT_OUTPUT_DIR / f"bagger_output_{result.bundle_hash[:12]}.json"
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
