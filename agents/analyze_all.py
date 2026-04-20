"""
analyze-all orchestrator — Phase 5-H.

Runs all portfolio agents in sequence over a single composite bundle,
collects their outputs, and writes everything to Agent_Outputs in one
batch transaction. One agent failure does not abort the run.

Called from manager.py:
    python manager.py analyze-all
    python manager.py analyze-all --fresh-bundle
    python manager.py analyze-all --agents rebuy,tax,valuation
    python manager.py analyze-all --live

Architecture:
  1. Optionally build fresh market + vault + composite bundles.
  2. Resolve latest composite bundle.
  3. Call each agent's analyze() with live=False (no individual Sheet writes).
     Each agent writes its own JSON output to bundles/.
  4. Read each agent's JSON output and reconstruct the Pydantic model.
  5. Collect sheet rows from the 6 standard-schema agents
     (tax, valuation, concentration, macro, thesis, bagger).
     Rebuy uses a legacy schema — it is included in the manifest
     summary but NOT in the standard Agent_Outputs batch write.
  6. [if --live] Single archive-before-overwrite + batch write.
  7. Write AgentRunManifest to bundles/runs/.
  8. Print Rich summary table.
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
from rich.rule import Rule
from rich.table import Table

import config
from agents.schemas.run_manifest_schema import AgentRunManifest, AgentRunSummary
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import archive_and_overwrite_agent_outputs

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Agent registry — standard-schema agents (11-col Agent_Outputs format)
# ---------------------------------------------------------------------------
# Rebuy uses a legacy write pattern; it is run separately and included in
# the manifest summary, but its rows are NOT in the standard batch write.

_STANDARD_AGENTS = [
    "tax",
    "valuation",
    "concentration",
    "macro",
    "thesis",
    "bagger",
    "value",
]

_ALL_AGENTS = ["rebuy"] + _STANDARD_AGENTS   # rebuy first (no external API calls)

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]

# Compact write format for Agent_Outputs tab — human-readable, no UUID noise
_COMPACT_HEADERS = [
    "run_date", "run_id_short", "agent", "signal",
    "ticker", "action", "narrative", "scale_step", "severity", "score",
]

# Severity sort order: data quality issues surface first, then actionable rows
_SEVERITY_ORDER = {"data_quality": 0, "action": 1, "alert": 2, "watch": 3, "info": 4}

RUNS_DIR = Path("bundles") / "runs"


# ---------------------------------------------------------------------------
# Agent_Outputs row transformation helpers
# ---------------------------------------------------------------------------

def _clean_headline(text: str, max_len: int = 80) -> str:
    """Truncate action text cleanly on a word boundary, never mid-word."""
    text = str(text)
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return truncated + "…"


def _compact_run_ts(run_ts: str) -> str:
    """Convert ISO-8601 UTC timestamp to 'YYYY-MM-DD HH:MM' (no seconds, no T/Z)."""
    try:
        dt = datetime.fromisoformat(run_ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return run_ts[:16]


def _transform_to_compact(rows: list[list], run_id_short: str, run_date: str) -> list[list]:
    """
    Convert 11-col agent rows to 10-col compact format:
      Old: [run_id, run_ts, composite_hash, agent, signal_type, ticker,
            action, rationale, scale_step, severity, dry_run]
      New: [run_date, run_id_short, agent, signal, ticker, action,
            narrative, scale_step, severity, score]
    composite_hash is dropped (lives in the manifest file).
    dry_run is replaced by score (empty — available for future use).
    """
    compact = []
    for r in rows:
        if len(r) < 11:
            continue
        compact.append([
            run_date,
            run_id_short,
            r[3],                        # agent
            r[4],                        # signal (was signal_type)
            r[5],                        # ticker
            _clean_headline(str(r[6])),  # action (word-boundary truncated)
            r[7],                        # narrative (was rationale)
            r[8],                        # scale_step
            r[9],                        # severity
            "",                          # score (empty; replaces dry_run)
        ])
    return compact


def _collapse_hold_rows(rows: list[list]) -> list[list]:
    """
    Collapse valuation-agent HOLD rows (severity=info) into a single summary row.
    Individual rows with severity in (action, alert, watch, data_quality) are kept.
    The archive tab receives the full uncollapsed set (handled upstream).
    """
    hold_tickers: list[str] = []
    hold_run_date = ""
    hold_run_id_short = ""
    non_hold: list[list] = []

    for r in rows:
        # Compact format: [run_date, run_id_short, agent, signal, ticker, action, narrative, scale_step, severity, score]
        #                   [0]        [1]           [2]    [3]     [4]     [5]     [6]        [7]         [8]       [9]
        is_valuation_hold = (
            r[2] == "valuation"
            and str(r[3]).lower() in ("hold",)
            and r[8] == "info"
        )
        if is_valuation_hold:
            hold_tickers.append(str(r[4]))
            if not hold_run_date:
                hold_run_date = r[0]
                hold_run_id_short = r[1]
        else:
            non_hold.append(r)

    if hold_tickers:
        n = len(hold_tickers)
        ticker_str = ", ".join(hold_tickers[:50])
        if len(hold_tickers) > 50:
            ticker_str += f" +{len(hold_tickers) - 50} more"
        non_hold.append([
            hold_run_date, hold_run_id_short,
            "valuation", "hold",
            f"[HOLD SUMMARY — {n} positions]",
            "Hold — see narrative for position list",
            ticker_str, "", "info", "",
        ])

    return non_hold


def _sort_by_severity(rows: list[list]) -> list[list]:
    """Sort rows: data_quality → action → alert → watch → info."""
    return sorted(rows, key=lambda r: _SEVERITY_ORDER.get(str(r[8]), 5))


# ---------------------------------------------------------------------------
# Per-agent runner
# ---------------------------------------------------------------------------

def _load_agent_module(agent_name: str):
    """Lazy-import an agent module by name. Returns the module."""
    import importlib
    module_map = {
        "rebuy":         "agents.rebuy_analyst",
        "tax":           "agents.tax_agent",
        "valuation":     "agents.valuation_agent",
        "concentration": "agents.concentration_hedger",
        "macro":         "agents.macro_cycle_agent",
        "thesis":        "agents.thesis_screener",
        "bagger":        "agents.bagger_screener",
        "value":         "agents.value_investing_screener",
    }
    mod_path = module_map.get(agent_name)
    if not mod_path:
        raise ValueError(f"Unknown agent: {agent_name}")
    return importlib.import_module(mod_path)


def _load_schema_class(agent_name: str):
    """Return the top-level Pydantic schema class for the agent's JSON output."""
    import importlib
    schema_map = {
        "rebuy":         ("agents.schemas.rebuy_schema",          "RebuyAnalystResponse"),
        "tax":           ("agents.schemas.tax_schema",            "TaxAgentOutput"),
        "valuation":     ("agents.schemas.valuation_schema",      "ValuationAgentOutput"),
        "concentration": ("agents.schemas.concentration_schema",  "ConcentrationAgentOutput"),
        "macro":         ("agents.schemas.macro_cycle_schema",    "MacroCycleResponse"),
        "thesis":        ("agents.schemas.thesis_screener_schema","ThesisScreenerResponse"),
        "bagger":        ("agents.schemas.bagger_schema",         "BaggerScreenerResponse"),
        "value":         ("agents.schemas.value_investing_schema", "ValueInvestingResponse"),
    }
    mod_path, class_name = schema_map[agent_name]
    mod = importlib.import_module(mod_path)
    return getattr(mod, class_name)


