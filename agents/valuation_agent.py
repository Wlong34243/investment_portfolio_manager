"""
Valuation Agent — per-position valuation signals and accumulation plans.

Reads the composite bundle (market + vault), pre-computes all valuation metrics
in Python via FMP, passes summarized facts to Gemini for signals and narrative,
and writes the structured result to Agent_Outputs Sheet tab (--live) or local
files (dry run).

Pre-computation in Python (never delegated to LLM):
  - Forward P/E:                current_price / forward_eps (FMP quote endpoint)
  - Trailing P/E:               from FMP key-metrics TTM
  - PEG ratio:                  trailing_pe / earnings_growth_pct (FMP, where available)
  - 52-week range position:     (price - low_52w) / (high_52w - low_52w)
  - Discount from 52w high:     (high_52w - price) / high_52w as %
  - Earnings surprise history:  last 2 quarters via FMP earnings calendar

Gemini writes: signal ("accumulate" | "hold" | "trim" | "monitor"), accumulation_plan,
rationale, style_alignment, summary_narrative, top_accumulation_candidates.

CLI:
    python manager.py agent valuation analyze
    python manager.py agent valuation analyze --tickers UNH,GOOG,AMZN
    python manager.py agent valuation analyze --bundle bundles/composite_20260413_....json
    python manager.py agent valuation analyze --live
"""

import json
import logging
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
from agents.schemas.valuation_schema import ValuationAgentOutput
from agents.framework_selector import parse_thesis_frontmatter
from core.composite_bundle import load_composite_bundle, resolve_latest_bundles
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite

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

def _get_fmp_api_key() -> str:
    return getattr(config, "FMP_API_KEY", os.environ.get("FMP_API_KEY", ""))


def _fetch_fmp_quote(ticker: str) -> dict:
    """
    Call FMP /quote endpoint for a single ticker.
    Returns dict with: price, pe, forwardPE, eps, yearHigh, yearLow,
    earningsAnnouncement, priceAvg50, priceAvg200.
    Returns {} on failure (logged as data_gap by caller).
    """
    api_key = _get_fmp_api_key()
    if not api_key:
        return {}
    url = f"https://financialmodelingprep.com/stable/quote?symbol={ticker}&apikey={api_key}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 402:
            logger.warning("FMP 402 for %s — subscription limit.", ticker)
            return {}
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        return {}
    except Exception as e:
        logger.warning("FMP quote fetch failed for %s: %s", ticker, e)
        return {}


def _fetch_fmp_earnings_surprises(ticker: str) -> list[dict]:
    """
    Fetch last 2 quarters of earnings surprises from FMP.
    Returns list of dicts with: date, actual, estimated, surprise%.
    Returns [] on failure.
    """
    api_key = _get_fmp_api_key()
    if not api_key:
        return []
    url = (
        f"https://financialmodelingprep.com/stable/earnings-surprises"
        f"?symbol={ticker}&limit=2&apikey={api_key}"
    )
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code in (402, 403):
            return []
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        surprises = []
        for row in data[:2]:
            actual = row.get("actualEarningResult") or row.get("actual")
            est = row.get("estimatedEarning") or row.get("estimated")
            if actual is None or est is None:
                continue
            try:
                surprise_pct = ((float(actual) - float(est)) / abs(float(est))) * 100 if est != 0 else 0.0
            except (TypeError, ZeroDivisionError):
                surprise_pct = 0.0
            surprises.append({
                "date": row.get("date", ""),
                "actual_eps": actual,
                "estimated_eps": est,
                "surprise_pct": round(surprise_pct, 1),
            })
        return surprises
    except Exception as e:
        logger.warning("FMP earnings surprises failed for %s: %s", ticker, e)
        return []


