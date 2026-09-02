"""Assertion cards — load proposed decisions and desk ratification."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent


def _conditions_plain(conditions: dict) -> str:
    op = conditions.get("operator", "all")
    legs = conditions.get("legs") or []
    parts = []
    for leg in legs:
        parts.append(f"{leg.get('metric')} {leg.get('comparator')} {leg.get('value')}")
    joiner = " AND " if op == "all" else " OR "
    return joiner.join(parts) if parts else "(none)"


def load_proposed_assertions() -> list[dict[str, Any]]:
    from core.decisions.store import load_proposals

    cards: list[dict[str, Any]] = []
    for rec in load_proposals(status="proposed"):
        d = rec.to_dict()
        d["conditions_plain"] = _conditions_plain(d.get("conditions") or {})
        cards.append(d)
    return cards


def sort_assertions(cards: list[dict[str, Any]], crosshair_tickers: set[str]) -> list[dict[str, Any]]:
    implicated: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for card in cards:
        tickers = {str(t).upper() for t in (card.get("tickers") or [])}
        if tickers & crosshair_tickers:
            card = dict(card)
            card["signal_implicated"] = True
            implicated.append(card)
        else:
            card = dict(card)
            card["signal_implicated"] = False
            other.append(card)
    return implicated + other


def _apply_decided_on(rec: Any, decided_on: Optional[str]) -> Optional[str]:
    if rec.decided_on_status != "unknown":
        return None
    if not decided_on or not str(decided_on).strip():
        return "decided_on required when decided_on_status is unknown"
    rec.decided_on = str(decided_on).strip()[:10]
    rec.decided_on_status = "known"
    return None


def ratify_proposal(
    decision_id: str,
    action: str,
    text: str = "",
    decided_on: Optional[str] = None,
    *,
    live: bool = True,
) -> dict[str, Any]:
    """
    Confirm / Correct / Reject a proposed decision.

    action: confirm | correct | reject
    """
    from core.decisions.schema import DecisionRecord
    from core.decisions.store import load_proposal, update_proposal_status, write_binding
    from utils.thesis_utils import ThesisManager

    rec = load_proposal(decision_id)
    if rec is None:
        return {"ok": False, "error": f"Proposal {decision_id!r} not found"}
    if rec.status != "proposed":
        return {"ok": False, "error": f"Proposal status is {rec.status!r}, not proposed"}

    action = action.strip().lower()
    today = date.today().isoformat()

    if action == "reject":
        reason = text.strip() or "rejected at desk"
        if not live:
            return {"ok": True, "dry_run": True, "action": "reject", "reason": reason}
        out = update_proposal_status(decision_id, "rejected", rejection_reason=reason, live=True)
        return {"ok": out.get("ok", False), "action": "reject", **out}

    if action not in ("confirm", "correct"):
        return {"ok": False, "error": f"Unknown action {action!r}"}

    date_err = _apply_decided_on(rec, decided_on)
    if date_err:
        return {"ok": False, "error": date_err}

    if action == "confirm":
        rec.proposed_restatement = None
    elif action == "correct":
        if not text.strip():
            return {"ok": False, "error": "Correct requires restatement text"}
        rec.restatement = text.strip()
        rec.restatement_author = "bill"
        rec.proposed_restatement = None

    if not live:
        return {
            "ok": True,
            "dry_run": True,
            "action": action,
            "would_write": f"vault/decisions/{decision_id}.md",
            "tickers": rec.tickers,
        }

    bind_out = write_binding(rec, ratification=True, live=True)
    if not bind_out.get("ok"):
        return bind_out

    update_proposal_status(
        decision_id,
        "ratified",
        ratified_on=today,
        decided_on=rec.decided_on,
        decided_on_status=rec.decided_on_status,
        restatement=rec.restatement,
        restatement_author=rec.restatement_author,
        clear_proposed_restatement=True,
        live=True,
    )

    thesis_paths: list[str] = []
    for ticker in rec.tickers:
        t = str(ticker).strip().upper()
        path = ROOT / "vault" / "theses" / f"{t}_thesis.md"
        if not path.is_file():
            continue
        backup = path.with_suffix(path.suffix + f".bak.{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        mgr = ThesisManager(path)
        mgr.update_frontmatter({"last_ratified": today})
        mgr.save(backup=False)
        thesis_paths.append(str(path))

    return {
        "ok": True,
        "action": action,
        "binding_path": bind_out.get("path"),
        "thesis_paths": thesis_paths,
    }