def _output_json_path(agent_name: str, hash12: str) -> Path:
    return Path("bundles") / f"{agent_name}_output_{hash12}.json"


def _get_rebuy_summary(result, run_id: str, run_ts: str) -> tuple[list, AgentRunSummary]:
    """Build a minimal summary row for the rebuy agent (legacy schema)."""
    if result is None:
        return [], AgentRunSummary(agent="rebuy", status="failed", error_msg="no result")
    candidates = getattr(result, "candidates", [])
    scale_in = [c for c in candidates if getattr(c, "proposed_next_step", "") == "scale_in"]
    top = f"Scale-in: {scale_in[0].ticker}" if scale_in else ("Hold" if candidates else "no candidates")
    return [], AgentRunSummary(
        agent="rebuy",
        status="success",
        findings_count=len(scale_in),
        top_action=top[:80],
        sheet_rows=0,   # rebuy uses legacy write — not in standard batch
        output_json_path=str(_output_json_path("rebuy", result.bundle_hash[:12])),
    )


def _run_one_agent(
    agent_name: str,
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    errors: list[str],
) -> tuple[list[list], AgentRunSummary]:
    """
    Call one agent's runner function directly.
    Returns (sheet_rows, summary).
    """
    console.print(Rule(f"[bold cyan] {agent_name.upper()} agent ", style="cyan"))

    try:
        mod = _load_agent_module(agent_name)
        
        # Determine the runner function name
        runner_name = f"run_{agent_name}_agent"
        if agent_name == "rebuy": runner_name = "run_rebuy_analyst"
        if agent_name == "valuation": runner_name = "run_valuation_agent"
        if agent_name == "bagger": runner_name = "run_bagger_agent"
        if agent_name == "macro": runner_name = "run_macro_agent"
        if agent_name == "thesis": runner_name = "run_thesis_agent"
        if agent_name == "tax": runner_name = "run_tax_agent"
        if agent_name == "concentration": runner_name = "run_concentration_agent"
        if agent_name == "behavioral": runner_name = "run_behavioral_agent"
        
        runner_fn = getattr(mod, runner_name)
        
        # Call runner (most standard agents use this signature)
        # Note: dry_run=False here because analyze_all handles the live write
        result, rows = runner_fn(bundle_path=bundle_path, run_id=run_id, run_ts=run_ts, dry_run=False)
        
    except Exception as e:
        err = f"{agent_name}: {type(e).__name__}: {str(e)[:800]}"
        errors.append(err)
        console.print(f"[red]! {agent_name} failed: {err}[/]")
        return [], AgentRunSummary(agent=agent_name, status="failed", error_msg=err)

    # Rebuy uses legacy schema — no standard rows
    if agent_name == "rebuy":
        _, summary = _get_rebuy_summary(result, run_id, run_ts)
        return [], summary

    # Count non-portfolio-summary rows
    non_summary_rows = [r for r in rows if len(r) > 5 and r[5] != "PORTFOLIO"]
    top_action = rows[0][6][:80] if rows else ""

    summary = AgentRunSummary(
        agent=agent_name,
        status="success",
        findings_count=len(non_summary_rows),
        top_action=top_action,
        sheet_rows=len(rows),
        output_json_path="", # In-memory now
    )
    return rows, summary


