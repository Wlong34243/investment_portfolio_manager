"""Bootstrap SQLite from Sheets — Phase 1 vertical first (txn / realized / tax)."""

from __future__ import annotations

import logging

from core.store.sheets_store import SheetsPortfolioStore
from core.store.sqlite_store import SqlitePortfolioStore

logger = logging.getLogger(__name__)


def sync_sqlite_from_sheets(*, live: bool = False, include_holdings_cache: bool = False) -> dict:
    """
    Copy ledger tabs from Sheets into SQLite.

    Phase 1 spine: transactions, realized_gl, tax_control (via refresh recomputed
    separately), trade_log optional. Holdings is opt-in cache only.
    """
    sheets = SheetsPortfolioStore()
    sqlite = SqlitePortfolioStore()
    summary: dict = {"live": live}

    tx = sheets.get_transactions()
    gl = sheets.get_realized_gl()
    tl = sheets.get_trade_log()
    rr = sheets.get_rotation_review()
    dv = sheets.get_decision_view()

    summary["transactions"] = len(tx)
    summary["realized_gl"] = len(gl)
    summary["trade_log"] = len(tl)
    summary["rotation_review"] = len(rr)
    summary["decision_view"] = len(dv)

    if include_holdings_cache:
        holdings = sheets.get_holdings_current()
        summary["holdings_cache"] = len(holdings)
    else:
        holdings = None
        summary["holdings_cache"] = "skipped (not Phase-1 ledger)"

    if not live:
        summary["dry_run"] = True
        return summary

    sqlite.replace_transactions(tx, live=True)
    sqlite.replace_realized_gl(gl, live=True)
    sqlite.replace_trade_log(tl, live=True)
    sqlite.replace_rotation_review(rr, live=True)
    if holdings is not None:
        sqlite.replace_holdings_current(holdings, live=True)
    if not dv.empty:
        rows = dv.to_dict(orient="records")
        header = sqlite.decision_header() or "Decision_View (synced from Sheets)"
        sqlite.replace_decision_view(header, rows, live=True)

    # Tax_Control multi-zone sheet is not a clean lot table — prefer live
    # refresh_tax_control which already shadows computed metrics+lots.
    summary["tax_note"] = "run pm refresh tax --live to shadow tax_control metrics/lots"

    sqlite.record_pipeline_run(
        "sync_from_sheets",
        live=True,
        ok=True,
        detail=str(summary),
    )
    summary["dry_run"] = False
    logger.info("sync_from_sheets complete: %s", summary)
    return summary
