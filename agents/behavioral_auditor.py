"""
Behavioral Finance Auditor Agent -- Morgan Housel Framework.

Evaluates the investor's recent portfolio behavior against the psychological
principles of 'The Psychology of Money': compounding interruption, volatility
tolerance, margin of safety, and playing the right game.

No quantitative pre-computation. The agent reads the composite bundle (positions,
unrealized P&L, allocation) plus recent Trade_Log entries and produces 3-7
behavioral audit findings per run.

CLI:
    python manager.py agent behavioral analyze
    python manager.py agent behavioral analyze --bundle bundles/composite_20260414_....json
    python manager.py agent behavioral analyze --trade-days 60
    python manager.py agent behavioral analyze --live
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
from agents.schemas.behavioral_schema import BehavioralAuditorResponse
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from utils.gemini_client import ask_gemini_composite

logger = logging.getLogger(__name__)

app = typer.Typer(help="Behavioral Finance Auditor -- Morgan Housel framework")
console = Console()

AGENT_NAME = "behavioral_auditor"

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "behavioral_auditor_system.txt"
_FRAMEWORK_PATH     = (
    Path(__file__).parent.parent / "vault" / "frameworks" / "psychology_of_money.json"
)

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]

_VERDICT_TO_SEVERITY = {
    "IRRATIONAL": "action",
    "CAUTION":    "watch",
    "REASONABLE": "info",
}


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def _build_positions_context(market: dict) -> str:
    """
    Produce a compact, human-readable positions summary sorted by unrealized
    gain/loss so the LLM can spot behavioral patterns at a glance.
    """
    positions = market.get("positions", [])
    investable = [
        p for p in positions
        if not p.get("is_cash") and p.get("ticker") not in config.CASH_TICKERS
    ]
    cash_rows = [
        p for p in positions
        if p.get("is_cash") or p.get("ticker") in config.CASH_TICKERS
    ]

    total_value = float(market.get("total_value", 1) or 1)

    # Sort investable by unrealized_gain_loss ascending (worst losses first)
    def _unr(p):
        raw = p.get("unrealized_gain_loss") or p.get("gain_loss") or 0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    investable_sorted = sorted(investable, key=_unr)

    rows = []
    for p in investable_sorted:
        ticker     = p.get("ticker", "?")
        mkt_val    = float(p.get("market_value") or p.get("current_value") or 0)
        weight_pct = round(mkt_val / total_value * 100, 1)
        unr        = _unr(p)
        unr_pct    = p.get("unrealized_gain_loss_pct") or p.get("gain_loss_pct")
        try:
            unr_pct = f"{float(unr_pct):.1f}%" if unr_pct is not None else "n/a"
        except (TypeError, ValueError):
            unr_pct = "n/a"
        rows.append(
            f"  {ticker:<6} weight={weight_pct:>5.1f}%  unrealized=${unr:>10,.0f}  ({unr_pct})"
        )

    cash_total = sum(
        float(p.get("market_value") or p.get("current_value") or 0) for p in cash_rows
    )
    cash_pct = round(cash_total / total_value * 100, 1)

    return (
        f"PORTFOLIO SNAPSHOT  total_value=${total_value:,.0f}  positions={len(investable)}\n"
        f"Cash/money-market: ${cash_total:,.0f} ({cash_pct}% of portfolio)\n\n"
        f"Positions sorted worst-to-best unrealized P&L:\n"
        + "\n".join(rows)
    )


def _load_recent_trades(days: int) -> str:
    """
    Attempt to read the most recent Trade_Log rows from Google Sheets.
    Returns a formatted string for the LLM prompt, or an empty string if unavailable.
    """
    try:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        try:
            ws = ss.worksheet(config.TAB_TRADE_LOG)
        except Exception:
            return ""

        all_rows = ws.get_all_values()
        if len(all_rows) < 2:
            return ""

        header = all_rows[0]
        cutoff = date.today() - timedelta(days=days)

        recent = []
        try:
            date_idx = header.index("Date")
        except ValueError:
            date_idx = 0

        for row in all_rows[1:]:
            if len(row) <= date_idx:
                continue
            try:
                row_date = datetime.strptime(row[date_idx], "%Y-%m-%d").date()
                if row_date >= cutoff:
                    # Zip header + row, keep only readable fields
                    recent.append(dict(zip(header, row)))
            except (ValueError, TypeError):
                continue

        if not recent:
            return ""

        lines = [f"RECENT TRADE LOG (last {days} days, {len(recent)} entries):"]
        for r in recent[-20:]:   # cap at 20 to keep context tight
            lines.append(
                f"  {r.get('Date','')}  "
                f"SOLD={r.get('Sell_Ticker','')}  "
                f"BOUGHT={r.get('Buy_Ticker','')}  "
                f"type={r.get('Rotation_Type','')}  "
                f"bet={r.get('Implicit_Bet','')[:60]}"
            )
        return "\n".join(lines)

    except Exception as e:
        logger.debug("Could not load Trade_Log for behavioral context: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Sheet write helpers
# ---------------------------------------------------------------------------

def _result_to_sheet_rows(
    result: BehavioralAuditorResponse,
    run_id: str,
    run_ts: str,
    dry_run: bool,
) -> list[list]:
    rows = []
    composite_hash_short = result.bundle_hash[:16]
    dry_str = "TRUE" if dry_run else "FALSE"

    # One row per audit finding
    for audit in result.audits:
        severity = _VERDICT_TO_SEVERITY.get(audit.final_verdict, "info")
        rationale = f"{audit.housel_principle}: {audit.housel_quote[:150]}"
        rows.append([
            run_id, run_ts, composite_hash_short, AGENT_NAME,
            "behavioral_audit",
            "PORTFOLIO",
            audit.final_verdict,
            f"{audit.action_analyzed[:200]} | {audit.compounding_check[:100]}",
            "",          # scale_step — N/A for behavioral audits
            severity,
            dry_str,
        ])

    # Summary row
    rows.append([
        run_id, run_ts, composite_hash_short, AGENT_NAME,
        "behavioral_summary", "PORTFOLIO",
        result.overall_behavioral_score,
        f"{result.summary_narrative[:300]} | TOP RISK: {result.top_risk[:150]}",
        "", "info", dry_str,
    ])

    return rows


def _write_to_agent_outputs(ss, new_rows: list[list]) -> None:
    existing_tabs = {ws.title for ws in ss.worksheets()}

    if config.TAB_AGENT_OUTPUTS not in existing_tabs:
        ws_out = ss.add_worksheet(
            title=config.TAB_AGENT_OUTPUTS,
            rows=2000,
            cols=len(_AGENT_OUTPUTS_HEADERS) + 1,
        )
        time.sleep(1.0)
        ws_out.insert_row(_AGENT_OUTPUTS_HEADERS, 1)
        ws_out.freeze(rows=1)
        time.sleep(0.5)
    else:
        ws_out = ss.worksheet(config.TAB_AGENT_OUTPUTS)

    ws_out.append_rows(new_rows, value_input_option="USER_ENTERED")
    time.sleep(0.5)
    console.print(
        f"[green]LIVE -- wrote {len(new_rows)} row(s) to {config.TAB_AGENT_OUTPUTS}.[/]"
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
    trade_days: int = typer.Option(
        60,
        "--trade-days",
        help="How many days of Trade_Log history to include as behavioral context.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write output to Agent_Outputs Sheet tab. Default: dry run.",
    ),
):
    """
    Behavioral Finance Auditor -- Morgan Housel framework.

    Audits portfolio behavior (compounding interruptions, volatility tolerance,
    margin of safety) against the Psychology of Money principles. Produces
    3-7 behavioral audit findings from the composite bundle + recent Trade_Log.
    """

    # --- Banner ---
    if live:
        console.print(Panel.fit(
            "[bold white on red] LIVE MODE -- Sheet writes enabled [/]",
            border_style="red",
        ))
    else:
        console.print(Panel.fit(
            "[bold black on yellow] DRY RUN -- No Sheet writes. Use --live to enable. [/]",
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
                "[red]ERROR: No composite bundles found. "
                "Run: python manager.py bundle composite[/]"
            )
            raise typer.Exit(1)
        bundle_path = composite_candidates[-1]
        console.print(f"[dim]Using latest composite bundle: {bundle_path.name}[/]")
    else:
        bundle_path = Path(bundle)
        if not bundle_path.exists():
            console.print(f"[red]ERROR: Bundle not found: {bundle_path}[/]")
            raise typer.Exit(1)

    # --- Load composite + market sub-bundle for Python context building ---
    composite = load_composite_bundle(bundle_path)
    console.print(f"[dim]Composite hash: {composite['composite_hash'][:16]}...[/]")

    market = load_bundle(Path(composite["market_bundle_path"]))
    positions_context = _build_positions_context(market)

    # --- Load Housel framework JSON ---
    framework_context = ""
    if _FRAMEWORK_PATH.exists():
        try:
            framework_context = _FRAMEWORK_PATH.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Could not load psychology_of_money.json: %s", e)
    else:
        console.print(
            f"[yellow]! Framework not found at {_FRAMEWORK_PATH}. "
            "Audit will proceed without structured principle references.[/]"
        )

    # --- Load recent Trade_Log entries (optional context) ---
    with console.status(f"[cyan]Loading Trade_Log (last {trade_days} days)..."):
        trade_context = _load_recent_trades(trade_days)
    if trade_context:
        console.print(f"[dim]Trade_Log context loaded ({trade_context.count(chr(10))} entries).[/]")
    else:
        console.print("[dim]Trade_Log unavailable or empty -- auditing positions only.[/]")

    # --- Load system instruction ---
    system_instruction = ""
    if _SYSTEM_PROMPT_PATH.exists():
        system_instruction = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()

    # --- Build user prompt ---
    user_prompt = (
        f"Audit this portfolio for behavioral finance violations under the Morgan Housel framework.\n\n"
        f"## Portfolio State\n"
        f"{positions_context}\n\n"
    )
    if trade_context:
        user_prompt += f"## Recent Actions\n{trade_context}\n\n"
    if framework_context:
        user_prompt += (
            f"## Psychology of Money Framework Reference\n"
            f"{framework_context}\n\n"
        )
    user_prompt += (
        f"## Instructions\n"
        f"Produce 3-7 behavioral audit findings. Each finding must cite a specific "
        f"observable pattern from the portfolio data above -- not generic advice.\n"
        f"Use housel_principle to reference the exact principle_id from the framework JSON.\n"
        f"overall_behavioral_score must be one of: DISCIPLINED, MIXED, AT_RISK.\n"
        f"final_verdict for each audit must be one of: REASONABLE, CAUTION, IRRATIONAL.\n\n"
        f"bundle_hash (MUST echo in your response): {composite['composite_hash']}\n\n"
        f"Produce a BehavioralAuditorResponse JSON object."
    )

    # --- Gemini call ---
    console.print("[cyan]Querying Gemini -- behavioral audit in progress...[/]")
    with console.status("[cyan]Analyzing portfolio behavior against Housel principles..."):
        result = ask_gemini_composite(
            prompt=user_prompt,
            composite_bundle_path=bundle_path,
            response_schema=BehavioralAuditorResponse,
            system_instruction=system_instruction,
        )

    if result is None:
        console.print("[red]ERROR: Gemini returned no response.[/]")
        raise typer.Exit(1)

    # --- Console output ---
    score_color = {
        "DISCIPLINED": "green",
        "MIXED":       "yellow",
        "AT_RISK":     "red",
    }.get(result.overall_behavioral_score, "white")

    console.print(
        f"\n[bold {score_color}]Behavioral Score: {result.overall_behavioral_score}[/]"
    )
    console.print(f"[dim]{result.summary_narrative}[/]")
    console.print(f"[bold yellow]Top Risk:[/] {result.top_risk}\n")

    audit_table = Table(title=f"Behavioral Audit Findings ({len(result.audits)})", show_lines=True)
    audit_table.add_column("Verdict", style="bold", width=12)
    audit_table.add_column("Action Analyzed", width=40)
    audit_table.add_column("Principle", width=22)
    audit_table.add_column("Compounding Check", width=40)
    for audit in result.audits:
        verdict_style = {
            "IRRATIONAL": "red",
            "CAUTION":    "yellow",
            "REASONABLE": "green",
        }.get(audit.final_verdict, "white")
        audit_table.add_row(
            f"[{verdict_style}]{audit.final_verdict}[/]",
            audit.action_analyzed[:120],
            audit.housel_principle,
            audit.compounding_check[:120],
        )
    console.print(audit_table)

    # --- Sheet write (live mode only) ---
    if not live:
        console.print(
            Panel.fit(
                f"[bold black on yellow] DRY RUN -- {len(result.audits)} finding(s) not written. "
                "Use --live to persist. [/]",
                border_style="yellow",
            )
        )
        return

    run_id = str(uuid.uuid4())
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_rows = _result_to_sheet_rows(result, run_id, run_ts, dry_run=False)

    with console.status(f"[cyan]Writing {len(new_rows)} row(s) to {config.TAB_AGENT_OUTPUTS}..."):
        try:
            from utils.sheet_readers import get_gspread_client
            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            _write_to_agent_outputs(ss, new_rows)
        except Exception as e:
            console.print(f"[red]ERROR: Sheet write failed: {e}[/]")
            raise typer.Exit(1)


if __name__ == "__main__":
    app()