# ---------------------------------------------------------------------------
# Sheet write (single batch, archive-before-overwrite)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fresh bundle builder
# ---------------------------------------------------------------------------

def _build_fresh_bundles() -> Path:
    """Build market → vault → composite bundles and return composite path."""
    from core.bundle import build_bundle, write_bundle
    from core.vault_bundle import build_vault_bundle, write_vault_bundle
    from core.composite_bundle import build_composite_bundle, write_composite_bundle

    console.print("[cyan]--fresh-bundle: building market snapshot...[/]")
    market_bundle = build_bundle(source="auto", csv_path=None, cash_manual=0.0)
    market_path = write_bundle(market_bundle)
    console.print(f"[dim]Market bundle: {market_path.name}[/]")

    console.print("[cyan]--fresh-bundle: building vault snapshot...[/]")
    tickers = [p["ticker"] for p in market_bundle.positions
               if not p.get("is_cash")]
    vault_bundle = build_vault_bundle(ticker_list=tickers, include_drive=False)
    vault_path = write_vault_bundle(vault_bundle)
    console.print(f"[dim]Vault bundle: {vault_path.name}[/]")

    console.print("[cyan]--fresh-bundle: building composite bundle...[/]")
    composite = build_composite_bundle(market_path, vault_path)
    composite_path = write_composite_bundle(composite)
    console.print(f"[dim]Composite bundle: {composite_path.name}[/]")

    with console.status("[cyan]Enriching: ATR stops..."):
        try:
            from tasks.enrich_atr import enrich_composite_bundle as _enrich_atr
            _enrich_atr(composite_path)
            console.print("[dim]ATR stops injected.[/]")
        except Exception as e:
            console.print(f"[yellow]! ATR enrichment skipped: {e}[/]")

    with console.status("[cyan]Enriching: Murphy TA indicators..."):
        try:
            from tasks.enrich_technicals import enrich_composite_bundle as _enrich_technicals
            _enrich_technicals(composite_path)
            console.print("[dim]Murphy TA indicators injected.[/]")
        except Exception as e:
            console.print(f"[yellow]! Technical enrichment skipped: {e}[/]")

    return composite_path


