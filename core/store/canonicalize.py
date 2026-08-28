"""
Shared cell canonicalization for ledger fingerprints and retrieval hashes.

Hardcoded per-module money/date lists are how a canonicalizer silently stops
canonicalizing (see ledger_hash FAIL under STORE_PRIMARY=sqlite, 2026-08-21+).
Keep the column vocabulary here; consumers import — they do not re-declare.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

import pandas as pd

from utils.sheet_readers import coerce_sheet_numeric_series

# ---------------------------------------------------------------------------
# Column vocabulary — single source for money / bool / date detection
# ---------------------------------------------------------------------------

TX_MONEY: tuple[str, ...] = ("Net Amount", "Amount", "Fees", "Price", "Quantity")
GL_MONEY: tuple[str, ...] = (
    "Proceeds",
    "Cost Basis",
    "Gain Loss $",
    "ST Gain Loss",
    "LT Gain Loss",
    "Disallowed Loss",
    "Quantity",
    "Proceeds Per Share",
    "Cost Per Share",
    "Gain Loss %",
)
TAX_LOT_MONEY: tuple[str, ...] = (
    "Gain Loss",
    "ST Gain Loss",
    "LT Gain Loss",
    "Disallowed Loss",
)

# Union for retrieval_hash when the template does not declare a money set.
ALL_MONEY: frozenset[str] = frozenset(TX_MONEY + GL_MONEY + TAX_LOT_MONEY)

# Columns whose TRUE/FALSE *strings* are normalized to bool.
# Adding a name here does NOT opt into blank→False — that is a separate decision.
BOOL_COLUMNS: frozenset[str] = frozenset(
    {
        "Wash Sale",
        "Is Primary Acct",
    }
)

# Opt-in only: blank / None means False (not "unknown").
# Wash Sale: no wash sale recorded → no wash sale. Do not inherit this for the
# next tax boolean without an explicit decision — "no" and "unknown" differ.
BOOL_BLANK_MEANS_FALSE: frozenset[str] = frozenset(
    {
        "Wash Sale",
    }
)

# Explicit date columns that do not end with "date" / contain "date" oddly.
DATE_COLUMNS: frozenset[str] = frozenset(
    {
        "Date Acquired",
        "Date Sold",
        "Opened Date",
        "Closed Date",
        "Trade Date",
        "Import Date",
        "Open Date",
        "Close Date",
    }
)


def is_date_key(key: str) -> bool:
    """True when the column should canonicalize to YYYY-MM-DD."""
    k = str(key)
    if k in DATE_COLUMNS:
        return True
    kl = k.lower()
    # "Trade Date", "Opened Date", "as_of_date", "event_date"
    if "date" in kl:
        return True
    return False


def is_money_key(key: str, money_cols: Iterable[str] | None = None) -> bool:
    if money_cols is not None:
        return str(key) in set(money_cols)
    return str(key) in ALL_MONEY


def is_bool_key(key: str) -> bool:
    return str(key) in BOOL_COLUMNS


def blank_means_false(key: str) -> bool:
    """True only for columns explicitly listed in BOOL_BLANK_MEANS_FALSE."""
    return str(key) in BOOL_BLANK_MEANS_FALSE


def sha256_canonical(payload: dict) -> str:
    """Same discipline as core.bundle._sha256_canonical."""
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()


def cell(v: Any) -> Any:
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


def money_cell(series_val: Any) -> float | None:
    if series_val is None or (isinstance(series_val, float) and pd.isna(series_val)):
        return None
    if isinstance(series_val, str) and series_val.strip() == "":
        return None
    s = coerce_sheet_numeric_series(pd.Series([series_val]))
    v = s.iloc[0]
    if pd.isna(v):
        return None
    return round(float(v), 2)


def bool_cell(series_val: Any, *, blank_means_false: bool = False) -> bool | None:
    """
    Canonicalize Sheets TRUE/FALSE strings.

    blank_means_false=False (default): blank/None → None (unknown ≠ no).
    blank_means_false=True: blank/None → False — only via BOOL_BLANK_MEANS_FALSE.
    """
    if series_val is None or (isinstance(series_val, float) and pd.isna(series_val)):
        return False if blank_means_false else None
    if isinstance(series_val, bool):
        return series_val
    s = str(series_val).strip().upper()
    if s in ("", "NONE", "NULL"):
        return False if blank_means_false else None
    if s in ("FALSE", "F", "0", "N", "NO"):
        return False
    if s in ("TRUE", "T", "1", "Y", "YES"):
        return True
    return None


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def date_cell(series_val: Any) -> str | None:
    c = cell(series_val)
    if c is None:
        return None
    if isinstance(c, str) and _DATE_RE.match(c):
        return c[:10]
    ts = pd.to_datetime(c, errors="coerce")
    if pd.isna(ts):
        return str(c) if c is not None else None
    return ts.strftime("%Y-%m-%d")


def normalize_value(
    key: str,
    v: Any,
    *,
    money_cols: Iterable[str] | None = None,
) -> Any:
    k = str(key)
    if is_bool_key(k):
        return bool_cell(v, blank_means_false=blank_means_false(k))
    if is_money_key(k, money_cols):
        return money_cell(v)
    if is_date_key(k):
        return date_cell(v)
    return cell(v)


def normalize_record(
    rec: dict[str, Any],
    *,
    money_cols: Iterable[str] | None = None,
) -> dict[str, Any]:
    return {str(k): normalize_value(str(k), v, money_cols=money_cols) for k, v in rec.items()}


def normalize_records(
    df: pd.DataFrame,
    money_cols: tuple[str, ...] | None = None,
) -> list[dict]:
    if df is None or df.empty:
        return []
    out = [
        normalize_record(rec, money_cols=money_cols)
        for rec in df.to_dict(orient="records")
    ]
    out.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
    return out


def normalize_metrics(metrics: dict[str, Any] | None) -> dict[str, Any]:
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
            mv = money_cell(v)
            out[k] = mv if mv is not None else cell(v)
        else:
            out[k] = cell(v)
    return out


def normalize_table_rows(
    rows: list[dict[str, Any]] | None,
    *,
    money_cols: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """For retrieval_hash — same cell rules without requiring a DataFrame."""
    if not rows:
        return []
    out = [normalize_record(r, money_cols=money_cols) for r in rows]
    out.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
    return out
