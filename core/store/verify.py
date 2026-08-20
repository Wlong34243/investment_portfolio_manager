"""Reconcile Sheets vs SQLite — value-level (to the cent) + streak + ledger hash."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

import config
from core.store.ledger_hash import ledger_fingerprint
from core.store.sheets_store import SheetsPortfolioStore
from core.store.sqlite_store import SqlitePortfolioStore
from utils.sheet_readers import coerce_sheet_numeric_series


@dataclass
class VerifyResult:
    ok: bool
    lines: list[str] = field(default_factory=list)
    sheets_reachable: bool = True
    streak_ok: bool = False
    aggregates: dict[str, Any] = field(default_factory=dict)


def _money_sum(df: pd.DataFrame, col: str) -> float:
    if df is None or df.empty or col not in df.columns:
        return 0.0
    return float(coerce_sheet_numeric_series(df[col]).fillna(0.0).sum())


def _metric_money(metrics: dict[str, Any], key: str) -> float | None:
    if not metrics or key not in metrics:
        return None
    s = coerce_sheet_numeric_series(pd.Series([metrics[key]]))
    v = s.iloc[0]
    if pd.isna(v):
        return None
    return round(float(v), 2)


def _realized_aggregates(df: pd.DataFrame) -> dict[str, float]:
    return {
        "proceeds": round(_money_sum(df, "Proceeds"), 2),
        "cost_basis": round(_money_sum(df, "Cost Basis"), 2),
        "gain_loss": round(_money_sum(df, "Gain Loss $"), 2),
        "st_gain_loss": round(_money_sum(df, "ST Gain Loss"), 2),
        "lt_gain_loss": round(_money_sum(df, "LT Gain Loss"), 2),
        "disallowed_loss": round(_money_sum(df, "Disallowed Loss"), 2),
        "row_count": float(len(df) if df is not None else 0),
    }


def _txn_aggregates(df: pd.DataFrame) -> dict[str, float]:
    return {
        "net_amount": round(_money_sum(df, "Net Amount"), 2),
        "amount": round(_money_sum(df, "Amount"), 2),
        "fees": round(_money_sum(df, "Fees"), 2),
        "row_count": float(len(df) if df is not None else 0),
    }


def _tax_lot_aggregates(df: pd.DataFrame) -> dict[str, float]:
    return {
        "gain_loss": round(_money_sum(df, "Gain Loss"), 2),
        "st_gain_loss": round(_money_sum(df, "ST Gain Loss"), 2),
        "lt_gain_loss": round(_money_sum(df, "LT Gain Loss"), 2),
        "disallowed_loss": round(_money_sum(df, "Disallowed Loss"), 2),
        "row_count": float(len(df) if df is not None else 0),
    }


def _cent_equal(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol


def _closed_dates(df: pd.DataFrame) -> set[str]:
    if df is None or df.empty or "Closed Date" not in df.columns:
        return set()
    s = pd.to_datetime(df["Closed Date"], errors="coerce")
    return {d.date().isoformat() for d in s.dropna()}


def _append_streak(entry: dict[str, Any]) -> None:
    path = Path(config.STORE_VERIFY_STREAK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _read_streak() -> list[dict[str, Any]]:
    path = Path(config.STORE_VERIFY_STREAK_PATH)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def record_parity_result(*, ok: bool, sheets_hash: str, sqlite_hash: str) -> None:
    _append_streak({
        "kind": "parity",
        "ts": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "ok": ok,
        "sheets_hash": sheets_hash,
        "sqlite_hash": sqlite_hash,
    })


def evaluate_streak(n: int | None = None) -> tuple[bool, list[str]]:
    """
    N consecutive *verify runs* with ok=True (not calendar days).

    Weekends / days with no scheduled morning neither advance nor break the
    streak — only recorded verify invocations count. Non-vacuous: at least one
    run in the window saw realized_gl row_count > 0. Also requires ≥1
    bundle-parity result (kind=parity) recorded in the log (any time before
    cutover check — prefer inside the same campaign window).
    """
    n = n if n is not None else config.STORE_VERIFY_STREAK_N
    lines: list[str] = []
    rows = _read_streak()
    if not rows:
        lines.append(f"streak: empty log ({config.STORE_VERIFY_STREAK_PATH}) — 0/{n}")
        return False, lines

    verify_rows = [r for r in rows if r.get("kind", "verify") != "parity"]
    parity_rows = [r for r in rows if r.get("kind") == "parity"]

    window = verify_rows[-n:]
    if len(window) < n:
        lines.append(f"streak FAIL: only {len(window)}/{n} verify runs recorded")
        return False, lines

    for i, r in enumerate(window):
        if not r.get("ok"):
            lines.append(
                f"streak FAIL: run {i + 1}/{n} in window ok=false "
                f"(ts={r.get('ts')})"
            )
            return False, lines

    realized_counts = [int(r.get("realized_row_count") or 0) for r in window]
    if max(realized_counts) <= 0:
        lines.append(
            "streak FAIL: window has realized_row_count=0 on every run — "
            "vacuous green (need ≥1 realized lot in the N-run window)"
        )
        return False, lines

    if not any(r.get("ok") for r in parity_rows):
        lines.append(
            "streak FAIL: no successful bundle-parity result recorded "
            "(run `pm store bundle-parity`)"
        )
        return False, lines

    lines.append(
        f"streak PASS: {n} consecutive green verify runs "
        f"(latest ts={window[-1].get('ts')}); "
        f"max_realized_rows={max(realized_counts)}; "
        f"parity_ok_count={sum(1 for r in parity_rows if r.get('ok'))}"
    )
    return True, lines


def _compare_money_map(
    *,
    prefix: str,
    sheets_map: dict[str, float],
    sqlite_map: dict[str, float],
    keys: tuple[str, ...],
    lines: list[str],
) -> bool:
    ok = True
    for key in keys:
        sv = sheets_map.get(key, 0.0)
        qv = sqlite_map.get(key, 0.0)
        if key == "row_count":
            if int(sv) != int(qv):
                ok = False
                lines.append(f"FAIL {prefix}.{key} sheets={int(sv)} sqlite={int(qv)}")
            else:
                lines.append(f"{prefix}.{key} MATCH ({int(qv)})")
        elif not _cent_equal(float(sv), float(qv)):
            ok = False
            lines.append(f"FAIL {prefix}.{key} sheets={sv:.2f} sqlite={qv:.2f}")
        else:
            lines.append(f"{prefix}.{key} MATCH ({qv:.2f})")
    return ok


def _compare_tax_metrics(
    s_metrics: dict[str, Any],
    q_metrics: dict[str, Any],
    lines: list[str],
) -> bool:
    ok = True
    # Money KPIs — exclude timestamps
    money_keys = [
        k
        for k in config.TAX_CONTROL_KPI_LABELS
        if k not in ("Last Updated", "Refreshed")
    ]
    # Also bridge keys when present on either side
    for extra in ("ST_Gains", "ST_Losses", "LT_Gains", "LT_Losses"):
        if extra in s_metrics or extra in q_metrics:
            money_keys.append(extra)

    if not s_metrics and not q_metrics:
        lines.append("FAIL tax_control.metrics both empty")
        return False
    if not s_metrics:
        lines.append("FAIL tax_control.metrics sheets empty (parse or refresh missing)")
        return False
    if not q_metrics:
        lines.append("FAIL tax_control.metrics sqlite empty — run `pm refresh tax --live`")
        return False

    for key in money_keys:
        sv = _metric_money(s_metrics, key)
        qv = _metric_money(q_metrics, key)
        if sv is None and qv is None:
            continue
        if sv is None or qv is None:
            ok = False
            lines.append(f"FAIL tax_control.metric.{key} sheets={sv} sqlite={qv}")
        elif not _cent_equal(sv, qv):
            ok = False
            lines.append(
                f"FAIL tax_control.metric.{key} sheets={sv:.2f} sqlite={qv:.2f}"
            )
        else:
            lines.append(f"tax_control.metric.{key} MATCH ({qv:.2f})")
    return ok


def verify_stores(
    rel_tol: float = 0.01,
    record_streak: bool = True,
    check_ledger_hash: bool = True,
) -> VerifyResult:
    """
    Value-level reconcile to the cent for transactions, realized_gl, and
    tax_control (metrics + lots). Plus canonical ledger fingerprint parity.
    """
    del rel_tol  # CLI compat; value checks are absolute to the cent
    sheets = SheetsPortfolioStore()
    sqlite = SqlitePortfolioStore()
    lines: list[str] = []
    try:
        s_tx = sheets.get_transactions()
        s_gl = sheets.get_realized_gl()
        s_tax = sheets.get_tax_control_lots()
        s_metrics = sheets.get_tax_control_metrics()
    except Exception as e:
        return VerifyResult(
            ok=False,
            sheets_reachable=False,
            lines=[f"Sheets read failed: {e}"],
        )

    q_tx = sqlite.get_transactions()
    q_gl = sqlite.get_realized_gl()
    q_tax = sqlite.get_tax_control_lots()
    q_metrics = sqlite.get_tax_control_metrics()

    s_tx_agg = _txn_aggregates(s_tx)
    q_tx_agg = _txn_aggregates(q_tx)
    s_gl_agg = _realized_aggregates(s_gl)
    q_gl_agg = _realized_aggregates(q_gl)
    s_tax_agg = _tax_lot_aggregates(s_tax)
    q_tax_agg = _tax_lot_aggregates(q_tax)

    lines.append(
        f"STORE_PRIMARY={config.STORE_PRIMARY} STORE_BACKEND={config.STORE_BACKEND}"
    )
    lines.append(
        f"Sheets: txns={int(s_tx_agg['row_count'])} net={s_tx_agg['net_amount']:,.2f} | "
        f"realized={int(s_gl_agg['row_count'])} proceeds={s_gl_agg['proceeds']:,.2f} "
        f"gl={s_gl_agg['gain_loss']:,.2f} | "
        f"tax_lots={int(s_tax_agg['row_count'])} tax_metrics={len(s_metrics)}"
    )
    lines.append(
        f"SQLite: txns={int(q_tx_agg['row_count'])} net={q_tx_agg['net_amount']:,.2f} | "
        f"realized={int(q_gl_agg['row_count'])} proceeds={q_gl_agg['proceeds']:,.2f} "
        f"gl={q_gl_agg['gain_loss']:,.2f} | "
        f"tax_lots={int(q_tax_agg['row_count'])} tax_metrics={len(q_metrics)}"
    )

    empty_shadow = (
        q_tx_agg["row_count"] == 0
        and q_gl_agg["row_count"] == 0
        and q_tax_agg["row_count"] == 0
        and not q_metrics
    )
    if empty_shadow:
        lines.append(
            "VERIFY FAIL: SQLite tax/txn/realized vertical empty — shadow not populated. "
            "Run `pm store sync-from-sheets --live` and `pm refresh tax --live`."
        )
        result = VerifyResult(ok=False, lines=lines)
        if record_streak:
            _append_streak({
                "kind": "verify",
                "ts": datetime.now(timezone.utc).isoformat(),
                "date": datetime.now(timezone.utc).date().isoformat(),
                "ok": False,
                "reason": "empty_shadow",
                "realized_row_count": int(s_gl_agg["row_count"]),
                "closed_dates": sorted(_closed_dates(s_gl)),
            })
            streak_ok, streak_lines = evaluate_streak()
            result.streak_ok = streak_ok
            result.lines.extend(streak_lines)
        return result

    ok = True
    ok = _compare_money_map(
        prefix="txn",
        sheets_map=s_tx_agg,
        sqlite_map=q_tx_agg,
        keys=("row_count", "net_amount", "amount", "fees"),
        lines=lines,
    ) and ok

    ok = _compare_money_map(
        prefix="realized",
        sheets_map=s_gl_agg,
        sqlite_map=q_gl_agg,
        keys=(
            "row_count",
            "proceeds",
            "cost_basis",
            "gain_loss",
            "st_gain_loss",
            "lt_gain_loss",
            "disallowed_loss",
        ),
        lines=lines,
    ) and ok

    ok = _compare_tax_metrics(s_metrics, q_metrics, lines) and ok
    ok = _compare_money_map(
        prefix="tax_lots",
        sheets_map=s_tax_agg,
        sqlite_map=q_tax_agg,
        keys=(
            "row_count",
            "gain_loss",
            "st_gain_loss",
            "lt_gain_loss",
            "disallowed_loss",
        ),
        lines=lines,
    ) and ok

    # Phase 1 acceptance: ledger fingerprint parity (bundle-canonical SHA).
    # Catches NUMERIC vs string serialization before STORE_PRIMARY flip.
    if check_ledger_hash:
        h_sheets = ledger_fingerprint(
            transactions=s_tx,
            realized_gl=s_gl,
            tax_metrics=s_metrics,
            tax_lots=s_tax,
        )
        h_sqlite = ledger_fingerprint(
            transactions=q_tx,
            realized_gl=q_gl,
            tax_metrics=q_metrics,
            tax_lots=q_tax,
        )
        lines.append(f"ledger_hash.sheets={h_sheets}")
        lines.append(f"ledger_hash.sqlite={h_sqlite}")
        if h_sheets != h_sqlite:
            ok = False
            lines.append(
                "FAIL ledger_hash parity — Sheets vs SQLite fingerprints differ "
                "(serialization / row drift; fix before STORE_PRIMARY=sqlite)"
            )
        else:
            lines.append(f"ledger_hash MATCH ({h_sheets[:12]}…)")

    if ok:
        lines.append("VERIFY PASS (value-level txn + realized + tax_control + ledger_hash)")
    else:
        lines.append("VERIFY FAIL")

    closed = sorted(_closed_dates(s_gl))
    if record_streak:
        _append_streak({
            "kind": "verify",
            "ts": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).date().isoformat(),
            "ok": ok,
            "realized_row_count": int(s_gl_agg["row_count"]),
            "closed_dates": closed,
            "ledger_hash_ok": (
                check_ledger_hash
                and "ledger_hash MATCH" in "\n".join(lines)
            ),
        })

    streak_ok, streak_lines = evaluate_streak()
    lines.extend(streak_lines)

    return VerifyResult(
        ok=ok,
        lines=lines,
        streak_ok=streak_ok,
        aggregates={
            "sheets_tx": s_tx_agg,
            "sqlite_tx": q_tx_agg,
            "sheets_gl": s_gl_agg,
            "sqlite_gl": q_gl_agg,
            "sheets_tax_lots": s_tax_agg,
            "sqlite_tax_lots": q_tax_agg,
        },
    )
