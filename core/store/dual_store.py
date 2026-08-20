"""DualPortfolioStore — Sheets cockpit + SQLite shadow on --live writes.

Reads honor STORE_PRIMARY explicitly (default sheets). Never auto-flip.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

import config
from core.store.protocol import StoreSnapshot
from core.store.sheets_store import SheetsPortfolioStore
from core.store.sqlite_store import SqlitePortfolioStore

logger = logging.getLogger(__name__)


class DualPortfolioStore:
    name = "dual"

    def __init__(self) -> None:
        self.sheets = SheetsPortfolioStore()
        self.sqlite = SqlitePortfolioStore()

    def _reader(self) -> SheetsPortfolioStore | SqlitePortfolioStore:
        primary = (config.STORE_PRIMARY or "sheets").strip().lower()
        if primary == "sqlite":
            return self.sqlite
        if primary != "sheets":
            logger.warning("Unknown STORE_PRIMARY=%r — using sheets", primary)
        return self.sheets

    def status(self) -> StoreSnapshot:
        # Status always samples both (informational); reads use _reader().
        try:
            s = self.sheets.status()
        except Exception as e:
            s = StoreSnapshot(backend="sheets", notes=[f"sheets status failed: {e}"])
        q = self.sqlite.status()
        return StoreSnapshot(
            backend=self.name,
            position_count=s.position_count,
            total_market_value=s.total_market_value,
            transaction_count=s.transaction_count,
            trade_log_count=s.trade_log_count,
            realized_gl_count=s.realized_gl_count,
            tax_control_lot_count=s.tax_control_lot_count,
            rotation_review_count=s.rotation_review_count,
            notes=[
                f"STORE_PRIMARY={config.STORE_PRIMARY}",
                f"sheets_txns={s.transaction_count} sheets_realized={s.realized_gl_count}",
                f"sqlite_txns={q.transaction_count} sqlite_realized={q.realized_gl_count} "
                f"sqlite_tax_lots={q.tax_control_lot_count}",
            ]
            + s.notes
            + q.notes,
        )

    def get_holdings_current(self) -> pd.DataFrame:
        return self._reader().get_holdings_current()

    def get_transactions(self) -> pd.DataFrame:
        return self._reader().get_transactions()

    def get_trade_log(self) -> pd.DataFrame:
        return self._reader().get_trade_log()

    def get_realized_gl(self) -> pd.DataFrame:
        return self._reader().get_realized_gl()

    def get_rotation_review(self) -> pd.DataFrame:
        return self._reader().get_rotation_review()

    def get_tax_control_lots(self) -> pd.DataFrame:
        # Strict STORE_PRIMARY — no silent prefer-SQLite when sheets is primary.
        return self._reader().get_tax_control_lots()

    def get_tax_control_metrics(self) -> dict[str, Any]:
        return self._reader().get_tax_control_metrics()

    def get_decision_view(self) -> pd.DataFrame:
        return self._reader().get_decision_view()

    def get_decision_header(self) -> str:
        # Header lives in SQLite meta after Decision_View builds; Sheets tab has no separate header store.
        return self.sqlite.decision_header()

    def get_crosshairs_items(self) -> list[dict[str, Any]]:
        df = self.get_decision_view()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def replace_holdings_current(self, df: pd.DataFrame, *, live: bool) -> None:
        self.sheets.replace_holdings_current(df, live=live)
        self.sqlite.replace_holdings_current(df, live=live)

    def replace_transactions(self, df: pd.DataFrame, *, live: bool) -> None:
        self.sheets.replace_transactions(df, live=live)
        self.sqlite.replace_transactions(df, live=live)

    def replace_trade_log(self, df: pd.DataFrame, *, live: bool) -> None:
        self.sheets.replace_trade_log(df, live=live)
        self.sqlite.replace_trade_log(df, live=live)

    def replace_trade_log_staging(self, df: pd.DataFrame, *, live: bool) -> None:
        self.sheets.replace_trade_log_staging(df, live=live)
        self.sqlite.replace_trade_log_staging(df, live=live)

    def replace_realized_gl(self, df: pd.DataFrame, *, live: bool) -> None:
        self.sheets.replace_realized_gl(df, live=live)
        self.sqlite.replace_realized_gl(df, live=live)

    def replace_rotation_review(self, df: pd.DataFrame, *, live: bool) -> None:
        self.sheets.replace_rotation_review(df, live=live)
        self.sqlite.replace_rotation_review(df, live=live)

    def replace_tax_control(
        self,
        metrics: dict[str, Any],
        lots_df: pd.DataFrame,
        *,
        live: bool,
    ) -> None:
        self.sqlite.replace_tax_control(metrics, lots_df, live=live)

    def replace_decision_view(
        self,
        header: str,
        rows: list[dict[str, Any]],
        *,
        live: bool,
    ) -> None:
        self.sqlite.replace_decision_view(header, rows, live=live)

    def record_pipeline_run(
        self,
        command: str,
        *,
        live: bool,
        ok: bool,
        detail: Optional[str] = None,
    ) -> None:
        self.sqlite.record_pipeline_run(command, live=live, ok=ok, detail=detail)
        self.sheets.record_pipeline_run(command, live=live, ok=ok, detail=detail)
