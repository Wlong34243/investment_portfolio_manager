"""
Investment Portfolio Manager — CLI entry point.

Headless, auditable, linear execution. Every run freezes its inputs to
an immutable bundle and exits. No reruns, no state leakage, no hidden
caches.

Usage:
    python manager.py snapshot --csv path/to/positions.csv --cash 10000
    python manager.py snapshot --csv path/to/positions.csv --cash 10000 --live
    python manager.py vault snapshot
    python manager.py bundle composite
"""

import atexit
import json
import subprocess
import time
import sys
import os
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List

# Ensure project root is in sys.path to avoid shadowing by other projects' 'config.py'
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Under pythonw.exe (no console attached — used by the PortfolioUI logon
# task specifically to avoid a console window), sys.stdout/sys.stderr are
# None, not just discarded. The first print()/logging call/rich Console
# write anywhere downstream throws AttributeError and kills the process
# with no trace anywhere (CLAUDE.md Known Issues, 2026-08-28). Redirect to
# a log file before anything else runs so a pythonw-launched process can
# both run unattended and leave evidence if it crashes.
if sys.stdout is None or sys.stderr is None:
    _log_dir = _ROOT / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _pyw_log = open(
        _log_dir / "pythonw_stdio.log", "a", buffering=1,
        encoding="utf-8", errors="replace",
    )
    sys.stdout = _pyw_log
    sys.stderr = _pyw_log

# Windows consoles default to cp1252; unencodable chars (arrows, emoji) must
# degrade to '?' rather than crash the command mid-output.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

import pandas as pd
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from core.bundle import build_bundle, write_bundle, load_bundle
from core.vault_bundle import (
    build_vault_bundle, write_vault_bundle, load_vault_bundle,
    THESES_DIR,
)
from core.composite_bundle import (
    build_composite_bundle, write_composite_bundle,
    load_composite_bundle, resolve_latest_bundles,
)

app = typer.Typer(help="Investment Portfolio Manager CLI", no_args_is_help=True)
console = Console()

# --- REFRESH GROUP (New) ---
refresh_app = typer.Typer(help="Unified command for rebuilding computed Sheet views.")
app.add_typer(refresh_app, name="refresh")

# --- CLEAN GROUP (New) ---
clean_app = typer.Typer(help="Unified command for filesystem hygiene.")
app.add_typer(clean_app, name="clean")

# --- INGEST GROUP (New) ---
ingest_app = typer.Typer(help="Unified data ingestion (transactions, realized-gl, podcasts).")
app.add_typer(ingest_app, name="ingest")

# --- CORE/LEGACY GROUPS (Many now aliased/hidden) ---
journal_app = typer.Typer(help="Journaling commands — record manual decisions.")
app.add_typer(journal_app, name="journal")

trade_app = typer.Typer(help="Trade log review and decision tuning. (Deprecated: use 'refresh rotations')")
app.add_typer(trade_app, name="trade", hidden=True)

vault_app = typer.Typer(help="Manage the vault bundle (thesis files, transcripts).")
app.add_typer(vault_app, name="vault")

bundle_app = typer.Typer(help="Build and inspect composite bundles.")
app.add_typer(bundle_app, name="bundle")

sync_app = typer.Typer(help="Sync data from external sources. (Deprecated: use 'ingest')")
app.add_typer(sync_app, name="sync", hidden=True)

tax_app = typer.Typer(help="Tax visibility: Tax_Control refresh + pre-trade surface (Prompt 9).")
app.add_typer(tax_app, name="tax")

dashboard_app = typer.Typer(help="Dashboard maintenance commands. (Deprecated: use 'refresh dashboard')")
app.add_typer(dashboard_app, name="dashboard", hidden=True)

export_app = typer.Typer(help="Export context packages for frontier LLM analysis.")
app.add_typer(export_app, name="export")

podcast_app = typer.Typer(help="Podcast transcript collection and optional AI analysis.")
app.add_typer(podcast_app, name="podcast")

publish_app = typer.Typer(help="Publish small, stable output to a Drive-synced folder for reading on other devices.")
app.add_typer(publish_app, name="publish")

# --- AGENT GROUP ---
agent_app = typer.Typer(help="AI agents that consume the composite bundle and produce local output.")
app.add_typer(agent_app, name="agent")

# --- STORE / UI (SQLite ledger + local Command Center) ---
store_app = typer.Typer(help="PortfolioStore: SQLite shadow ledger status, verify, sync.")
app.add_typer(store_app, name="store")

corpus_app = typer.Typer(help="Corpus FTS5 index — searchable vault/transcripts/digests with citation.")
app.add_typer(corpus_app, name="corpus")

ui_app = typer.Typer(help="Local read-mostly Command Center UI.")
app.add_typer(ui_app, name="ui")

probe_app = typer.Typer(
    help="Read-only Schwab market-data probes (Phase 1). Writes only under agent_outputs/schwab_probe/.",
    hidden=True,
)
app.add_typer(probe_app, name="probe")

build_app = typer.Typer(help="Build computed Sheet views (income, cash-flows, risk-metrics).")
app.add_typer(build_app, name="build")


@build_app.command("income-tracking")
def build_income_tracking_cmd(
    live: bool = typer.Option(False, "--live"),
    days: int = typer.Option(400, "--days"),
):
    from tasks.build_income_tracking import main as m
    m(live=live, days=days)


@build_app.command("cash-flows")
def build_cash_flows_cmd(
    live: bool = typer.Option(False, "--live"),
    days: int = typer.Option(90, "--days"),
):
    from tasks.build_flow_ledger import main as m
    m(live=live, days=days)


@build_app.command("risk-metrics")
def build_risk_metrics_cmd(
    live: bool = typer.Option(False, "--live"),
    lookback_days: int = typer.Option(400, "--lookback-days"),
):
    from tasks.build_risk_metrics import main as m
    m(live=live, lookback_days=lookback_days)

# --- TOP LEVEL COMMANDS ---

@refresh_app.command("rotations")
@trade_app.command("review")
def trade_review(
    live: bool = typer.Option(False, "--live", help="Refresh attribution and write to Sheets. Default: DRY RUN.")
):
    """Refresh Rotation_Review with fresh attribution for all Trade_Log rows."""
    from tasks.compute_rotation_attribution import run_attribution
    run_attribution(live=live)

@journal_app.command("promote")
def journal_promote(
    live: bool = typer.Option(False, "--live", help="Write to live Sheets. Default: DRY RUN."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Promote approved staging rows from Trade_Log_Staging to Trade_Log.

    Input Status values accepted: ``approve`` (imperative) or ``approved`` (record).
    On success, Status is set to ``promoted`` and ``Promoted_At`` is stamped UTC.
    A row with Status=promoted and blank Promoted_At is treated as hand-typed —
    this command warns naming those rows but does not auto-correct them.
    """
    import uuid
    from datetime import datetime, timezone

    import config
    from utils.sheet_readers import get_gspread_client

    # Accept both the imperative input and the past-tense record form.
    APPROVE_INPUTS = {"approve", "approved"}

    # Column aliases: config names -> possible live sheet headers
    HEADER_ALIASES = {
        "Stage_ID": ["Stage_ID"],
        "Date": ["Date"],
        "Sell_Tickers": ["Sell_Tickers", "Sell_Ticker"],
        "Sell_Proceeds": ["Sell_Proceeds"],
        "Buy_Tickers": ["Buy_Tickers", "Buy_Ticker"],
        "Buy_Amount": ["Buy_Amount"],
        "Rotation_Type": ["Rotation_Type"],
        "Implicit_Bet": ["Implicit_Bet"],
        "Thesis_Brief": ["Thesis_Brief"],
        "Status": ["Status"],
        "Promoted_At": ["Promoted_At"],
        "Fingerprint": ["Fingerprint"],
        "Sell_RSI_At_Decision": ["Sell_RSI_At_Decision", "Sell RSI"],
        "Sell_Trend_At_Decision": ["Sell_Trend_At_Decision", "Sell Trend"],
        "Sell_Price_vs_MA200_At_Decision": ["Sell_Price_vs_MA200_At_Decision", "Sell vs MA200"],
        "Buy_RSI_At_Decision": ["Buy_RSI_At_Decision", "Buy RSI"],
        "Buy_Trend_At_Decision": ["Buy_Trend_At_Decision", "Buy Trend"],
        "Buy_Price_vs_MA200_At_Decision": ["Buy_Price_vs_MA200_At_Decision", "Buy vs MA200"],
    }

    with console.status("[cyan]Reading Trade_Log_Staging..."):
        try:
            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            try:
                staging_ws = ss.worksheet(config.TAB_TRADE_LOG_STAGING)
            except Exception:
                console.print(f"[red]ERROR: Tab '{config.TAB_TRADE_LOG_STAGING}' not found. Run derive_rotations first.[/]")
                raise typer.Exit(code=1)

            all_rows = staging_ws.get_all_values()
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]ERROR reading staging: {e}[/]")
            raise typer.Exit(code=1)

    if len(all_rows) < 2:
        console.print("[yellow]Trade_Log_Staging is empty — nothing to promote.[/]")
        raise typer.Exit()

    header = list(all_rows[0])
    data_rows = all_rows[1:]  # 1-indexed row 2 onward in the sheet

    # Promoted_At may be missing on older staging tabs. Never mutate the sheet
    # until --live: dry-run only reports what would happen.
    missing_promoted_at = "Promoted_At" not in header
    if missing_promoted_at:
        console.print(
            "[yellow]! Promoted_At column missing from Trade_Log_Staging header. "
            "Will add it under --live; dry-run performs zero Sheet mutations.[/]"
        )

    def _hdr_idx(name: str) -> int:
        for alias in HEADER_ALIASES.get(name, [name]):
            if alias in header:
                return header.index(alias)
        # Fall back to config column order if sheet matches config layout
        try:
            return config.TRADE_LOG_STAGING_COLUMNS.index(name)
        except ValueError:
            return -1

    def _col(row: list, name: str) -> str:
        idx = _hdr_idx(name)
        if idx < 0:
            return ""
        padded = row + [""] * (len(header) - len(row))
        return padded[idx] if idx < len(padded) else ""

    try:
        status_col_idx = header.index("Status")
    except ValueError:
        console.print("[red]ERROR: 'Status' column not found in Trade_Log_Staging header.[/]")
        raise typer.Exit(code=1)

    promoted_at_idx = header.index("Promoted_At") if "Promoted_At" in header else -1

    # Startup check: hand-typed terminal state (promoted with blank Promoted_At)
    hand_typed = []
    for i, row in enumerate(data_rows):
        padded = row + [""] * (len(header) - len(row))
        st = padded[status_col_idx].strip().lower()
        pa = padded[promoted_at_idx].strip() if promoted_at_idx >= 0 and promoted_at_idx < len(padded) else ""
        if st == "promoted" and not pa:
            sid = _col(padded, "Stage_ID") or f"row {i + 2}"
            hand_typed.append(sid)
    if hand_typed:
        console.print(
            f"[yellow]! {len(hand_typed)} row(s) have Status=promoted with blank Promoted_At "
            "(hand-typed / pre-hardening). Not auto-corrected.[/]"
        )
        for sid in hand_typed[:12]:
            console.print(f"[yellow]    - {sid}[/]")
        if len(hand_typed) > 12:
            console.print(f"[yellow]    ... and {len(hand_typed) - 12} more[/]")

    # Build list of (sheet_row_number, data_row) for approve/approved rows
    approved: list[tuple[int, list]] = []
    for i, row in enumerate(data_rows):
        padded = row + [""] * (len(header) - len(row))
        if padded[status_col_idx].strip().lower() in APPROVE_INPUTS:
            approved.append((i + 2, padded))

    if not approved:
        console.print("[yellow]No rows with Status='approve'/'approved' found in Trade_Log_Staging.[/]")
        raise typer.Exit()

    # Preview table
    preview = Table(title=f"Rows to Promote ({len(approved)})", show_header=True)
    preview.add_column("Stage_ID[:8]", style="dim")
    preview.add_column("Date", style="cyan")
    preview.add_column("Sell_Tickers")
    preview.add_column("Buy_Tickers")
    preview.add_column("Rotation_Type", style="yellow")
    preview.add_column("Implicit_Bet")
    for _, row in approved:
        preview.add_row(
            _col(row, "Stage_ID")[:8],
            _col(row, "Date"),
            _col(row, "Sell_Tickers"),
            _col(row, "Buy_Tickers"),
            _col(row, "Rotation_Type"),
            _col(row, "Implicit_Bet") or "[dim]<blank>[/]",
        )
    console.print(preview)

    # Warn on blank Implicit_Bet
    blank_bets = [row for _, row in approved if not _col(row, "Implicit_Bet").strip()]
    if blank_bets:
        console.print(f"[yellow]! {len(blank_bets)} row(s) have a blank Implicit_Bet — fill them in the Sheet before promoting.[/]")
        if not yes and not live:
            console.print("[dim]Continuing in dry-run mode regardless.[/]")

    if not live:
        console.print(Panel.fit(
            f"[bold black on yellow] DRY RUN — Would promote {len(approved)} row(s). Use --live to write. [/]",
            border_style="yellow",
        ))
        if missing_promoted_at:
            console.print("[dim]Would also add Promoted_At column to staging header.[/]")
        return

    # --live only below this line: schema ensure, Trade_Log append, staging marks.

    # Ensure Promoted_At column exists on the live sheet (append if missing)
    if missing_promoted_at:
        console.print("[cyan]Adding Promoted_At column to Trade_Log_Staging header...[/]")
        new_col = len(header) + 1
        staging_ws.update_cell(1, new_col, "Promoted_At")
        time.sleep(0.5)
        all_rows = staging_ws.get_all_values()
        header = list(all_rows[0])
        data_rows = all_rows[1:]
        if "Promoted_At" not in header:
            console.print("[red]ERROR: failed to add Promoted_At column.[/]")
            raise typer.Exit(code=1)
        # Rebuild approved rows against refreshed header (same sheet row numbers)
        approved = []
        try:
            status_col_idx = header.index("Status")
        except ValueError:
            console.print("[red]ERROR: 'Status' column not found after header update.[/]")
            raise typer.Exit(code=1)
        for i, row in enumerate(data_rows):
            padded = row + [""] * (len(header) - len(row))
            if padded[status_col_idx].strip().lower() in APPROVE_INPUTS:
                approved.append((i + 2, padded))

    # Confirm (skip with --yes)
    if not yes:
        console.print(f"\n[bold]About to promote {len(approved)} row(s) to Trade_Log and mark them 'promoted' in staging.[/]")
        confirm = typer.confirm("Proceed?")
        if not confirm:
            console.print("[yellow]Aborted.[/]")
            raise typer.Exit()

    # Build Trade_Log rows
    trade_log_rows = []
    for _, row in approved:
        trade_log_rows.append([
            _col(row, "Date"),
            _col(row, "Sell_Tickers"),
            _col(row, "Sell_Proceeds"),
            _col(row, "Buy_Tickers"),
            _col(row, "Buy_Amount"),
            _col(row, "Implicit_Bet"),
            _col(row, "Thesis_Brief"),
            _col(row, "Rotation_Type"),
            _col(row, "Sell_RSI_At_Decision"),
            _col(row, "Sell_Trend_At_Decision"),
            _col(row, "Sell_Price_vs_MA200_At_Decision"),
            _col(row, "Buy_RSI_At_Decision"),
            _col(row, "Buy_Trend_At_Decision"),
            _col(row, "Buy_Price_vs_MA200_At_Decision"),
            _col(row, "Stage_ID"),
            _col(row, "Fingerprint"),
        ])

    with console.status(f"[cyan]Writing {len(trade_log_rows)} row(s) to {config.TAB_TRADE_LOG}..."):
        try:
            try:
                trade_ws = ss.worksheet(config.TAB_TRADE_LOG)
            except Exception:
                console.print(f"[yellow]Creating {config.TAB_TRADE_LOG} tab...[/]")
                trade_ws = ss.add_worksheet(
                    title=config.TAB_TRADE_LOG,
                    rows="200",
                    cols=len(config.TRADE_LOG_COLUMNS),
                )
                trade_ws.insert_row(config.TRADE_LOG_COLUMNS, 1)
                trade_ws.freeze(rows=1)
                time.sleep(1)

            trade_ws.append_rows(trade_log_rows, value_input_option="USER_ENTERED")
        except Exception as e:
            console.print(f"[red]ERROR writing to {config.TAB_TRADE_LOG}: {e}[/]")
            raise typer.Exit(code=1)

    # Post-write verification: re-read Trade_Log and confirm every fingerprint
    with console.status("[cyan]Verifying write..."):
        try:
            written_fingerprints = set(trade_ws.col_values(
                config.TRADE_LOG_COLUMNS.index("Fingerprint") + 1
            ))
        except Exception as e:
            console.print(f"[red]ERROR: could not verify write to {config.TAB_TRADE_LOG}: {e}[/]")
            console.print("[yellow]Staging rows NOT marked promoted -- re-run after confirming Trade_Log manually.[/]")
            raise typer.Exit(code=1)

    missing = [r for r in trade_log_rows if r[-1] and r[-1] not in written_fingerprints]
    if missing:
        console.print(
            f"[red]ERROR: {len(missing)} row(s) missing from {config.TAB_TRADE_LOG} "
            "after write -- append reported success but verification read disagrees.[/]"
        )
        console.print("[yellow]Staging rows NOT marked promoted. Investigate before retrying.[/]")
        raise typer.Exit(code=1)

    console.print(f"[green]Fingerprint verification OK — {len(trade_log_rows)} fingerprint(s) present in Trade_Log.[/]")

    # Mark promoted + stamp Promoted_At (UTC) — single batched update (no cell-by-cell).
    from gspread.utils import rowcol_to_a1

    promoted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_status_col = status_col_idx + 1
    new_pa_col = (header.index("Promoted_At") + 1) if "Promoted_At" in header else None
    batch = []
    for sheet_row_num, _ in approved:
        batch.append({
            "range": rowcol_to_a1(sheet_row_num, new_status_col),
            "values": [["promoted"]],
        })
        if new_pa_col:
            batch.append({
                "range": rowcol_to_a1(sheet_row_num, new_pa_col),
                "values": [[promoted_at]],
            })
    with console.status("[cyan]Marking staging rows as 'promoted' + Promoted_At (batch)..."):
        try:
            chunk = 50
            for start in range(0, len(batch), chunk):
                staging_ws.batch_update(batch[start : start + chunk], value_input_option="USER_ENTERED")
                if start + chunk < len(batch):
                    time.sleep(1.0)
        except Exception as e:
            console.print(f"[yellow]! WARNING: Could not update staging status: {e}[/]")
            console.print("[yellow]  Trade_Log rows were written — update staging manually.[/]")

    console.print(f"\n[bold green]SUCCESS:[/] Promoted {len(trade_log_rows)} row(s) to {config.TAB_TRADE_LOG}.")
    console.print(f"[dim]Staging Status=promoted; Promoted_At={promoted_at}.[/]")


@journal_app.command("reconcile")
def journal_reconcile(
    live: bool = typer.Option(False, "--live", help="Write rationale_proposals. Default: DRY RUN."),
    backlog_only: bool = typer.Option(
        False,
        "--backlog-only",
        help="Batch-close promoted-blank pre-accrual + superseded; leave pending untouched.",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="Reserved — hand Implicit_Bet on Trade_Log for top-$ survivors, not machine proposals.",
    ),
):
    """
    Rationale loop batch triage (amended 2026-08-27).

    Discriminator is staging Status + fill date, not match_strength:
      pending → skip (queue, not backlog)
      promoted + blank + fill < 2026-08-27 → predates_evidence_capture
      superseded → superseded_cluster
    Weak corpus hits on pre-accrual fills are ambient noise — not batched as proposals.
    """
    from rich.table import Table

    from core.journal.batch import plan_batch, apply_batch_reasons, top_by_dollars
    from core.journal.persist import batch_reject_none
    from core.journal.reconcile import load_unreconciled_clusters
    from core.journal.propose import EVIDENCE_ACCRUAL_START

    console.print("[bold]Loading unreconciled clusters (Sheets staging + Trade_Log)…[/]")
    # Clear robust-reader cache so Stage_ID UUID fix is visible this process
    from utils.sheet_readers import get_trade_log_staging, get_trade_log

    get_trade_log_staging.cache_clear()
    get_trade_log.cache_clear()

    clusters = load_unreconciled_clusters()
    console.print(f"Clusters after superset collapse: {len(clusters)}")
    plan = plan_batch(clusters)
    console.print(
        f"plan: predates(promoted+pre-{EVIDENCE_ACCRUAL_START})={len(plan.predates)} | "
        f"superseded={len(plan.superseded)} | pending_skipped={len(plan.pending_skipped)} | "
        f"post_accrual_promoted={len(plan.post_accrual_promoted)} | other={len(plan.other)}"
    )

    batch_props = apply_batch_reasons(clusters)
    table = Table(title="Batch close candidates (sign-off — review before --live)")
    table.add_column("reason")
    table.add_column("id")
    table.add_column("date")
    table.add_column("status")
    table.add_column("sells")
    table.add_column("buys")
    table.add_column("$")
    from core.journal.batch import dollars

    for p in batch_props:
        # find cluster for dollars
        c = next((x for x in clusters if x.cluster_id == p.cluster_id), None)
        d = dollars(c) if c else 0.0
        table.add_row(
            p.batch_reason,
            p.cluster_id[:14],
            p.fill_date.isoformat(),
            (p.status or "")[:10],
            ",".join(p.sell_tickers[:4]),
            ",".join(p.buy_tickers[:4]),
            f"{d:,.0f}",
        )
    console.print(table)

    console.print("\n[bold]Top 15 promoted-blank by $ — hand-author Implicit_Bet (reconstructed_after)[/]")
    promoted_like = [
        c
        for c in clusters
        if (c.status or "").lower() == "promoted" or c.source == "trade_log"
    ]
    top = top_by_dollars(promoted_like, n=15, status=None)
    t2 = Table()
    t2.add_column("#")
    t2.add_column("date")
    t2.add_column("$")
    t2.add_column("sells")
    t2.add_column("buys")
    t2.add_column("id")
    t2.add_column("src")
    for i, (c, d) in enumerate(top, 1):
        t2.add_row(
            str(i),
            c.fill_date.isoformat(),
            f"{d:,.0f}",
            ",".join(c.sell_tickers[:5]),
            ",".join(c.buy_tickers[:5]),
            c.cluster_id[:14],
            c.source,
        )
    console.print(t2)

    if not live:
        console.print(
            "\n[bold black on yellow] DRY RUN — wrote nothing. "
            "After sign-off: --live --backlog-only closes predates + superseded only. [/]"
        )
        console.print(
            "[dim]Write path: SQLite rationale_proposals only — "
            "does not open Trade_Log_Staging or Trade_Log.[/]"
        )
        return

    if not backlog_only:
        console.print("[yellow]--live without --backlog-only: refusing broad write. Use --backlog-only.[/]")
        return

    console.print(
        "[bold]LIVE write target: SQLite table rationale_proposals only. "
        "No Sheets writes. Staging writer remains unsafe (header mismatch) — not invoked.[/]"
    )
    n = batch_reject_none(batch_props, live=True)
    console.print(f"[green]Batch-closed {n} proposals (see rationale_proposals.batch_reason).[/]")
    if interactive:
        console.print(
            "[dim]Interactive machine proposals deferred — author Implicit_Bet on Trade_Log "
            "for the 2026 top-$ list when ready (no clock).[/]"
        )


@journal_app.command("precommit")
def journal_precommit(
    ticker: Optional[str] = typer.Option(None, "--ticker", help="Ticker for declare / filter list."),
    type: Optional[str] = typer.Option(None, "--type", help="Trigger type (fwd_pe, price, …)."),
    side: Optional[str] = typer.Option(None, "--side", help="trim | add"),
    level: Optional[float] = typer.Option(None, "--level", help="Declared band level."),
    action: Optional[str] = typer.Option(None, "--action", help="Intended action text."),
    note: str = typer.Option("", "--note", help="Reasoning at declaration time."),
    list_flag: bool = typer.Option(False, "--list", help="List precommitments."),
    open_only: bool = typer.Option(False, "--open-only", help="With --list: open/fired only."),
    close_id: Optional[int] = typer.Option(None, "--close", help="Close precommitment by id."),
    reason: Optional[str] = typer.Option(None, "--reason", help="Close reason."),
    pending: bool = typer.Option(False, "--pending", help="List pending firings; optional respond."),
    detect: bool = typer.Option(False, "--detect", help="Run firing detector against signal_events."),
    respond: Optional[str] = typer.Option(
        None, "--respond", help="With --firing: a|p|d (acted|passed|defer)."
    ),
    firing: Optional[int] = typer.Option(None, "--firing", help="Firing id for --respond."),
    force: bool = typer.Option(False, "--force", help="Allow declare when level ≠ thesis band."),
    live: bool = typer.Option(False, "--live", help="Write SQLite. Default: DRY RUN."),
):
    """
    Pre-commitment capture (Instrument prompt 8).

    Declare a dated intention against a thesis band; morning detects crossings;
    you respond acted/passed. Only path that produces Rationale_Provenance=declared_before.
    """
    from rich.table import Table

    from core.journal import precommit as pc

    if list_flag:
        rows = pc.list_precommitments(ticker=ticker, open_only=open_only)
        t = Table(title="precommitments")
        for col in ("id", "ticker", "type", "side", "level", "status", "action", "thesis_at"):
            t.add_column(col)
        for r in rows:
            t.add_row(
                str(r.id),
                r.ticker,
                r.trigger_type,
                r.band_side,
                str(r.band_level),
                r.status,
                (r.intended_action or "")[:40],
                str(r.thesis_band_at_declaration),
            )
        console.print(t)
        return

    if close_id is not None:
        res = pc.close_precommitment(close_id, reason=reason or "", live=live)
        console.print(("[green]" if res.ok else "[red]") + res.message + "[/]")
        if not res.ok:
            raise typer.Exit(code=1)
        if not live:
            console.print("[bold black on yellow] DRY RUN — wrote nothing [/]")
        return

    if detect:
        summary = pc.detect_firings(live=live)
        mode = "LIVE" if live else "DRY RUN"
        console.print(f"[bold]{mode}[/] detect_firings: {summary}")
        console.print(f"pending firings: {pc.pending_count()}")
        return

    if pending or (respond and firing is not None):
        if respond and firing is not None:
            res = pc.respond_firing(firing, response=respond, note=note, live=live)
            console.print(("[green]" if res.ok else "[red]") + res.message + "[/]")
            if not res.ok:
                raise typer.Exit(code=1)
            if not live:
                console.print("[bold black on yellow] DRY RUN — wrote nothing [/]")
            return
        rows = pc.list_pending_firings()
        if not rows:
            console.print("[dim]No pending precommitment firings.[/]")
            return
        for r in rows:
            decl = r["declared_at"]
            decl_s = decl.date().isoformat() if hasattr(decl, "date") else str(decl)[:10]
            doctr = "DOWNGRADED (HOLD_TAX)" if r["doctrine_downgraded"] else "not downgraded"
            console.print(
                f"[bold]{r['ticker']}[/]  {r['trigger_type']} {r['band_side']} @ {r['band_level']}   "
                f"declared {decl_s} ({r['intended_action']!r})"
            )
            console.print(
                f"  FIRED {r['event_date']} — reading {r['metric_value']}  "
                f"[table:signal_events#{r['signal_event_id']}]  firing_id={r['firing_id']}"
            )
            console.print(f"  Doctrine: {doctr}.")
            console.print("  Response?  [a]cted  [p]assed  [d]efer     (use --respond / --firing --live)")
        console.print(f"\n[bold]{len(rows)}[/] pending. Pass recorded with `--respond p --firing N --live`.")
        return

    # Declare
    if not ticker or not type or not side or level is None or not action:
        console.print(
            "[red]Declare requires --ticker --type --side --level --action "
            "(or use --list / --pending / --close / --detect).[/]"
        )
        raise typer.Exit(code=1)
    res = pc.declare(
        ticker=ticker,
        trigger_type=type,
        side=side,
        level=level,
        action=action,
        note=note,
        force=force,
        live=live,
    )
    style = "green" if res.ok else "red"
    console.print(f"[{style}]{res.message}[/]")
    if res.requires_force and not force:
        raise typer.Exit(code=1)
    if not res.ok:
        raise typer.Exit(code=1)
    if not live:
        console.print("[bold black on yellow] DRY RUN — wrote nothing. Re-run with --live. [/]")


@journal_app.command("ingest-precommitments")
def journal_ingest_precommitments(
    live: bool = typer.Option(False, "--live", help="Write SQLite + mark Precommitments tab."),
):
    """Ingest Precommitments tab → SQLite (append-and-mark only; Bill writes the tab)."""
    from tasks.ingest_precommitments import ingest_precommitments_from_sheet

    ing = ingest_precommitments_from_sheet(live=live)
    mode = "LIVE" if live else "DRY RUN"
    console.print(
        f"[bold]{mode}[/] precommit ingest: ingested={ing.get('ingested')} "
        f"skipped={ing.get('skipped')}"
    )
    for flag in ing.get("flags") or []:
        console.print(f"[yellow]Band flag: {flag}[/]")
    for err in ing.get("errors") or []:
        console.print(f"[yellow]{err}[/]")
    if not live:
        console.print("[bold black on yellow] DRY RUN — wrote nothing. Re-run with --live. [/]")


@journal_app.command("rotation")
def journal_rotation(
    sold: str = typer.Option(..., "--sold", help="Comma-separated list of sell tickers."),
    bought: str = typer.Option(..., "--bought", help="Comma-separated list of buy tickers (or 'CASH')."),
    proceeds: float = typer.Option(..., "--proceeds", help="Total sell proceeds (USD)."),
    type: str = typer.Option(..., "--type", help="Rotation type: dry_powder | upgrade | rebalance | tax_loss."),
    bet: str = typer.Option(..., "--bet", help="Implicit bet / rationale for this rotation."),
    thesis: str = typer.Option("", "--thesis", help="Brief thesis note."),
    live: bool = typer.Option(False, "--live", help="Write to live Sheet. Default: DRY RUN."),
):
    """Record a portfolio rotation in the Trade_Log."""
    import uuid
    import config
    from utils.sheet_readers import get_gspread_client

    sell_tickers = [t.strip().upper() for t in sold.split(",")]
    
    if type not in ["dry_powder", "upgrade", "rebalance", "tax_loss"]:
        console.print(f"[red]ERROR: Invalid type: {type}. Must be dry_powder | upgrade | rebalance | tax_loss[/]")
        raise typer.Exit(code=1)

    trade_id = str(uuid.uuid4())
    today = datetime.now().strftime("%Y-%m-%d")
    proceeds_per_ticker = proceeds / len(sell_tickers)
    
    rows = []
    for ticker in sell_tickers:
        fingerprint = f"{today}|{ticker}|{bought}|{proceeds_per_ticker:.2f}"
        rows.append([
            today,
            ticker,
            round(proceeds_per_ticker, 2),
            bought.upper(),
            0.0,
            bet,
            thesis,
            type,
            trade_id,
            fingerprint
        ])

    if not live:
        console.print(Panel.fit(
            f"[bold black on yellow] DRY RUN — Would write {len(rows)} row(s) to {config.TAB_TRADE_LOG} [/]",
            border_style="yellow",
        ))
        for row in rows:
            console.print(f"Row: {row}")
        return

    with console.status(f"[cyan]Writing to {config.TAB_TRADE_LOG}..."):
        try:
            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            try:
                ws = ss.worksheet(config.TAB_TRADE_LOG)
            except:
                console.print(f"[yellow]Creating {config.TAB_TRADE_LOG} tab...[/]")
                ws = ss.add_worksheet(title=config.TAB_TRADE_LOG, rows="100", cols=len(config.TRADE_LOG_COLUMNS))
                ws.insert_row(config.TRADE_LOG_COLUMNS, 1)
                ws.freeze(rows=1)
                time.sleep(1)

            ws.append_rows(rows, value_input_option="USER_ENTERED")
            console.print(f"[bold green]SUCCESS:[/] Wrote {len(rows)} row(s) to {config.TAB_TRADE_LOG} (ID: {trade_id[:8]})")
        except Exception as e:
            console.print(f"[red]ERROR: Failed to write to Sheet: {e}[/]")
            raise typer.Exit(code=1)

_PIPELINE_LOCK_PATH = Path("logs") / "pipeline.lock"
_STALE_LOCK_HOURS = 3  # a hung run this old is treated as dead, not blocking


def _acquire_pipeline_lock():
    """Refuse to start a second `morning` run while one is already in
    progress. Gemini's 2026-07-29 review of the health-sentinel design
    flagged that a scheduled run and a manual run overlapping could race on
    logs/HEALTH_FAILURE.flag (one run's success deleting a flag the other
    just raised, or vice versa) -- serializing the whole pipeline here is
    the simpler fix, versus trying to make the sentinel itself concurrency-safe.
    Released automatically at process exit via atexit, so it doesn't require
    wrapping this large function in try/finally."""
    _PIPELINE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _PIPELINE_LOCK_PATH.exists():
        age_hours = (time.time() - _PIPELINE_LOCK_PATH.stat().st_mtime) / 3600
        if age_hours < _STALE_LOCK_HOURS:
            try:
                holder = _PIPELINE_LOCK_PATH.read_text(encoding="utf-8").strip()
            except OSError:
                holder = "unknown"
            console.print(
                f"[red]Another `morning` run appears to be in progress ({holder}, "
                f"{age_hours * 60:.0f}m old). Refusing to start a second one -- if that "
                f"run is dead, delete {_PIPELINE_LOCK_PATH} and retry.[/]"
            )
            raise typer.Exit(code=3)
        console.print(
            f"[yellow]Stale {_PIPELINE_LOCK_PATH} ({age_hours:.1f}h old) -- treating the "
            "prior run as dead and taking over.[/]"
        )

    _PIPELINE_LOCK_PATH.write_text(
        f"pid={os.getpid()} started={datetime.now().isoformat()}", encoding="utf-8"
    )

    def _release():
        try:
            if _PIPELINE_LOCK_PATH.exists():
                _PIPELINE_LOCK_PATH.unlink()
        except OSError:
            pass

    atexit.register(_release)


def run_health_report(verbose: bool = False):
    """Execution logic for health checks, returns exit code."""
    from tasks.health import run_all_checks, exit_code, CRITICAL, WARNING, PASS, WARN, FAIL
    from rich.text import Text

    console.print()
    with console.status("[cyan]Running health checks in parallel…"):
        results = run_all_checks()

    table = Table(
        title="Pipeline Health",
        show_header=True,
        header_style="bold cyan",
        box=None,
        padding=(0, 1),
    )
    table.add_column("Check",  style="cyan",  no_wrap=True, min_width=30)
    table.add_column("Status", justify="center", no_wrap=True, min_width=6)
    table.add_column("Detail", style="white")

    for r in results:
        if r.status == PASS:
            status_cell = Text("PASS", style="bold green")
        elif r.status == WARN:
            status_cell = Text("WARN", style="bold yellow")
        else:
            status_cell = Text("FAIL", style="bold red")

        level_marker = "" if r.level == CRITICAL else "[dim](W)[/dim] "
        name_cell = f"{level_marker}[cyan]{r.name}[/cyan]"
        detail_style = "red" if (r.status == FAIL and r.level == CRITICAL) else ("yellow" if r.status in (FAIL, WARN) else "white")
        table.add_row(name_cell, status_cell, f"[{detail_style}]{r.detail}[/{detail_style}]")

    console.print(table)

    if verbose:
        console.print()
        console.rule("[dim]Verbose Detail[/dim]")
        for r in results:
            if r.verbose:
                console.print(f"[cyan]{r.name}[/cyan]")
                for line in r.verbose.splitlines():
                    console.print(f"  [dim]{line}[/dim]")

    n_pass  = sum(1 for r in results if r.status == PASS)
    n_warn  = sum(1 for r in results if r.status == WARN)
    n_fail  = sum(1 for r in results if r.status == FAIL)
    console.print()
    summary_parts = [f"[green]{n_pass} passed[/green]"]
    if n_warn:
        summary_parts.append(f"[yellow]{n_warn} warning(s)[/yellow]")
    if n_fail:
        summary_parts.append(f"[red]{n_fail} failed[/red]")
    console.print("  ".join(summary_parts))
    console.print()
    return exit_code(results), results


@app.command()
def health(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show expanded detail for each check."),
):
    """
    Run pipeline health checks — Schwab tokens, API connectivity, Sheet, bundle age,
    FMP cache coverage, yfinance, transactions freshness, thesis coverage.
    """
    code, _results = run_health_report(verbose=verbose)
    raise typer.Exit(code=code)


@app.command("ask")
def ask_question(
    question: str = typer.Argument(..., help="Natural-language portfolio question."),
    since: Optional[str] = typer.Option(None, "--since", help="YYYY-MM-DD lower bound for corpus/tables."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan + retrieve only; no Gemini call."),
):
    """Grounded Q&A: retrieve evidence set → narrate with citations → validate."""
    from core.analyst.run import run_ask, write_report

    since_d = date.fromisoformat(since) if since else None
    result = run_ask(question, since=since_d, dry_run=dry_run)
    text = write_report(result, dry_run=dry_run)
    if isinstance(text, Path):
        console.print(f"[green]Wrote[/] {text}")
        console.print(text.read_text(encoding="utf-8")[:2000])
    else:
        console.print(text)
    if result.get("status") == "REFUSED":
        raise typer.Exit(code=1)
    if result.get("status") == "VALIDATION_FAILED":
        raise typer.Exit(code=2)


judge_app = typer.Typer(help="Judgment Engine — deterministic retrospective (no LLM).")
app.add_typer(judge_app, name="judge")


@judge_app.command("rotations")
def judge_rotations():
    """Unit A — rotation quality aggregates over frozen Rotation_Review."""
    from core.judgment.run import run_rotations, write_judgment_report

    body, meta, agg = run_rotations()
    path = write_judgment_report(body, meta, slug="rotations", rotation_agg=agg)
    console.print(f"[green]Wrote[/] {path}")
    console.print(body[:3000])


@judge_app.command("lifecycle")
def judge_lifecycle(
    ticker: Optional[str] = typer.Option(None, "--ticker", "-t", help="Single ticker campaign."),
    all_tickers: bool = typer.Option(False, "--all", help="Summary for every held ticker."),
    missing_json: bool = typer.Option(False, "--missing-json", help="Recompute tickers whose newest .md lacks a .json sidecar."),
    live: bool = typer.Option(False, "--live", help="Required with --missing-json to write artifacts."),
):
    """Unit B — position lifecycle campaign measurement."""
    from core.judgment.run import run_lifecycle, write_judgment_report

    if missing_json:
        if ticker or all_tickers:
            console.print("[red]--missing-json is mutually exclusive with --ticker and --all[/]")
            raise typer.Exit(code=1)
        from core.judgment.lifecycle_index import list_lifecycle_missing_json

        rows = list_lifecycle_missing_json()
        table = Table(title="Lifecycle sidecar backfill", show_header=True)
        table.add_column("Ticker")
        table.add_column("Action")
        table.add_column("MD path")
        for row in rows:
            table.add_row(row["ticker"], row["action"], row["path"])
        console.print(table)
        to_run = [r for r in rows if r["action"] == "run"]
        if not to_run:
            console.print("[green]All lifecycle artifacts have JSON sidecars.[/]")
            raise typer.Exit(code=0)
        if not live:
            console.print(
                "[yellow]Dry run — re-run with --live to recompute "
                f"{len(to_run)} ticker(s). ~2–3 min/ticker.[/]"
            )
            raise typer.Exit(code=0)
        est_min = int(len(to_run) * 2.5)
        console.print(
            f"[yellow]--missing-json --live runs ~2–3 min/ticker (~{est_min} min for {len(to_run)}). "
            "Do not pipe stdout — closing the pipe kills the run before the artifact writes.[/]"
        )
        for row in to_run:
            t = row["ticker"]
            console.print(f"[cyan]Recomputing {t}…[/]")
            body, meta, camp, _ = run_lifecycle(ticker=t, all_tickers=False)
            path = write_judgment_report(body, meta, slug=f"lifecycle_{t.lower()}", campaign=camp)
            console.print(f"[green]Wrote[/] {path}")
        raise typer.Exit(code=0)

    if not ticker and not all_tickers:
        console.print("[red]Specify --ticker, --all, or --missing-json[/]")
        raise typer.Exit(code=1)
    if all_tickers:
        from core.judgment.lifecycle import list_held_tickers

        n = len(list_held_tickers())
        est_min = int(n * 2.5)
        console.print(
            f"[yellow]--all runs ~2–3 min/ticker (~{est_min} min for {n} positions). "
            "Do not pipe stdout — closing the pipe kills the run before the artifact writes.[/]"
        )
    body, meta, camp, _ = run_lifecycle(ticker=ticker, all_tickers=all_tickers)
    if ticker:
        slug = f"lifecycle_{ticker.lower()}"
    else:
        slug = "lifecycle_all"
    path = write_judgment_report(body, meta, slug=slug, campaign=camp)
    console.print(f"[green]Wrote[/] {path}")
    console.print(body[:3000])


@judge_app.command("calibration")
def judge_calibration():
    """Unit C — calibration table scaffold (gates; blank quadrant visible)."""
    from core.judgment.run import run_calibration, write_judgment_report

    body, meta = run_calibration()
    path = write_judgment_report(body, meta, slug="calibration")
    console.print(f"[green]Wrote[/] {path}")
    console.print(body[:3000])


@app.command()
def snapshot(
    source: str = typer.Option("auto", "--source"),
    csv: Path | None = typer.Option(None, "--csv", exists=True),
    cash: float = typer.Option(0.0, "--cash"),
    enrich_atr: bool = typer.Option(True, "--enrich-atr/--no-enrich-atr"),
    enrich_technicals: bool = typer.Option(True, "--enrich-technicals/--no-enrich-technicals"),
    enrich_fmp: bool = typer.Option(True, "--enrich-fmp/--no-enrich-fmp"),
    enrich_styles: bool = typer.Option(True, "--enrich-styles/--no-enrich-styles"),
    live: bool = typer.Option(False, "--live"),
):
    """Freeze current market state to an immutable context bundle."""
    if source == "csv" and csv is None:
        console.print("[red]ERROR: --source csv requires --csv PATH[/]")
        raise typer.Exit(code=1)

    if live:
        console.print(Panel.fit("[bold white on red] LIVE MODE — Sheet writes enabled [/]", border_style="red"))
    else:
        console.print(Panel.fit("[bold black on yellow] DRY RUN — No Sheet writes. [/]", border_style="yellow"))

    with console.status(f"[cyan]Freezing market state from {source}..."):
        try:
            bundle = build_bundle(source=source, csv_path=csv, cash_manual=cash)
            path = write_bundle(bundle)
        except Exception as e:
            console.print(f"[red]ERROR: Snapshot failed: {e}[/]")
            raise typer.Exit(code=1)

    table = Table(title="Context Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Timestamp (UTC)", bundle.timestamp_utc)
    table.add_row("Bundle Hash", f"[bold green]{bundle.bundle_hash}[/]")
    table.add_row("Data Source", bundle.data_source)
    table.add_row("Positions", str(bundle.position_count))
    table.add_row("Total Value", f"${bundle.total_value:,.2f}")
    table.add_row("Bundle Path", str(path))
    console.print(table)

    from tasks.enrich_fundamentals import enrich_bundle_fundamentals
    with console.status("[cyan]Enriching with fundamentals..."):
        try:
            enrich_bundle_fundamentals(path)
        except Exception as e:
            console.print(f"[red]Fundamental enrichment failed: {e}[/]")

    if enrich_styles:
        from tasks.enrich_styles import enrich_bundle_styles
        try:
            enrich_bundle_styles(path)
        except Exception as e:
            console.print(f"[red]Style enrichment failed: {e}[/]")

    if enrich_fmp:
        from tasks.enrich_fmp import enrich_bundle_fmp
        with console.status("[cyan]Enriching with FMP..."):
            try:
                enrich_bundle_fmp(path)
            except Exception as e:
                console.print(f"[red]FMP enrichment failed: {e}[/]")

    if live:
        bundle_push(path=path, live=True)


# --- VAULT GROUP ---

@vault_app.command("snapshot")
def vault_snapshot(
    drive: bool = typer.Option(False, "--drive"),
    live: bool = typer.Option(False, "--live"),
):
    """Freeze vault documents (theses, transcripts) to an immutable vault bundle."""
    tickers = None
    try:
        market_bundles = sorted(list(Path("bundles").glob("context_bundle_*.json")), key=lambda p: p.stat().st_mtime)
        if market_bundles:
            market_data = load_bundle(market_bundles[-1])
            tickers = [p["ticker"] for p in market_data["positions"] if not p.get("is_cash")]
    except: pass

    with console.status("[cyan]Freezing vault..."):
        bundle = build_vault_bundle(ticker_list=tickers, include_drive=drive)
        path = write_vault_bundle(bundle)

    table = Table(title="Vault Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Vault Hash", f"[bold green]{bundle.vault_hash}[/]")
    table.add_row("Vault Doc Count", str(bundle.vault_doc_count))
    table.add_row("Bundle Path", str(path))
    console.print(table)


@vault_app.command("sync")
def vault_sync(
    ticker: str = typer.Option(None, "--ticker"),
    live: bool = typer.Option(False, "--live"),
    force: bool = typer.Option(False, "--force"),
    show_diff: bool = typer.Option(False, "--show-diff"),
    txn_limit: int = typer.Option(None, "--txn-limit", help="Max transactions per position in the thesis transaction log (default from config.THESIS_TXN_LOG_LIMIT)."),
):
    """Sync Sheets data into thesis files."""
    from core.thesis_sync_data import gather_thesis_sync_data
    from tasks.write_thesis_updates import write_thesis_updates

    with console.status("[cyan]Gathering sync data..."):
        tickers = [ticker.upper()] if ticker else None
        result = gather_thesis_sync_data(tickers=tickers, txn_limit=txn_limit)

    if result.parse_errors:
        for err in result.parse_errors:
            console.print(
                f"[yellow]Thesis frontmatter unparseable: {err.get('ticker')}: {err.get('error')}[/]"
            )

    payloads = result.payloads
    if not payloads:
        if result.parse_errors:
            console.print("[yellow]No syncable theses (frontmatter parse errors only).[/]")
        else:
            console.print("[yellow]No data found.[/]")
        return

    with console.status("[cyan]Updating thesis files..."):
        report = write_thesis_updates(payloads=payloads, dry_run=not live, force_recreate_regions=force, show_diff=show_diff)

    table = Table(title="Thesis Sync Report")
    table.add_column("Status", style="cyan")
    table.add_column("Count", style="white")
    table.add_row("Updated", str(report['updated']))
    table.add_row("Errors", str(report['errors']))
    table.add_row("Parse errors", str(len(result.parse_errors)))
    console.print(table)


@vault_app.command("sync-status")
def vault_sync_status():
    """Audit the staleness and drift of all thesis files."""
    from core.thesis_sync_data import gather_thesis_sync_data
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()

    with console.status("[cyan]Gathering data..."):
        result = gather_thesis_sync_data()

    if result.parse_errors:
        for err in result.parse_errors:
            console.print(
                f"[yellow]Thesis frontmatter unparseable: {err.get('ticker')}: {err.get('error')}[/]"
            )

    payloads = result.payloads

    table = Table(title="Thesis Sync Status")
    table.add_column("Ticker", style="cyan")
    table.add_column("Last Reviewed", style="white")
    table.add_column("Weight %", style="white")
    table.add_column("Ceiling %", style="white")
    table.add_column("Drift %", style="magenta")
    table.add_column("Status", style="white")

    for ticker, payload in payloads.items():
        path = Path(f"vault/theses/{ticker}_thesis.md")
        if not path.exists(): continue
        try:
            content = path.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            last_reviewed = "N/A"
            if fm_match:
                fm_data = yaml.load(fm_match.group(1))
                last_reviewed = fm_data.get('last_reviewed', "N/A")
            weight = f"{payload.current_allocation_pct:,.2f}%" if payload.current_allocation_pct is not None else "N/A"
            ceiling = f"{payload.size_ceiling_pct:,.2f}%" if payload.size_ceiling_pct else "N/A"
            drift_val = (payload.current_allocation_pct or 0) - (payload.size_ceiling_pct or 0)
            drift_str = f"{drift_val:+.2f}%"
            status = "OK"
            if drift_val > 1.0: status = "[bold red]OVER[/]"
            elif drift_val < -5.0: status = "[yellow]UNDER[/]"
            table.add_row(ticker, str(last_reviewed), weight, ceiling, drift_str, status)
        except:
            table.add_row(ticker, "ERR", "ERR", "ERR", "ERR", "ERR")
    console.print(table)


@vault_app.command("add-thesis")
def vault_add_thesis(ticker: str = typer.Argument(...)):
    """Scaffold a new _thesis.md file."""
    target = THESES_DIR / f"{ticker.upper()}_thesis.md"
    if target.exists():
        console.print(f"[yellow]! Thesis for {ticker.upper()} already exists.[/]")
        raise typer.Exit()
    _today = datetime.now().strftime("%Y-%m-%d")
    template = f"---\nticker: {ticker.upper()}\nstyle: GARP\nentry_date: {_today}\nlast_reviewed: {_today}\n---\n\n# {ticker.upper()} — Thesis\n"
    THESES_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(template)
    console.print(f"Created {target}")


@vault_app.command("thesis-audit")
def vault_thesis_audit():
    """Report quantitative trigger completeness."""
    thesis_files = sorted(THESES_DIR.glob("*_thesis.md"))
    table = Table(title="Thesis Audit")
    table.add_column("Ticker")
    table.add_column("File Size")
    for tf in thesis_files:
        table.add_row(tf.stem, f"{tf.stat().st_size} bytes")
    console.print(table)


# --- BUNDLE GROUP ---

@bundle_app.command("composite")
def bundle_composite(
    market: Path | None = typer.Option(None, "--market"),
    vault: Path | None = typer.Option(None, "--vault"),
    live: bool = typer.Option(False, "--live"),
):
    """Combine latest market + vault bundles into a composite."""
    try:
        if market and vault: market_path, vault_path = market, vault
        else: market_path, vault_path = resolve_latest_bundles()
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/]")
        raise typer.Exit(code=1)

    with console.status("[cyan]Building composite bundle..."):
        composite = build_composite_bundle(market_path, vault_path)
        path = write_composite_bundle(composite)

    table = Table(title="Composite Bundle", show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Composite Hash", f"[bold green]{composite.composite_hash}[/]")
    table.add_row("Bundle Path", str(path))
    console.print(table)

@bundle_app.command("push")
def bundle_push(
    path: Optional[Path] = typer.Option(None, "--path"),
    live: bool = typer.Option(False, "--live"),
):
    """Push bundle data to Sheets."""
    import pipeline
    if path is None:
        candidates = sorted(Path("bundles").glob("context_bundle_*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates: raise typer.Exit(code=1)
        path = candidates[-1]

    data = load_bundle(path)
    df = pd.DataFrame(data.get("positions", []))
    if 'weight_pct' in df.columns:
        # core/bundle.py only ever populates weight_pct (from market_value /
        # total_value); some enrichment steps add a 'weight' key that defaults
        # to 0.0 and is never actually filled in. Always prefer weight_pct
        # here -- checking "weight not in df.columns" let a bogus all-zero
        # 'weight' column silently win whenever both keys were present.
        df['weight'] = df['weight_pct'] / 100.0
    if 'import_date' not in df.columns:
        df['import_date'] = data.get('timestamp_utc', '')[:10]
    pipeline.write_to_sheets(df, cash_amount=data.get('cash_manual', 0.0), dry_run=not live)
    console.print("[green]Done.[/]")


@bundle_app.command("verify")
def bundle_verify(path: Path = typer.Argument(...)):
    """Verify bundle hash."""
    with open(path, "r") as f: data = json.load(f)
    try:
        if "composite_hash" in data: load_composite_bundle(path)
        elif "vault_hash" in data: load_vault_bundle(path)
        else: load_bundle(path)
        console.print(f"[bold green]PASS[/] Hash verified.")
    except Exception as e:
        console.print(f"[red]FAIL: {e}[/]")
        raise typer.Exit(code=1)


# --- SYNC GROUP ---

@ingest_app.command("transactions")
@sync_app.command("transactions")
def sync_transactions_cmd(
    days: int = typer.Option(90, "--days"),
    live: bool = typer.Option(False, "--live"),
    reconcile: bool = typer.Option(False, "--reconcile"),
    clean: bool = typer.Option(False, "--clean"),
    purge: bool = typer.Option(False, "--purge"),
):
    """Sync Schwab transaction history."""
    if clean:
        from tasks.sync_transactions import clean_junk_tickers
        success = clean_junk_tickers(live=live)
    else:
        from tasks.sync_transactions import sync_transactions
        success = sync_transactions(days=days, live=live, reconcile=reconcile)
    
    if success and purge:
        from utils.hygiene import purge_obsolete_data, print_purge_report
        report = purge_obsolete_data(dry_run=not live)
        print_purge_report(report, dry_run=not live)


@ingest_app.command("realized-gl")
@sync_app.command("realized-gl")
def sync_realized_gl_cmd(
    csv_path: Path = typer.Argument(..., exists=True),
    live: bool = typer.Option(False, "--live"),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Clear Realized_GL and write this CSV (rebuild). Default appends.",
    ),
    merge: bool = typer.Option(
        False,
        "--merge",
        help="Union this file with existing Realized_GL rows (dedupe by Fingerprint), then replace-write. "
        "Assumes the file is a COMPLETE re-export for every account it contains.",
    ),
    force_partial_merge: bool = typer.Option(
        False,
        "--force-partial-merge",
        help="Allow --merge when the file has fewer lots for an account than the sheet "
        "(dangerous: can erase real lots outside the file's date window).",
    ),
    purge: bool = typer.Option(False, "--purge"),
):
    """Import Realized G/L CSV (Schwab Lot Details or Chase HTML-.xls)."""
    from utils.gl_parser import parse_realized_gl_auto, detect_realized_gl_parser
    from utils.sheet_readers import get_gspread_client
    import pipeline

    if replace and merge:
        console.print("[red]Use only one of --replace or --merge.[/]")
        raise typer.Exit(1)
    if force_partial_merge and not merge:
        console.print("[red]--force-partial-merge requires --merge.[/]")
        raise typer.Exit(1)

    kind = detect_realized_gl_parser(csv_path)
    df = parse_realized_gl_auto(csv_path)
    if df.empty:
        console.print("[red]Parser returned 0 lots — check CSV format / account sections.[/]")
        return
    df['import_date'] = str(date.today())
    console.print(f"[cyan]Detected {kind} export[/]")

    st = df['term'].astype(str).str.lower().str.contains('short')
    lt = df['term'].astype(str).str.lower().str.contains('long')
    st_net = float(df.loc[st, 'st_gain_loss'].sum())
    lt_net = float(df.loc[lt, 'lt_gain_loss'].sum())
    console.print(
        f"[cyan]Parsed {len(df)} lots[/] | accounts={sorted(df['account'].astype(str).unique().tolist())} "
        f"| ST net ${st_net:,.2f} | LT net ${lt_net:,.2f} | "
        f"disallowed ${float(df['disallowed_loss'].sum()):,.2f}"
    )

    if live:
        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_REALIZED_GL)

        if merge:
            # Read existing sheet lots and union with the incoming parse.
            existing_vals = ws.get_all_values()
            if existing_vals and len(existing_vals) > 1:
                import pandas as _pd
                existing = _pd.DataFrame(existing_vals[1:], columns=existing_vals[0])
                # Normalize to parser column names via reverse GL_COL_MAP
                rev = {v: k for k, v in config.GL_COL_MAP.items()}
                existing = existing.rename(columns={c: rev.get(c, c) for c in existing.columns})
                # Coerce types used in fingerprints / tax math
                for col in [
                    "quantity", "proceeds_per_share", "cost_per_share", "proceeds",
                    "cost_basis", "unadjusted_cost", "gain_loss_dollars", "gain_loss_pct",
                    "lt_gain_loss", "st_gain_loss", "disallowed_loss", "holding_days",
                ]:
                    if col in existing.columns:
                        existing[col] = _pd.to_numeric(
                            existing[col].astype(str).str.replace(",", "", regex=False),
                            errors="coerce",
                        ).fillna(0.0)
                if "wash_sale" in existing.columns:
                    existing["wash_sale"] = existing["wash_sale"].astype(str).str.upper().isin(
                        ["TRUE", "YES", "Y"]
                    )
                if "is_primary_acct" in existing.columns:
                    existing["is_primary_acct"] = existing["is_primary_acct"].astype(str).str.upper().isin(
                        ["TRUE", "YES", "Y"]
                    )
                # Drop rows from the same account mask(s) being re-imported, then concat.
                # Completeness guard: refuse if the file has fewer lots for an account
                # than the sheet (partial re-import would erase real lots).
                new_accts = set(df["account"].astype(str))
                for acct in sorted(new_accts):
                    n_exist = int((existing["account"].astype(str) == acct).sum())
                    n_new = int((df["account"].astype(str) == acct).sum())
                    if n_exist > n_new and not force_partial_merge:
                        console.print(
                            f"[red]Merge refused for account {acct!r}: sheet has "
                            f"{n_exist} lots, file has {n_new}. A partial re-import "
                            f"would delete {n_exist - n_new} existing lot(s). "
                            f"Re-export the full account history, or pass "
                            f"--force-partial-merge if you intend to shrink.[/]"
                        )
                        raise typer.Exit(1)
                before = len(existing)
                existing = existing[~existing["account"].astype(str).isin(new_accts)].copy()
                console.print(
                    f"[dim]Merge: dropped {before - len(existing)} existing rows for "
                    f"re-imported account(s) {sorted(new_accts)}[/]"
                )
                df = _pd.concat([existing, df], ignore_index=True, sort=False)
            # Fall through to replace-write of the combined frame
            replace = True

        data_list = pipeline.sanitize_dataframe_for_sheets(df, config.GL_COLUMNS, config.GL_COL_MAP)

        def _cell(v):
            # RAW write: Sheets must not reinterpret booleans / dates.
            if isinstance(v, bool):
                return "TRUE" if v else "FALSE"
            if v is None:
                return ""
            return v

        data_list = [[_cell(c) for c in row] for row in data_list]

        if replace:
            # Archive-before-overwrite: keep prior values in a local stamp file, then clear+write.
            from pathlib import Path as _P
            archive_dir = _P("data") / "realized_gl_archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prior = ws.get_all_values()
            arch_path = archive_dir / f"Realized_GL_before_replace_{stamp}.csv"
            import csv as _csv
            with arch_path.open("w", newline="", encoding="utf-8") as f:
                _csv.writer(f).writerows(prior)
            console.print(f"[dim]Archived prior Realized_GL → {arch_path} ({len(prior)} rows)[/]")

            # clear() does not remove merges. Old Realized_GL formatting left merged
            # banner cells on rows 2-4; writing into them collapses the first lots.
            ws.clear()
            meta = ss.fetch_sheet_metadata()
            sheet_id = None
            merges = []
            frozen = 1
            for s in meta.get("sheets", []):
                props = s.get("properties", {})
                if props.get("title") != config.TAB_REALIZED_GL:
                    continue
                sheet_id = props.get("sheetId")
                merges = s.get("merges") or []
                frozen = props.get("gridProperties", {}).get("frozenRowCount", 1)
                break
            reqs = []
            if merges and sheet_id is not None:
                reqs.append({
                    "unmergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": max(m.get("endRowIndex", 0) for m in merges),
                            "startColumnIndex": 0,
                            "endColumnIndex": len(config.GL_COLUMNS),
                        }
                    }
                })
            if sheet_id is not None and frozen != 1:
                reqs.append({
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                })
            if reqs:
                ss.batch_update({"requests": reqs})
                console.print(f"[dim]Cleared {len(merges)} merge region(s); frozen rows -> 1[/]")

            header = [config.GL_COLUMNS]
            # RAW avoids USER_ENTERED mangling of bools / numeric strings into sparse rows.
            ws.update(range_name="A1", values=header + data_list, value_input_option="RAW")
            console.print(f"[green]Replaced Realized_GL with {len(data_list)} lots.[/]")
        else:
            ws.append_rows(data_list, value_input_option="RAW")
            console.print(f"[green]Appended {len(data_list)} lots.[/]")

        try:
            from core.store import get_store
            from utils.sheet_readers import get_realized_gl

            get_realized_gl.cache_clear()
            get_store().replace_realized_gl(get_realized_gl(), live=True)
            get_store().record_pipeline_run(
                "ingest_realized_gl", live=True, ok=True,
                detail=f"{'replace' if replace else 'append'} {len(data_list)}",
            )
        except Exception as e:
            console.print(f"[yellow]PortfolioStore realized_gl shadow failed: {e}[/]")
    else:
        mode = (
            "MERGE (union + replace-write)" if merge
            else ("REPLACE (clear + write)" if replace else "APPEND")
        )
        data_list = pipeline.sanitize_dataframe_for_sheets(df, config.GL_COLUMNS, config.GL_COL_MAP)
        console.print(f"[yellow]DRY RUN ({mode}): Would import {len(data_list)} lots. Use --live to write.[/]")

    if purge:
        from utils.hygiene import purge_obsolete_data, print_purge_report
        report = purge_obsolete_data(dry_run=not live)
        print_purge_report(report, dry_run=not live)


@ingest_app.command("podcasts")
def ingest_podcasts_cmd(
    analyze: bool = typer.Option(False, "--analyze"),
    live: bool = typer.Option(False, "--live"),
    purge: bool = typer.Option(False, "--purge"),
):
    """Ingest podcast transcripts."""
    podcast_batch(analyze=analyze, live=live)
    if purge:
        from utils.hygiene import purge_obsolete_data, print_purge_report
        report = purge_obsolete_data(dry_run=not live)
        print_purge_report(report, dry_run=not live)


@ingest_app.command("all")
def ingest_all(
    live: bool = typer.Option(False, "--live"),
    days: int = typer.Option(90, "--days"),
    purge: bool = typer.Option(False, "--purge"),
):
    """Ingest Transactions + Podcasts."""
    sync_transactions_cmd(days=days, live=live)
    ingest_podcasts_cmd(live=live)
    if purge:
        from utils.hygiene import purge_obsolete_data, print_purge_report
        report = purge_obsolete_data(dry_run=not live)
        print_purge_report(report, dry_run=not live)


# --- TAX GROUP ---

@refresh_app.command("tax")
@tax_app.command("refresh")
def tax_refresh(live: bool = typer.Option(False, "--live")):
    """Refresh Tax_Control tab."""
    from tasks.build_tax_control import refresh_tax_control_sheet
    refresh_tax_control_sheet(live=live)
    console.print("[green]Tax refresh complete.[/]")


@tax_app.command("project")
def tax_project(
    ticker: str = typer.Option(..., "--ticker"),
    shares: Optional[float] = typer.Option(None, "--shares", help="Trim size for 3d ESTIMATE bound."),
    as_of: Optional[str] = typer.Option(None, "--as-of", help="YYYY-MM-DD (default today)."),
):
    """
    Pre-trade tax surface (Prompt 9): wash [3a], LT ladder [3b], doctrine [3c], cost bound [3d].
    Every figure is an ESTIMATE — not a tax determination.
    """
    from datetime import date as date_cls

    from core.tax.surface import annotate_ticker, format_project_report

    ref = date_cls.fromisoformat(as_of) if as_of else date_cls.today()
    ann = annotate_ticker(ticker, as_of=ref, shares=shares)
    console.print(format_project_report(ann, shares=shares))


# --- DASHBOARD GROUP ---

@refresh_app.command("dashboard")
@dashboard_app.command("refresh")
def dashboard_refresh(
    live: bool = typer.Option(False, "--live"),
    update: bool = typer.Option(False, "--update"),
    tx_days: int = typer.Option(90, "--tx-days"),
):
    """Refreshes Dashboard views (runs same-day dislocation if missing)."""
    from tasks.build_valuation_card import main as build_val
    from tasks.build_decision_view import main as build_dec
    from tasks.build_command_center import main as build_cc
    from tasks.build_crosshairs import ensure_dislocation_payload, produce_crosshairs
    from tasks.format_sheets_dashboard_v2 import main as format_v2
    import scripts.live_update as live_up

    if update:
        live_up.update_portfolio(tx_days=tx_days)

    payload, path = ensure_dislocation_payload(run_if_missing=True, live=live)
    if path:
        console.print(f"[dim]Dislocation scan:[/] {path}")

    build_val(live=live)
    crosshairs = produce_crosshairs(dislocation_payload=payload, dislocation_path=path)
    build_cc(live=live, crosshairs=crosshairs)
    build_dec(live=live, crosshairs=crosshairs)
    try:
        from core.store.evidence import format_evidence_status, run_evidence_capture

        ev = run_evidence_capture(live=live, crosshairs=crosshairs)
        if ev.get("skipped"):
            console.print(f"[yellow]{ev.get('skip_reason')}[/]")
        else:
            console.print(format_evidence_status(ev.get("status")))
    except Exception as e:
        console.print(f"[yellow]Evidence capture failed (non-fatal): {e}[/]")
    format_v2(live=live)
    console.print("[green]Dashboard refresh complete (Valuation_Card, Decision_View, 0_DASHBOARD).[/]")


@store_app.command("status")
def store_status():
    """Show PortfolioStore backend and key aggregates."""
    from core.store import get_store
    import config as cfg

    store = get_store()
    snap = store.status()
    console.print(
        f"[bold]backend:[/] {snap.backend} "
        f"(STORE_BACKEND={cfg.STORE_BACKEND} STORE_PRIMARY={cfg.STORE_PRIMARY})"
    )
    console.print(f"  positions={snap.position_count}  MV=${snap.total_market_value:,.2f}")
    console.print(
        f"  txns={snap.transaction_count}  trade_log={snap.trade_log_count}  "
        f"realized={snap.realized_gl_count}  tax_lots={snap.tax_control_lot_count}  "
        f"rotation_review={snap.rotation_review_count}"
    )
    console.print(f"  sqlite path: {cfg.SQLITE_DB_PATH}")
    console.print(
        f"  streak gate: N={cfg.STORE_VERIFY_STREAK_N} consecutive verify runs; "
        f"backup keep daily={cfg.STORE_BACKUP_KEEP_DAILY} weekly={cfg.STORE_BACKUP_KEEP_WEEKLY}"
    )
    for n in snap.notes:
        console.print(f"  [dim]{n}[/]")


@store_app.command("verify")
def store_verify(
    require_streak: bool = typer.Option(
        False,
        "--require-streak",
        help="Exit 1 unless N consecutive green verify runs + ≥1 realized lot in window.",
    ),
):
    """Value-level Sheets vs SQLite reconcile (proceeds/cost/G/L/ST/LT/disallowed)."""
    from core.store import verify_stores

    result = verify_stores()
    for line in result.lines:
        console.print(line)
    if not result.ok:
        raise typer.Exit(code=1)
    if require_streak and not result.streak_ok:
        console.print("[red]Streak gate failed (--require-streak).[/]")
        raise typer.Exit(code=1)


@store_app.command("bundle-parity")
def store_bundle_parity():
    """Diff Sheets vs SQLite ledger fingerprints (bundle-canonical SHA)."""
    from core.store.bundle_parity import run_bundle_parity

    result = run_bundle_parity()
    for line in result.lines:
        console.print(line)
    if not result.ok:
        raise typer.Exit(code=1)


@store_app.command("sync-from-sheets")
def store_sync_from_sheets(
    live: bool = typer.Option(False, "--live", help="Write SQLite. Default: DRY RUN."),
    include_holdings: bool = typer.Option(
        False,
        "--include-holdings",
        help="Also copy Holdings_Current (cache only; not Phase-1 ledger).",
    ),
):
    """Copy transactions / realized_gl / trade_log into SQLite (tax via refresh tax --live)."""
    from core.store.sync_from_sheets import sync_sqlite_from_sheets

    summary = sync_sqlite_from_sheets(live=live, include_holdings_cache=include_holdings)
    mode = "LIVE" if live else "DRY RUN"
    console.print(f"[bold]{mode}[/] sync-from-sheets: {summary}")


@store_app.command("backup")
def store_backup(
    live: bool = typer.Option(False, "--live", help="VACUUM INTO + hash + Drive copy."),
):
    """Phase-1 acceptance backup: VACUUM INTO, SHA-256 sidecar, copy to Drive db_backups/."""
    from core.store.backup import backup_sqlite

    result = backup_sqlite(live=live)
    console.print(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@store_app.command("snapshot")
def store_snapshot(
    live: bool = typer.Option(False, "--live", help="VACUUM INTO daily snapshot under data/portfolio_store_backups/."),
):
    """Daily VACUUM INTO snapshot (stays in Drive-synced repo tree — offsite after ledger relocate)."""
    from core.store.backup import snapshot_sqlite

    result = snapshot_sqlite(live=live)
    console.print(result)
    if result.get("pruned") and result["pruned"].get("refused"):
        console.print(f"[yellow]{result['pruned']['refused']}[/]")
    if result.get("pruned") and result["pruned"].get("deleted"):
        for p in result["pruned"]["deleted"]:
            console.print(f"[dim]pruned:[/] {p}")
    if not result.get("ok"):
        raise typer.Exit(code=1)


@store_app.command("provenance")
def store_provenance():
    """If the local ledger were lost — what Schwab cannot give back."""
    from core.store.backup import provenance_table

    console.print(provenance_table())


@store_app.command("evidence-status")
def store_evidence_status():
    """Append-only evidence tables: row counts, accrual days, ten-day gate."""
    from core.store.evidence import format_evidence_status

    console.print(format_evidence_status())


@store_app.command("evidence-capture")
def store_evidence_capture(
    live: bool = typer.Option(False, "--live", help="Write evidence tables. Default: DRY RUN."),
):
    """Standalone evidence capture (signals + bars + fundamentals). --live required to write."""
    from core.store.evidence import format_evidence_status, run_evidence_capture

    summary = run_evidence_capture(live=live)
    mode = "LIVE" if live else "DRY RUN"
    if summary.get("skipped"):
        console.print(f"[yellow]{summary.get('skip_reason')}[/]")
        return
    console.print(f"[bold]{mode}[/] evidence-capture: {summary.get('results')}")
    console.print(format_evidence_status(summary.get("status")))


@corpus_app.command("index")
def corpus_index(
    live: bool = typer.Option(False, "--live", help="Write index. Default: DRY RUN."),
    rebuild: bool = typer.Option(False, "--rebuild", help="Drop and rebuild (requires --live --yes)."),
    yes: bool = typer.Option(False, "--yes", help="Confirm destructive --rebuild."),
    source: Optional[str] = typer.Option(None, "--source", help="Limit to one source_type."),
):
    """Incremental corpus FTS index. Re-index of unchanged files writes nothing."""
    from core.corpus.index import run_index

    try:
        report = run_index(live=live, rebuild=rebuild, yes=yes, source_type=source)
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1)
    mode = "LIVE" if live else "DRY RUN"
    console.print(
        f"[bold]{mode}[/] corpus index: new={report.new} changed={report.changed} "
        f"unchanged={report.unchanged} deleted={report.deleted} writes={report.writes}"
    )
    for st, bucket in sorted(report.by_source.items()):
        console.print(f"  {st}: {bucket}")
    if report.parse_failures:
        console.print("[yellow]Parse failures:[/]")
        for p in report.parse_failures:
            console.print(f"  - {p}")


@corpus_app.command("status")
def corpus_status_cmd():
    """Per source_type: docs, chunks, date range, last indexed."""
    from core.corpus.index import corpus_status

    st = corpus_status()
    for name, bucket in st["by_source"].items():
        console.print(
            f"{name}: docs={bucket['docs']} chunks={bucket['chunks']} "
            f"oldest={bucket['oldest']} newest={bucket['newest']} "
            f"last_indexed={bucket['last_indexed']}"
        )
    console.print(f"totals: {st['totals']}")


@corpus_app.command("search")
def corpus_search_cmd(
    query: str = typer.Argument(..., help="FTS5 query string"),
    ticker: Optional[List[str]] = typer.Option(None, "--ticker", help="Filter by ticker tag (repeatable)."),
    source_type: Optional[List[str]] = typer.Option(None, "--source-type", help="Filter source_type."),
    since: Optional[str] = typer.Option(None, "--since", help="YYYY-MM-DD"),
    until: Optional[str] = typer.Option(None, "--until", help="YYYY-MM-DD"),
    limit: int = typer.Option(10, "--limit"),
):
    """Search the corpus; each hit is path:line with a snippet."""
    from core.corpus.search import format_hit, search_ranked

    since_d = date.fromisoformat(since) if since else None
    until_d = date.fromisoformat(until) if until else None
    hits = search_ranked(
        query,
        tickers=ticker,
        source_types=source_type,
        since=since_d,
        until=until_d,
        limit=limit,
    )
    if not hits:
        console.print("[dim]No hits.[/]")
        return
    for h in hits:
        console.print(format_hit(h))
        console.print("")


@store_app.command("publish-cockpit")
def store_publish_cockpit(
    live: bool = typer.Option(False, "--live", help="Write static HTML under agent_outputs/command_center/."),
    publish: bool = typer.Option(
        False,
        "--publish",
        help="Also copy to Drive Portfolio_Analysis (same mirror as pm publish analysis).",
    ),
):
    """Render static Command Center HTML for phone/Drive monitoring (not localhost)."""
    from core.store.publish_static import render_static_cockpit

    result = render_static_cockpit(live=live)
    console.print(result)
    if live and publish:
        from scripts.backup_to_drive import publish_analysis

        pub = publish_analysis(live=True)
        console.print(f"Drive publish: {pub}")


@export_app.command("sheets")
def export_sheets(
    live: bool = typer.Option(False, "--live", help="Write Tax_Control grid from SQLite to Sheets."),
):
    """Re-export computed Tax_Control from SQLite to Sheets (cockpit continuity)."""
    from core.store.export_sheets import export_sheets_from_store

    result = export_sheets_from_store(live=live)
    console.print(result)


@ui_app.command("serve")
def ui_serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
):
    """Optional local debug server. Product monitoring surface is `pm store publish-cockpit --live --publish`."""
    import uvicorn

    console.print(
        "[yellow]Debug only[/] — phone access uses Drive-published static HTML "
        "(`pm store publish-cockpit --live --publish`), not this localhost server."
    )
    console.print(f"[cyan]Serving UI at http://{host}:{port}[/]  (Ctrl+C to stop)")
    reload = os.getenv("PM_UI_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run("ui.app:app", host=host, port=port, reload=reload)


# --- EXPORT GROUP ---

@export_app.command("list")
def export_list():
    """List scenarios."""
    for s, d in config.EXPORT_SCENARIOS.items():
        console.print(f"  {s:15s} {d}")


@export_app.command("run")
def export_run(
    scenario: str = typer.Argument(..., help="Scenario name (see 'pm export list')"),
):
    """Build a context package for the given scenario and save to exports/."""
    if scenario not in config.EXPORT_SCENARIOS:
        console.print(f"[red]Unknown scenario '{scenario}'. Run 'pm export list' to see options.[/]")
        raise typer.Exit(1)

    if scenario == "tax-rebalance":
        _export_tax_rebalance()
    else:
        console.print(f"[yellow]Scenario '{scenario}' is listed but not yet implemented.[/]")
        raise typer.Exit(1)


def _export_tax_rebalance():
    """Build a tax-rebalance context package from live Sheet data."""
    import pandas as pd
    from tasks.export_package import (
        create_package_dir, write_manifest, write_readme,
        write_context_json, write_prompt_markdown,
    )
    from utils.sheet_readers import get_gspread_client, read_gsheet_robust

    with console.status("[cyan]Reading Sheet data..."):
        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)

        # Tax_Control KPI strip (row 2 = labels, row 3 = values)
        tax_raw = ss.worksheet(config.TAB_TAX_CONTROL).get_all_values()
        tax_kpis = {}
        if len(tax_raw) >= 3:
            labels = tax_raw[1]
            values = tax_raw[2]
            for i, label in enumerate(labels):
                if label and i < len(values):
                    tax_kpis[label] = values[i]

        # Holdings — unrealized positions for TLH candidates
        df_h = read_gsheet_robust(ss.worksheet(config.TAB_HOLDINGS_CURRENT))
        df_h["Market Value"] = pd.to_numeric(df_h.get("Market Value", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df_h["Unrealized G/L"] = pd.to_numeric(df_h.get("Unrealized G/L", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df_h["Unrealized G/L %"] = pd.to_numeric(df_h.get("Unrealized G/L %", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df_h["Weight"] = pd.to_numeric(df_h.get("Weight", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df_h = df_h[~df_h["Ticker"].astype(str).isin(config.CASH_TICKERS)]

        # Normalize weight to percentage if stored as decimal
        if df_h["Weight"].max() <= 1.5:
            df_h["Weight"] = df_h["Weight"] * 100

        tlh_candidates = df_h[df_h["Unrealized G/L"] < config.TLH_LOSS_THRESHOLD_USD].sort_values("Unrealized G/L")
        gains_at_risk = df_h[df_h["Unrealized G/L"] > 0].sort_values("Unrealized G/L", ascending=False).head(15)

        # Realized G/L — wash sale lots + recent lots
        try:
            df_gl = read_gsheet_robust(ss.worksheet(config.TAB_REALIZED_GL))
            df_gl["Gain Loss $"] = pd.to_numeric(df_gl.get("Gain Loss $", pd.Series(dtype=float)), errors="coerce").fillna(0)
            wash_lots = df_gl[df_gl.get("Wash Sale", pd.Series(dtype=str)).astype(str).str.upper() == "TRUE"]
        except Exception:
            df_gl = pd.DataFrame()
            wash_lots = pd.DataFrame()

    # Build context dict
    context = {
        "generated_at": datetime.now().isoformat(),
        "tax_posture_ytd": tax_kpis,
        "tlh_candidates": tlh_candidates[["Ticker", "Market Value", "Unrealized G/L", "Unrealized G/L %", "Weight"]].to_dict("records"),
        "largest_unrealized_gains": gains_at_risk[["Ticker", "Market Value", "Unrealized G/L", "Unrealized G/L %", "Weight"]].to_dict("records"),
        "wash_sale_lots": wash_lots[["Ticker", "Closed Date", "Gain Loss $", "Disallowed Loss"]].to_dict("records") if not wash_lots.empty else [],
        "tlh_threshold_usd": config.TLH_LOSS_THRESHOLD_USD,
    }

    prompt = f"""# Tax-Rebalance Analysis — {datetime.now().strftime("%Y-%m-%d")}

You are a tax-efficient portfolio advisor. The attached context.json contains:
- YTD realized gain/loss posture (Net ST, Net LT, wash sale count, estimated tax liability)
- Tax-loss harvesting (TLH) candidates: unrealized losses exceeding ${abs(config.TLH_LOSS_THRESHOLD_USD):,.0f}
- Largest unrealized gains at risk of triggering a tax event
- Active wash sale lots requiring 30-day replacement discipline

## Instructions

1. **Posture Assessment** — Summarize the current YTD tax position. Is the portfolio net-positive (tax bill likely) or net-negative (harvesting capacity)?

2. **TLH Recommendations** — For each TLH candidate, recommend whether to harvest, hold, or wait. Flag any 30-day wash sale window risks from recent realized lots in the same ticker.

3. **Gains Protection** — For the top unrealized gainers, flag which have held long-term (>1 year) vs. short-term. Note which are approaching a calendar-year trigger.

4. **Rebalance Pairing** — Suggest any loss-harvest / replacement-buy pairs that reduce concentration risk while respecting wash sale rules.

5. **Priority Action List** — Rank the top 3 actions by tax impact. Be specific: ticker, action, rationale.

## Context

See attached context.json.
"""

    with console.status("[cyan]Writing package..."):
        pkg_dir = create_package_dir("tax-rebalance")
        write_context_json(pkg_dir, context)
        write_prompt_markdown(pkg_dir, prompt)
        write_manifest(pkg_dir, "tax-rebalance", "n/a", "1.0.0", {
            "tlh_candidates": len(context["tlh_candidates"]),
            "wash_lots": len(context["wash_sale_lots"]),
        })
        write_readme(pkg_dir, "tax-rebalance",
            "YTD tax posture, TLH candidates, and gain/loss pairing analysis.",
            "Paste prompt.md into your LLM, then attach or paste context.json.")

    console.print(f"[green]Package ready:[/] {pkg_dir}")
    console.print(f"  TLH candidates : {len(context['tlh_candidates'])}")
    console.print(f"  Unrealized gains: {len(context['largest_unrealized_gains'])}")
    console.print(f"  Wash sale lots : {len(context['wash_sale_lots'])}")
    console.print(f"\nNext: paste [bold]prompt.md[/] into your LLM, attach [bold]context.json[/].")


@clean_app.command("theses")
def clean_theses(
    live: bool = typer.Option(False, "--live", help="Archive orphan thesis files. Default: DRY RUN."),
    min_age_days: int = typer.Option(
        7, "--min-age-days",
        help="Fallback freshness guard used only if Holdings_Current's Import Date can't be read.",
    ),
):
    """
    Detect thesis files under vault/theses/*.md for tickers no longer held,
    and move them to vault/theses/archive/.

    A position bought between Schwab syncs is, by definition, absent from
    Holdings_Current -- so without a freshness guard this command archives
    the thesis for a position that was just opened (see SKHY, 2026-07-29).
    A thesis is skipped, not archived, when its frontmatter entry_date or
    its file mtime is on or after the Holdings_Current refresh date.
    """
    from utils.sheet_readers import get_gspread_client, read_gsheet_robust
    import shutil

    # Get current held tickers
    held_tickers = set()
    refresh_date = None
    try:
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_HOLDINGS_CURRENT)
        df_h = read_gsheet_robust(ws)
        if not df_h.empty:
            # "Import Date" is stamped on every row by the same sync that
            # writes Holdings_Current itself -- the closest thing this sheet
            # has to a refresh footer.
            if "Import Date" in df_h.columns:
                import_dates = []
                for raw in df_h["Import Date"].dropna().astype(str):
                    raw = raw.strip()[:10]
                    try:
                        import_dates.append(datetime.strptime(raw, "%Y-%m-%d").date())
                    except ValueError:
                        continue
                if import_dates:
                    refresh_date = max(import_dates)
            df_h = df_h[~df_h["Ticker"].astype(str).isin(config.CASH_TICKERS)]
            held_tickers = set(df_h["Ticker"].astype(str).str.strip().str.upper())
    except Exception as e:
        console.print(f"[yellow]Could not query live sheet for held tickers: {e}. Falling back to latest bundle.[/]")
        try:
            candidates = sorted(Path("bundles").glob("context_bundle_*.json"), key=lambda p: p.stat().st_mtime)
            if candidates:
                with open(candidates[-1], "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                held_tickers = {p["ticker"].strip().upper() for p in data.get("positions", []) if not p.get("is_cash")}
        except Exception as e2:
            console.print(f"[red]Failed to fetch held tickers: {e2}[/]")
            raise typer.Exit(code=1)

    if not held_tickers:
        console.print("[red]No held tickers found. Aborting safety check to avoid deleting everything.[/]")
        raise typer.Exit(code=1)

    if refresh_date is not None:
        cutoff_date = refresh_date
        cutoff_label = f"Holdings_Current refresh ({refresh_date.isoformat()})"
    else:
        cutoff_date = date.today() - timedelta(days=min_age_days)
        cutoff_label = f"--min-age-days={min_age_days} cutoff ({cutoff_date.isoformat()})"
        console.print(
            f"[yellow]Could not read Holdings_Current's Import Date -- falling back to {cutoff_label}.[/]"
        )

    # Scan theses dir
    theses_dir = Path("vault/theses")
    archive_dir = theses_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    theses_files = list(theses_dir.glob("*_thesis.md"))
    orphans = []
    skipped = []
    for tf in theses_files:
        ticker = tf.stem.replace("_thesis", "").upper()
        if ticker in held_tickers:
            continue

        entry_date = None
        try:
            raw = tf.read_text(encoding="utf-8")
            m = re.search(r"^entry_date:\s*['\"]?(\d{4}-\d{2}-\d{2})", raw, re.MULTILINE)
            if m:
                entry_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except Exception:
            pass
        mtime_date = datetime.fromtimestamp(tf.stat().st_mtime).date()

        if (entry_date is not None and entry_date >= cutoff_date) or mtime_date >= cutoff_date:
            skipped.append((ticker, tf))
            continue

        orphans.append((ticker, tf))

    if skipped:
        for ticker, tf in sorted(skipped):
            console.print(
                f"[yellow]SKIPPED {ticker}: thesis newer than {cutoff_label} -- "
                "position may not have synced yet.[/]"
            )

    if not orphans:
        console.print("[green]No orphan thesis files to archive.[/]")
        return

    mode = "LIVE" if live else "DRY RUN"
    console.print(f"[bold cyan]Orphan Thesis Archiving — {mode}[/]")
    console.print(f"Found {len(orphans)} orphan thesis file(s):")
    for ticker, tf in sorted(orphans):
        console.print(f"  - {ticker} ({tf.name})")

    if not live:
        console.print("[yellow]\nDRY RUN — no files moved. Re-run with --live to archive these files.[/]")
        return

    # Perform move in live mode
    moved_count = 0
    for ticker, tf in orphans:
        dest = archive_dir / tf.name
        try:
            shutil.move(str(tf), str(dest))
            console.print(f"  [green]Archived:[/] {tf.name} -> {dest}")
            moved_count += 1
        except Exception as e:
            console.print(f"  [red]Failed to archive {tf.name}: {e}[/]")

    console.print(f"\n[bold green]SUCCESS:[/] Archived {moved_count} orphan thesis file(s).")


@clean_app.command("exports")
@export_app.command("cleanup")
def export_cleanup(
    days: int = typer.Option(config.PURGE_DEFAULT_DAYS_EXPORTS, "--days"),
    live: bool = typer.Option(False, "--live"),
):
    """Clean old exports."""
    from utils.hygiene import purge_obsolete_data, print_purge_report
    report = purge_obsolete_data(days_exports=days, dry_run=not live)
    print_purge_report({"exports": report["exports"]}, dry_run=not live)

@clean_app.command("podcasts")
@podcast_app.command("clean")
def podcast_clean(
    days: int = typer.Option(config.PURGE_DEFAULT_DAYS_PODCASTS, "--days"),
    live: bool = typer.Option(False, "--live"),
):
    """Clean old podcasts."""
    from utils.hygiene import purge_obsolete_data, print_purge_report
    report = purge_obsolete_data(days_podcasts=days, dry_run=not live)
    print_purge_report({"podcasts": report["podcasts"]}, dry_run=not live)

@clean_app.command("bundles")
def clean_bundles(
    days: int = typer.Option(config.PURGE_DEFAULT_DAYS_BUNDLES, "--days"),
    live: bool = typer.Option(False, "--live"),
):
    """Clean old bundles."""
    from utils.hygiene import purge_obsolete_data, print_purge_report
    report = purge_obsolete_data(days_bundles=days, dry_run=not live)
    print_purge_report({"bundles": report["bundles"]}, dry_run=not live)

@clean_app.command("all")
def clean_all(live: bool = typer.Option(False, "--live")):
    """Clean everything."""
    from utils.hygiene import purge_obsolete_data, print_purge_report
    report = purge_obsolete_data(dry_run=not live)
    print_purge_report(report, dry_run=not live)


@export_app.command("inspect")
def export_inspect(path: Path = typer.Argument(...)):
    """Inspect package."""
    console.print(f"Inspecting {path}")

@podcast_app.command("fetch")
def podcast_fetch(video_id: str = typer.Argument(...), source_name: str = "Manual"):
    """Fetch transcript."""
    from tasks.podcast_fetcher import fetch_transcript_to_file
    fetch_transcript_to_file(video_id, source_name=source_name)
    console.print("[green]Done.[/]")


@podcast_app.command("batch")
def podcast_batch(
    analyze: bool = typer.Option(False, "--analyze", help="Run Gemini macro analysis after fetching."),
    live: bool = typer.Option(False, "--live", help="Save dedup log and run Sheet writes. Default: DRY RUN."),
):
    """Fetch latest episode transcripts for all tracked podcast channels."""
    from tasks.batch_podcast_sync import (
        get_latest_video, load_processed_videos, save_processed_videos,
        PODCAST_CHANNELS,
    )
    from tasks.podcast_fetcher import fetch_transcript_to_file

    mode = "LIVE" if live else "DRY RUN"
    console.print(f"[bold cyan]Batch Podcast Sync — {mode}[/]")

    processed = load_processed_videos()
    counts = {"fetched": 0, "skipped": 0, "failed": 0}

    for channel_name, cfg in PODCAST_CHANNELS.items():
        channel_id = cfg["channel_id"]
        title_filter = cfg.get("title_filter")
        console.print(f"\nChecking [cyan]{channel_name}[/]...")
        video_id, title = get_latest_video(channel_id, title_filter=title_filter)

        if video_id is None:
            console.print(f"  [red]Could not fetch latest video[/]")
            counts["failed"] += 1
            continue

        console.print(f"  Latest: [dim]{title}[/] ({video_id})")

        if video_id in processed:
            console.print(f"  [yellow]SKIP[/] — already processed on {processed[video_id]['processed_at'][:10]}")
            counts["skipped"] += 1
            continue

        try:
            save_path = fetch_transcript_to_file(video_id, source_name=f"{channel_name}: {title}")
            word_count = len(save_path.read_text(encoding="utf-8").split())
            console.print(f"  [green]Fetched[/] {word_count:,} words -> {save_path.name}")
            processed[video_id] = {
                "channel": channel_name,
                "title": title,
                "processed_at": datetime.now().isoformat(),
            }
            counts["fetched"] += 1
        except Exception as e:
            console.print(f"  [red]FAILED:[/] {e}")
            counts["failed"] += 1
            continue

        if analyze:
            try:
                from utils.agents.podcast_analyst import analyze_podcast
                text = save_path.read_text(encoding="utf-8")
                result = analyze_podcast(text, source_name=f"{channel_name}: {title}")
                if result:
                    console.print(f"  [dim]Analysis: {result.get('executive_summary', '')[:80]}[/]")
            except Exception as e:
                console.print(f"  [yellow]Analysis failed:[/] {e}")

    if live:
        save_processed_videos(processed)
        console.print("\n[dim]Dedup log saved.[/]")
    else:
        console.print("\n[bold yellow]DRY RUN — dedup log not saved. Use --live to persist.[/]")

    console.print(
        f"\n[bold]Done:[/] {counts['fetched']} fetched, "
        f"{counts['skipped']} skipped, {counts['failed']} failed"
    )


@podcast_app.command("ingest-spotify")
def podcast_ingest_spotify(
    days: int = typer.Option(None, "--days", help="Ingestion window in days. Default: config.SPOTIFY_DIGEST_WINDOW_DAYS."),
    live: bool = typer.Option(False, "--live", help="Write summary files and ledger. Default: DRY RUN."),
    seed_ledger: bool = typer.Option(False, "--seed-ledger", help="Backfill ledger for already hand-ingested digests; generates no summary files."),
):
    """Ingest Spotify Studio daily allocation digests into data/podcast_summaries/."""
    from tasks.ingest_spotify_digests import main as ingest_spotify_digests, seed_ledger as seed_spotify_ledger

    if seed_ledger:
        seed_spotify_ledger(live=live)
    else:
        ingest_spotify_digests(days=days, live=live)


@podcast_app.command("bundle")
def podcast_bundle(last_n: int = typer.Option(10, "--last-n", help="Number of most recent transcripts to include")):
    """Concatenate the N most recent transcripts into a single Markdown file for LLM use."""
    from tasks.podcast_fetcher import TRANSCRIPTS_DIR
    from datetime import datetime as _dt

    transcript_files = sorted(TRANSCRIPTS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    selected = transcript_files[:last_n]

    if not selected:
        console.print("[red]No transcripts found. Run 'pm podcast fetch' or 'pm podcast batch' first.[/]")
        raise typer.Exit(1)

    bundle_dir = Path("data/podcast_bundles")
    bundle_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.now().strftime("%Y-%m-%d_%H%M")
    out_path = bundle_dir / f"bundle_{ts}.md"

    lines = [f"# Podcast Bundle — {ts}", f"_Includes {len(selected)} transcript(s)_", ""]
    for tf in reversed(selected):  # chronological order
        lines += [f"---", f"## {tf.stem}", ""]
        lines.append(tf.read_text(encoding="utf-8"))
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    size_kb = out_path.stat().st_size // 1024
    console.print(f"[green]Bundle written:[/] {out_path}  ({size_kb} KB, {len(selected)} transcripts)")


def _morning_summary(
    console: Console,
    mode_label: str,
    step_results: list,
    tx_ok: bool,
    snapshot_ok: bool,
    tax_refreshed: bool,
    skip_tax: bool,
    start_time: float,
) -> None:
    elapsed = time.time() - start_time
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)
    elapsed_str = f"{h:02d}:{m:02d}:{s:02d}"

    icons = {"pass": "[bold green]OK[/]", "warn": "[bold yellow]WARN[/]", "fail": "[bold red]FAIL[/]", "skip": "[dim]SKIP[/dim]"}

    lines = [f"[bold]Mode:[/] {'[bold green]LIVE[/]' if mode_label == 'LIVE' else '[bold yellow]DRY RUN[/]'}"]
    lines.append("")
    lines.append("[bold]Steps:[/]")
    for name, status in step_results:
        lines.append(f"  {icons.get(status, '-')} {name}")
    lines.append("")
    lines.append(f"[bold]Snapshot written:[/]      {'[green]yes[/]' if snapshot_ok else '[red]no[/]'}")
    lines.append(f"[bold]Transactions synced:[/]   {'[green]yes[/]' if tx_ok else '[yellow]see above[/]'}")
    lines.append(f"[bold]Tax_Control refreshed:[/] {'[green]yes[/]' if tax_refreshed else ('[dim]skipped[/dim]' if skip_tax else '[yellow]no[/]')}")
    lines.append("")
    lines.append(f"[bold]Total elapsed:[/] {elapsed_str}")

    console.print()
    console.print(Panel("\n".join(lines), title="[bold]Morning Pipeline Summary[/]", border_style="cyan"))


@app.command("morning")
def morning(
    live: bool = typer.Option(False, "--live", help="Write to Google Sheets. Without this, runs as a dry-run preview."),
    skip_health: bool = typer.Option(False, "--skip-health", help="Skip the upfront health check (not recommended)."),
    skip_transactions: bool = typer.Option(False, "--skip-transactions", help="Skip transaction sync."),
    skip_podcasts: bool = typer.Option(False, "--skip-podcasts", help="Skip the podcast batch sync step."),
    skip_tax: bool = typer.Option(False, "--skip-tax", help="Skip the Tax_Control refresh."),
    tx_days: int = typer.Option(7, "--tx-days", help="Days of transactions to sync. Default 7."),
    continue_on_warning: bool = typer.Option(True, "--continue-on-warning/--strict", help="Continue past health warnings."),
    skip_vault_sync: bool = typer.Option(False, "--skip-vault-sync", help="Skip vault sync to markdown theses."),
    skip_composite: bool = typer.Option(False, "--skip-composite", help="Skip building composite bundle."),
    skip_export: bool = typer.Option(False, "--skip-export", help="Skip building the AI briefing package in exports/."),
    skip_dislocation: bool = typer.Option(False, "--skip-dislocation", help="Skip the dislocation scan."),
    skip_risk_metrics: bool = typer.Option(False, "--skip-risk-metrics", help="Skip Risk_Metrics rebuild inside STEP 5."),
):
    """
    Run the full market-open pipeline: health -> Schwab sync -> snapshot -> podcast sync ->
    dislocation scan -> dashboard refresh (Crosshairs) -> vault sync -> composite bundle ->
    AI briefing export -> derive rotations -> publish.
    """
    _acquire_pipeline_lock()
    from tasks.health import run_all_checks, exit_code as health_exit_code, CRITICAL, FAIL, WARN, PASS
    from tasks.build_valuation_card import main as build_val
    from tasks.build_decision_view import main as build_dec
    from tasks.build_command_center import main as build_cc
    from tasks.build_crosshairs import produce_crosshairs
    from tasks.format_sheets_dashboard_v2 import main as format_v2
    from tasks.build_tax_control import refresh_tax_control_sheet
    import scripts.live_update as live_up
    
    start_time = time.time()
    mode_label = "LIVE" if live else "DRY RUN"

    step_results = []
    snapshot_ok = False
    tx_ok = False
    tax_refreshed = False

    # 1. Health Check
    if not skip_health:
        console.print("\n[bold cyan]STEP 0 - Health Check[/]")
        code, health_results = run_health_report()
        from tasks.health import write_failure_sentinel, clear_failure_sentinel

        # Determine worst status from the report
        if code == 1:
            step_results.append(("Health", "fail"))
            console.print(Panel("[bold red]Cannot proceed — Critical health failures detected.[/]", style="red"))
            if not sys.stdin.isatty():
                # Unattended run (Task Scheduler / cron): never block on an
                # interactive prompt. Fail fast with a clear log line instead
                # -- and, unlike before, leave a sentinel on disk so the next
                # run (or anything reading exports/) knows a gap happened
                # instead of everyone finding out by reading the log by hand.
                sentinel_path = write_failure_sentinel(health_results)
                console.print(
                    "[red]UNATTENDED RUN: critical health failure — skipping interactive "
                    "reauth prompt. Fix manually: `python manager.py login` or "
                    "schwab_emergency_reauth.bat, then re-run morning.[/]\n"
                    f"[red]Wrote {sentinel_path} — cleared automatically on the next run "
                    "that passes health.[/]"
                )
                _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
                raise typer.Exit(code=1)
            from rich.prompt import Confirm
            if Confirm.ask("Would you like to run the Schwab reauthentication script now?"):
                subprocess.run([sys.executable, "scripts/schwab_manual_reauth.py"])
                console.print("[yellow]Reauthentication complete. Please run `pm morning` again.[/]")
            _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
            raise typer.Exit(code=1)
        elif code == 2:
            step_results.append(("Health", "warn"))
            clear_failure_sentinel()  # no critical failure this run -- any prior gap is over
            if not continue_on_warning:
                console.print(Panel("[bold yellow]Health warnings detected — halting (--strict mode).[/]", style="yellow"))
                _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)
                raise typer.Exit(code=2)
        else:
            step_results.append(("Health", "pass"))
            if clear_failure_sentinel():
                console.print("[green]Cleared logs/HEALTH_FAILURE.flag — health is back to green.[/]")
    else:
        step_results.append(("Health", "skip"))

    # 2. Sync Transactions & Positions (Writes to Sheets)
    if not skip_transactions:
        console.print("\n[bold cyan]STEP 1 - Syncing Schwab Transactions & Positions...[/]")
        try:
            from tasks.sync_transactions import sync_transactions
            success = sync_transactions(days=tx_days, live=live)
            if success:
                tx_ok = True
                step_results.append(("Transactions", "pass"))
            else:
                step_results.append(("Transactions", "warn"))
        except Exception as e:
            console.print(f"[yellow]Transaction sync failed: {e}[/]")
            step_results.append(("Transactions", "fail"))
    else:
        step_results.append(("Transactions", "skip"))

    # 3. Live Update (Fetches fresh prices and writes to Sheets if live)
    console.print("\n[bold cyan]STEP 2 - Updating Portfolio State...[/]")
    try:
        live_up.update_portfolio(tx_days=tx_days, dry_run=not live)
        step_results.append(("Live Update", "pass"))
    except Exception as e:
        console.print(f"[red]Portfolio update failed: {e}[/]")
        step_results.append(("Live Update", "fail"))

    # 4. Snapshot (Freeze Sheets state to Bundle)
    console.print("\n[bold cyan]STEP 3 - Freezing Context Bundle...[/]")
    try:
        bundle = build_bundle(source="auto", cash_manual=0.0)
        path = write_bundle(bundle)
        console.print(f"[green]Snapshot frozen:[/] {path.name} ({bundle.bundle_hash[:8]})")
        snapshot_ok = True
        step_results.append(("Snapshot", "pass"))
    except Exception as e:
        console.print(f"[red]Snapshot failed: {e}[/]")
        step_results.append(("Snapshot", "fail"))

    # 5. Batch Podcast Sync (non-fatal; always continues regardless of result or --strict)
    #    batch_podcast_sync.main() uses argparse so we can't call it in-process cleanly;
    #    we shell out via subprocess — the same decoupled pattern the batch script uses
    #    when it shells out to weekly_podcast_sync.py.
    if not skip_podcasts:
        console.print("\n[bold cyan]STEP 4 - Batch Podcast Sync...[/]")
        try:
            script_path = Path(__file__).parent / "tasks" / "batch_podcast_sync.py"
            cmd = [sys.executable, str(script_path)]
            if live:
                cmd.append("--live")
            # 600s, not 180s: each new episode found costs a transcript
            # download + a Gemini call over the full transcript, sequentially,
            # on top of up to 10 RSS checks -- a morning with several new
            # episodes queued across channels routinely exceeded 180s.
            pod_result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            # Logger writes to stderr; parse summary lines from there
            output = pod_result.stderr
            n_processed = 0
            n_failed = 0
            pm = re.search(r"Processed: \[(.+?)\]", output)
            if pm:
                n_processed = len([x for x in pm.group(1).split(",") if x.strip()])
            fm = re.search(r"Failed: \[(.+?)\]", output)
            if fm:
                n_failed = len([x for x in fm.group(1).split(",") if x.strip()])

            for line in output.strip().splitlines()[-6:]:
                if line.strip():
                    console.print(f"  [dim]{line}[/dim]")

            label = f"Podcasts ({n_processed} new)" if n_processed else "Podcasts"
            if n_failed > 0:
                console.print(f"  [yellow]! {n_failed} channel(s) failed to fetch[/]")
                step_results.append((label, "warn"))
            else:
                step_results.append((label, "pass"))
        except Exception as e:
            console.print(f"[yellow]Podcast sync error: {e}[/]")
            step_results.append(("Podcasts", "warn"))
    else:
        step_results.append(("Podcasts", "skip"))

    # 5b. Spotify Studio Digest Ingestion (non-fatal; folder may not exist on this machine)
    if not skip_podcasts:
        console.print("\n[bold cyan]STEP 4b - Spotify Digests...[/]")
        try:
            from tasks.ingest_spotify_digests import main as ingest_spotify_digests
            spotify_result = ingest_spotify_digests(live=live)
            n_new = len(spotify_result["ingested"])
            label = f"Spotify Digests ({n_new} new)"
            if spotify_result.get("warn"):
                step_results.append((label, "warn"))
            elif spotify_result["failed"]:
                step_results.append((label, "warn"))
            else:
                step_results.append((label, "pass"))
        except Exception as e:
            console.print(f"[yellow]Spotify digest ingestion error: {e}[/]")
            step_results.append(("Spotify Digests", "warn"))
    else:
        step_results.append(("Spotify Digests", "skip"))

    # 5c. Extract High-Signal Moments (cached, position-independent; skips
    #     transcripts already processed, so a normal morning only pays for
    #     the 2-5 new episodes from STEP 4 above). Non-fatal: one bad
    #     transcript must not break the rest of the pipeline.
    if not skip_podcasts:
        console.print("\n[bold cyan]STEP 4c - Extracting High-Signal Moments...[/]")
        try:
            from tasks.extract_moments import run_extract_moments
            moments_result = run_extract_moments()
            n_new = len(moments_result["processed"])
            n_failed = len(moments_result["failed"])
            label = f"Moments ({n_new} new transcript(s))"
            if n_failed > 0:
                console.print(f"  [yellow]! {n_failed} transcript(s) failed extraction[/]")
                step_results.append((label, "warn"))
            else:
                step_results.append((label, "pass"))
        except Exception as e:
            console.print(f"[yellow]Moment extraction error: {e}[/]")
            step_results.append(("Moments", "warn"))
    else:
        step_results.append(("Moments", "skip"))

    # 4.5 Dislocation Scan — must run before STEP 5 so Crosshairs sees today's payload
    # (0_DASHBOARD is clear-and-rebuild; a late scan cannot be patched in).
    dislocation_payload = None
    dislocation_path = None
    if not skip_dislocation:
        console.print("\n[bold cyan]STEP 4.5 - Dislocation Scan...[/]")
        try:
            from tasks.dislocation_scan import run_scan
            scan_result = run_scan(live=live)
            dislocation_payload = scan_result["payload"]
            dislocation_path = scan_result["json_path"]
            console.print(
                f"[green]Dislocation scan:[/] {dislocation_payload['universe_size']} tickers, "
                f"{dislocation_payload['flagged_count']} flagged. {scan_result['md_path']}"
            )
            step_results.append(("Dislocation Scan", "pass"))
        except Exception as e:
            console.print(f"[red]Dislocation scan failed: {e}[/]")
            step_results.append(("Dislocation Scan", "fail"))
    else:
        step_results.append(("Dislocation Scan", "skip"))

    # 5. Refresh Dashboard (Valuation_Card → Crosshairs → CC / Decision_View)
    console.print("\n[bold cyan]STEP 5 - Refreshing Dashboard...[/]")
    try:
        build_val(live=live, include_all=True)
        if not skip_risk_metrics:
            try:
                from tasks.build_risk_metrics import main as build_risk
                build_risk(live=live)
            except Exception as e:
                console.print(f"[yellow]Risk_Metrics rebuild failed (non-fatal): {e}[/]")
        crosshairs = produce_crosshairs(
            dislocation_payload=dislocation_payload,
            dislocation_path=dislocation_path,
        )
        build_cc(live=live, crosshairs=crosshairs)
        build_dec(live=live, crosshairs=crosshairs)
        # Evidence capture after Decision_View so the list matches what Bill saw.
        try:
            from core.store.evidence import format_evidence_status, run_evidence_capture

            ev = run_evidence_capture(live=live, crosshairs=crosshairs)
            if ev.get("skipped"):
                console.print(f"[yellow]{ev.get('skip_reason')}[/]")
            else:
                mode = "LIVE" if live else "DRY RUN"
                console.print(f"[dim]Evidence capture ({mode}): {ev.get('results')}[/]")
                console.print(format_evidence_status(ev.get("status")))
            # Pre-commitment sheet ingest (append-and-mark) before firing detection.
            try:
                from tasks.ingest_precommitments import ingest_precommitments_from_sheet

                ing = ingest_precommitments_from_sheet(live=live)
                mode = "LIVE" if live else "DRY RUN"
                console.print(
                    f"[dim]Precommit ingest ({mode}): ingested={ing.get('ingested')} "
                    f"skipped={ing.get('skipped')}[/]"
                )
                for flag in ing.get("flags") or []:
                    console.print(f"[yellow]Precommit band flag: {flag}[/]")
                for err in ing.get("errors") or []:
                    console.print(f"[yellow]Precommit ingest: {err}[/]")
            except Exception as e:
                console.print(f"[yellow]Precommit ingest failed (non-fatal): {e}[/]")
            # Pre-commitment firings read signal_events — must run after evidence capture.
            try:
                from core.journal import precommit as pc

                fire_summary = pc.detect_firings(live=live)
                n_pending = pc.pending_count()
                mode = "LIVE" if live else "DRY RUN"
                console.print(
                    f"[dim]Precommit detect ({mode}): {fire_summary} | "
                    f"pending firings: {n_pending}[/]"
                )
                if n_pending:
                    console.print(
                        f"[bold yellow]{n_pending} precommitment firing(s) awaiting response "
                        f"— pm journal precommit --pending[/]"
                    )
            except Exception as e:
                console.print(f"[yellow]Precommit detect failed (non-fatal): {e}[/]")
            # Bounded lifecycle refresh: yesterday's fill tickers only.
            try:
                from core.judgment.increment import recompute_campaigns_for_yesterday

                inc = recompute_campaigns_for_yesterday(live=live)
                if inc.get("tickers"):
                    console.print(
                        f"[dim]Lifecycle increment ({'LIVE' if live else 'DRY RUN'}): "
                        f"recomputed {inc['tickers']} (fills on {inc.get('date')})[/]"
                    )
            except Exception as e:
                console.print(f"[yellow]Lifecycle increment failed (non-fatal): {e}[/]")
        except Exception as e:
            console.print(f"[yellow]Evidence capture failed (non-fatal): {e}[/]")
        if not skip_tax:
            refresh_tax_control_sheet(live=live)
            tax_refreshed = True
        format_v2(live=live)
        step_results.append(("Dashboard", "pass"))
    except Exception as e:
        console.print(f"[red]Dashboard refresh failed: {e}[/]")
        step_results.append(("Dashboard", "fail"))

    # 7. Vault Sync (sync Sheets data back to local thesis files)
    if not skip_vault_sync:
        console.print("\n[bold cyan]STEP 6 - Syncing Sheets to Local Thesis Files...[/]")
        try:
            from core.thesis_sync_data import gather_thesis_sync_data
            from tasks.write_thesis_updates import write_thesis_updates
            
            result = gather_thesis_sync_data()
            parse_errors = result.parse_errors or []
            payloads = result.payloads
            if parse_errors:
                for err in parse_errors:
                    console.print(
                        f"[yellow]Thesis frontmatter unparseable: "
                        f"{err.get('ticker')}: {err.get('error')}[/]"
                    )
            if payloads:
                report = write_thesis_updates(payloads=payloads, dry_run=not live, force_recreate_regions=False, show_diff=False)
                if parse_errors or report.get('errors', 0) > 0:
                    console.print(
                        f"[yellow]Vault sync completed with warnings "
                        f"(parse_errors={len(parse_errors)}, write_errors={report.get('errors', 0)}). "
                        f"Updated {report['updated']} file(s).[/]"
                    )
                    step_results.append(("Vault Sync", "warn"))
                else:
                    console.print(f"[green]Vault sync completed successfully. Updated {report['updated']} file(s).[/]")
                    step_results.append(("Vault Sync", "pass"))
            else:
                if parse_errors:
                    console.print("[yellow]No vault sync payloads — frontmatter parse errors only.[/]")
                    step_results.append(("Vault Sync", "warn"))
                else:
                    console.print("[yellow]No vault sync data found.[/]")
                    step_results.append(("Vault Sync", "pass"))
        except Exception as e:
            console.print(f"[red]Vault sync failed: {e}[/]")
            step_results.append(("Vault Sync", "fail"))
    else:
        step_results.append(("Vault Sync", "skip"))

    # 8. Vault Snapshot (rebuild local vault bundle)
    if not skip_composite:
        console.print("\n[bold cyan]STEP 7 - Freezing Vault Snapshot...[/]")
        try:
            tickers = None
            try:
                if 'bundle' in locals() and bundle:
                    tickers = [p["ticker"] for p in bundle.positions if not p.get("is_cash")]
                else:
                    market_bundles = sorted(list(Path("bundles").glob("context_bundle_*.json")), key=lambda p: p.stat().st_mtime)
                    if market_bundles:
                        market_data = load_bundle(market_bundles[-1])
                        tickers = [p["ticker"] for p in market_data["positions"] if not p.get("is_cash")]
            except Exception as e:
                console.print(f"[dim]Failed to resolve tickers for vault snapshot: {e}[/dim]")

            vault_bundle = build_vault_bundle(ticker_list=tickers, include_drive=False)
            vault_path = write_vault_bundle(vault_bundle)
            console.print(f"[green]Vault snapshot frozen:[/] {vault_path.name} ({vault_bundle.vault_hash[:8]})")
            step_results.append(("Vault Snapshot", "pass"))
        except Exception as e:
            console.print(f"[red]Vault snapshot failed: {e}[/]")
            step_results.append(("Vault Snapshot", "fail"))
    else:
        step_results.append(("Vault Snapshot", "skip"))

    # 9. Build Composite Bundle
    if not skip_composite:
        console.print("\n[bold cyan]STEP 8 - Building Composite Bundle...[/]")
        try:
            market_path = None
            if 'path' in locals() and path:
                market_path = path
            
            vault_path_resolved = None
            if 'vault_path' in locals() and vault_path:
                vault_path_resolved = vault_path
            else:
                vault_bundles = sorted(list(Path("bundles").glob("vault_bundle_*.json")), key=lambda p: p.stat().st_mtime)
                if vault_bundles:
                    vault_path_resolved = vault_bundles[-1]

            if not market_path or not vault_path_resolved:
                market_path, vault_path_resolved = resolve_latest_bundles()

            composite = build_composite_bundle(market_path, vault_path_resolved)
            comp_path = write_composite_bundle(composite)
            console.print(f"[green]Composite bundle built:[/] {comp_path.name} ({composite.composite_hash[:8]})")
            step_results.append(("Composite Bundle", "pass"))
        except Exception as e:
            console.print(f"[red]Composite bundle failed: {e}[/]")
            step_results.append(("Composite Bundle", "fail"))
    else:
        step_results.append(("Composite Bundle", "skip"))

    # 10. Export AI Briefing Package
    # Morning already does every piece of work the briefing needs; it used to stop
    # one step short and leave the user to run make_ai_briefing.bat by hand. This
    # turns the composite bundle built above into the uploadable package.
    if not skip_export:
        console.print("\n[bold cyan]STEP 9 - Exporting AI Briefing Package...[/]")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "tasks/export_ai_briefing.py",
                    "--lookthrough", "refresh",
                    "--no-open",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            out = (result.stdout or "") + (result.stderr or "")

            # Surface the preflight block - it names vault problems (theses for
            # positions no longer held, missing scaling sections) that the export
            # works around but the user should still see.
            if "--- Preflight ---" in out:
                for line in out.splitlines():
                    if line.strip().startswith(("SKIPPED", "BLOCKING", "SYSTEM")) or "thesis files have no" in line:
                        console.print(f"  [yellow]{line.strip()}[/]")

            pkg_line = next(
                (l for l in out.splitlines() if l.startswith("Package: ")), None
            )
            if result.returncode == 0 and pkg_line:
                console.print(f"[green]Briefing package:[/] {pkg_line.replace('Package: ', '')}")
                console.print("[dim]Upload SUBMIT_ME.md from that folder.[/]")
                step_results.append(("AI Briefing", "pass"))
            elif result.returncode != 0:
                # Surface the real failure — otherwise ModuleNotFoundError etc.
                # look identical to a preflight ABORT (warn, no traceback).
                err_tail = "\n".join(
                    [l for l in out.splitlines() if l.strip()][-12:]
                )
                if err_tail:
                    console.print(f"[yellow]{err_tail}[/]")
                console.print("[yellow]Export halted (non-zero exit).[/]")
                console.print("[dim]Override: python tasks\\export_ai_briefing.py --lookthrough refresh --force[/]")
                step_results.append(("AI Briefing", "warn"))
            else:
                console.print("[yellow]Export finished but no package path was reported.[/]")
                step_results.append(("AI Briefing", "warn"))
        except subprocess.TimeoutExpired:
            console.print("[yellow]Export timed out after 5 minutes (ETF holdings fetch may be slow).[/]")
            step_results.append(("AI Briefing", "warn"))
        except Exception as e:
            console.print(f"[red]Briefing export failed: {e}[/]")
            step_results.append(("AI Briefing", "fail"))
    else:
        step_results.append(("AI Briefing", "skip"))

    # 11. Derive Rotations (Writes Trade_Log_Staging if live)
    console.print("\n[bold cyan]STEP 10 - Deriving Candidate Rotations...[/]")
    try:
        from tasks.derive_rotations import _read_transactions, derive_clusters, write_staging
        # Look back 90 days (default lookback)
        lookback_since = date.today() - timedelta(days=90)
        df_rot = _read_transactions(since=lookback_since, until=date.today())
        if df_rot.empty:
            console.print("[yellow]No transactions found in lookback window.[/]")
            step_results.append(("Derive Rotations", "pass"))
        else:
            clusters = derive_clusters(df_rot, window_days=1)
            if not clusters:
                console.print("[yellow]No candidate rotations derived.[/]")
                step_results.append(("Derive Rotations", "pass"))
            else:
                n_written = write_staging(clusters, dry_run=not live, dry_run_verify=False)
                if live:
                    console.print(f"[green]Successfully derived {len(clusters)} candidate rotations. Wrote {n_written} new rows to Trade_Log_Staging.[/]")
                else:
                    console.print(f"[yellow]DRY RUN: Derived {len(clusters)} candidate rotations. Run with --live to write to Trade_Log_Staging.[/]")
                step_results.append(("Derive Rotations", "pass"))
    except Exception as e:
        console.print(f"[red]Derive rotations failed: {e}[/]")
        step_results.append(("Derive Rotations", "fail"))

    # Dislocation already ran at STEP 4.5 (before dashboard/Crosshairs). Do not re-scan.

    # 12. Publish analysis outputs to Drive (non-fatal; Drive letter may not
    # exist on some future machine -- degrades to warn, never aborts).
    console.print("\n[bold cyan]STEP 11 - Publishing Analysis to Drive...[/]")
    try:
        from scripts.backup_to_drive import publish_analysis
        publish_result = publish_analysis(live=live)
        if publish_result["warn"]:
            console.print(f"[yellow]{publish_result['warn']}[/]")
            step_results.append(("Publish Analysis", "warn"))
        else:
            n_copied = len(publish_result["copied"])
            console.print(f"[green]Publish analysis:[/] {n_copied} file(s) copied, "
                           f"{len(publish_result['skipped'])} unchanged.")
            step_results.append((f"Publish Analysis ({n_copied} copied)", "pass"))
    except Exception as e:
        console.print(f"[yellow]Publish analysis error: {e}[/]")
        step_results.append(("Publish Analysis", "warn"))

    _morning_summary(console, mode_label, step_results, tx_ok, snapshot_ok, tax_refreshed, skip_tax, start_time)

    # Exit with code based on worst step
    worst = "pass"
    for _, status in step_results:
        if status == "fail": worst = "fail"
        elif status == "warn" and worst != "fail": worst = "warn"
    
    if worst == "fail": raise typer.Exit(code=1)
    if worst == "warn": raise typer.Exit(code=2)
    raise typer.Exit(code=0)


@app.command("dislocation-scan")
def dislocation_scan(
    live: bool = typer.Option(False, "--live", help="Reserved for future Sheet-write promotion; currently a no-op."),
    losers_limit: int = typer.Option(50, "--losers-limit", help="Max FMP biggest-losers candidates to evaluate before the market-cap floor."),
):
    """
    Facts-only daily screen for the quality-franchise / double-digit-selloff /
    cheap-forward-multiple pattern across current holdings, data/watchlist.json,
    and FMP's biggest-losers list. No price targets, no buy/sell language.
    """
    from tasks.dislocation_scan import run_scan
    result = run_scan(losers_limit=losers_limit, live=live)
    payload = result["payload"]
    console.print(f"[green]Universe:[/] {payload['universe_size']} tickers, {payload['flagged_count']} flagged.")
    console.print(f"  JSON: {result['json_path']}")
    console.print(f"  Markdown: {result['md_path']}")


@publish_app.command("analysis")
def publish_analysis_cmd(
    live: bool = typer.Option(False, "--live", help="Actually copy files. Default: DRY RUN."),
):
    """
    One-way, newest-wins copy of agent_outputs/{ai_briefing_analysis,ideas,
    dislocation_scan}/*.md to a Drive-synced folder (default G:\\My Drive\\
    Portfolio_Analysis, override with PORTFOLIO_ANALYSIS_DRIVE_DIR). Never
    deletes at the destination; skips files with an identical SHA-256.
    """
    from scripts.backup_to_drive import publish_analysis
    result = publish_analysis(live=live)
    if result["warn"]:
        console.print(f"[yellow]WARN: {result['warn']}[/]")
        raise typer.Exit(code=0)
    mode = "LIVE" if live else "DRY RUN"
    console.print(
        f"[green][{mode}][/] considered {len(result['considered'])}, "
        f"copied {len(result['copied'])}, skipped {len(result['skipped'])} (identical hash)."
    )
    for name in result["copied"]:
        console.print(f"  copied: {name}")


@app.command("extract-moments")
def extract_moments(
    force: Optional[str] = typer.Option(None, "--force", help="Transcript filename or stem to force re-extraction of."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max number of NEW transcripts to process this run."),
):
    """
    Cached high-signal moment extraction (reversal / non_consensus /
    position_disclosure / specific_claim / disagreement) over podcast
    transcripts. Position-independent and idempotent -- skips any
    transcript with an existing data/moments/*.moments.json cache file.
    Relevance tagging happens later, at export time, never here.
    """
    from tasks.extract_moments import run_extract_moments
    result = run_extract_moments(force=force, limit=limit)
    console.print(
        f"[green]Moments:[/] processed {len(result['processed'])}, "
        f"skipped {len(result['skipped'])} (cached), "
        f"failed {len(result['failed'])}, "
        f"{result['total_candidates']} candidate(s) written."
    )
    if result["failed"]:
        console.print(f"[yellow]Failed: {', '.join(result['failed'])}[/]")


@probe_app.command("price-history")
def probe_price_history(
    ticker: str = typer.Argument(..., help="Ticker symbol"),
    days: int = typer.Option(365, "--days"),
    interval: str = typer.Option("daily", "--interval"),
    no_cache: bool = typer.Option(False, "--no-cache"),
):
    """Fetch Schwab OHLCV bars and print head/tail. Read-only."""
    from utils.schwab_client import get_market_client, fetch_price_history

    client = get_market_client()
    if client is None:
        console.print("[red]Market client unavailable[/]")
        raise typer.Exit(1)
    df = fetch_price_history(
        client, ticker, period_days=days, interval=interval, use_cache=not no_cache
    )
    if df.empty:
        console.print("[yellow]Empty frame[/]")
        raise typer.Exit(1)
    console.print(f"rows={len(df)} min={df.index.min()} max={df.index.max()} tz={df.index.tz}")
    console.print(df.head(3).to_string())
    console.print("...")
    console.print(df.tail(3).to_string())


@probe_app.command("fundamentals")
def probe_fundamentals(
    tickers: list[str] = typer.Argument(..., help="One or more tickers"),
):
    """Dump Schwab instrument fundamentals. Writes raw JSON under agent_outputs/schwab_probe/."""
    import json
    from pathlib import Path
    from utils.schwab_client import get_market_client, fetch_instrument_fundamentals

    client = get_market_client()
    if client is None:
        console.print("[red]Market client unavailable[/]")
        raise typer.Exit(1)

    # Raw dump for three (or whatever was passed)
    out_dir = Path("agent_outputs/schwab_probe")
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "fundamentals_raw_2026-08-25.json"
    try:
        r = client.get_instruments(
            [t.upper() for t in tickers],
            client.Instrument.Projection.FUNDAMENTAL,
        )
        r.raise_for_status()
        raw = r.json()
        raw_path.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
        console.print(f"Raw dump → {raw_path}")
    except Exception as e:
        console.print(f"[yellow]Raw dump failed: {e}[/]")

    df = fetch_instrument_fundamentals(client, tickers)
    if df.empty:
        console.print("[yellow]Empty fundamentals frame[/]")
        raise typer.Exit(1)
    for _, row in df.iterrows():
        console.print(f"\n=== {row['ticker']} keys ===")
        console.print(row.get("_raw_fundamental_keys"))
        console.print(row.drop(labels=["_raw_fundamental_keys"], errors="ignore").to_string())


@probe_app.command("market-hours")
def probe_market_hours(
    date: Optional[str] = typer.Option(None, "--date", help="YYYY-MM-DD"),
):
    """Print is_trading_day and raw market hours for a date."""
    from datetime import date as date_cls
    from utils.schwab_client import get_market_client, fetch_market_hours, is_trading_day

    client = get_market_client()
    if client is None:
        console.print("[red]Market client unavailable[/]")
        raise typer.Exit(1)
    d = date_cls.fromisoformat(date) if date else None
    payload = fetch_market_hours(client, date_=d)
    open_flag = is_trading_day(client, date_=d)
    console.print(f"is_trading_day={open_flag!r}")
    console.print(payload)


@probe_app.command("reconcile")
def probe_reconcile():
    """Run scripts/reconcile_price_history_2026-08-25.py (Schwab vs yfinance)."""
    import runpy
    from pathlib import Path

    script = Path("scripts/reconcile_price_history_2026-08-25.py")
    if not script.exists():
        console.print(f"[red]Missing {script}[/]")
        raise typer.Exit(1)
    runpy.run_path(str(script), run_name="__main__")


@probe_app.command("price-source-stats")
def probe_price_source_stats():
    """Show auto-fallback counter from utils.price_history."""
    from utils.price_history import fallback_stats
    stats = fallback_stats()
    console.print(stats)


@app.command("login")
def login():
    """
    Run the Schwab OAuth manual reauthentication script to update credentials.
    """
    from scripts.schwab_manual_reauth import run_reauth
    run_reauth()


@app.command("backup")
def backup(
    name: Optional[str] = typer.Option(None, help="Name of the zip file in Drive."),
    folder_id: Optional[str] = typer.Option(None, help="ID of the Drive folder to upload to.")
):
    """
    Archive the project (excluding credentials/venv/caches) and upload to Google Drive.
    """
    from scripts.backup_to_drive import backup as run_backup
    run_backup(name=name, folder_id=folder_id)


# --- AGENT GROUP ---

@agent_app.command("ideas")
def agent_ideas(
    since_days: int = typer.Option(7, "--since-days", help="Look back N days for transcripts."),
    bundle_path: Optional[Path] = typer.Option(None, "--bundle-path", help="Path to composite bundle. Auto-detects latest if omitted."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print report to stdout instead of writing to disk."),
    skip_ingest: bool = typer.Option(False, "--skip-ingest", help="Skip podcast ingestion and use transcripts already on disk."),
):
    """
    Generate investment candidates from recent podcast transcripts.

    Fetches new podcast transcripts first, then runs the idea generator.
    Consumes the composite bundle + data/podcast_transcripts/ and writes a markdown
    report to agent_outputs/ideas/. Use --dry-run to print to stdout.
    """
    import logging as _logging
    import time as _time
    from utils.agents.idea_generator import run_idea_generator, write_idea_report

    if not _logging.getLogger().handlers:
        _logging.basicConfig(
            level=_logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )

    if not skip_ingest:
        console.print("[bold cyan]Step 1/2 — Ingesting new podcast transcripts...[/]")
        try:
            podcast_batch(analyze=False, live=True)
        except Exception as e:
            console.print(f"[yellow]Podcast ingestion failed: {e} — continuing with existing transcripts.[/]")
        console.print()

    console.print("[bold cyan]Step 2/2 — Running idea generator...[/]" if not skip_ingest else "[bold cyan]Running idea generator...[/]")

    bundle_path_str = str(bundle_path) if bundle_path else None

    with console.status("[cyan]Running idea generator..."):
        t0 = _time.time()
        try:
            output = run_idea_generator(
                composite_bundle_path=bundle_path_str,
                since_days=since_days,
            )
        except FileNotFoundError as e:
            console.print(f"[red]ERROR: {e}[/]")
            raise typer.Exit(code=1)
        elapsed = _time.time() - t0

    if dry_run:
        report_text = write_idea_report(output, dry_run=True)
        console.print(report_text)
        console.print(f"\n[dim]Generated in {elapsed:.1f}s | {len(output.candidates)} candidate(s) | {len(output.transcripts_analyzed)} transcript(s)[/]")
        return

    report_path = write_idea_report(output)
    console.print(f"\n[bold green]Report written:[/] {report_path}")
    console.print(
        f"[cyan]{len(output.candidates)} candidate(s)[/] across "
        f"[cyan]{len(output.transcripts_analyzed)} transcript(s)[/] "
        f"in {elapsed:.1f}s"
    )
    if output.notes:
        console.print(f"[dim]Notes: {output.notes[:120]}{'...' if len(output.notes) > 120 else ''}[/]")


@agent_app.command("valuation-drift")
def agent_valuation_drift(
    ticker: Optional[str] = typer.Option(None, "--ticker", help="Limit to one ticker."),
    bundle_path: Optional[Path] = typer.Option(
        None, "--bundle-path", help="Composite bundle path. Latest if omitted."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print report; do not write."),
):
    """Fundamentals drift vs Option A baseline. Local markdown only; no Sheets writes."""
    from utils.agents.valuation_drift import run_valuation_drift, write_drift_report

    with console.status("[cyan]Running valuation drift..."):
        try:
            output = run_valuation_drift(
                composite_bundle_path=str(bundle_path) if bundle_path else None,
                ticker=ticker,
                dry_run=dry_run,
            )
        except FileNotFoundError as e:
            console.print(f"[red]ERROR: {e}[/]")
            raise typer.Exit(code=1)

    if dry_run:
        console.print(write_drift_report(output, dry_run=True))
        return
    path = write_drift_report(output)
    console.print(f"[bold green]Report written:[/] {path}")
    console.print(f"positions={len(output.positions)} bundle_hash={output.bundle_hash[:12]}…")


if __name__ == "__main__":
    app()
