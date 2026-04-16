"""
Tax Intelligence Agent — TLH candidates and portfolio rebalancing actions.

Reads the composite bundle (market + vault), pre-computes all tax metrics in
Python, passes only summarized facts to Gemini for narrative, and writes the
structured result to Agent_Outputs Sheet tab (--live) or local files (dry run).
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from agents.schemas.tax_schema import TaxAgentOutput
from core.composite_bundle import load_composite_bundle, resolve_latest_bundles
from core.bundle import load_bundle
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import archive_and_overwrite_agent_outputs
from utils.formatters import dicts_to_markdown_table

logger = logging.getLogger(__name__)

app = typer.Typer(help="Tax Intelligence Agent — TLH candidates and rebalancing actions")
console = Console()

AGENT_OUTPUT_DIR = Path("bundles")
AGENT_NAME = "tax"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "tax_agent_system.txt"

# Column headers for Agent_Outputs tab (Appendix A schema)
_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]


# ---------------------------------------------------------------------------
# Python pre-computation helpers
# ---------------------------------------------------------------------------

def _get_float(d: dict, key: str, default: float = 0.0) -> float:
    """Safe float extraction from position dict."""
    v = d.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _compute_holding_days(acquisition_date_raw, today: date) -> int:
    """
    Parse acquisition_date string → days held.
    Returns -1 if the date is missing, 'unknown', or unparseable.
    """
    if not acquisition_date_raw or str(acquisition_date_raw).lower() in ("unknown", "none", "n/a", ""):
        return -1
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            acq = datetime.strptime(str(acquisition_date_raw).strip(), fmt).date()
            return (today - acq).days
        except ValueError:
            continue
    logger.warning("Could not parse acquisition_date: %r", acquisition_date_raw)
    return -1


def _compute_tlh_candidates(positions: list[dict], today: date) -> list[dict]:
    """
    Scan positions for TLH candidates (unrealized_gl < TLH_LOSS_THRESHOLD_USD).
    Returns list of fact dicts — no LLM fields populated here.
    """
    threshold = config.TLH_LOSS_THRESHOLD_USD  # negative value e.g. -500.0
    candidates = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_EQUIVALENT_TICKERS:
            continue

        unrealized_gl = _get_float(pos, "unrealized_gl")
        if unrealized_gl >= threshold:  # threshold is negative; skip if loss < threshold
            continue

        holding_days = _compute_holding_days(pos.get("acquisition_date"), today)
        candidates.append({
            "ticker": ticker,
            "unrealized_loss_usd": round(unrealized_gl, 2),
            "holding_period_days": holding_days,
            "short_term": (holding_days != -1 and holding_days < 365),
            "current_weight_pct": round(_get_float(pos, "weight") * 100, 2),
        })
    return sorted(candidates, key=lambda x: x["unrealized_loss_usd"])


def _get_realized_gl_for_wash_sale():
    """Attempt to load Realized_GL from Sheets for wash-sale checks."""
    try:
        from utils.sheet_readers import get_realized_gl
        return get_realized_gl()
    except Exception as e:
        logger.debug("Wash sale check skipped: could not load Realized_GL (%s)", e)
        return None


def _check_wash_sale_risk(ticker: str, realized_gl_df) -> dict:
    """
    Check if ticker was sold at a loss in the last 30 days.
    (Simplified: if it appears in Realized_GL with a loss and recent date).
    """
    if realized_gl_df is None or realized_gl_df.empty:
        return {"wash_sale_risk": False, "wash_sale_details": ""}

    # Filter for ticker and loss
    ticker_col = 'ticker' if 'ticker' in realized_gl_df.columns else 'Ticker'
    loss_col = 'gain_loss_dollars' if 'gain_loss_dollars' in realized_gl_df.columns else 'Gain Loss $'
    date_col = 'closed_date' if 'closed_date' in realized_gl_df.columns else 'Closed Date'

    ticker_losses = realized_gl_df[
        (realized_gl_df[ticker_col] == ticker) & 
        (realized_gl_df[loss_col].astype(float) < 0)
    ]

    if ticker_losses.empty:
        return {"wash_sale_risk": False, "wash_sale_details": ""}

    # Check date range (within 30 days)
    # GSheets reader might return strings or timestamps
    ticker_losses[date_col] = pd.to_datetime(ticker_losses[date_col], errors='coerce')
    recent_losses = ticker_losses[
        ticker_losses[date_col] > (datetime.now() - timedelta(days=30))
    ]

    if not recent_losses.empty:
        return {
            "wash_sale_risk": True,
            "wash_sale_details": f"Sold at loss on {recent_losses.iloc[0][date_col].strftime('%Y-%m-%d')}"
        }

    return {"wash_sale_risk": False, "wash_sale_details": ""}


def _compute_drift(positions: list[dict], total_value: float) -> list[dict]:
    """
    Compute current vs target asset class allocation.
    Returns list of facts for Gemini to suggest rebalancing actions.
    """
    from utils.sheet_readers import get_target_allocation
    try:
        targets_df = get_target_allocation()
    except Exception as e:
        logger.warning("Rebalance check skipped: could not load Target_Allocation (%s)", e)
        return []

    if targets_df.empty:
        return []

    # Aggregate actuals
    actual_mv: dict[str, float] = {}
    ticker_by_class: dict[str, list[str]] = {}

    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_EQUIVALENT_TICKERS:
            continue
        ac = (pos.get("asset_class") or pos.get("Asset Class") or "Unallocated").strip()
        if not ac or ac.lower() in ("nan", "none", "n/a", ""):
            ac = "Unallocated"
        mv = _get_float(pos, "market_value") or _get_float(pos, "value")
        actual_mv[ac] = actual_mv.get(ac, 0.0) + mv
        if ac not in ticker_by_class: ticker_by_class[ac] = []
        ticker_by_class[ac].append(ticker)

    # Compare to targets
    target_map = {}
    for _, row in targets_df.iterrows():
        ac = str(row.iloc[0]).strip()
        raw_tgt = row.iloc[1]
        if not ac or pd.isna(raw_tgt): continue
        try:
            target_map[ac] = float(str(raw_tgt).replace('%',''))
        except ValueError: continue

    drift_facts = []
    for ac, target_pct in target_map.items():
        actual_pct = (actual_mv.get(ac, 0.0) / total_value * 100) if total_value > 0 else 0.0
        drift_pct = actual_pct - target_pct

        if abs(drift_pct) < config.REBALANCE_THRESHOLD_PCT:
            continue

        direction = "trim" if drift_pct > 0 else "underweight"
        # Representative tickers: top-3 by market value in this class
        tickers = ticker_by_class.get(ac, [])
        drift_facts.append({
            "asset_class": ac,
            "target_pct": round(target_pct, 1),
            "actual_pct": round(actual_pct, 1),
            "drift_pct": round(drift_pct, 1),
            "direction": direction,
            "representative_tickers": tickers[:3]
        })

    return drift_facts


def _result_to_sheet_rows(
    result: TaxAgentOutput,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    """Serialize TaxAgentOutput to Agent_Outputs tab rows."""
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for c in result.tlh_candidates:
        action = c.scale_step
        severity = "action" if c.unrealized_loss_usd < -5000 else "watch"
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "tlh_candidate", c.ticker, action,
            c.tlh_rationale,
            c.scale_step, severity, dry_str,
        ])

    for r in result.rebalance_actions:
        if r.ticker in config.CASH_TICKERS:
            continue
        action = r.scale_step
        severity = "action" if abs(r.drift_pct) > 10 else "watch"
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "rebalance", r.ticker, action,
            r.rationale,
            r.scale_step, severity, dry_str,
        ])

    if result.warnings:
        for w in result.warnings:
            rows.append([
                run_id, run_ts, composite_hash_short, AGENT_NAME,
                "warning", "PORTFOLIO", w[:120],
                w, "", "info", dry_str,
            ])

    return rows

# ---------------------------------------------------------------------------
# Runner & CLI
# ---------------------------------------------------------------------------

import pandas as pd # needed for _check_wash_sale_risk

def run_tax_agent(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    dry_run: bool = True,
) -> tuple[TaxAgentOutput, list[list]]:
    """
    Orchestrates the Tax Agent analysis.
    Returns (result_object, list_of_sheet_rows).
    """
    system_prompt_text = _SYSTEM_PROMPT_PATH.read_text()

    # --- Load Data ---
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))

    # --- Build investable position list ---
    investable = [
        p for p in market["positions"]
        if p.get("ticker") not in config.CASH_EQUIVALENT_TICKERS
    ]
    total_value = market.get("total_value", 0.0)
    
    # Calculate cash value from specific equivalent tickers (including SGOV)
    cash_value = sum(
        _get_float(p, "market_value") or _get_float(p, "value")
        for p in market["positions"]
        if p.get("ticker") in config.CASH_EQUIVALENT_TICKERS
    )
    
    today = date.today()
    tax_year = today.year

    # --- Pre-computation ---
    tl_facts_raw = _compute_tlh_candidates(investable, today)
    realized_gl_df = _get_realized_gl_for_wash_sale()
    
    tlh_facts = []
    for f in tl_facts_raw:
        risk = _check_wash_sale_risk(f["ticker"], realized_gl_df)
        f.update(risk)
        tlh_facts.append(f)

    drift_facts = _compute_drift(investable, total_value)

    # Markdown Tables for flat data (Optimization)
    tlh_section = dicts_to_markdown_table(tlh_facts) if tlh_facts else "No positions exceed the TLH loss threshold."
    drift_section = dicts_to_markdown_table(drift_facts) if drift_facts else "No asset classes exceed the rebalancing drift threshold."

    user_prompt = (
        f"Analyze the following portfolio for tax-loss harvesting and rebalancing.\n\n"
        f"## Pre-Computed TLH Candidates (use exact numbers — do NOT recalculate)\n"
        f"Loss threshold: ${abs(config.TLH_LOSS_THRESHOLD_USD):,.0f}\n"
        f"Tax year: {tax_year}\n\n"
        f"{tlh_section}\n\n"
        f"## Pre-Computed Asset-Class Drift (use exact percentages — do NOT recalculate)\n"
        f"Drift threshold: {config.REBALANCE_THRESHOLD_PCT:.0f}%\n\n"
        f"{drift_section}\n\n"
        f"## Portfolio Context\n"
        f"Total portfolio value: ${total_value:,.2f}\n"
        f"Cash (dry powder): ${cash_value:,.2f} "
        f"({cash_value / total_value * 100:.1f}% of portfolio)\n"
        f"bundle_hash (MUST echo in your response): {composite['composite_hash']}\n\n"
        "For each TLH candidate: write tlh_rationale, suggested_replacement, scale_step.\n"
        "For each drift action: the `ticker` field should name the best representative "
        "position to act on (from representative_tickers provided above).\n"
        "Write summary_narrative (3-5 sentences) and surface any warnings.\n"
        "Produce a TaxAgentOutput JSON object."
    )

    # --- Call Gemini ---
    result: TaxAgentOutput | None = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=TaxAgentOutput,
        system_instruction=system_prompt_text,
        max_tokens=8000,
    )

    if result is None:
        raise RuntimeError("Gemini returned no result.")

    sheet_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run)
    return result, sheet_rows


@app.command("analyze")
def main(
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
    """Pre-compute TLH candidates and rebalancing actions from the composite bundle."""
    run_id = str(uuid.uuid4())[:8]
    run_ts = datetime.now(timezone.utc).isoformat()

    # --- Banner ---
    if live:
        console.print(Panel.fit("[bold white on red] LIVE MODE — Sheet writes enabled [/]", border_style="red"))
    else:
        console.print(Panel.fit("[bold black on yellow] DRY RUN — No Sheet writes. [/]", border_style="yellow"))

    # --- Resolve bundle path ---
    if bundle == "latest":
        composite_candidates = sorted(Path("bundles").glob("composite_bundle_*.json"), key=lambda p: p.stat().st_mtime)
        if not composite_candidates:
            console.print("[red]ERROR: No composite bundles found.[/]")
            raise typer.Exit(1)
        bundle_path = composite_candidates[-1]
    else:
        bundle_path = Path(bundle)
        if not bundle_path.exists():
            console.print(f"[red]ERROR: Bundle not found: {bundle_path}[/]")
            raise typer.Exit(1)

    console.print(f"[bold]Tax Intelligence Agent[/] | Run ID: {run_id} | Live: {live}")
    console.print(f"[dim]Bundle: {bundle_path.name}[/]")

    try:
        result, sheet_rows = run_tax_agent(bundle_path, run_id, run_ts, dry_run=not live)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(1)

    # --- Rich summary table ---
    summary = Table(title="Tax Intelligence Agent — Summary", show_header=False, box=None)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Bundle Hash", result.bundle_hash[:16] + "...")
    summary.add_row("Generated At", result.generated_at)
    summary.add_row("TLH Candidates", str(len(result.tlh_candidates)))
    summary.add_row("Rebalance Actions", str(len(result.rebalance_actions)))
    summary.add_row("Warnings", str(len(result.warnings)))
    console.print(summary)

    # --- Local audit file ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = Path("bundles/runs") / f"tax_analysis_{run_ts.replace(':', '')}_{run_id}.json"
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
