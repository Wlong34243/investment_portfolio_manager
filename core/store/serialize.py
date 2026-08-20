"""Shared DataFrame <-> JSON row helpers for store backends."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if pd.isna(obj):
        return None
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def df_to_payloads(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty:
        return []
    records = df.to_dict(orient="records")
    return [json.dumps(rec, default=_json_default) for rec in records]


def payloads_to_df(payloads: list[str]) -> pd.DataFrame:
    if not payloads:
        return pd.DataFrame()
    rows = [json.loads(p) for p in payloads]
    return pd.DataFrame(rows)


def metrics_to_json(metrics: dict[str, Any]) -> str:
    return json.dumps(metrics, default=_json_default)


def metrics_from_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


def coerce_mv(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 0.0
    for col in ("Market Value", "market_value", "MV", "Position MV"):
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            return float(s.sum())
    return 0.0


def coerce_count(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return int(len(df))
