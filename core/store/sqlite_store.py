"""SQLite-backed PortfolioStore — local ledger for shadow dual-write and reads."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Type

import pandas as pd
from sqlalchemy import delete, select

import config
from core.store.column_normalize import normalize_dataframe_columns
from core.store.models import (
    DecisionViewRow,
    HoldingsCurrentRow,
    MetaKV,
    PipelineRun,
    RealizedGLRow,
    RotationReviewRow,
    TaxControlLotRow,
    TradeLogRow,
    TradeLogStagingRow,
    TransactionRow,
    get_session,
)
from core.store.protocol import StoreSnapshot
from core.store.serialize import (
    coerce_count,
    coerce_mv,
    df_to_payloads,
    metrics_from_json,
    metrics_to_json,
    payloads_to_df,
)

logger = logging.getLogger(__name__)

_META_TAX_METRICS = "tax_control_metrics"
_META_DECISION_HEADER = "decision_view_header"


class SqlitePortfolioStore:
    name = "sqlite"

    def status(self) -> StoreSnapshot:
        holdings = self.get_holdings_current()
        return StoreSnapshot(
            backend=self.name,
            position_count=coerce_count(holdings),
            total_market_value=coerce_mv(holdings),
            transaction_count=coerce_count(self.get_transactions()),
            trade_log_count=coerce_count(self.get_trade_log()),
            realized_gl_count=coerce_count(self.get_realized_gl()),
            tax_control_lot_count=coerce_count(self.get_tax_control_lots()),
            rotation_review_count=coerce_count(self.get_rotation_review()),
        )

    def _load_table(
        self, model: Type, canonical_columns: Optional[list[str]] = None
    ) -> pd.DataFrame:
        with get_session() as session:
            rows = session.scalars(select(model)).all()
            payloads = [r.payload_json for r in rows]
        df = payloads_to_df(payloads)
        if canonical_columns is not None:
            df = normalize_dataframe_columns(df, canonical_columns)
        return df

    def _replace_table(self, model: Type, df: pd.DataFrame, *, live: bool) -> None:
        if not live:
            return
        payloads = df_to_payloads(df)
        with get_session() as session:
            session.execute(delete(model))
            for p in payloads:
                kwargs: dict[str, Any] = {"payload_json": p}
                if model is HoldingsCurrentRow:
                    try:
                        rec = json.loads(p)
                        kwargs["ticker"] = str(
                            rec.get("Ticker") or rec.get("ticker") or ""
                        )
                    except json.JSONDecodeError:
                        kwargs["ticker"] = ""
                elif model is TransactionRow:
                    try:
                        rec = json.loads(p)
                        kwargs["fingerprint"] = rec.get("fingerprint") or rec.get(
                            "Fingerprint"
                        )
                    except json.JSONDecodeError:
                        pass
                session.add(model(**kwargs))
            session.commit()
        logger.info("sqlite replaced %s with %d rows", model.__tablename__, len(payloads))

    def get_holdings_current(self) -> pd.DataFrame:
        return self._load_table(HoldingsCurrentRow, config.POSITION_COLUMNS)

    def get_transactions(self) -> pd.DataFrame:
        return self._load_table(TransactionRow, config.TRANSACTION_COLUMNS)

    def get_trade_log(self) -> pd.DataFrame:
        return self._load_table(TradeLogRow, config.TRADE_LOG_COLUMNS)

    def get_realized_gl(self) -> pd.DataFrame:
        return self._load_table(RealizedGLRow, config.GL_COLUMNS)

    def get_rotation_review(self) -> pd.DataFrame:
        return self._load_table(RotationReviewRow, config.ROTATION_REVIEW_COLUMNS)

    def get_tax_control_lots(self) -> pd.DataFrame:
        return self._load_table(TaxControlLotRow, config.TAX_CONTROL_LOTS_COLUMNS)

    def get_tax_control_metrics(self) -> dict[str, Any]:
        with get_session() as session:
            row = session.get(MetaKV, _META_TAX_METRICS)
            return metrics_from_json(row.value if row else None)

    def get_decision_view(self) -> pd.DataFrame:
        with get_session() as session:
            rows = session.scalars(
                select(DecisionViewRow).order_by(DecisionViewRow.rank)
            ).all()
            payloads = [r.payload_json for r in rows]
        return payloads_to_df(payloads)

    def get_crosshairs_items(self) -> list[dict[str, Any]]:
        df = self.get_decision_view()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def replace_holdings_current(self, df: pd.DataFrame, *, live: bool) -> None:
        self._replace_table(HoldingsCurrentRow, df, live=live)

    def replace_transactions(self, df: pd.DataFrame, *, live: bool) -> None:
        self._replace_table(TransactionRow, df, live=live)

    def replace_trade_log(self, df: pd.DataFrame, *, live: bool) -> None:
        self._replace_table(TradeLogRow, df, live=live)

    def replace_trade_log_staging(self, df: pd.DataFrame, *, live: bool) -> None:
        self._replace_table(TradeLogStagingRow, df, live=live)

    def replace_realized_gl(self, df: pd.DataFrame, *, live: bool) -> None:
        self._replace_table(RealizedGLRow, df, live=live)

    def replace_rotation_review(self, df: pd.DataFrame, *, live: bool) -> None:
        self._replace_table(RotationReviewRow, df, live=live)

    def replace_tax_control(
        self,
        metrics: dict[str, Any],
        lots_df: pd.DataFrame,
        *,
        live: bool,
    ) -> None:
        if not live:
            return
        with get_session() as session:
            session.merge(
                MetaKV(key=_META_TAX_METRICS, value=metrics_to_json(metrics))
            )
            session.execute(delete(TaxControlLotRow))
            for p in df_to_payloads(lots_df):
                session.add(TaxControlLotRow(payload_json=p))
            session.commit()
        logger.info("sqlite tax_control metrics + %d lots", len(lots_df))

    def replace_decision_view(
        self,
        header: str,
        rows: list[dict[str, Any]],
        *,
        live: bool,
    ) -> None:
        if not live:
            return
        with get_session() as session:
            session.merge(MetaKV(key=_META_DECISION_HEADER, value=header or ""))
            session.execute(delete(DecisionViewRow))
            for i, row in enumerate(rows):
                session.add(
                    DecisionViewRow(
                        rank=i,
                        payload_json=json.dumps(row, default=str),
                    )
                )
            session.commit()

    def decision_header(self) -> str:
        with get_session() as session:
            row = session.get(MetaKV, _META_DECISION_HEADER)
            return (row.value if row else "") or ""

    def get_decision_header(self) -> str:
        return self.decision_header()

    def record_pipeline_run(
        self,
        command: str,
        *,
        live: bool,
        ok: bool,
        detail: Optional[str] = None,
    ) -> None:
        with get_session() as session:
            session.add(
                PipelineRun(command=command, live=live, ok=ok, detail=detail)
            )
            session.commit()
