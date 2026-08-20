"""Sheets-backed PortfolioStore — wraps existing sheet_readers / direct gspread."""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

import config
from core.store.protocol import StoreSnapshot
from core.store.serialize import coerce_count, coerce_mv

logger = logging.getLogger(__name__)


class SheetsPortfolioStore:
    name = "sheets"

    def __init__(self) -> None:
        # One Tax_Control fetch shared by get_tax_control_lots/metrics per instance.
        self._tax_control_cache: Optional[tuple[dict[str, Any], pd.DataFrame]] = None

    def status(self) -> StoreSnapshot:
        notes: list[str] = []
        try:
            holdings = self.get_holdings_current()
            tx = self.get_transactions()
            tl = self.get_trade_log()
            gl = self.get_realized_gl()
            tax = self.get_tax_control_lots()
            rr = self.get_rotation_review()
            return StoreSnapshot(
                backend=self.name,
                position_count=coerce_count(holdings),
                total_market_value=coerce_mv(holdings),
                transaction_count=coerce_count(tx),
                trade_log_count=coerce_count(tl),
                realized_gl_count=coerce_count(gl),
                tax_control_lot_count=coerce_count(tax),
                rotation_review_count=coerce_count(rr),
            )
        except Exception as e:
            notes.append(f"status failed: {e}")
            return StoreSnapshot(backend=self.name, notes=notes)

    def get_holdings_current(self) -> pd.DataFrame:
        from utils.sheet_readers import get_holdings_current

        get_holdings_current.cache_clear()
        return get_holdings_current()

    def get_transactions(self) -> pd.DataFrame:
        from utils.sheet_readers import get_transactions

        get_transactions.cache_clear()
        return get_transactions()

    def get_trade_log(self) -> pd.DataFrame:
        from utils.sheet_readers import get_trade_log

        get_trade_log.cache_clear()
        return get_trade_log()

    def get_realized_gl(self) -> pd.DataFrame:
        from utils.sheet_readers import get_realized_gl

        get_realized_gl.cache_clear()
        return get_realized_gl()

    def get_rotation_review(self) -> pd.DataFrame:
        return self._read_tab(config.TAB_ROTATION_REVIEW)

    def get_tax_control_lots(self) -> pd.DataFrame:
        _metrics, lots = self._tax_control_pair()
        return lots

    def get_tax_control_metrics(self) -> dict[str, Any]:
        metrics, _lots = self._tax_control_pair()
        return metrics

    def _tax_control_pair(self) -> tuple[dict[str, Any], pd.DataFrame]:
        if self._tax_control_cache is not None:
            return self._tax_control_cache
        pair = self._parse_tax_control()
        self._tax_control_cache = pair
        return pair

    def _parse_tax_control(self) -> tuple[dict[str, Any], pd.DataFrame]:
        """Parse multi-zone Tax_Control tab into metrics dict + lots DataFrame."""
        try:
            from utils.sheet_readers import get_gspread_client

            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            ws = ss.worksheet(config.TAB_TAX_CONTROL)
            values = ws.get_all_values()
        except Exception as e:
            logger.warning("Tax_Control parse failed: %s", e)
            return {}, pd.DataFrame()

        if not values:
            return {}, pd.DataFrame()

        metrics: dict[str, Any] = {}
        labels = config.TAX_CONTROL_KPI_LABELS
        for i, row in enumerate(values):
            # KPI label row followed by values
            if row[: len(labels)] == list(labels) and i + 1 < len(values):
                vals = values[i + 1]
                for j, lab in enumerate(labels):
                    metrics[lab] = vals[j] if j < len(vals) else ""
                break

        # Bridge gains/losses if present (optional keys used by builder)
        for row in values:
            joined = " ".join(str(c) for c in row)
            if joined.startswith("Gains:") and "Losses:" in joined:
                # row layout: Gains ST, Losses ST, Gains LT, Losses LT
                try:
                    def _parse_bridge(cell: str) -> float:
                        part = cell.split(":", 1)[-1].replace(",", "").strip()
                        return float(part) if part else 0.0

                    if len(row) >= 4:
                        metrics.setdefault("ST_Gains", _parse_bridge(row[0]))
                        metrics.setdefault("ST_Losses", _parse_bridge(row[1]))
                        metrics.setdefault("LT_Gains", _parse_bridge(row[2]))
                        metrics.setdefault("LT_Losses", _parse_bridge(row[3]))
                except ValueError:
                    pass
                break

        lots_cols = list(config.TAX_CONTROL_LOTS_COLUMNS)
        lots_df = pd.DataFrame()
        for i, row in enumerate(values):
            if row[: len(lots_cols)] == lots_cols:
                body = values[i + 1 :]
                lots_df = pd.DataFrame(body, columns=lots_cols) if body else pd.DataFrame(columns=lots_cols)
                # Drop blank ticker rows
                if not lots_df.empty and "Ticker" in lots_df.columns:
                    lots_df = lots_df[lots_df["Ticker"].astype(str).str.strip() != ""].reset_index(drop=True)
                break

        return metrics, lots_df

    def get_decision_view(self) -> pd.DataFrame:
        return self._read_tab(config.TAB_DECISION_VIEW)

    def get_decision_header(self) -> str:
        return ""

    def get_crosshairs_items(self) -> list[dict[str, Any]]:
        df = self.get_decision_view()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def _read_tab(self, tab: str) -> pd.DataFrame:
        try:
            from utils.sheet_readers import get_gspread_client, read_gsheet_robust

            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            ws = ss.worksheet(tab)
            return read_gsheet_robust(ws)
        except Exception as e:
            logger.warning("Sheets read %s failed: %s", tab, e)
            return pd.DataFrame()

    # --- Writes: Sheets path remains owned by existing builders. ---
    # These methods are no-ops for replace_* on Sheets alone when builders
    # already wrote; DualStore calls SqlitePortfolioStore for shadow copies.
    # Explicit replace_* here only used when STORE_BACKEND=sheets and a
    # caller wants a store-shaped API (Tax_Control seam).

    def replace_holdings_current(self, df: pd.DataFrame, *, live: bool) -> None:
        if not live:
            return
        logger.info("SheetsPortfolioStore.replace_holdings_current: deferred to pipeline writers")

    def replace_transactions(self, df: pd.DataFrame, *, live: bool) -> None:
        if not live:
            return
        logger.info("SheetsPortfolioStore.replace_transactions: deferred to sync_transactions")

    def replace_trade_log(self, df: pd.DataFrame, *, live: bool) -> None:
        if not live:
            return

    def replace_trade_log_staging(self, df: pd.DataFrame, *, live: bool) -> None:
        if not live:
            return

    def replace_realized_gl(self, df: pd.DataFrame, *, live: bool) -> None:
        if not live:
            return

    def replace_rotation_review(self, df: pd.DataFrame, *, live: bool) -> None:
        if not live:
            return

    def replace_tax_control(
        self,
        metrics: dict[str, Any],
        lots_df: pd.DataFrame,
        *,
        live: bool,
    ) -> None:
        """Write Tax_Control grid — same layout as build_tax_control."""
        if not live:
            return
        self._write_tax_grid(metrics, lots_df)

    def _write_tax_grid(self, metrics: dict[str, Any], lots_df: pd.DataFrame) -> None:
        from utils.sheet_readers import get_gspread_client
        from utils.sheet_writers import safe_execute

        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_TAX_CONTROL)

        lots_df_out = lots_df.copy()
        if not lots_df_out.empty and "Closed Date" in lots_df_out.columns:
            lots_df_out["Closed Date"] = pd.to_datetime(
                lots_df_out["Closed Date"], errors="coerce"
            ).dt.strftime("%Y-%m-%d").fillna("")

        table_data = lots_df_out.values.tolist() if not lots_df_out.empty else []
        all_values = (
            [["TAX CONTROL — YTD Realized Tax Posture"]]
            + [config.TAX_CONTROL_KPI_LABELS]
            + [[metrics.get(label, 0) for label in config.TAX_CONTROL_KPI_LABELS]]
            + [["Planning tool — not tax advice. Estimates based on configured rates and realized data only."]]
            + [[""]]
            + [["Short-Term Bridge (gains vs losses)", "", "Long-Term Bridge (gains vs losses)", ""]]
            + [[
                f"Gains: {metrics.get('ST_Gains', 0):,.0f}",
                f"Losses: {metrics.get('ST_Losses', 0):,.0f}",
                f"Gains: {metrics.get('LT_Gains', 0):,.0f}",
                f"Losses: {metrics.get('LT_Losses', 0):,.0f}",
            ]]
            + [[""]]
            + [["Tax-Relevant Realized Lots (YTD) — wash sales pinned on top"]]
            + [config.TAX_CONTROL_LOTS_COLUMNS]
            + table_data
        )

        import numpy as np

        def _to_python(v):
            if isinstance(v, np.integer):
                return int(v)
            if isinstance(v, np.floating):
                return float(v) if not np.isnan(v) else ""
            if isinstance(v, np.bool_):
                return bool(v)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return ""
            return v

        all_values = [[_to_python(c) for c in row] for row in all_values]
        safe_execute(ws.clear)
        safe_execute(ws.update, range_name="A1", values=all_values, value_input_option="USER_ENTERED")

    def replace_decision_view(
        self,
        header: str,
        rows: list[dict[str, Any]],
        *,
        live: bool,
    ) -> None:
        if not live:
            return
        logger.info("SheetsPortfolioStore.replace_decision_view: deferred to build_decision_view")

    def record_pipeline_run(
        self,
        command: str,
        *,
        live: bool,
        ok: bool,
        detail: Optional[str] = None,
    ) -> None:
        logger.info("pipeline_run sheets=%s live=%s ok=%s %s", command, live, ok, detail or "")
