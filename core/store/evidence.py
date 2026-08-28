"""
Append-only evidence capture — SQLite-only, not routed through PortfolioStore.

Mirror tables use replace-semantics over Sheet tabs. Evidence tables
(signal_events, bars_daily, fundamentals_snapshot) are permanent records:
INSERT OR IGNORE only, never UPDATE/DELETE/clear-and-rebuild. Writers require
live=True to mutate; dry-run reports attempted counts without touching the DB.

Resolves code-audit A8 (dry-run still writes disk) *for these tables only*.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import config
from core.store.models import (
    BarDaily,
    FundamentalsSnapshot,
    MetaKV,
    SignalEvent,
    get_engine,
    get_session,
)

logger = logging.getLogger(__name__)

EVIDENCE_GATE_DAYS = 10
ACCRUAL_META_KEY = "evidence_first_accrual_date"
HEALTH_FAILURE_FLAG = Path("logs") / "HEALTH_FAILURE.flag"

_SOURCE_BY_REASON = {
    "NEAR_TRIM": "crosshairs",
    "NEAR_ADD": "crosshairs",
    "HOLD_TAX": "crosshairs",
    "DISLOCATION": "dislocation_scan",
    "MISSING_LEVEL": "level_coverage",
    "ADD_SUSPENDED": "crosshairs",
}


@dataclass
class EvidenceWriteResult:
    table: str
    attempted: int
    inserted: int
    ignored_duplicate: int
    live: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cash_set() -> set[str]:
    return {str(t).upper() for t in getattr(config, "CASH_TICKERS", [])}


def _held_tickers() -> list[str]:
    cash = _cash_set()
    try:
        from core.store import get_store

        df = get_store().get_holdings_current()
        if df is not None and not df.empty:
            col = "Ticker" if "Ticker" in df.columns else ("ticker" if "ticker" in df.columns else None)
            if col:
                out = []
                for t in df[col].astype(str).str.strip().str.upper():
                    if t and t not in cash and t != "NAN":
                        out.append(t)
                if out:
                    return sorted(set(out))
    except Exception as e:
        logger.warning("evidence: holdings via store failed (%s); falling back to bundle", e)

    from tasks.dislocation_scan import _latest_bundle_positions

    out = []
    for pos in _latest_bundle_positions():
        t = str(pos.get("ticker") or pos.get("symbol") or "").upper().strip()
        if not t or t in cash or pos.get("is_cash"):
            continue
        out.append(t)
    return sorted(set(out))


def _watchlist_tickers() -> list[str]:
    from tasks.dislocation_scan import WATCHLIST_PATH_DEFAULT, _load_watchlist

    return _load_watchlist(WATCHLIST_PATH_DEFAULT)


def _bar_universe() -> list[str]:
    return sorted(set(_held_tickers()) | set(_watchlist_tickers()))


def _signal_source(signal_type: str) -> str:
    if signal_type in _SOURCE_BY_REASON:
        return _SOURCE_BY_REASON[signal_type]
    if signal_type.startswith("NEAR_TRIM"):
        return "crosshairs"
    return "crosshairs"


def _crosshair_to_row(item: Any, event_date: date, rank: int) -> dict:
    override_tag = getattr(item, "override_tag", None) or getattr(item, "doctrine_tag", None) or None
    reason = getattr(item, "reason_code", "") or ""
    # HOLD_TAX / ADD_SUSPENDED become signal_type when present so the record
    # names the override; doctrine_downgraded is an explicit CrosshairItem flag
    # set only for doctrine.md downgrade_informational (never denylisted).
    signal_type = override_tag if override_tag else reason
    trigger_type = getattr(item, "trigger_type", None) or None
    dist_trim = getattr(item, "dist_trim", None)
    dist_add = getattr(item, "dist_add", None)
    trim = getattr(item, "trim", None)
    add = getattr(item, "add", None)
    price = getattr(item, "price", None)

    band_side = None
    band_level = None
    distance_pct = None
    metric_value = price
    if signal_type in ("NEAR_TRIM", "HOLD_TAX") or (dist_trim is not None and (dist_add is None or abs(dist_trim or 0) <= abs(dist_add or 0))):
        if dist_trim is not None:
            band_side = "trim"
            band_level = trim
            distance_pct = dist_trim
    if signal_type == "NEAR_ADD" or (band_side is None and dist_add is not None):
        band_side = "add"
        band_level = add
        distance_pct = dist_add

    rank_score = getattr(item, "rank_score", 0) or 0
    rank_bucket = int(rank_score) // 100 * 100 if rank_score else 0
    source = _signal_source(signal_type)
    payload = item.to_dict() if hasattr(item, "to_dict") else dict(item)
    # Normalize payload key name for the permanent record
    if "doctrine_tag" in payload and "override_tag" not in payload:
        payload["override_tag"] = payload.pop("doctrine_tag")
    fp = _fingerprint(event_date.isoformat(), payload.get("ticker"), signal_type, trigger_type, source)

    if hasattr(item, "doctrine_downgraded"):
        doctrine_downgraded = bool(item.doctrine_downgraded)
    else:
        # Legacy safety: never invent True from an unknown tag
        doctrine_downgraded = False

    return {
        "event_date": event_date,
        "ticker": str(payload.get("ticker", "")).upper(),
        "signal_type": signal_type,
        "trigger_type": trigger_type,
        "metric_value": metric_value,
        "band_level": band_level,
        "band_side": band_side,
        "distance_pct": distance_pct,
        "rank_bucket": rank_bucket,
        "rank": rank,
        "source": source,
        "doctrine_downgraded": doctrine_downgraded,
        "payload_json": json.dumps(payload, default=str, sort_keys=True),
        "fingerprint": fp,
    }


def record_signal_events(
    rows: list[dict],
    *,
    event_date: date,
    live: bool,
) -> EvidenceWriteResult:
    """Insert Crosshairs-derived signal rows. Idempotent via fingerprint UNIQUE."""
    attempted = len(rows)
    if not live:
        logger.info(
            "evidence signal_events DRY-RUN: would write %d row(s) for %s",
            attempted,
            event_date,
        )
        return EvidenceWriteResult("signal_events", attempted, 0, 0, live=False)

    get_engine()
    inserted = 0
    with get_session() as session:
        for row in rows:
            stmt = (
                sqlite_insert(SignalEvent)
                .values(
                    event_date=row["event_date"],
                    captured_at=_utcnow(),
                    ticker=row["ticker"],
                    signal_type=row["signal_type"],
                    trigger_type=row.get("trigger_type"),
                    metric_value=row.get("metric_value"),
                    band_level=row.get("band_level"),
                    band_side=row.get("band_side"),
                    distance_pct=row.get("distance_pct"),
                    rank_bucket=row.get("rank_bucket", 0),
                    rank=row.get("rank", 0),
                    source=row["source"],
                    doctrine_downgraded=bool(row.get("doctrine_downgraded")),
                    payload_json=row["payload_json"],
                    fingerprint=row["fingerprint"],
                )
                .on_conflict_do_nothing(index_elements=["fingerprint"])
            )
            result = session.execute(stmt)
            inserted += int(result.rowcount or 0)
        session.commit()
    ignored = attempted - inserted
    logger.info(
        "evidence signal_events: attempted=%d inserted=%d ignored_duplicate=%d",
        attempted,
        inserted,
        ignored,
    )
    return EvidenceWriteResult("signal_events", attempted, inserted, ignored, live=True)


def record_bars(
    ticker: str,
    bars: pd.DataFrame,
    *,
    source: str,
    live: bool,
) -> EvidenceWriteResult:
    """Insert daily OHLCV rows. UNIQUE(ticker, bar_date, source)."""
    ticker = (ticker or "").upper().strip()
    source = (source or "unknown").lower()
    if bars is None or bars.empty:
        return EvidenceWriteResult("bars_daily", 0, 0, 0, live=live)

    records = []
    for idx, row in bars.iterrows():
        if hasattr(idx, "date"):
            bar_date = idx.date() if callable(getattr(idx, "date", None)) else idx
            if hasattr(bar_date, "date"):
                bar_date = bar_date.date()
        else:
            bar_date = pd.Timestamp(idx).date()
        records.append(
            {
                "ticker": ticker,
                "bar_date": bar_date,
                "open": _safe_float(row.get("open")),
                "high": _safe_float(row.get("high")),
                "low": _safe_float(row.get("low")),
                "close": _safe_float(row.get("close")),
                "volume": _safe_float(row.get("volume")),
                "source": source,
            }
        )
    attempted = len(records)
    if not live:
        logger.info(
            "evidence bars_daily DRY-RUN: would write %d bar(s) for %s/%s",
            attempted,
            ticker,
            source,
        )
        return EvidenceWriteResult("bars_daily", attempted, 0, 0, live=False)

    get_engine()
    inserted = 0
    with get_session() as session:
        for rec in records:
            stmt = (
                sqlite_insert(BarDaily)
                .values(captured_at=_utcnow(), **rec)
                .on_conflict_do_nothing(index_elements=["ticker", "bar_date", "source"])
            )
            result = session.execute(stmt)
            inserted += int(result.rowcount or 0)
        session.commit()
    ignored = attempted - inserted
    return EvidenceWriteResult("bars_daily", attempted, inserted, ignored, live=True)


def record_fundamentals(
    rows: list[dict],
    *,
    as_of_date: date,
    live: bool,
) -> EvidenceWriteResult:
    attempted = len(rows)
    if not live:
        logger.info(
            "evidence fundamentals_snapshot DRY-RUN: would write %d row(s) for %s",
            attempted,
            as_of_date,
        )
        return EvidenceWriteResult("fundamentals_snapshot", attempted, 0, 0, live=False)

    get_engine()
    inserted = 0
    with get_session() as session:
        for row in rows:
            payload = row.get("payload_json")
            if not isinstance(payload, str):
                payload = json.dumps(row.get("payload") or row, default=str, sort_keys=True)
            stmt = (
                sqlite_insert(FundamentalsSnapshot)
                .values(
                    ticker=str(row["ticker"]).upper(),
                    as_of_date=as_of_date,
                    fwd_pe=row.get("fwd_pe"),
                    trailing_pe=row.get("trailing_pe"),
                    price_to_book=row.get("price_to_book"),
                    market_cap=row.get("market_cap"),
                    dividend_yield=row.get("dividend_yield"),
                    week52_high=row.get("week52_high"),
                    week52_low=row.get("week52_low"),
                    eps=row.get("eps"),
                    source=row.get("source") or "fmp_client",
                    captured_at=_utcnow(),
                    payload_json=payload,
                )
                .on_conflict_do_nothing(index_elements=["ticker", "as_of_date", "source"])
            )
            result = session.execute(stmt)
            inserted += int(result.rowcount or 0)
        session.commit()
    ignored = attempted - inserted
    return EvidenceWriteResult(
        "fundamentals_snapshot", attempted, inserted, ignored, live=True
    )


def _safe_float(val) -> Optional[float]:
    try:
        if val is None or (isinstance(val, float) and val != val):
            return None
        if val == "":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _table_stats(session, model, date_col) -> dict:
    n = session.scalar(select(func.count()).select_from(model)) or 0
    distinct_days = session.scalar(select(func.count(func.distinct(date_col)))) or 0
    first_d = session.scalar(select(func.min(date_col)))
    last_d = session.scalar(select(func.max(date_col)))
    return {
        "rows": int(n),
        "distinct_trading_days": int(distinct_days),
        "first": first_d.isoformat() if first_d else None,
        "last": last_d.isoformat() if last_d else None,
    }


def _clean_trading_days(session) -> int:
    """Distinct event_dates in signal_events (proxy for clean capture days)."""
    return int(
        session.scalar(select(func.count(func.distinct(SignalEvent.event_date)))) or 0
    )


def evidence_status() -> dict:
    """Per-table counts + ten-day accrual gate."""
    get_engine()
    with get_session() as session:
        status = {
            "signal_events": _table_stats(session, SignalEvent, SignalEvent.event_date),
            "bars_daily": _table_stats(session, BarDaily, BarDaily.bar_date),
            "fundamentals_snapshot": _table_stats(
                session, FundamentalsSnapshot, FundamentalsSnapshot.as_of_date
            ),
        }
        accrual = session.get(MetaKV, ACCRUAL_META_KEY)
        first_accrual = accrual.value if accrual else None
        clean_days = _clean_trading_days(session)

    remaining = max(0, EVIDENCE_GATE_DAYS - clean_days)
    gate_met = clean_days >= EVIDENCE_GATE_DAYS
    status["evidence_first_accrual_date"] = first_accrual
    status["clean_trading_days"] = clean_days
    status["gate_met"] = gate_met
    status["gate_remaining"] = remaining
    status["gate_line"] = (
        f"GATE: MET — {clean_days} clean trading days accrued."
        if gate_met
        else (
            f"GATE: NOT MET — {remaining} more clean trading day(s) required "
            f"before any retrospective reads this table."
        )
    )
    return status


def _set_first_accrual(event_date: date) -> None:
    get_engine()
    with get_session() as session:
        existing = session.get(MetaKV, ACCRUAL_META_KEY)
        if existing is None:
            session.add(
                MetaKV(key=ACCRUAL_META_KEY, value=event_date.isoformat(), updated_at=_utcnow())
            )
            session.commit()
            logger.info("evidence_first_accrual_date set to %s", event_date.isoformat())


def _max_bar_date(ticker: str, source: str) -> Optional[date]:
    get_engine()
    with get_session() as session:
        return session.scalar(
            select(func.max(BarDaily.bar_date)).where(
                BarDaily.ticker == ticker.upper(),
                BarDaily.source == source.lower(),
            )
        )


def _gather_fundamentals_rows(tickers: list[str], as_of_date: date) -> list[dict]:
    from utils.fmp_client import get_fundamentals

    rows = []
    for ticker in tickers:
        fund = get_fundamentals(ticker) or {}
        if not fund:
            continue
        rows.append(
            {
                "ticker": ticker,
                "fwd_pe": _safe_float(fund.get("forward_pe")),
                "trailing_pe": _safe_float(fund.get("trailing_pe")),
                "price_to_book": _safe_float(fund.get("pb_ratio")),
                "market_cap": _safe_float(fund.get("market_cap")),
                "dividend_yield": _safe_float(fund.get("dividend_yield")),
                "week52_high": _safe_float(fund.get("52w_high")),
                "week52_low": _safe_float(fund.get("52w_low")),
                "eps": _safe_float(fund.get("eps_ttm")),
                "source": "fmp_client",
                "payload": fund,
            }
        )
    return rows


def _capture_bars(tickers: list[str], *, live: bool) -> list[EvidenceWriteResult]:
    from utils.price_history import get_bars

    results = []
    for ticker in tickers:
        df = get_bars(ticker, period_days=365)
        if df is None or df.empty:
            continue
        used = str(df.attrs.get("source") or getattr(config, "PRICE_HISTORY_SOURCE", "auto"))
        max_existing = _max_bar_date(ticker, used) if live else None
        if max_existing is not None:
            # Incremental: only dates after max(bar_date) for this source
            mask = pd.Series(
                [pd.Timestamp(i).date() > max_existing for i in df.index],
                index=df.index,
            )
            df = df.loc[mask]
        if df.empty:
            results.append(EvidenceWriteResult("bars_daily", 0, 0, 0, live=live))
            continue
        results.append(record_bars(ticker, df, source=used, live=live))
    return results


def run_evidence_capture(
    *,
    live: bool = False,
    crosshairs: Any = None,
    event_date: Optional[date] = None,
    skip_trading_day_check: bool = False,
) -> dict:
    """
    Capture signals (from in-memory Crosshairs), incremental bars, and
    fundamentals for held (+ watchlist for bars) tickers.

    Skip entirely when the session is closed (weekend/holiday). Treat
    unknown (None) as proceed — same pattern as Daily_Snapshots.
    """
    from utils.market_calendar import is_session_open

    event_date = event_date or date.today()
    summary: dict[str, Any] = {
        "live": live,
        "event_date": event_date.isoformat(),
        "skipped": False,
        "results": [],
    }

    if not skip_trading_day_check:
        # Prompt names market_calendar.is_trading_day; the wrapper is is_session_open.
        flag = is_session_open(event_date)
        if flag is False:
            msg = f"evidence capture skipped — non-trading day {event_date.isoformat()}"
            logger.info(msg)
            summary["skipped"] = True
            summary["skip_reason"] = msg
            return summary

    if HEALTH_FAILURE_FLAG.exists() and live:
        logger.warning(
            "HEALTH_FAILURE.flag present — capturing anyway but day will not count as clean "
            "for gate purposes until flag is cleared (gate uses distinct signal event_dates)."
        )

    # --- Signals ---
    signal_rows: list[dict] = []
    if crosshairs is not None:
        items = getattr(crosshairs, "items", None) or []
        for i, item in enumerate(items, start=1):
            signal_rows.append(_crosshair_to_row(item, event_date, rank=i))
    else:
        # Standalone repair path: rebuild Crosshairs (may re-run dislocation ensure).
        from tasks.build_crosshairs import produce_crosshairs

        result = produce_crosshairs()
        for i, item in enumerate(result.items, start=1):
            signal_rows.append(_crosshair_to_row(item, event_date, rank=i))

    sig_res = record_signal_events(signal_rows, event_date=event_date, live=live)
    summary["results"].append(sig_res)

    # --- Bars ---
    bar_results = _capture_bars(_bar_universe(), live=live)
    summary["results"].extend(bar_results)

    # --- Fundamentals (held only) ---
    fund_rows = _gather_fundamentals_rows(_held_tickers(), event_date)
    fund_res = record_fundamentals(fund_rows, as_of_date=event_date, live=live)
    summary["results"].append(fund_res)

    if live and sig_res.inserted > 0 and not HEALTH_FAILURE_FLAG.exists():
        _set_first_accrual(event_date)

    summary["status"] = evidence_status()
    return summary


def format_evidence_status(status: Optional[dict] = None) -> str:
    status = status or evidence_status()
    lines = []
    for table in ("signal_events", "bars_daily", "fundamentals_snapshot"):
        s = status[table]
        lines.append(
            f"{table}: {s['rows']:,} rows | {s['distinct_trading_days']} trading days accrued "
            f"| first {s['first'] or '—'} | last {s['last'] or '—'}"
        )
    if status.get("evidence_first_accrual_date"):
        lines.append(f"evidence_first_accrual_date: {status['evidence_first_accrual_date']}")
    lines.append(status["gate_line"])
    return "\n".join(lines)
