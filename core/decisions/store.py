"""Decision record persistence — quarantine vs binding split."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

from ruamel.yaml import YAML

from core.decisions.schema import DecisionRecord
from core.decisions.validate import validate

REPO_ROOT = Path(__file__).resolve().parents[2]
PROPOSALS_DIR = REPO_ROOT / "data" / "decision_proposals"
BINDING_DIR = REPO_ROOT / "vault" / "decisions"


def _yaml() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def load_proposals(*, status: Optional[str] = None) -> list[DecisionRecord]:
    if not PROPOSALS_DIR.is_dir():
        return []
    out: list[DecisionRecord] = []
    for path in sorted(PROPOSALS_DIR.glob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rec = DecisionRecord.from_dict(data)
            if status is None or rec.status == status:
                out.append(rec)
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    return out


def load_proposal(decision_id: str) -> Optional[DecisionRecord]:
    path = PROPOSALS_DIR / f"{decision_id}.json"
    if not path.is_file():
        return None
    return DecisionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_proposal(record: DecisionRecord, *, live: bool = True) -> dict[str, Any]:
    """Write to quarantine. Rejects ratified status."""
    errs = validate(record, target="proposal")
    if errs:
        return {"ok": False, "errors": errs}
    path = PROPOSALS_DIR / f"{record.id}.json"
    if not live:
        return {"ok": True, "dry_run": True, "path": str(path)}
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path)}


def update_proposal_status(
    decision_id: str,
    status: str,
    *,
    rejection_reason: str = "",
    ratified_on: Optional[str] = None,
    decided_on: Optional[str] = None,
    decided_on_status: Optional[str] = None,
    restatement: Optional[str] = None,
    restatement_author: Optional[str] = None,
    clear_proposed_restatement: bool = False,
    live: bool = True,
) -> dict[str, Any]:
    rec = load_proposal(decision_id)
    if rec is None:
        return {"ok": False, "error": f"proposal {decision_id!r} not found"}
    rec.status = status
    if rejection_reason:
        rec.rejection_reason = rejection_reason
    if ratified_on:
        rec.ratified_on = ratified_on
    if decided_on is not None:
        rec.decided_on = decided_on
    if decided_on_status is not None:
        rec.decided_on_status = decided_on_status
    if restatement is not None:
        rec.restatement = restatement
    if restatement_author is not None:
        rec.restatement_author = restatement_author
    if clear_proposed_restatement:
        rec.proposed_restatement = None
    return write_proposal(rec, live=live)


def write_binding(record: DecisionRecord, *, ratification: bool = False, live: bool = True) -> dict[str, Any]:
    """Write to vault/decisions/. Requires ratification=True; never overwrites."""
    if not ratification:
        return {"ok": False, "error": "vault/decisions/ requires ratification=True"}
    rec = DecisionRecord.from_dict(record.to_dict())
    rec.status = "ratified"
    rec.proposed_restatement = None
    if not rec.ratified_on:
        rec.ratified_on = date.today().isoformat()
    errs = validate(rec, target="binding")
    if errs:
        return {"ok": False, "errors": errs}
    path = BINDING_DIR / f"{rec.id}.md"
    if path.is_file():
        return {"ok": False, "error": f"binding file already exists: {path}"}
    if not live:
        return {"ok": True, "dry_run": True, "path": str(path)}
    BINDING_DIR.mkdir(parents=True, exist_ok=True)
    yaml = _yaml()
    import io

    buf = io.StringIO()
    yaml.dump(rec.to_binding_dict(), buf)
    fm = buf.getvalue().rstrip()
    body_parts = [rec.assertion.strip()]
    if rec.restatement and rec.restatement.strip():
        body_parts.append(f"## Restatement ({rec.restatement_author or 'bill'})\n\n{rec.restatement.strip()}")
    if rec.falsifier.strip():
        body_parts.append("## Falsifier\n\n" + rec.falsifier.strip())
    content = f"---\n{fm}\n---\n\n" + "\n\n".join(body_parts) + "\n"
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(path)}
