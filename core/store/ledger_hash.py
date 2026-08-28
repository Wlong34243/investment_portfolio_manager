"""Canonical ledger fingerprints for Sheets vs SQLite parity (bundle hash discipline).

Coverage (portfolio_store_ledger_v1): transactions, realized_gl,
tax_control_metrics, tax_control_lots. Does NOT include trade_log,
trade_log_staging, holdings_current, rotation_review, or decision_view.

Cell rules live in core.store.canonicalize — do not re-declare money/date lists here.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from core.store.canonicalize import (
    GL_MONEY,
    TAX_LOT_MONEY,
    TX_MONEY,
    normalize_metrics,
    normalize_records,
    sha256_canonical,
)

# Re-export names used by tests / bisect scripts
_TX_MONEY = TX_MONEY
_GL_MONEY = GL_MONEY
_TAX_LOT_MONEY = TAX_LOT_MONEY
_normalize_records = normalize_records
_normalize_metrics = normalize_metrics
_sha256_canonical = sha256_canonical


def ledger_fingerprint(
    *,
    transactions: pd.DataFrame,
    realized_gl: pd.DataFrame,
    tax_metrics: dict[str, Any] | None,
    tax_lots: pd.DataFrame,
) -> str:
    """
    Hash of the Phase-1 vertical after shared money/date/bool normalization.

    Catches Sheets-string vs SQLite-NUMERIC serialization drift before
    STORE_PRIMARY flips consumers that stamp composite_hash.
    """
    payload = {
        "schema": "portfolio_store_ledger_v1",
        "transactions": normalize_records(transactions, TX_MONEY),
        "realized_gl": normalize_records(realized_gl, GL_MONEY),
        "tax_control_metrics": normalize_metrics(tax_metrics),
        "tax_control_lots": normalize_records(tax_lots, TAX_LOT_MONEY),
    }
    return sha256_canonical(payload)
