"""
Find unreconciled rotation clusters (blank Implicit_Bet) for the rationale loop.

Reads Trade_Log_Staging from Sheets (SQLite mirror is empty — dual-write gap).
Reuses find_superseded_groups so nested supersets collapse to the widest row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

from tasks.compute_rotation_attribution import find_superseded_groups
from utils.sheet_readers import get_trade_log, get_trade_log_staging


@dataclass
class UnreconciledCluster:
    cluster_id: str  # Stage_ID or Trade_Log_ID of the widest row
    fingerprint: str
    fill_date: date
    sell_tickers: list[str]
    buy_tickers: list[str]
    status: str
    source: str  # "staging" | "trade_log"
    implicit_bet: str
    superseded_ids: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_date(v: Any) -> Optional[date]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def _split_tickers(raw: Any) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    parts = [p.strip().upper() for p in str(raw).replace(";", ",").split(",")]
    return [p for p in parts if p and p.lower() != "nan"]


def _blank_bet(v: Any) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True
    s = str(v).strip()
    return s == "" or s.lower() == "nan"


def _row_dict(rec: dict) -> dict[str, Any]:
    """Normalize staging plurals onto Trade_Log singular keys for find_superseded_groups."""
    out = dict(rec)
    if "Sell_Ticker" not in out and "Sell_Tickers" in out:
        out["Sell_Ticker"] = out.get("Sell_Tickers")
    if "Buy_Ticker" not in out and "Buy_Tickers" in out:
        out["Buy_Ticker"] = out.get("Buy_Tickers")
    if "Trade_Log_ID" not in out and "Stage_ID" in out:
        out["Trade_Log_ID"] = out.get("Stage_ID")
    return out


def _looks_like_hash(s: str) -> bool:
    """Fingerprints are 12-char hex from derive_rotations; reject RSI/price junk."""
    s = s.strip().lower()
    if len(s) < 8:
        return False
    return all(c in "0123456789abcdef" for c in s)


def _cluster_id(rec: dict, *, prefer_stage: bool) -> str:
    """Stable id: prefer Stage_ID/Trade_Log_ID when non-empty; else Fingerprint."""
    if prefer_stage:
        for key in ("Stage_ID", "Trade_Log_ID"):
            v = rec.get(key)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            # Sheets often leaves Stage_ID as 0.0 — treat as missing
            if isinstance(v, (int, float)) and float(v) == 0.0:
                continue
            s = str(v).strip()
            if s and s.lower() != "nan" and s != "0" and s != "0.0":
                return s
    fp = rec.get("Fingerprint")
    if fp is not None and not (isinstance(fp, float) and pd.isna(fp)):
        s = str(fp).strip()
        if s and s.lower() != "nan" and _looks_like_hash(s):
            return s
    # last resort — date + tickers
    d = str(rec.get("Date") or "").strip()
    sells = str(rec.get("Sell_Tickers") or rec.get("Sell_Ticker") or "")
    buys = str(rec.get("Buy_Tickers") or rec.get("Buy_Ticker") or "")
    return f"{d}|{sells}|{buys}"


def load_unreconciled_clusters(
    *,
    include_staging: bool = True,
    include_trade_log: bool = True,
) -> list[UnreconciledCluster]:
    """
    Rows with blank Implicit_Bet, collapsed to widest nested row per Date.

    Staging is authoritative for the promoted-blank backlog (Sheets).
    Trade_Log blank rows are included so capture-context gaps on the log itself
    are visible — same fingerprint may appear in both; prefer staging when both.
    """
    rows: list[dict[str, Any]] = []
    meta: dict[str, dict[str, Any]] = {}  # id -> {source, fingerprint, status, ...}

    if include_staging:
        staging = get_trade_log_staging()
        for rec in staging.to_dict(orient="records"):
            if not _blank_bet(rec.get("Implicit_Bet")):
                continue
            rd = _row_dict(rec)
            rid = _cluster_id(rec, prefer_stage=True)
            rd["Trade_Log_ID"] = rid
            rd["Stage_ID"] = rid
            rows.append(rd)
            meta[rid] = {
                "source": "staging",
                "fingerprint": (
                    str(rec.get("Fingerprint") or "").strip()
                    if _looks_like_hash(str(rec.get("Fingerprint") or ""))
                    else rid
                ),
                "status": str(rec.get("Status") or "").strip(),
                "raw": rec,
            }

    if include_trade_log:
        tl = get_trade_log()
        staging_fps = {m["fingerprint"] for m in meta.values() if m["fingerprint"]}
        for rec in tl.to_dict(orient="records"):
            if not _blank_bet(rec.get("Implicit_Bet")):
                continue
            fp = str(rec.get("Fingerprint") or "").strip()
            if fp and fp in staging_fps:
                continue  # staging already covers this cluster
            rd = _row_dict(rec)
            rid = _cluster_id(rec, prefer_stage=False)
            rd["Trade_Log_ID"] = rid
            rows.append(rd)
            meta[rid] = {
                "source": "trade_log",
                "fingerprint": fp if _looks_like_hash(fp) else rid,
                "status": "trade_log",
                "raw": rec,
            }

    if not rows:
        return []

    superseded, _groups = find_superseded_groups(rows)
    children: dict[str, list[str]] = {}
    for narrow, wide in superseded.items():
        children.setdefault(wide, []).append(narrow)

    out: list[UnreconciledCluster] = []
    seen: set[str] = set()
    for rd in rows:
        rid = str(rd.get("Trade_Log_ID") or rd.get("Stage_ID") or "").strip()
        if not rid or rid in superseded:
            continue
        if rid in seen:
            continue
        seen.add(rid)
        m = meta.get(rid, {})
        fd = _parse_date(rd.get("Date"))
        if fd is None:
            continue
        sells = _split_tickers(rd.get("Sell_Ticker") or rd.get("Sell_Tickers"))
        buys = _split_tickers(rd.get("Buy_Ticker") or rd.get("Buy_Tickers"))
        out.append(
            UnreconciledCluster(
                cluster_id=rid,
                fingerprint=m.get("fingerprint") or "",
                fill_date=fd,
                sell_tickers=sells,
                buy_tickers=buys,
                status=m.get("status") or "",
                source=m.get("source") or "",
                implicit_bet="",
                superseded_ids=children.get(rid, []),
                raw=m.get("raw") or rd,
            )
        )

    out.sort(key=lambda c: (c.fill_date, c.cluster_id))
    return out
