"""
utils/doctrine_reader.py — Canonical reader for vault/doctrine.md.

Same role as thesis_reader for theses: one parse path for Crosshairs,
export_ai_briefing, and any later consumer. Missing or malformed doctrine
must never raise HEALTH_FAILURE or block a morning run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_DOCTRINE_PATH = Path("vault") / "doctrine.md"
KNOWN_ACTIONS = frozenset({"context_only", "downgrade_informational"})


@dataclass
class Constraint:
    id: str
    established: str
    scope: str
    summary: str
    affects: list[str] = field(default_factory=list)
    action: str = "context_only"
    tickers: list[str] = field(default_factory=list)
    restated: Optional[str] = None


@dataclass
class Doctrine:
    doctrine_version: int = 0
    updated: str = ""
    constraints: list[Constraint] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    path: Optional[Path] = None
    missing: bool = False

    def __str__(self) -> str:
        if self.missing:
            return "Doctrine(missing=True)"
        ids = [c.id for c in self.constraints]
        return (
            f"Doctrine(version={self.doctrine_version}, updated={self.updated!r}, "
            f"constraints={ids}, parse_errors={len(self.parse_errors)})"
        )


def _frontmatter_block(text: str) -> Optional[str]:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text[3:end].strip("\n")


def _parse_constraint(raw: Any, errors: list[str]) -> Optional[Constraint]:
    if not isinstance(raw, dict):
        errors.append(f"constraint is not a mapping: {type(raw).__name__}")
        return None
    cid = str(raw.get("id") or "").strip()
    if not cid:
        errors.append("constraint missing id")
        return None
    action = str(raw.get("action") or "").strip()
    if action and action not in KNOWN_ACTIONS:
        logger.warning("doctrine: unknown action %r on constraint %s — ignored", action, cid)
        errors.append(f"{cid}: unknown action {action!r}")
        return None
    if not action:
        action = "context_only"
    tickers_raw = raw.get("tickers") or []
    if not isinstance(tickers_raw, list):
        errors.append(f"{cid}: tickers must be a list")
        tickers_raw = []
    tickers = sorted({str(t).strip().upper() for t in tickers_raw if str(t).strip()})
    affects_raw = raw.get("affects") or []
    if not isinstance(affects_raw, list):
        affects_raw = []
    affects = [str(a).strip() for a in affects_raw if str(a).strip()]
    summary = str(raw.get("summary") or "").strip()
    return Constraint(
        id=cid,
        established=str(raw.get("established") or "").strip(),
        scope=str(raw.get("scope") or "").strip(),
        summary=summary,
        affects=affects,
        action=action,
        tickers=tickers,
        restated=(str(raw["restated"]).strip() if raw.get("restated") else None),
    )


def load_doctrine(path: Path | None = None) -> Doctrine:
    """Load doctrine. Missing file → empty Doctrine(missing=True). Never raises."""
    p = Path(path) if path is not None else DEFAULT_DOCTRINE_PATH
    if not p.is_file():
        return Doctrine(missing=True, path=p)

    errors: list[str] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        return Doctrine(missing=True, path=p, parse_errors=[str(e)])

    if not _YAML_AVAILABLE:
        return Doctrine(
            path=p,
            parse_errors=["PyYAML not available — doctrine frontmatter not parsed"],
        )

    block = _frontmatter_block(text)
    if block is None:
        return Doctrine(path=p, parse_errors=["no YAML frontmatter block"])

    try:
        data = _yaml.safe_load(block) or {}
    except Exception as e:
        return Doctrine(path=p, parse_errors=[f"YAML parse failed: {e}"])

    if not isinstance(data, dict):
        return Doctrine(path=p, parse_errors=["frontmatter is not a mapping"])

    constraints: list[Constraint] = []
    raw_list = data.get("constraints") or []
    if not isinstance(raw_list, list):
        errors.append("constraints is not a list")
        raw_list = []
    for raw in raw_list:
        c = _parse_constraint(raw, errors)
        if c is not None:
            constraints.append(c)

    try:
        version = int(data.get("doctrine_version") or 0)
    except (TypeError, ValueError):
        version = 0
        errors.append("doctrine_version not an int")

    return Doctrine(
        doctrine_version=version,
        updated=str(data.get("updated") or "").strip(),
        constraints=constraints,
        parse_errors=errors,
        path=p,
        missing=False,
    )


def constraints_for_ticker(doctrine: Doctrine, ticker: str) -> list[Constraint]:
    t = (ticker or "").strip().upper()
    out: list[Constraint] = []
    for c in doctrine.constraints:
        if c.scope == "portfolio":
            out.append(c)
        elif t and t in c.tickers:
            out.append(c)
    return out


def downgrade_rule(
    doctrine: Doctrine, ticker: str, reason_code: str
) -> Optional[Constraint]:
    """First matching downgrade_informational constraint for ticker + reason_code."""
    t = (ticker or "").strip().upper()
    rc = (reason_code or "").strip()
    for c in doctrine.constraints:
        if c.action != "downgrade_informational":
            continue
        if rc not in c.affects:
            continue
        if c.scope == "position" and t in c.tickers:
            return c
        if c.scope == "portfolio":
            return c
    return None
