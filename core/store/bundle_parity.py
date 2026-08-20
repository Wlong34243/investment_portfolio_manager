"""Sheets vs SQLite ledger parity using bundle canonical SHA discipline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.bundle import _sha256_canonical
from core.store.ledger_hash import ledger_fingerprint
from core.store.sheets_store import SheetsPortfolioStore
from core.store.sqlite_store import SqlitePortfolioStore


@dataclass
class BundleParityResult:
    ok: bool
    sheets_hash: str = ""
    sqlite_hash: str = ""
    lines: list[str] = field(default_factory=list)
    differing_paths: list[str] = field(default_factory=list)


def _payload(
    *,
    transactions,
    realized_gl,
    tax_metrics,
    tax_lots,
) -> dict[str, Any]:
    """
    Hashable stand-in for the store-backed surfaces Phase 2 will feed into
    bundle consumers. Uses the same _sha256_canonical as ContextBundle.
    Money normalization lives in ledger_fingerprint; here we also emit a
    second hash of the raw fingerprint string for MATCH reporting.
    """
    fp = ledger_fingerprint(
        transactions=transactions,
        realized_gl=realized_gl,
        tax_metrics=tax_metrics,
        tax_lots=tax_lots,
    )
    return {
        "schema": "store_bundle_parity_v1",
        "ledger_fingerprint": fp,
        "txn_rows": int(len(transactions) if transactions is not None else 0),
        "realized_rows": int(len(realized_gl) if realized_gl is not None else 0),
        "tax_lot_rows": int(len(tax_lots) if tax_lots is not None else 0),
        "tax_metric_keys": sorted((tax_metrics or {}).keys()),
    }


def run_bundle_parity(*, max_diff_paths: int = 20) -> BundleParityResult:
    sheets = SheetsPortfolioStore()
    sqlite = SqlitePortfolioStore()
    lines: list[str] = []
    try:
        s_tx = sheets.get_transactions()
        s_gl = sheets.get_realized_gl()
        s_tax = sheets.get_tax_control_lots()
        s_metrics = sheets.get_tax_control_metrics()
    except Exception as e:
        return BundleParityResult(ok=False, lines=[f"Sheets read failed: {e}"])

    q_tx = sqlite.get_transactions()
    q_gl = sqlite.get_realized_gl()
    q_tax = sqlite.get_tax_control_lots()
    q_metrics = sqlite.get_tax_control_metrics()

    p_sheets = _payload(
        transactions=s_tx,
        realized_gl=s_gl,
        tax_metrics=s_metrics,
        tax_lots=s_tax,
    )
    p_sqlite = _payload(
        transactions=q_tx,
        realized_gl=q_gl,
        tax_metrics=q_metrics,
        tax_lots=q_tax,
    )
    h_sheets = _sha256_canonical(p_sheets)
    h_sqlite = _sha256_canonical(p_sqlite)

    lines.append(f"ts={datetime.now(timezone.utc).isoformat()}")
    lines.append(f"sheets_hash={h_sheets}")
    lines.append(f"sqlite_hash={h_sqlite}")
    lines.append(
        f"sheets rows: txn={p_sheets['txn_rows']} realized={p_sheets['realized_rows']} "
        f"tax_lots={p_sheets['tax_lot_rows']}"
    )
    lines.append(
        f"sqlite rows: txn={p_sqlite['txn_rows']} realized={p_sqlite['realized_rows']} "
        f"tax_lots={p_sqlite['tax_lot_rows']}"
    )

    diffs: list[str] = []
    for key in sorted(set(p_sheets) | set(p_sqlite)):
        if p_sheets.get(key) != p_sqlite.get(key):
            diffs.append(f"{key}: sheets={p_sheets.get(key)!r} sqlite={p_sqlite.get(key)!r}")

    if h_sheets == h_sqlite:
        lines.append("MATCH")
        result = BundleParityResult(
            ok=True,
            sheets_hash=h_sheets,
            sqlite_hash=h_sqlite,
            lines=lines,
        )
    else:
        lines.append("DIFFER")
        for d in diffs[:max_diff_paths]:
            lines.append(f"  path {d}")
        result = BundleParityResult(
            ok=False,
            sheets_hash=h_sheets,
            sqlite_hash=h_sqlite,
            lines=lines,
            differing_paths=diffs[:max_diff_paths],
        )

    try:
        from core.store.verify import record_parity_result

        record_parity_result(ok=result.ok, sheets_hash=h_sheets, sqlite_hash=h_sqlite)
    except Exception as e:
        lines.append(f"parity streak record failed: {e}")
        result.lines = lines

    return result