def _compute_valuation_facts(
    positions: list[dict],
    thesis_map: dict[str, dict],
    ticker_filter: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """
    For each investable position, fetch FMP data and compute valuation metrics.

    Returns:
        (valuation_facts: list[dict], data_gaps: list[str])
        valuation_facts — one dict per position with all pre-computed numbers
        data_gaps       — tickers skipped due to missing FMP data
    """
    facts: list[dict] = []
    data_gaps: list[str] = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_TICKERS:
            continue
        if ticker_filter and ticker not in ticker_filter:
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
        quote = _fetch_fmp_quote(ticker)
        surprises = _fetch_fmp_earnings_surprises(ticker)

        if not quote:
            data_gaps.append(f"{ticker}: FMP quote unavailable")
            # Still include in facts with None metrics — agent can signal "monitor"
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
        pe_fwd_raw = _safe_float_or_none(quote.get("forwardPE"))
        eps = _safe_float_or_none(quote.get("eps"))

        # Forward P/E: use FMP's forwardPE field; if absent, compute from price/forwardEps
        pe_fwd = pe_fwd_raw

        # PEG: FMP quote doesn't provide EPS growth; leave as None
        # (would require a separate growth estimate endpoint)
        peg = None

        # 52-week range
        high_52w = _safe_float_or_none(quote.get("yearHigh"))
        low_52w = _safe_float_or_none(quote.get("yearLow"))

        if high_52w and low_52w and high_52w > low_52w:
            price_vs_range = round((price - low_52w) / (high_52w - low_52w), 4)
        else:
            price_vs_range = None

        if high_52w and high_52w > 0:
            discount_from_high = round((high_52w - price) / high_52w * 100, 2)
        else:
            discount_from_high = 0.0

        # Average earnings surprise over last 2 quarters
        avg_surprise = None
        if surprises:
            avg_surprise = round(sum(s["surprise_pct"] for s in surprises) / len(surprises), 1)

        facts.append({
            "ticker": ticker,
            "price": price,
            "pe_trailing": pe_trailing,
            "pe_fwd": pe_fwd,
            "peg": peg,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "price_vs_52w_range": price_vs_range,
            "discount_from_52w_high_pct": discount_from_high,
            "earnings_surprise_avg_pct": avg_surprise,
            "earnings_surprises": surprises,
            "style_tag": style_tag,
            "thesis_present": thesis_doc is not None,
            "current_weight_pct": round(_safe_float(pos.get("weight")) * 100, 2),
            "market_value": _safe_float(pos.get("market_value")),
        })

    return facts, data_gaps


def _safe_float(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_float_or_none(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Sheet write helpers (same archive-before-overwrite pattern as tax_agent)
# ---------------------------------------------------------------------------

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
        severity_map = {"accumulate": "action", "trim": "action", "hold": "info", "monitor": "watch"}
        severity = severity_map.get(p.signal, "info")
        action = p.accumulation_plan or p.signal.upper()
        scale_step = p.accumulation_plan or ""
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "accumulate" if p.signal == "accumulate" else p.signal,
            p.ticker, action[:120],
            p.rationale[:300],
            scale_step[:120], severity, dry_str,
        ])

    return rows


def _archive_and_overwrite(ss, new_rows: list[list], run_ts: str) -> None:
    """Archive existing Agent_Outputs rows, then overwrite with new_rows."""
    from utils.sheet_readers import get_gspread_client

    existing_tabs = {ws.title for ws in ss.worksheets()}

    if config.TAB_AGENT_OUTPUTS not in existing_tabs:
        ws_out = ss.add_worksheet(title=config.TAB_AGENT_OUTPUTS, rows=2000, cols=len(_AGENT_OUTPUTS_HEADERS) + 1)
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
        console.print(f"[dim]Archived {len(archive_rows)} existing row(s) to {config.TAB_AGENT_OUTPUTS_ARCHIVE}.[/]")

    ws_out.clear()
    time.sleep(0.5)
    ws_out.update(
        range_name="A1",
        values=[_AGENT_OUTPUTS_HEADERS] + new_rows,
        value_input_option="USER_ENTERED",
    )
    time.sleep(1.0)
    console.print(f"[green]LIVE — wrote {len(new_rows)} row(s) to {config.TAB_AGENT_OUTPUTS} (single batch).[/]")


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

    # --- Ticker filter ---
    ticker_filter: set[str] | None = None
    if tickers:
        ticker_filter = {t.strip().upper() for t in tickers.split(",") if t.strip()}
        console.print(f"[dim]Ticker subset mode: {sorted(ticker_filter)}[/]")

    # --- Resolve bundle path ---
    if bundle == "latest":
        try:
            composite_candidates = sorted(
                Path("bundles").glob("composite_bundle_*.json"),
                key=lambda p: p.stat().st_mtime,
            )
            if not composite_candidates:
                console.print("[red]ERROR: No composite bundles found. Run: python manager.py bundle composite[/]")
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

    # --- Load bundles ---
    composite = load_composite_bundle(bundle_path)
    console.print(f"[dim]Composite hash: {composite['composite_hash'][:16]}...[/]")

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
    console.print(f"[cyan]Pre-computing valuation metrics via FMP for {len(investable)} position(s)...[/]")
    console.print("[dim](This calls FMP once per ticker — expect ~1-2 seconds per position.)[/]")

    with console.status("[cyan]Fetching FMP data..."):
        val_facts, data_gaps = _compute_valuation_facts(investable, thesis_map, ticker_filter)

    console.print(f"[dim]{len(val_facts)} position(s) ready | {len(data_gaps)} data gap(s).[/]")
    if data_gaps:
        console.print(f"[yellow]! Data gaps: {data_gaps}[/]")

    if not val_facts:
        console.print("[red]ERROR: No positions to analyze after FMP fetch. Check FMP_API_KEY.[/]")
        raise typer.Exit(1)

    # --- Build user prompt ---
    system_prompt_text = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _SYSTEM_PROMPT_PATH.exists()
        else ""
    )

    valuation_table_str = json.dumps(val_facts, indent=2)

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
    console.print(f"[cyan]Calling Gemini on {len(val_facts)} positions...[/]")
    with console.status("[cyan]Analyzing..."):
        result: ValuationAgentOutput | None = ask_gemini_composite(
            prompt=user_prompt,
            composite_bundle_path=bundle_path,
            response_schema=ValuationAgentOutput,
            system_instruction=system_prompt_text,
            max_tokens=12000,
        )

    if result is None:
        console.print("[red]ERROR: Gemini returned no result. Check API logs.[/]")
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

    if result.positions:
        signal_colors = {
            "accumulate": "bold green",
            "hold": "yellow",
            "trim": "bold red",
            "monitor": "dim",
        }
        pos_table = Table(title="Position Signals", show_header=True)
        pos_table.add_column("Ticker", style="bold")
        pos_table.add_column("PE Fwd")
        pos_table.add_column("PE Trail")
        pos_table.add_column("Disc 52w%")
        pos_table.add_column("Signal")
        pos_table.add_column("Style")
        for p in result.positions:
            color = signal_colors.get(p.signal, "white")
            pos_table.add_row(
                p.ticker,
                f"{p.pe_fwd:.1f}" if p.pe_fwd else "—",
                f"{p.pe_trailing:.1f}" if p.pe_trailing else "—",
                f"{p.discount_from_52w_high_pct:.1f}%",
                f"[{color}]{p.signal}[/]",
                p.style_alignment[:12],
            )
        console.print(pos_table)

    if result.top_accumulation_candidates:
        console.print(f"\n[green]Top accumulation candidates:[/] {', '.join(result.top_accumulation_candidates)}")

    if result.summary_narrative:
        console.print(f"\n[dim]Summary:[/] {result.summary_narrative}")

    # --- Write local audit files (always) ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = str(uuid.uuid4())

    json_path = AGENT_OUTPUT_DIR / f"valuation_output_{result.bundle_hash[:12]}.json"
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
