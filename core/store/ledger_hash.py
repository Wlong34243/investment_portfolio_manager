"""Canonical ledger fingerprints for Sheets vs SQLite parity (bundle hash discipline)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from utils.sheet_readers import coerce_sheet_numeric_series


# Money / numeric columns normalized to cents before hashing so Sheets strings
# and SQLite NUMERIC serialize to the same canonical form.
_TX_MONEY = ("Net Amount", "Amount", "Fees", "Price", "Quantity")
_GL_MONEY = (
    "Proceeds",
    "Cost Basis",
    "Gain Loss $",
    "ST Gain Loss",
    "LT Gain Loss",
    "Disallowed Loss",
    "Quantity",
)
_TAX_LOT_MONEY = (
    "Gain Loss",
    "ST Gain Loss",
    "LT Gain Loss",
    "Disallowed Loss",
)


def _sha256_canonical(payload: dict) -> str:
    """Same discipline as core.bundle._sha256_canonical."""
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()


def _cell(v: Any) -> Any:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s != "" else None
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()[:10]
        except Exception:
            return str(v)
    return v


def _money_cell(series_val: Any) -> float | None:
    if series_val is None or (isinstance(series_val, float) and pd.isna(series_val)):
        return None
    if isinstance(series_val, str) and series_val.strip() == "":
        return None
    s = coerce_sheet_numeric_series(pd.Series([series_val]))
    v = s.iloc[0]
    if pd.isna(v):
        return None
    return round(float(v), 2)


def _normalize_records(df: pd.DataFrame, money_cols: tuple[str, ...]) -> list[dict]:
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for rec in df.to_dict(orient="records"):
        row: dict[str, Any] = {}
        for k, v in rec.items():
            key = str(k)
            if key in money_cols:
                row[key] = _money_cell(v)
            else:
                cell = _cell(v)
                # Dates → YYYY-MM-DD when parseable
                if key.lower().endswith("date") and cell is not None:
                    ts = pd.to_datetime(cell, errors="coerce")
                    row[key] = None if pd.isna(ts) else ts.strftime("%Y-%m-%d")
                else:
                    row[key] = cell
        out.append(row)
    out.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
    return out


def _normalize_metrics(metrics: dict[str, Any] | None) -> dict[str, Any]:
    if not metrics:
        return {}
    # Timestamps and whole-dollar Sheets bridge display differ by construction.
    skip = {"Last Updated", "Refreshed", "ST_Gains", "ST_Losses", "LT_Gains", "LT_Losses"}
    out: dict[str, Any] = {}
    for k, v in metrics.items():
        if k in skip:
            continue
        if isinstance(v, (int, float)) or (
            isinstance(v, str) and any(ch.isdigit() for ch in v)
        ):
            mv = _money_cell(v)
            out[k] = mv if mv is not None else _cell(v)
        else:
            out[k] = _cell(v)
    return out


def ledger_fingerprint(
    *,
    transactions: pd.DataFrame,
    realized_gl: pd.DataFrame,
    tax_metrics: dict[str, Any] | None,
    tax_lots: pd.DataFrame,
) -> str:
    """
    Hash of the Phase-1 vertical after money normalization.

    Catches Sheets-string vs SQLite-NUMERIC serialization drift before
    STORE_PRIMARY flips consumers that stamp composite_hash.
    """
    payload = {
        "schema": "portfolio_store_ledger_v1",
        "transactions": _normalize_records(transactions, _TX_MONEY),
        "realized_gl": _normalize_records(realized_gl, _GL_MONEY),
        "tax_control_metrics": _normalize_metrics(tax_metrics),
        "tax_control_lots": _normalize_records(tax_lots, _TAX_LOT_MONEY),
    }
    return _sha256_canonical(payload)
