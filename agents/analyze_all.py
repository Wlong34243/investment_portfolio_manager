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
]

_ALL_AGENTS = ["rebuy"] + _STANDARD_AGENTS   # rebuy first (no external API calls)

_AGENT_OUTPUTS_HEADERS = [
    "run_id", "run_ts", "composite_hash", "agent",
    "signal_type", "ticker", "action", "rationale",
    "scale_step", "severity", "dry_run",
]

RUNS_DIR = Path("bundles") / "runs"


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
    bundle_str: str,
    composite_hash: str,
    run_id: str,
    run_ts: str,
    errors: list[str],
) -> tuple[list[list], AgentRunSummary]:
    """
    Call one agent's analyze() with live=False, read its JSON output,
    and return (sheet_rows, summary). On failure returns ([], failed_summary).
    """
    hash12 = composite_hash[:12]
    json_path = _output_json_path(agent_name, hash12)

    console.print(Rule(f"[bold cyan] {agent_name.upper()} agent ", style="cyan"))

    try:
        mod = _load_agent_module(agent_name)
        analyze_fn = getattr(mod, "analyze")
        
        # Typer workaround: if we call the function directly, we must provide 
        # values for all arguments that default to typer.Option/Argument, 
        # otherwise they will be passed as OptionInfo/ArgumentInfo objects.
        kwargs = {"bundle": bundle_str, "live": False}
        
        # Check if agent supports --ticker or --tickers subset
        import inspect
        sig = inspect.signature(analyze_fn)
        if "ticker" in sig.parameters:
            kwargs["ticker"] = None
        if "tickers" in sig.parameters:
            kwargs["tickers"] = None
            
        analyze_fn(**kwargs)
    except typer.Exit as e:
        code = getattr(e, "exit_code", 1)
        err = f"{agent_name}: exited with code {code}"
        errors.append(err)
        console.print(f"[red]! {agent_name} exited (code {code})[/]")
        return [], AgentRunSummary(agent=agent_name, status="failed", error_msg=err)
    except SystemExit as e:
        err = f"{agent_name}: SystemExit({e.code})"
        errors.append(err)
        console.print(f"[red]! {agent_name} SystemExit({e.code})[/]")
        return [], AgentRunSummary(agent=agent_name, status="failed", error_msg=err)
    except Exception as e:
        err = f"{agent_name}: {type(e).__name__}: {str(e)[:300]}"
        errors.append(err)
        console.print(f"[red]! {agent_name} failed: {err}[/]")
        return [], AgentRunSummary(agent=agent_name, status="failed", error_msg=err)

    # Read JSON output
    if not json_path.exists():
        err = f"{agent_name}: JSON output not found at {json_path}"
        errors.append(err)
        return [], AgentRunSummary(agent=agent_name, status="failed", error_msg=err)

    try:
        schema_cls = _load_schema_class(agent_name)
        result = schema_cls.model_validate(json.loads(json_path.read_text()))
    except Exception as e:
        err = f"{agent_name}: failed to parse JSON output: {e}"
        errors.append(err)
        return [], AgentRunSummary(agent=agent_name, status="failed", error_msg=err)

    # Rebuy uses legacy schema — no standard rows
    if agent_name == "rebuy":
        _, summary = _get_rebuy_summary(result, run_id, run_ts)
        return [], summary

    # Standard agents: call _result_to_sheet_rows
    try:
        row_fn = getattr(_load_agent_module(agent_name), "_result_to_sheet_rows")
        rows = row_fn(result, run_id, run_ts, dry_run=False)
    except Exception as e:
        err = f"{agent_name}: row generation failed: {e}"
        errors.append(err)
        return [], AgentRunSummary(agent=agent_name, status="failed",
                                   error_msg=err,
                                   output_json_path=str(json_path))

    # Count non-portfolio-summary rows
    non_summary_rows = [r for r in rows if len(r) > 5 and r[5] != "PORTFOLIO"]
    top_action = rows[0][6][:80] if rows else ""

    summary = AgentRunSummary(
        agent=agent_name,
        status="success",
        findings_count=len(non_summary_rows),
        top_action=top_action,
        sheet_rows=len(rows),
        output_json_path=str(json_path),
    )
    return rows, summary


# ---------------------------------------------------------------------------
# Sheet write (single batch, archive-before-overwrite)
# ---------------------------------------------------------------------------

def _batch_write(ss, all_rows: list[list], run_ts: str) -> None:
    existing_tabs = {ws.title for ws in ss.worksheets()}

    if config.TAB_AGENT_OUTPUTS not in existing_tabs:
        ws_out = ss.add_worksheet(
            title=config.TAB_AGENT_OUTPUTS, rows=5000, cols=len(_AGENT_OUTPUTS_HEADERS) + 1
        )
        time.sleep(1.0)
        existing_rows = []
    else:
        ws_out = ss.worksheet(config.TAB_AGENT_OUTPUTS)
        existing_rows = ws_out.get_all_values()

    # Archive existing rows
    if len(existing_rows) > 1:
        if config.TAB_AGENT_OUTPUTS_ARCHIVE not in existing_tabs:
            ws_arc = ss.add_worksheet(
                title=config.TAB_AGENT_OUTPUTS_ARCHIVE,
                rows=20000, cols=len(_AGENT_OUTPUTS_HEADERS) + 2,
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

    # Single batch overwrite
    ws_out.clear()
    time.sleep(0.5)
    ws_out.update(
        range_name="A1",
        values=[_AGENT_OUTPUTS_HEADERS] + all_rows,
        value_input_option="USER_ENTERED",
    )
    time.sleep(1.0)
    console.print(
        f"[green]LIVE — wrote {len(all_rows)} total row(s) to {config.TAB_AGENT_OUTPUTS} "
        f"(single batch, {len(all_rows)} rows across all agents).[/]"
    )


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
    tickers = [p["ticker"] for p in market_bundle.model_dump().get("positions", [])
               if not p.get("is_cash")]
    vault_bundle = build_vault_bundle(ticker_list=tickers, include_drive=False)
    vault_path = write_vault_bundle(vault_bundle)
    console.print(f"[dim]Vault bundle: {vault_path.name}[/]")

    console.print("[cyan]--fresh-bundle: building composite bundle...[/]")
    composite = build_composite_bundle(market_path, vault_path)
    composite_path = write_composite_bundle(composite)
    console.print(f"[dim]Composite bundle: {composite_path.name}[/]")

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
            bundle_str=bundle_str,
            composite_hash=composite_hash,
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

    # Sheet write (live mode only)
    total_rows = len(all_standard_rows)
    if live and all_standard_rows:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        _batch_write(ss, all_standard_rows, run_ts)
    elif live and not all_standard_rows:
        console.print("[yellow]LIVE: no standard rows to write (all agents failed or produced no output).[/]")
    else:
        console.print(
            f"[dim]DRY RUN: {total_rows} row(s) queued across {len(succeeded)} agent(s) "
            f"— not written. Use --live to write.[/]"
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
