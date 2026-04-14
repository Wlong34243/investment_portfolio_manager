"""
Concentration Hedger Agent — position, sector, and correlation concentration risk.

Reads the composite bundle (market + vault), pre-computes all risk metrics in
Python, passes only summarized facts to Gemini for hedge suggestions and narrative,
and writes the structured result to Agent_Outputs Sheet tab (--live) or local
files (dry run).

Pre-computation in Python (never delegated to LLM):
  - Single-position weight vs CONCENTRATION_SINGLE_THRESHOLD (8%)
  - Sector weight vs CONCENTRATION_SECTOR_THRESHOLD (30%)
  - Portfolio beta: weighted beta from yfinance Ticker.info['beta']
  - Pairwise Pearson correlation: 1yr daily returns, top-20 positions via yfinance bulk download
  - High-correlation pairs: |r| > CORRELATION_FLAG_THRESHOLD (0.85)
  - Stress scenarios: portfolio_value × portfolio_beta × market_shock (Python math only)

Gemini writes: hedge_suggestion, scale_step, summary_narrative, priority_actions.
No LLM math anywhere.

CLI:
    python manager.py agent concentration analyze
    python manager.py agent concentration analyze --bundle bundles/composite_20260413_....json
    python manager.py agent concentration analyze --live
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import typer
import yfinance as yf
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from agents.schemas.concentration_schema import ConcentrationAgentOutput
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite

logger = logging.getLogger(__name__)

app = typer.Typer(help="Concentration Hedger — position, sector, and correlation risk flags")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "concentration"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "concentration_hedger_system.txt"

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]


# ---------------------------------------------------------------------------
# Sector resolution (positions have no GICS sector in the bundle; use static map
# with yfinance as last-resort fallback for unknown tickers)
# ---------------------------------------------------------------------------

SECTOR_FALLBACK: dict[str, str] = {
    # --- Technology (broad — includes Comm Services tech and AWS for concentration) ---
    "GOOG":  "Technology",    # Alphabet — effectively a tech conglomerate
    "META":  "Technology",    # Meta Platforms
    "AMZN":  "Technology",    # Amazon — AWS is primary value driver
    "MSFT":  "Technology",
    "NVDA":  "Technology",
    "AMD":   "Technology",
    "AVGO":  "Technology",
    "CSCO":  "Technology",
    "DELL":  "Technology",
    "INTC":  "Technology",
    "SNPS":  "Technology",    # Synopsys — EDA software
    "CRWD":  "Technology",    # CrowdStrike
    "PANW":  "Technology",    # Palo Alto Networks
    "NOW":   "Technology",    # ServiceNow
    "CRWV":  "Technology",    # CoreWeave — AI cloud
    "CORZ":  "Technology",    # Core Scientific — AI/Bitcoin data centers
    "IREN":  "Technology",    # Iris Energy — AI/Bitcoin mining
    # --- Communication Services ---
    "NFLX":  "Communication Services",
    "DIS":   "Communication Services",
    # --- Health Care ---
    "UNH":   "Health Care",
    # --- Energy ---
    "XOM":   "Energy",
    "ET":    "Energy",
    "CNQ":   "Energy",
    "BE":    "Energy",        # Bloom Energy — fuel cells
    # --- Financials ---
    "CFG":   "Financials",
    "COF":   "Financials",
    # --- Industrials ---
    "CAT":   "Industrials",
    "ETN":   "Industrials",
    "HWM":   "Industrials",
    "BA":    "Industrials",   # Boeing
    # --- Real Estate ---
    "DLR":   "Real Estate",
    # --- Utilities ---
    "NEE":   "Utilities",
    # --- Consumer Discretionary ---
    "BABA":  "Consumer Discretionary",
    # --- ETFs: sector ---
    "QQQM":  "Technology",    # Nasdaq 100 — predominantly tech
    "IGV":   "Technology",    # iShares Expanded Tech-Software
    "XBI":   "Health Care",   # SPDR Biotech
    "XLV":   "Health Care",   # Health Care Select Sector
    "XLF":   "Financials",    # Financial Select Sector
    "XLE":   "Energy",        # Energy Select Sector
    "PPA":   "Industrials",   # Invesco Aerospace & Defense
    "IFRA":  "Industrials",   # iShares US Infrastructure
    # --- ETFs: broad / international ---
    "RSP":   "Diversified",   # Equal-weight S&P 500
    "VTI":   "Diversified",   # Total US Market
    "VEA":   "International", # Developed Markets ex-US
    "VEU":   "International", # All-World ex-US
    "EWJ":   "International", # Japan
    "EWZ":   "International", # Brazil
    "EFG":   "International", # MSCI EAFE Growth
    "EMXC":  "International", # Emerging ex-China
    "BBJP":  "International", # JPMorgan BetaBuilders Japan
    # --- Fixed Income / Cash ---
    "JPIE":  "Fixed Income",
    "SGOV":  "Cash",
}


def _resolve_sector(pos: dict) -> str:
    """
    Resolve the GICS sector for a position.
    Priority order:
      1. Bundle `sector` field (populated if enrichment ever fills it in)
      2. SECTOR_FALLBACK static map (covers the full portfolio as of Phase 5)
      3. yfinance Ticker.info["sector"] — last-resort for unknown tickers
      4. "Other" if all sources fail
    """
    ticker = pos.get("ticker", "")
    # 1. Bundle field
    bundle_sector = pos.get("sector")
    if bundle_sector and bundle_sector not in ("", "N/A", None):
        return bundle_sector
    # 2. Static map
    if ticker in SECTOR_FALLBACK:
        return SECTOR_FALLBACK[ticker]
    # 3. yfinance fallback (for tickers added to portfolio after the map was built)
    try:
        info = yf.Ticker(ticker).info
        yf_sector = info.get("sector")
        if yf_sector:
            return yf_sector
    except Exception:
        pass
    return "Other"


# ---------------------------------------------------------------------------
# Python pre-computation helpers
# ---------------------------------------------------------------------------

def _safe_float(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _compute_single_position_flags(positions: list[dict], total_value: float) -> list[dict]:
    """Flag positions whose weight exceeds CONCENTRATION_SINGLE_THRESHOLD."""
    threshold = config.CONCENTRATION_SINGLE_THRESHOLD  # 0.08 = 8%
    flags = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_TICKERS:
            continue
        mv = _safe_float(pos.get("market_value"))
        weight = mv / total_value if total_value > 0 else 0.0
        if weight > threshold:
            breach = weight * 100 - threshold * 100
            flags.append({
                "flag_type": "single_position",
                "tickers_involved": [ticker],
                "current_weight_pct": round(weight * 100, 2),
                "threshold_pct": threshold * 100,
                "severity": "action" if breach > 3.0 else "watch",
            })
    flags.sort(key=lambda f: f["current_weight_pct"], reverse=True)
    return flags


def _compute_sector_flags(positions: list[dict], total_value: float) -> list[dict]:
    """
    Flag GICS sectors whose combined weight exceeds CONCENTRATION_SECTOR_THRESHOLD.

    Uses _resolve_sector() to map each position to its sector — bundle field first,
    then SECTOR_FALLBACK static map, then yfinance. Groups by resolved sector name,
    not the raw asset_class field (which is always 'Equity' in the current bundle).
    """
    threshold = config.CONCENTRATION_SECTOR_THRESHOLD  # 0.30 = 30%
    sector_mv: dict[str, float] = {}
    sector_tickers: dict[str, list[str]] = {}

    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_TICKERS:
            continue
        sector = _resolve_sector(pos)
        mv = _safe_float(pos.get("market_value"))
        sector_mv[sector] = sector_mv.get(sector, 0.0) + mv
        sector_tickers.setdefault(sector, []).append(ticker)

    flags = []
    for sector, mv in sector_mv.items():
        weight = mv / total_value if total_value > 0 else 0.0
        if weight > threshold:
            breach = weight * 100 - threshold * 100
            # Top contributors by market value
            top_tickers = sorted(
                sector_tickers.get(sector, []),
                key=lambda t: next(
                    (_safe_float(p.get("market_value")) for p in positions if p.get("ticker") == t),
                    0.0,
                ),
                reverse=True,
            )[:10]
            flags.append({
                "flag_type": "sector",
                "sector": sector,
                "tickers_involved": top_tickers,
                "current_weight_pct": round(weight * 100, 2),
                "threshold_pct": threshold * 100,
                "severity": "action" if breach > 3.0 else "watch",
            })

    flags.sort(key=lambda f: f["current_weight_pct"], reverse=True)
    return flags


def _fetch_portfolio_beta(positions: list[dict], total_value: float) -> tuple[float, dict[str, float]]:
    """
    Fetch beta for each investable position from yfinance.info['beta'].
    Returns (weighted_portfolio_beta, per_ticker_beta_dict).

    Falls back to 1.0 (market-neutral) if yfinance returns None.
    Cash tickers always get beta=0.0.
    """
    per_ticker_beta: dict[str, float] = {}

    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_TICKERS:
            per_ticker_beta[ticker] = 0.0
            continue
        try:
            info = yf.Ticker(ticker).info
            raw_beta = info.get("beta")
            if raw_beta is not None:
                per_ticker_beta[ticker] = float(np.clip(float(raw_beta), -0.5, 3.5))
            else:
                per_ticker_beta[ticker] = 1.0
        except Exception as e:
            logger.warning("yfinance beta fetch failed for %s: %s", ticker, e)
            per_ticker_beta[ticker] = 1.0

    # Weighted beta
    weighted_beta = 0.0
    for pos in positions:
        ticker = pos.get("ticker", "")
        mv = _safe_float(pos.get("market_value"))
        weight = mv / total_value if total_value > 0 else 0.0
        weighted_beta += weight * per_ticker_beta.get(ticker, 1.0)

    return round(float(weighted_beta), 4), per_ticker_beta


def _compute_correlation_pairs(
    positions: list[dict],
    total_value: float,
    threshold: float | None = None,
) -> list[dict]:
    """
    Download 1yr daily prices for ALL investable positions via yfinance bulk download.
    Compute pairwise Pearson correlation and return pairs exceeding threshold.

    Changes from original (Phase 5 remediation Fix 3):
      - Expanded from top-20 to ALL investable positions — ensures small positions
        like CRWD (#34) and PANW (#49) are included in the matrix.
      - dropna(how='all') instead of dropna() — prevents NaN contamination from
        tickers with sparse data from excluding other tickers' valid rows.
      - corr(min_periods=100) — requires at least 100 common trading days; pairs
        with fewer common periods produce NaN (skipped, not treated as zero).
      - NaN correlation values are explicitly skipped (math.isnan check).

    Returns list of dicts: {ticker_a, ticker_b, correlation, combined_weight_pct}.
    Returns [] if download fails or fewer than 2 tickers available.
    """
    import math
    if threshold is None:
        threshold = config.CORRELATION_FLAG_THRESHOLD

    investable = [
        p for p in positions if p.get("ticker") not in config.CASH_TICKERS
    ]

    if len(investable) < 2:
        return []

    tickers = [p["ticker"] for p in investable]

    weight_map = {
        p["ticker"]: _safe_float(p.get("market_value")) / total_value * 100
        for p in investable
    }

    try:
        import pandas as pd
        data = yf.download(tickers, period="1y", auto_adjust=True, progress=False)
        # Handle MultiIndex columns from yfinance (multi-ticker download)
        if hasattr(data.columns, "levels"):
            level0 = data.columns.get_level_values(0)
            if "Close" in level0:
                prices = data["Close"]
            elif "Adj Close" in level0:
                prices = data["Adj Close"]
            else:
                prices = data
        else:
            prices = data

        # dropna(how='all'): drop rows where ALL tickers are NaN.
        # Avoids excluding rows caused by a single ticker with a trading halt or new listing.
        returns = prices.pct_change().dropna(how="all")

        # min_periods=100: require at least 100 common data points per pair.
        # Pairs with fewer common rows get NaN correlation (skipped below).
        corr_matrix = returns.corr(min_periods=100)

    except Exception as e:
        logger.warning("Correlation matrix computation failed: %s", e)
        return []

    pairs = []
    ticker_list = list(corr_matrix.columns)
    for i, ta in enumerate(ticker_list):
        for tb in ticker_list[i + 1:]:
            try:
                r = float(corr_matrix.loc[ta, tb])
            except (KeyError, TypeError):
                continue
            # Skip NaN pairs — insufficient common data points, not zero correlation
            if math.isnan(r):
                continue
            if abs(r) > threshold:
                pairs.append({
                    "flag_type": "correlation_pair",
                    "tickers_involved": [ta, tb],
                    "correlation": round(r, 4),
                    "combined_weight_pct": round(
                        weight_map.get(ta, 0.0) + weight_map.get(tb, 0.0), 2
                    ),
                    "current_weight_pct": round(
                        weight_map.get(ta, 0.0) + weight_map.get(tb, 0.0), 2
                    ),
                    "threshold_pct": threshold * 100,
                    "severity": "action" if abs(r) > 0.92 else "watch",
                })

    # Sort by correlation magnitude descending.
    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)

    # Tiered output: equity-equity pairs first, then ETF/hybrid pairs.
    # With threshold=0.50, international ETF pairs (BBJP/EWJ=0.999, VEA/VEU=0.985)
    # dominate the top-N ranking and bury actionable equity pairs like CRWD/PANW and
    # AMD/NVDA. Partitioning by ETF membership surfaces equity signals first.
    _ETF_TICKERS = frozenset({
        "QQQM", "IGV", "XBI", "XLV", "XLF", "XLE", "PPA", "IFRA",
        "RSP", "VTI", "VEA", "VEU", "EWJ", "EWZ", "EFG", "EMXC", "BBJP",
        "JPIE", "SGOV",
    })
    equity_pairs = [
        p for p in pairs
        if p["tickers_involved"][0] not in _ETF_TICKERS
        and p["tickers_involved"][1] not in _ETF_TICKERS
    ]
    etf_pairs = [
        p for p in pairs
        if p["tickers_involved"][0] in _ETF_TICKERS
        or p["tickers_involved"][1] in _ETF_TICKERS
    ]
    # Top-20 equity pairs + top-5 ETF pairs; total ≤ 25 keeps Gemini prompt manageable.
    return equity_pairs[:20] + etf_pairs[:5]


def _compute_stress_scenarios(portfolio_value: float, portfolio_beta: float) -> dict[str, float]:
    """
    Dollar impact per stress scenario from config.STRESS_SCENARIOS.
    Reuses the same math as utils/risk.py::run_stress_tests() — no yfinance call.
    Returns dict keyed by slugified scenario name.
    """
    results: dict[str, float] = {}
    for name, pct in config.STRESS_SCENARIOS:
        impact = portfolio_value * portfolio_beta * pct
        slug = name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("%", "pct").replace(",", "").replace("-", "neg")
        results[slug] = round(impact, 2)
    return results


# ---------------------------------------------------------------------------
# Sheet write helpers
# ---------------------------------------------------------------------------

def _result_to_sheet_rows(
    result: ConcentrationAgentOutput,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    """Serialize ConcentrationAgentOutput to Agent_Outputs tab rows."""
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for f in result.flags:
        ticker_str = ", ".join(f.tickers_involved[:3])
        action = f.scale_step[:120]
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            f.flag_type,
            ticker_str,
            action,
            f.hedge_suggestion[:300],
            f.scale_step[:120],
            f.severity,
            dry_str,
        ])

    # Portfolio-level summary row
    rows.append([
        run_id, run_ts, composite_hash_short, AGENT_NAME,
        "portfolio_risk", "PORTFOLIO",
        f"Beta: {result.portfolio_beta:.2f}",
        result.summary_narrative[:300],
        "", "info", dry_str,
    ])

    return rows


def _archive_and_overwrite(ss, new_rows: list[list], run_ts: str) -> None:
    """Archive existing Agent_Outputs rows, then overwrite with new_rows."""
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
# CLI command
# ---------------------------------------------------------------------------

@app.command()
def analyze(
    bundle: Optional[str] = typer.Option(
        "latest",
        "--bundle",
        help="Composite bundle path or 'latest' to use most recent.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write output to Agent_Outputs Sheet tab. Default: dry run.",
    ),
):
    """Pre-compute concentration and correlation risk; Gemini writes hedge suggestions."""

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
            console.print("[red]ERROR: No composite bundles found. Run: python manager.py bundle composite[/]")
            raise typer.Exit(1)
        bundle_path = composite_candidates[-1]
        console.print(f"[dim]Using latest composite bundle: {bundle_path.name}[/]")
    else:
        bundle_path = Path(bundle)
        if not bundle_path.exists():
            console.print(f"[red]ERROR: Bundle not found: {bundle_path}[/]")
            raise typer.Exit(1)

    # --- Load bundles ---
    composite = load_composite_bundle(bundle_path)
    console.print(f"[dim]Composite hash: {composite['composite_hash'][:16]}...[/]")

    market = load_bundle(Path(composite["market_bundle_path"]))

    investable = [
        p for p in market["positions"]
        if p.get("ticker") not in config.CASH_TICKERS
    ]
    total_value = market.get("total_value", 0.0)
    cash_manual = market.get("cash_manual", 0.0)

    console.print(
        f"[dim]{len(investable)} investable positions | portfolio ${total_value:,.0f}[/]"
    )

    # --- Pre-compute: single-position concentration ---
    console.print("[cyan]Pre-computing single-position concentration flags...[/]")
    single_flags = _compute_single_position_flags(investable, total_value)
    console.print(f"[dim]{len(single_flags)} single-position flag(s) above {config.CONCENTRATION_SINGLE_THRESHOLD*100:.0f}%.[/]")

    # --- Pre-compute: sector concentration ---
    console.print("[cyan]Pre-computing sector concentration flags...[/]")
    sector_flags = _compute_sector_flags(investable, total_value)
    console.print(f"[dim]{len(sector_flags)} sector flag(s) above {config.CONCENTRATION_SECTOR_THRESHOLD*100:.0f}%.[/]")

    # --- Pre-compute: portfolio beta (yfinance, one call per ticker) ---
    console.print(f"[cyan]Fetching beta for {len(investable)} positions via yfinance...[/]")
    with console.status("[cyan]Fetching betas..."):
        portfolio_beta, ticker_betas = _fetch_portfolio_beta(market["positions"], total_value)
    console.print(f"[dim]Portfolio beta: {portfolio_beta:.3f}[/]")

    # --- Pre-compute: stress scenarios ---
    stress_scenarios = _compute_stress_scenarios(total_value, portfolio_beta)
    console.print(
        "[dim]Stress scenarios computed: "
        + ", ".join(f"{k}: ${v:,.0f}" for k, v in list(stress_scenarios.items())[:3])
        + "...[/]"
    )

    # --- Pre-compute: correlation matrix ---
    console.print("[cyan]Computing pairwise correlations (1yr daily, top-20 positions)...[/]")
    with console.status("[cyan]Downloading price history..."):
        corr_pairs = _compute_correlation_pairs(investable, total_value)
    console.print(
        f"[dim]{len(corr_pairs)} high-correlation pair(s) above |r|={config.CORRELATION_FLAG_THRESHOLD}.[/]"
    )

    # --- Combine all flags ---
    all_flags = single_flags + sector_flags + corr_pairs

    # --- Build thesis snippets for flagged tickers ---
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))
    flagged_tickers: set[str] = set()
    for f in all_flags:
        flagged_tickers.update(f.get("tickers_involved", []))

    thesis_snippets: dict[str, str] = {}
    for doc in vault["documents"]:
        if doc.get("doc_type") == "thesis" and doc.get("ticker") in flagged_tickers:
            content = doc.get("content") or ""
            # Pass first 400 chars of thesis as rotation priority context
            ticker = doc.get("ticker")
            if ticker:
                thesis_snippets[ticker] = content[:400].replace("\n", " ").strip()

    # --- Build user prompt ---
    system_prompt_text = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _SYSTEM_PROMPT_PATH.exists()
        else ""
    )

    flags_section = json.dumps(all_flags, indent=2) if all_flags else "No concentration flags above thresholds."
    stress_section = json.dumps(stress_scenarios, indent=2)
    thesis_section = json.dumps(thesis_snippets, indent=2) if thesis_snippets else "{}"

    user_prompt = (
        f"Analyze the following concentration and correlation risks for this portfolio.\n\n"
        f"## Pre-Computed Concentration Flags (use exact numbers — do NOT recalculate)\n"
        f"Single-position threshold: {config.CONCENTRATION_SINGLE_THRESHOLD * 100:.0f}%\n"
        f"Sector threshold: {config.CONCENTRATION_SECTOR_THRESHOLD * 100:.0f}%\n"
        f"Correlation threshold: |r| > {config.CORRELATION_FLAG_THRESHOLD}\n\n"
        f"{flags_section}\n\n"
        f"## Portfolio Risk Metrics (pre-computed)\n"
        f"Portfolio beta: {portfolio_beta}\n"
        f"Total portfolio value: ${total_value:,.2f}\n"
        f"Cash (dry powder): ${cash_manual:,.2f}\n\n"
        f"## Stress Scenario Dollar Impacts (beta-adjusted, pre-computed)\n"
        f"{stress_section}\n\n"
        f"## Thesis Snippets for Flagged Tickers (for rotation priority context)\n"
        f"{thesis_section}\n\n"
        f"## Instructions\n"
        "For each flag in the list above:\n"
        "  - Write a hedge_suggestion (specific, actionable, names real securities).\n"
        "  - Write a scale_step using staged language.\n"
        "  - Confirm or adjust severity based on the magnitude.\n"
        "Write a summary_narrative (3-5 sentences) covering beta, top risk, key correlation, one priority.\n"
        "Return priority_actions as an ordered ticker list — highest urgency first.\n\n"
        f"bundle_hash (MUST echo in your response): {composite['composite_hash']}\n\n"
        "Produce a ConcentrationAgentOutput JSON object."
    )

    # --- Call Gemini ---
    flag_count = len(all_flags)
    console.print(
        f"[cyan]Calling Gemini on {flag_count} flag(s) "
        f"({len(single_flags)} single-pos, {len(sector_flags)} sector, {len(corr_pairs)} corr)...[/]"
    )
    with console.status("[cyan]Analyzing..."):
        result: ConcentrationAgentOutput | None = ask_gemini_composite(
            prompt=user_prompt,
            composite_bundle_path=bundle_path,
            response_schema=ConcentrationAgentOutput,
            system_instruction=system_prompt_text,
            max_tokens=8000,
        )

    if result is None:
        console.print("[red]ERROR: Gemini returned no result. Check API logs.[/]")
        raise typer.Exit(1)

    # --- Overwrite pre-computed scalars with Python truth ---
    # Gemini might hallucinate portfolio_beta; overwrite with our computed value.
    result.portfolio_beta = portfolio_beta
    result.stress_scenarios = stress_scenarios

    # --- Rich summary ---
    summary = Table(title="Concentration Hedger — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Generated At", result.generated_at)
    summary.add_row("Portfolio Beta", f"{result.portfolio_beta:.3f}")
    summary.add_row("Flags", str(len(result.flags)))
    summary.add_row("Priority Actions", str(len(result.priority_actions)))
    console.print(summary)

    if result.flags:
        flag_table = Table(title="Concentration Flags", show_header=True)
        flag_table.add_column("Type", style="bold")
        flag_table.add_column("Tickers")
        flag_table.add_column("Weight %")
        flag_table.add_column("Threshold %")
        flag_table.add_column("Severity")
        for f in result.flags:
            sev_color = "bold red" if f.severity == "action" else "yellow"
            flag_table.add_row(
                f.flag_type,
                ", ".join(f.tickers_involved[:3]),
                f"{f.current_weight_pct:.1f}%",
                f"{f.threshold_pct:.1f}%",
                f"[{sev_color}]{f.severity}[/]",
            )
        console.print(flag_table)

    # Stress scenarios table
    stress_table = Table(title="Stress Scenarios (Python-computed)", show_header=True)
    stress_table.add_column("Scenario")
    stress_table.add_column("Dollar Impact", style="bold")
    for k, v in result.stress_scenarios.items():
        color = "green" if v > 0 else "red"
        stress_table.add_row(k.replace("_", " "), f"[{color}]${v:,.0f}[/]")
    console.print(stress_table)

    if result.priority_actions:
        console.print(f"\n[yellow]Priority actions:[/] {', '.join(result.priority_actions)}")

    if result.summary_narrative:
        console.print(f"\n[dim]Summary:[/] {result.summary_narrative}")

    # --- Write local audit files ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = str(uuid.uuid4())

    json_path = AGENT_OUTPUT_DIR / f"concentration_output_{result.bundle_hash[:12]}.json"
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
