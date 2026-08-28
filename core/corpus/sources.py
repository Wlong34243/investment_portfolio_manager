"""Declarative corpus source registry. Add a source = entry + reader, not new control flow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from utils.moment_windows import load_ticker_aliases

REPO_ROOT = Path(__file__).resolve().parents[2]

_DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")
_FM_DATE = re.compile(r"(?m)^(?:date|as_of|established)\s*:\s*['\"]?(\d{4}-\d{2}-\d{2})")


@dataclass
class DocPayload:
    title: str
    body: str
    doc_date: Optional[date]
    tickers: list[str]
    date_is_inferred: bool
    body_line_base: int = 0


@dataclass
class SourceSpec:
    source_type: str
    glob: str
    reader: Callable[[Path], DocPayload]
    is_bills_writing: bool
    is_model_output: bool
    is_authoritative: bool = False


def _norm_path(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        rel = path
    return rel.as_posix()


def _date_from_name(path: Path) -> Optional[date]:
    m = _DATE_IN_NAME.search(path.name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _date_from_frontmatter(text: str) -> Optional[date]:
    m = _FM_DATE.search(text[:4000])
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _strip_frontmatter(text: str) -> tuple[str, str, int]:
    """
    Return (frontmatter, body, body_line_base).

    body_line_base: newlines before body start — add to chunker line numbers
    for coordinates in the original file on disk.
    """
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            body_start = end + 4
            while body_start < len(text) and text[body_start] == "\n":
                body_start += 1
            body = text[body_start:]
            base = text.count("\n", 0, body_start)
            return fm, body, base
    return "", text, 0


_alias_cache: Optional[dict[str, list[str]]] = None


def _aliases() -> dict[str, list[str]]:
    global _alias_cache
    if _alias_cache is None:
        try:
            _alias_cache = load_ticker_aliases()
        except OSError:
            _alias_cache = {}
    return _alias_cache


def tag_tickers(text: str, extra: Optional[list[str]] = None) -> list[str]:
    """Reuse moment_windows alias patterns — do not fork a second matcher."""
    from utils.moment_windows import _alias_patterns

    found: set[str] = set(extra or [])
    patterns = _alias_patterns(_aliases())
    # Also match bare tickers that appear as $TICKER or whole-word uppercase
    for ticker, pat in patterns:
        if pat.search(text):
            found.add(ticker)
    for m in re.finditer(r"\$([A-Z]{1,5})\b", text):
        found.add(m.group(1))
    return sorted(found)


def _read_markdown(path: Path, *, ticker_from_stem: bool = False) -> DocPayload:
    raw = path.read_text(encoding="utf-8", errors="replace")
    fm, body, body_line_base = _strip_frontmatter(raw)
    title = path.stem.replace("_", " ")
    for line in (fm or "").splitlines():
        if line.lower().startswith("title:"):
            title = line.split(":", 1)[1].strip().strip("'\"")
            break
    doc_date = _date_from_frontmatter(raw) or _date_from_name(path)
    inferred = doc_date is None
    if inferred:
        doc_date = datetime.fromtimestamp(path.stat().st_mtime).date()
    extra = []
    if ticker_from_stem:
        stem = path.stem
        if stem.endswith("_thesis"):
            extra.append(stem[: -len("_thesis")].upper())
        else:
            extra.append(stem.upper())
    tickers = tag_tickers(body, extra=extra)
    return DocPayload(
        title=title,
        body=body,
        doc_date=doc_date,
        tickers=tickers,
        date_is_inferred=inferred,
        body_line_base=body_line_base,
    )


def _read_plain(path: Path) -> DocPayload:
    body = path.read_text(encoding="utf-8", errors="replace")
    doc_date = _date_from_name(path)
    inferred = doc_date is None
    if inferred:
        doc_date = datetime.fromtimestamp(path.stat().st_mtime).date()
    return DocPayload(
        title=path.stem,
        body=body,
        doc_date=doc_date,
        tickers=tag_tickers(body),
        date_is_inferred=inferred,
    )


def _read_moment(path: Path) -> DocPayload:
    data = json.loads(path.read_text(encoding="utf-8"))
    moments = data.get("moments") or []
    parts = []
    tickers: set[str] = set()
    for m in moments:
        frag = m.get("fragment") or ""
        ctx = m.get("context") or ""
        cue = m.get("cue_matched") or m.get("moment_type") or ""
        src = m.get("source_episode") or ""
        parts.append(f"[moment] cue={cue} source={src}\n{frag}\n{ctx}")
        for t in m.get("tickers_touched") or []:
            tickers.add(str(t).upper())
    body = "\n\n".join(parts) if parts else path.read_text(encoding="utf-8", errors="replace")
    doc_date = _date_from_name(path)
    inferred = doc_date is None
    if inferred:
        doc_date = datetime.fromtimestamp(path.stat().st_mtime).date()
    return DocPayload(
        title=path.stem,
        body=body,
        doc_date=doc_date,
        tickers=sorted(tickers) or tag_tickers(body),
        date_is_inferred=inferred,
    )


SOURCES: list[SourceSpec] = [
    SourceSpec("thesis", "vault/theses/*.md", lambda p: _read_markdown(p, ticker_from_stem=True), True, False),
    SourceSpec(
        "thesis_archive",
        "vault/theses/archive/*.md",
        lambda p: _read_markdown(p, ticker_from_stem=True),
        True,
        False,
    ),
    SourceSpec("doctrine", "vault/doctrine.md", _read_markdown, True, False, is_authoritative=True),
    SourceSpec("research", "vault/research/**/*.md", _read_markdown, False, False),
    # framework: deliberately omitted. vault/frameworks/ currently holds only
    # desktop.ini (JSON frameworks live under archive/vault_frameworks_dup_*).
    # Re-add with a JSON reader when live framework files return — do not leave
    # a source_type that indexes zero files and silently returns no hits.
    SourceSpec("transcript", "data/podcast_transcripts/*", _read_plain, False, False),
    SourceSpec("podcast_summary", "data/podcast_summaries/*.md", _read_plain, False, True),
    # Prompt glob said *.md under spotify_digests; live tree keeps allocation-*.txt
    # corpus copies there and writes PROVENANCE onto the podcast_summaries Spotify_*.md.
    # Index both: raw digest text + provenance-stamped summary (distinct paths).
    SourceSpec("spotify_digest", "data/spotify_digests/allocation-*.txt", _read_plain, False, False),
    SourceSpec(
        "spotify_digest",
        "data/podcast_summaries/*Spotify_Podcast_Aggregate*",
        _read_markdown,
        False,
        False,
    ),
    SourceSpec("moment", "data/moments/*.moments.json", _read_moment, False, False),
    SourceSpec("agent_output", "agent_outputs/**/*.md", _read_markdown, False, True),
]


def iter_source_files(source_type: Optional[str] = None) -> list[tuple[SourceSpec, Path]]:
    out: list[tuple[SourceSpec, Path]] = []
    for spec in SOURCES:
        if source_type and spec.source_type != source_type:
            continue
        for path in sorted(REPO_ROOT.glob(spec.glob)):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name.endswith(".bak") or ".bak." in name or name == "desktop.ini":
                continue
            # podcast_summaries verification sidecars stay indexable as summaries if under glob;
            # exclude nested verification/ only when under summaries
            rel = _norm_path(path)
            if "/verification/" in rel:
                continue
            # Spotify aggregates are registered as spotify_digest, not podcast_summary
            if spec.source_type == "podcast_summary" and "Spotify_Podcast_Aggregate" in path.name:
                continue
            out.append((spec, path))
    return out


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