# ---------------------------------------------------------------------------
# Main orchestration entry point
# ---------------------------------------------------------------------------

def run_analyze_all(
    agents_str: str,
    fresh_bundle: bool,
    live: bool,
) -> None:
    """
    Orchestrate all agents, collect outputs, single batch write, write manifest.
    Called from manager.py analyze-all command.
    """
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = str(uuid.uuid4())

    # Banner
    if live:
        console.print(Panel.fit(
            "[bold white on red] LIVE MODE — Single batch write to Agent_Outputs [/]",
            border_style="red",
        ))
    else:
        console.print(Panel.fit(
            "[bold black on yellow] DRY RUN — No Sheet writes. Use --live to enable. [/]",
            border_style="yellow",
        ))

    # Parse agents list
    requested_agents = [a.strip().lower() for a in agents_str.split(",") if a.strip()]
    unknown = [a for a in requested_agents if a not in _ALL_AGENTS]
    if unknown:
        console.print(f"[red]ERROR: Unknown agent(s): {unknown}. Valid: {_ALL_AGENTS}[/]")
        raise typer.Exit(1)

    console.print(f"[dim]Agents to run: {requested_agents}[/]")
    console.print(f"[dim]Run ID: {run_id}[/]")

    # Optionally build fresh bundles
    composite_path: Optional[Path] = None
    if fresh_bundle:
        try:
            composite_path = _build_fresh_bundles()
        except Exception as e:
            console.print(f"[red]ERROR: Fresh bundle build failed: {e}[/]")
            raise typer.Exit(1)

    # Resolve latest composite bundle
    if composite_path is None:
        candidates = sorted(
            Path("bundles").glob("composite_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            console.print(
                "[red]ERROR: No composite bundles found. "
                "Run: python manager.py bundle composite (or use --fresh-bundle)[/]"
            )
            raise typer.Exit(1)
        composite_path = candidates[-1]
        console.print(f"[dim]Using latest composite bundle: {composite_path.name}[/]")

    # Load composite to get hash
    from core.composite_bundle import load_composite_bundle
    composite_data = load_composite_bundle(composite_path)
    composite_hash = composite_data["composite_hash"]
    console.print(f"[dim]Composite hash: {composite_hash[:16]}...[/]")

    bundle_str = str(composite_path)

    # Run all requested agents
    errors: list[str] = []
    all_standard_rows: list[list] = []
    summaries: list[AgentRunSummary] = []
    succeeded: list[str] = []
    failed: list[str] = []
    skipped = [a for a in _ALL_AGENTS if a not in requested_agents]

    for agent_name in requested_agents:
        rows, summary = _run_one_agent(
            agent_name=agent_name,
            bundle_path=composite_path,
            run_id=run_id,
            run_ts=run_ts,
            errors=errors,
        )
        summaries.append(summary)
        if summary.status == "success":
            succeeded.append(agent_name)
            if agent_name in _STANDARD_AGENTS:
                all_standard_rows.extend(rows)
        else:
            failed.append(agent_name)

    for agent_name in skipped:
        summaries.append(AgentRunSummary(agent=agent_name, status="skipped"))

    console.print(Rule("[bold]analyze-all complete", style="green"))

    # Transform raw 11-col rows → compact 10-col readable format
    run_id_short = run_id[:8]
    run_date = _compact_run_ts(run_ts)
    compact_rows = _transform_to_compact(all_standard_rows, run_id_short, run_date)
    compact_rows = _collapse_hold_rows(compact_rows)
    compact_rows = _sort_by_severity(compact_rows)

    # Sheet write (live mode only)
    total_rows = len(compact_rows)
    if live and compact_rows:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        archive_and_overwrite_agent_outputs(ss, compact_rows, run_ts, _COMPACT_HEADERS)
    elif live and not compact_rows:
        console.print("[yellow]LIVE: no standard rows to write (all agents failed or produced no output).[/]")
    else:
        console.print(
            f"[dim]DRY RUN: {total_rows} compact row(s) from {len(all_standard_rows)} raw rows "
            f"across {len(succeeded)} agent(s) — not written. Use --live to write.[/]"
        )

    # Write manifest to bundles/runs/
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = run_ts[:10].replace("-", "")
    manifest_filename = f"manifest_{run_id[:8]}_{date_tag}.json"
    manifest_path = RUNS_DIR / manifest_filename

    manifest = AgentRunManifest(
        run_id=run_id,
        run_ts=run_ts,
        composite_hash=composite_hash,
        composite_hash_short=composite_hash[:16],
        composite_bundle_path=str(composite_path),
        agents_requested=requested_agents,
        agents_succeeded=succeeded,
        agents_failed=failed,
        agents_skipped=skipped,
        agent_summaries=summaries,
        total_sheet_rows=total_rows,
        errors=errors,
        dry_run=not live,
        fresh_bundle=fresh_bundle,
        manifest_path=str(manifest_path),
    )
    manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2))
    console.print(f"[dim]Manifest written: {manifest_path}[/]")

    # Rich summary table
    summary_table = Table(title="analyze-all Summary", show_header=True)
    summary_table.add_column("Agent", style="bold")
    summary_table.add_column("Status")
    summary_table.add_column("Findings")
    summary_table.add_column("Sheet Rows")
    summary_table.add_column("Top Action")

    for s in summaries:
        color = {"success": "green", "failed": "bold red", "skipped": "dim"}[s.status]
        findings = str(s.findings_count) if s.status == "success" else "—"
        rows_col = str(s.sheet_rows) if s.status == "success" else "—"
        top = (s.top_action or s.error_msg or "")[:60]
        summary_table.add_row(
            s.agent,
            f"[{color}]{s.status.upper()}[/]",
            findings,
            rows_col,
            top,
        )

    console.print(summary_table)
    console.print(
        f"\n[bold]Run ID:[/] {run_id[:8]}...  "
        f"[bold]Hash:[/] {composite_hash[:12]}...  "
        f"[bold]Agents:[/] {len(succeeded)}/{len(requested_agents)} succeeded  "
        f"[bold]Rows:[/] {total_rows}  "
        f"[bold]Mode:[/] {'LIVE' if live else 'DRY RUN'}"
    )

    if failed:
        console.print(f"\n[bold red]Failed agents:[/] {', '.join(failed)}")
        for err in errors:
            console.print(f"  [red]•[/] {err}")

    if fresh_bundle:
        console.print(
            "\n[yellow]Note: rebuy agent uses a legacy write schema and is included in the "
            "manifest but NOT in the standard Agent_Outputs batch write.[/]"
        )
