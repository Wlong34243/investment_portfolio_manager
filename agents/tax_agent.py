"""
Tax Intelligence Agent — TLH candidates and portfolio rebalancing actions.

Reads the composite bundle (market + vault), pre-computes all tax metrics in
Python, passes only summarized facts to Gemini for narrative, and writes the
structured result to Agent_Outputs Sheet tab (--live) or local files (dry run).

Pre-computation in Python (never delegated to LLM):
  - Unrealized G/L per position (from bundle fields)
  - Holding period in days (from acquisition_date)
  - Short-term vs long-term classification (< 365 days)
  - TLH candidates (unrealized_gl < TLH_LOSS_THRESHOLD_USD)
  - Wash sale risk (BUY transactions in last 30 days for each candidate ticker)
  - Asset-class drift from Target_Allocation (read from Sheets)

Gemini writes: narrative rationale, replacement suggestions, scale steps, summary.

CLI:
    python manager.py agent tax analyze
    python manager.py agent tax analyze --bundle bundles/composite_20260413_....json
    python manager.py agent tax analyze --live
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
        if ticker in config.CASH_TICKERS:
            continue

        unrealized_gl = _get_float(pos, "unrealized_gl")
        if unrealized_gl >= threshold:  # threshold is negative; skip if loss < threshold
            continue

        holding_days = _compute_holding_days(
            pos.get("acquisition_date") or pos.get("tax_treatment"),
            today,
        )
        short_term = holding_days < 365 if holding_days > 0 else True  # conservative default

        candidates.append({
            "ticker": ticker,
            "unrealized_loss_usd": round(abs(unrealized_gl), 2),
            "holding_period_days": holding_days,
            "short_term": short_term,
            "wash_sale_risk": False,  # populated by _flag_wash_sale_risks
        })

    # Sort by largest loss first
    candidates.sort(key=lambda x: x["unrealized_loss_usd"], reverse=True)
    return candidates


def _flag_wash_sale_risks(candidates: list[dict]) -> set[str]:
    """
    Read the Transactions tab from Google Sheets and flag tickers with a BUY
    transaction in the last 30 days. Returns set of risky ticker symbols.

    If the Transactions tab is unavailable, logs a warning and returns empty set
    (the agent run continues; Gemini will be told data was unavailable).
    """
    from utils.sheet_readers import get_gspread_client

    risky: set[str] = set()
    candidate_tickers = {c["ticker"] for c in candidates}
    if not candidate_tickers:
        return risky

    cutoff = date.today() - timedelta(days=30)

    try:
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_TRANSACTIONS)
        rows = ws.get_all_values()
    except Exception as e:
        logger.warning("Could not read Transactions tab for wash-sale check: %s", e)
        return risky

    if len(rows) < 2:
        return risky

    headers = [h.strip().lower() for h in rows[0]]
    try:
        date_idx = next(i for i, h in enumerate(headers) if "date" in h and "trade" in h)
    except StopIteration:
        try:
            date_idx = next(i for i, h in enumerate(headers) if "date" in h)
        except StopIteration:
            logger.warning("No date column found in Transactions tab.")
            return risky

    try:
        action_idx = next(i for i, h in enumerate(headers) if "action" in h)
        ticker_idx = next(i for i, h in enumerate(headers) if "ticker" in h or "symbol" in h)
    except StopIteration:
        logger.warning("Missing action or ticker column in Transactions tab.")
        return risky

    for row in rows[1:]:
        if len(row) <= max(date_idx, action_idx, ticker_idx):
            continue
        ticker = row[ticker_idx].strip().upper()
        if ticker not in candidate_tickers:
            continue
        action = row[action_idx].strip().lower()
        if "buy" not in action:
            continue
        raw_date = row[date_idx].strip()
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                txn_date = datetime.strptime(raw_date, fmt).date()
                if txn_date >= cutoff:
                    risky.add(ticker)
                break
            except ValueError:
                continue

    return risky


def _compute_drift(positions: list[dict], total_value: float) -> list[dict]:
    """
    Compute asset-class drift vs Target_Allocation tab.
    Returns list of drift fact dicts for asset classes exceeding REBALANCE_THRESHOLD_PCT.
    If Target_Allocation is unavailable, returns empty list.
    """
    from utils.sheet_readers import get_gspread_client

    if total_value <= 0:
        return []

    # --- Read Target_Allocation ---
    try:
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_TARGET_ALLOCATION)
        rows = ws.get_all_values()
    except Exception as e:
        logger.warning("Could not read Target_Allocation tab: %s", e)
        return []

    if len(rows) < 2:
        return []

    headers = [h.strip() for h in rows[0]]
    target_map: dict[str, float] = {}

    # Find asset-class and target-pct columns flexibly
    ac_col = next((i for i, h in enumerate(headers) if "asset" in h.lower() and "class" in h.lower()), None)
    tgt_col = next((i for i, h in enumerate(headers) if "target" in h.lower() and "%" in h), None)
    if tgt_col is None:
        tgt_col = next((i for i, h in enumerate(headers) if "target" in h.lower()), None)
    if ac_col is None or tgt_col is None:
        logger.warning("Target_Allocation tab missing expected columns: %s", headers)
        return []

    for row in rows[1:]:
        if len(row) <= max(ac_col, tgt_col):
            continue
        ac = row[ac_col].strip()
        raw_tgt = row[tgt_col].strip().replace("%", "").replace(",", "")
        if not ac or not raw_tgt:
            continue
        try:
            target_map[ac] = float(raw_tgt)
        except ValueError:
            continue

    if not target_map:
        logger.warning("Target_Allocation tab has no parseable rows.")
        return []

    # --- Compute actual weights per asset class from bundle positions ---
    # Exclude cash tickers
    actual_mv: dict[str, float] = {}
    ticker_by_class: dict[str, list[str]] = {}

    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in config.CASH_TICKERS:
            continue
        ac = (pos.get("asset_class") or pos.get("Asset Class") or "Unallocated").strip()
        if not ac or ac.lower() in ("nan", "none", "n/a", ""):
            ac = "Unallocated"
        mv = _get_float(pos, "market_value") or _get_float(pos, "value")
        actual_mv[ac] = actual_mv.get(ac, 0.0) + mv
        ticker_by_class.setdefault(ac, []).append(ticker)

    # --- Compute drift ---
    drift_facts = []
    for ac, target_pct in target_map.items():
        actual_pct = actual_mv.get(ac, 0.0) / total_value * 100
        drift_pct = round(actual_pct - target_pct, 2)
        if abs(drift_pct) < config.REBALANCE_THRESHOLD_PCT:
            continue
        direction = "overweight" if drift_pct > 0 else "underweight"
        # Representative tickers: top-3 by market value in this class
        tickers = ticker_by_class.get(ac, [])
        tickers_sorted = sorted(
            tickers,
            key=lambda t: next(
                (_get_float(p, "market_value") or _get_float(p, "value")
                 for p in positions if p.get("ticker") == t),
                0.0,
            ),
            reverse=True,
        )[:3]
        drift_facts.append({
            "asset_class": ac,
            "current_weight_pct": round(actual_pct, 2),
            "target_weight_pct": round(target_pct, 2),
            "drift_pct": drift_pct,
            "direction": direction,
            "representative_tickers": tickers_sorted,
        })

    # Sort by absolute drift descending
    drift_facts.sort(key=lambda x: abs(x["drift_pct"]), reverse=True)
    return drift_facts


# ---------------------------------------------------------------------------
# Sheet write helpers
# ---------------------------------------------------------------------------

def _archive_and_overwrite(
    ss,
    new_rows: list[list],
    run_ts: str,
    composite_hash: str,
    dry_run: bool,
) -> None:
    """
    Archive-before-overwrite pattern for Agent_Outputs tab.
    1. Copy existing rows to Agent_Outputs_Archive with archived_at prepended.
    2. Overwrite Agent_Outputs with new_rows in a single batch call.
    """
    existing_tabs = {ws.title for ws in ss.worksheets()}

    # --- Get or create Agent_Outputs ---
    if config.TAB_AGENT_OUTPUTS not in existing_tabs:
        ws_out = ss.add_worksheet(title=config.TAB_AGENT_OUTPUTS, rows=2000, cols=len(_AGENT_OUTPUTS_HEADERS) + 1)
        time.sleep(1.0)
        existing_rows = []
    else:
        ws_out = ss.worksheet(config.TAB_AGENT_OUTPUTS)
        existing_rows = ws_out.get_all_values()

    # --- Archive existing rows ---
    if len(existing_rows) > 1:  # more than just header
        if config.TAB_AGENT_OUTPUTS_ARCHIVE not in existing_tabs:
            ws_arc = ss.add_worksheet(
                title=config.TAB_AGENT_OUTPUTS_ARCHIVE,
                rows=10000,
                cols=len(_AGENT_OUTPUTS_HEADERS) + 2,
            )
            time.sleep(1.0)
            arc_headers = ["archived_at"] + existing_rows[0]
            ws_arc.update(range_name="A1", values=[arc_headers], value_input_option="USER_ENTERED")
            time.sleep(0.5)
        else:
            ws_arc = ss.worksheet(config.TAB_AGENT_OUTPUTS_ARCHIVE)

        archive_rows = [[run_ts] + row for row in existing_rows[1:]]
        # Append to archive (archive grows over time; never overwritten)
        if archive_rows:
            ws_arc.append_rows(archive_rows, value_input_option="USER_ENTERED")
            time.sleep(1.0)
        console.print(f"[dim]Archived {len(archive_rows)} existing row(s) to {config.TAB_AGENT_OUTPUTS_ARCHIVE}.[/]")

    # --- Overwrite Agent_Outputs with new data (single batch call) ---
    ws_out.clear()
    time.sleep(0.5)
    all_data = [_AGENT_OUTPUTS_HEADERS] + new_rows
    ws_out.update(range_name="A1", values=all_data, value_input_option="USER_ENTERED")
    time.sleep(1.0)
    console.print(f"[green]LIVE — wrote {len(new_rows)} row(s) to {config.TAB_AGENT_OUTPUTS} (single batch).[/]")


def _result_to_sheet_rows(
    result: TaxAgentOutput,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    """Serialize TaxAgentOutput to Agent_Outputs tab rows (Appendix A schema)."""
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    for c in result.tlh_candidates:
        action = c.scale_step
        severity = "action" if c.unrealized_loss_usd > 5000 else "watch"
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
    """Pre-compute TLH candidates and rebalancing actions from the composite bundle."""

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

    # --- Load composite bundle ---
    composite = load_composite_bundle(bundle_path)
    console.print(f"[dim]Composite hash: {composite['composite_hash'][:16]}...[/]")

    # --- Load market sub-bundle ---
    market = load_bundle(Path(composite["market_bundle_path"]))

    # --- Build investable position list ---
    investable = [
        p for p in market["positions"]
        if p.get("ticker") not in config.CASH_TICKERS
    ]
    total_value = market.get("total_value", 0.0)
    cash_manual = market.get("cash_manual", 0.0)
    today = date.today()
    tax_year = today.year

    console.print(f"[dim]{len(investable)} investable positions | portfolio ${total_value:,.0f}[/]")

    # --- Pre-compute TLH candidates ---
    console.print("[cyan]Pre-computing TLH candidates...[/]")
    tlh_facts = _compute_tlh_candidates(investable, today)
    console.print(f"[dim]{len(tlh_facts)} TLH candidate(s) above ${abs(config.TLH_LOSS_THRESHOLD_USD):,.0f} threshold.[/]")

    # --- Flag wash sale risks ---
    if tlh_facts:
        console.print("[cyan]Checking wash-sale risks from Transactions tab...[/]")
        risky_tickers = _flag_wash_sale_risks(tlh_facts)
        for fact in tlh_facts:
            fact["wash_sale_risk"] = fact["ticker"] in risky_tickers
        if risky_tickers:
            console.print(f"[yellow]! Wash-sale risk flagged: {sorted(risky_tickers)}[/]")

    # --- Pre-compute drift ---
    console.print("[cyan]Pre-computing asset-class drift from Target_Allocation...[/]")
    drift_facts = _compute_drift(investable, total_value)
    console.print(f"[dim]{len(drift_facts)} asset class(es) exceed {config.REBALANCE_THRESHOLD_PCT:.0f}% drift threshold.[/]")

    # --- Build user prompt ---
    system_prompt_text = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _SYSTEM_PROMPT_PATH.exists()
        else ""
    )

    tlh_section = (
        json.dumps(tlh_facts, indent=2)
        if tlh_facts
        else "No positions exceed the TLH loss threshold."
    )
    drift_section = (
        json.dumps(drift_facts, indent=2)
        if drift_facts
        else "No asset classes exceed the rebalancing drift threshold."
    )

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
        f"Cash (dry powder): ${cash_manual:,.2f} "
        f"({cash_manual / total_value * 100:.1f}% of portfolio)\n"
        f"bundle_hash (MUST echo in your response): {composite['composite_hash']}\n\n"
        "For each TLH candidate: write tlh_rationale, suggested_replacement, scale_step.\n"
        "For each drift action: the `ticker` field should name the best representative "
        "position to act on (from representative_tickers provided above).\n"
        "Write summary_narrative (3-5 sentences) and surface any warnings.\n"
        "Produce a TaxAgentOutput JSON object."
    )

    # --- Call Gemini ---
    console.print(
        f"[cyan]Calling Gemini — {len(tlh_facts)} TLH candidates, "
        f"{len(drift_facts)} rebalance action(s)...[/]"
    )
    with console.status("[cyan]Analyzing..."):
        result: TaxAgentOutput | None = ask_gemini_composite(
            prompt=user_prompt,
            composite_bundle_path=bundle_path,
            response_schema=TaxAgentOutput,
            system_instruction=system_prompt_text,
            max_tokens=8000,
        )

    if result is None:
        console.print("[red]ERROR: Gemini returned no result. Check API logs.[/]")
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

    if result.tlh_candidates:
        tlh_table = Table(title="TLH Candidates", show_header=True)
        tlh_table.add_column("Ticker", style="bold")
        tlh_table.add_column("Loss $")
        tlh_table.add_column("Days Held")
        tlh_table.add_column("ST?")
        tlh_table.add_column("Wash Risk")
        tlh_table.add_column("Replacement")
        for c in result.tlh_candidates:
            wash_color = "red" if c.wash_sale_risk else "green"
            tlh_table.add_row(
                c.ticker,
                f"${c.unrealized_loss_usd:,.0f}",
                str(c.holding_period_days) if c.holding_period_days > 0 else "unknown",
                "yes" if c.short_term else "no",
                f"[{wash_color}]{'YES' if c.wash_sale_risk else 'no'}[/]",
                c.suggested_replacement or "—",
            )
        console.print(tlh_table)

    if result.rebalance_actions:
        reb_table = Table(title="Rebalance Actions", show_header=True)
        reb_table.add_column("Ticker", style="bold")
        reb_table.add_column("Direction")
        reb_table.add_column("Drift %")
        reb_table.add_column("Scale Step")
        for r in result.rebalance_actions:
            color = "red" if r.direction == "trim" else "green"
            reb_table.add_row(
                r.ticker,
                f"[{color}]{r.direction}[/]",
                f"{r.drift_pct:+.1f}%",
                r.scale_step[:60] + ("..." if len(r.scale_step) > 60 else ""),
            )
        console.print(reb_table)

    if result.warnings:
        console.print("\n[yellow]Warnings:[/]")
        for w in result.warnings:
            console.print(f"  [yellow]•[/] {w}")

    if result.summary_narrative:
        console.print(f"\n[dim]Summary:[/] {result.summary_narrative}")

    # --- Write local audit files (always, regardless of --live) ---
    AGENT_OUTPUT_DIR.mkdir(exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = str(uuid.uuid4())

    json_path = AGENT_OUTPUT_DIR / f"tax_output_{result.bundle_hash[:12]}.json"
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

    _archive_and_overwrite(ss, sheet_rows, run_ts, composite["composite_hash"], dry_run=False)
    console.print(f"[dim]Local audit file:[/] {json_path}")


if __name__ == "__main__":
    app()
