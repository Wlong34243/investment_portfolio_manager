"""PortfolioStore Protocol — persistence seam for holdings, tax, rotations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

import pandas as pd


@dataclass
class StoreSnapshot:
    """Lightweight health / reconcile summary."""

    backend: str
    position_count: int = 0
    total_market_value: float = 0.0
    transaction_count: int = 0
    trade_log_count: int = 0
    realized_gl_count: int = 0
    tax_control_lot_count: int = 0
    rotation_review_count: int = 0
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class PortfolioStore(Protocol):
    """Read/write contract used by pipeline builders and vault sync."""

    name: str

    def status(self) -> StoreSnapshot:
        ...

    def get_holdings_current(self) -> pd.DataFrame:
        ...

    def get_transactions(self) -> pd.DataFrame:
        ...

    def get_trade_log(self) -> pd.DataFrame:
        ...

    def get_realized_gl(self) -> pd.DataFrame:
        ...

    def get_rotation_review(self) -> pd.DataFrame:
        ...

    def get_tax_control_lots(self) -> pd.DataFrame:
        ...

    def get_tax_control_metrics(self) -> dict[str, Any]:
        ...

    def get_decision_view(self) -> pd.DataFrame:
        ...

    def get_crosshairs_items(self) -> list[dict[str, Any]]:
        ...

    def replace_holdings_current(self, df: pd.DataFrame, *, live: bool) -> None:
        ...

    def replace_transactions(self, df: pd.DataFrame, *, live: bool) -> None:
        ...

    def replace_trade_log(self, df: pd.DataFrame, *, live: bool) -> None:
        ...

    def replace_trade_log_staging(self, df: pd.DataFrame, *, live: bool) -> None:
        ...

    def replace_realized_gl(self, df: pd.DataFrame, *, live: bool) -> None:
        ...

    def replace_rotation_review(self, df: pd.DataFrame, *, live: bool) -> None:
        ...

    def replace_tax_control(
        self,
        metrics: dict[str, Any],
        lots_df: pd.DataFrame,
        *,
        live: bool,
    ) -> None:
        ...

    def replace_decision_view(
        self,
        header: str,
        rows: list[dict[str, Any]],
        *,
        live: bool,
    ) -> None:
        ...

    def record_pipeline_run(
        self,
        command: str,
        *,
        live: bool,
        ok: bool,
        detail: Optional[str] = None,
    ) -> None:
        ...
