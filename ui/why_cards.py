"""Why-cards assembly + write helpers (Lane A position + Lane B rotation)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent


def newest_briefing_manifest(exports_dir: Path | str = "exports") -> Optional[Path]:
    root = Path(exports_dir)
    if not root.is_dir():
        return None
    candidates: list[tuple[float, Path]] = []
    for p in root.iterdir():
        if not p.is_dir() or not p.name.startswith("ai_briefing_"):
            continue
        mf = p / "manifest.json"
        if mf.is_file():
            candidates.append((mf.stat().st_mtime, mf))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1].parent.name), reverse=True)
    return candidates[0][1]


def load_position_findings(exports_dir: Path | str = "exports") -> list[dict[str, Any]]:
    mf = newest_briefing_manifest(exports_dir)
    if mf is None:
        return []
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    block = data.get("undocumented_changes") or {}
    findings = block.get("findings") or []
    return [f for f in findings if isinstance(f, dict)]


def load_rotation_cards() -> list[dict[str, Any]]:
    from core.journal.reconcile import load_unreconciled_clusters

    out: list[dict[str, Any]] = []
    for c in load_unreconciled_clusters():
        if c.source != "trade_log":
            continue
        out.append(
            {
                "trade_log_id": c.cluster_id,
                "cluster_id": c.cluster_id,
                "fingerprint": c.fingerprint,
                "fill_date": c.fill_date.isoformat() if c.fill_date else "",
                "sell_tickers": c.sell_tickers,
                "buy_tickers": c.buy_tickers,
                "implicit_bet": c.implicit_bet,
                "question": "What was the substitution thesis for this basket?",
            }
        )
    return out


def write_position_answer(ticker: str, answer: str, *, live: bool = True) -> dict[str, Any]:
    """Append Review Log entry via ThesisManager. Dry-run when live=False."""
    from utils.thesis_utils import ThesisManager

    t = ticker.strip().upper()
    path = ROOT / "vault" / "theses" / f"{t}_thesis.md"
    if not path.is_file():
        return {"ok": False, "error": f"No thesis file for {t}"}
    text = answer.strip()
    if not text:
        return {"ok": False, "error": "Empty answer"}
    today = date.today().isoformat()
    if not live:
        return {"ok": True, "dry_run": True, "ticker": t, "would_append": f"- {today}: {text}"}
    backup = path.with_suffix(path.suffix + f".bak.{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    mgr = ThesisManager(path)
    mgr.append_review_log_entry(today, text)
    mgr.update_frontmatter({"last_reviewed": today})
    mgr.save(backup=False)
    return {"ok": True, "ticker": t, "path": str(path)}


def write_rotation_answer(
    trade_log_id: str,
    fingerprint: str,
    implicit_bet: str,
    thesis_brief: str = "",
    *,
    live: bool = True,
) -> dict[str, Any]:
    """Update Trade_Log row in one batch. Refuses fingerprint mismatch."""
    import config
    from utils.sheet_readers import get_gspread_client
    from utils.sheet_writers import safe_execute

    bet = implicit_bet.strip()
    if not bet:
        return {"ok": False, "error": "Implicit_Bet required"}
    if not live:
        return {
            "ok": True,
            "dry_run": True,
            "trade_log_id": trade_log_id,
            "would_write": {"Implicit_Bet": bet},
        }

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = safe_execute(ss.worksheet, config.TAB_TRADE_LOG)
    rows = safe_execute(ws.get_all_values)
    if not rows:
        return {"ok": False, "error": "Trade_Log empty"}
    headers = [h.strip() for h in rows[0]]
    try:
        id_col = headers.index("Trade_Log_ID")
        fp_col = headers.index("Fingerprint")
        bet_col = headers.index("Implicit_Bet")
        brief_col = headers.index("Thesis_Brief")
        prov_col = headers.index("Rationale_Provenance")
        ev_col = headers.index("Rationale_Evidence")
    except ValueError as e:
        return {"ok": False, "error": f"Trade_Log header missing: {e}"}

    target_row = None
    for i, row in enumerate(rows[1:], start=2):
        if len(row) <= id_col:
            continue
        if str(row[id_col]).strip() != str(trade_log_id).strip():
            continue
        sheet_fp = str(row[fp_col]).strip() if len(row) > fp_col else ""
        if sheet_fp != str(fingerprint).strip():
            return {
                "ok": False,
                "error": "Fingerprint mismatch — row changed under you",
                "expected": fingerprint,
                "actual": sheet_fp,
            }
        target_row = i
        break
    if target_row is None:
        return {"ok": False, "error": f"Trade_Log_ID {trade_log_id!r} not found"}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updates = [
        {"range": _col_letter(bet_col + 1) + str(target_row), "values": [[bet]]},
        {"range": _col_letter(prov_col + 1) + str(target_row), "values": [["reconstructed_after"]]},
        {"range": _col_letter(ev_col + 1) + str(target_row), "values": [[f"desk why-card {ts}"]]},
    ]
    if thesis_brief.strip():
        updates.append(
            {"range": _col_letter(brief_col + 1) + str(target_row), "values": [[thesis_brief.strip()]]}
        )
    safe_execute(ws.batch_update, updates, value_input_option="USER_ENTERED")

    # read-back
    after = safe_execute(ws.row_values, target_row)
    if len(after) <= bet_col or after[bet_col].strip() != bet:
        return {"ok": False, "error": "Post-write verification failed"}
    return {"ok": True, "trade_log_id": trade_log_id, "row": target_row}


def _col_letter(n: int) -> str:
    """1-based column index to A1 letter."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s
