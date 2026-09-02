"""Resolve source_ref paths and verify verbatim assertion substrings."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_LINE_SUFFIX_RE = re.compile(r"#L(\d+)$", re.I)


def normalize_ws(text: str) -> str:
    return " ".join((text or "").split())


def resolve_source_path(source_ref: str, root: Path = REPO_ROOT) -> Path:
    path_part = source_ref.split("#")[0].strip()
    return root / path_part


def source_excerpt(source_ref: str, root: Path = REPO_ROOT) -> str:
    """Return line at #L suffix when present, else full file text."""
    path = resolve_source_path(source_ref, root)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    text = path.read_text(encoding="utf-8")
    m = _LINE_SUFFIX_RE.search(source_ref.strip())
    if m:
        line_no = int(m.group(1))
        lines = text.splitlines()
        if 1 <= line_no <= len(lines):
            return lines[line_no - 1]
    return text


def assertion_in_source(assertion: str, source_ref: str, root: Path = REPO_ROOT) -> bool:
    """True when assertion is a whitespace-normalized substring of the cited source line."""
    ok, _ = assertion_on_source_line(assertion, source_ref, root=root)
    return ok


def assertion_on_source_line(
    assertion: str, source_ref: str, root: Path = REPO_ROOT
) -> tuple[bool, str]:
    """
    Verbatim check scoped to #L line when present.

    Returns (ok, error_hint). When #L is absent, checks whole file (discouraged).
    """
    if not assertion.strip() or not source_ref.strip():
        return False, "assertion and source_ref are required"
    if not _LINE_SUFFIX_RE.search(source_ref.strip()):
        try:
            hay = normalize_ws(source_excerpt(source_ref, root))
        except OSError:
            return False, f"source file not readable for {source_ref!r}"
        if normalize_ws(assertion) in hay:
            return True, ""
        return False, f"assertion not found in {source_ref!r} (no #L line suffix)"

    m = _LINE_SUFFIX_RE.search(source_ref.strip())
    line_no = int(m.group(1)) if m else 0
    try:
        hay = normalize_ws(source_excerpt(source_ref, root))
    except OSError:
        return False, f"source file not readable for {source_ref!r}"
    needle = normalize_ws(assertion)
    if needle in hay:
        return True, ""
    return False, f"assertion not found on line {line_no} of {source_ref.split('#')[0]!r}"
