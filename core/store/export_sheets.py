"""Re-export computed views from SQLite back to Sheets (cockpit continuity)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def export_sheets_from_store(*, live: bool = False) -> dict[str, Any]:
    """
    Push SQLite tax_control (+ decision_view if present) to Sheets.
    Holdings/Transactions remain written by their normal ingest paths.
    """
    from core.store import get_store
    from core.store.sheets_store import SheetsPortfolioStore

    store = get_store()
    # Prefer sqlite payload even when dual
    from core.store.sqlite_store import SqlitePortfolioStore

    sqlite = SqlitePortfolioStore()
    sheets = SheetsPortfolioStore()
    result: dict[str, Any] = {"live": live}

    metrics = sqlite.get_tax_control_metrics()
    lots = sqlite.get_tax_control_lots()
    result["tax_metrics"] = bool(metrics)
    result["tax_lots"] = len(lots)

    if live and metrics:
        sheets._write_tax_grid(metrics, lots)
        result["tax_control_exported"] = True
    else:
        result["tax_control_exported"] = False

    dv = sqlite.get_decision_view()
    result["decision_rows"] = len(dv)
    if live and not dv.empty:
        # Rebuild via existing builder is safer for formatting; here we only
        # note that SQLite has rows. Full Decision_View export stays in
        # build_decision_view --live.
        result["decision_export"] = "use pm refresh dashboard --live"
    return result
