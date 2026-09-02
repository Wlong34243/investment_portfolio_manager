"""Deterministic AI thematic index — reads JSON brief sidecars, no LLM."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.retrieval.api import TemplateCall, retrieve
from utils.moment_windows import _alias_patterns, _word_pattern, load_ticker_aliases

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIEFS_DIR = REPO_ROOT / "data" / "ai_briefs"
INDEX_PATH = REPO_ROOT / "data" / "ai_thematic_index.json"
ENTITY_ALIASES_PATH = REPO_ROOT / "data" / "ai_entity_aliases.json"
VERIFICATION_DIR = BRIEFS_DIR / "verification"

_DATE_PREFIX = re.compile(r"^(20\d{2}-\d{2}-\d{2})")


def _load_merged_aliases() -> tuple[dict[str, list[str]], set[str]]:
    base = load_ticker_aliases(str(REPO_ROOT / "data" / "ticker_aliases.json"))
    unlisted: set[str] = set()
    if ENTITY_ALIASES_PATH.exists():
        extra = json.loads(ENTITY_ALIASES_PATH.read_text(encoding="utf-8"))
        for ticker, aliases in (extra.get("tickers") or {}).items():
            base[ticker] = list(set(base.get(ticker, []) + aliases))
        unlisted = set(extra.get("unlisted") or [])
    return base, unlisted


def _held_tickers() -> set[str]:
    rs = retrieve(
        label="ai_index",
        caller="cli",
        queries=[TemplateCall("holdings_current", {})],
    )
    rows = rs.tables.get("holdings_current", [])
    out: set[str] = set()
    for r in rows:
        t = str(r.get("ticker") or r.get("Ticker") or "").upper()
        if t:
            out.add(t)
    return out


def _match_entities(
    names: list[str],
    alias_patterns: list[tuple[str, re.Pattern]],
    held: set[str],
    unlisted_allow: set[str],
) -> tuple[list[dict], list[dict], list[str], list[str]]:
    exposed: list[dict] = []
    listed_unheld: list[dict] = []
    unlisted: list[str] = []
    unmatched: list[str] = []

    seen_exposed: set[str] = set()
    seen_unheld: set[str] = set()

    for name in names:
        if not name or not str(name).strip():
            continue
        name = str(name).strip()
        if name in unlisted_allow:
            unlisted.append(name)
            continue

        matched_ticker: str | None = None
        matched_on: str | None = None
        for ticker, pattern in alias_patterns:
            if pattern.search(name):
                matched_ticker = ticker
                matched_on = name
                break

        if not matched_ticker:
            unmatched.append(name)
            continue

        if matched_ticker in held:
            if matched_ticker not in seen_exposed:
                exposed.append({"ticker": matched_ticker, "matched_on": matched_on or name})
                seen_exposed.add(matched_ticker)
        else:
            if matched_ticker not in seen_unheld:
                listed_unheld.append({"ticker": matched_ticker, "matched_on": matched_on or name})
                seen_unheld.add(matched_ticker)

    return exposed, listed_unheld, unlisted, unmatched


def _has_verification_sidecar(transcript_sha256: str) -> bool:
    if not transcript_sha256 or not VERIFICATION_DIR.exists():
        return False
    for p in VERIFICATION_DIR.glob("*"):
        if transcript_sha256[:16] in p.name or transcript_sha256 in p.read_text(encoding="utf-8", errors="ignore"):
            return True
    return False


def _brief_window_path(path: Path, days: int | None) -> bool:
    if days is None:
        return True
    m = _DATE_PREFIX.match(path.name)
    if not m:
        return True
    try:
        d = datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError:
        return True
    return d >= datetime.now() - timedelta(days=days)


def build_index(days: int | None = None) -> dict[str, Any]:
    aliases, unlisted_allow = _load_merged_aliases()
    patterns = _alias_patterns(aliases)
    held = _held_tickers()

    entries: list[dict[str, Any]] = []
    novelty_counts: Counter[str] = Counter()
    named_figure_total = 0
    ticker_mentions: Counter[str] = Counter()
    unmatched_all: Counter[str] = Counter()
    channels_with_briefs: set[str] = set()

    for json_path in sorted(BRIEFS_DIR.glob("*.json")):
        if not _brief_window_path(json_path, days):
            continue
        data = json.loads(json_path.read_text(encoding="utf-8"))
        md_path = json_path.with_suffix(".md")
        date_str = json_path.name[:10] if _DATE_PREFIX.match(json_path.name) else "unknown"
        channel = data.get("channel") or "unknown"
        channels_with_briefs.add(channel)

        names = list(data.get("named_orgs") or []) + list(data.get("named_systems") or [])
        exposed, listed_unheld, unlisted, unmatched = _match_entities(
            names, patterns, held, unlisted_allow
        )
        for u in unmatched:
            unmatched_all[u] += 1

        nf = sum(
            1
            for c in data.get("claims") or []
            if isinstance(c, dict) and c.get("specificity") == "named_figure"
        )
        qual = sum(
            1
            for c in data.get("claims") or []
            if isinstance(c, dict) and c.get("specificity") == "qualitative"
        )
        named_figure_total += nf
        novelty_counts[data.get("novelty") or "unknown"] += 1

        for bucket in (exposed, listed_unheld):
            for item in bucket:
                ticker_mentions[item["ticker"]] += 1
        for name in unlisted:
            ticker_mentions[f"unlisted:{name}"] += 1

        sha = ""
        if md_path.exists():
            m = re.search(r"transcript_sha256:\s*([a-f0-9]{64})", md_path.read_text(encoding="utf-8"))
            if m:
                sha = m.group(1)

        vid = ""
        vm = re.search(r"watch\?v=([A-Za-z0-9_-]+)", md_path.read_text(encoding="utf-8") if md_path.exists() else "")
        if vm:
            vid = vm.group(1)

        entries.append(
            {
                "brief_path": md_path.as_posix() if md_path.exists() else json_path.as_posix(),
                "video_url": f"https://www.youtube.com/watch?v={vid}" if vid else "",
                "channel": channel,
                "date": date_str,
                "headline": data.get("headline"),
                "novelty": data.get("novelty"),
                "source_quality": data.get("source_quality"),
                "named_figure_claims": nf,
                "qualitative_claims": qual,
                "exposed": exposed,
                "listed_unheld": listed_unheld,
                "unlisted": unlisted,
                "verified": _has_verification_sidecar(sha),
            }
        )

    from utils.channel_registry import load_channels

    ai_names = [c["name"] for c in load_channels("ai")]
    quiet = [c for c in ai_names if c not in channels_with_briefs]

    return {
        "generated_at": datetime.now().isoformat(),
        "window_days": days,
        "entries": sorted(entries, key=lambda e: e.get("date") or "", reverse=True),
        "ingestion_state": "ok" if entries else "no_briefs",
        "rollup": {
            "brief_count": len(entries),
            "novelty": dict(novelty_counts),
            "named_figure_claims_total": named_figure_total,
            "ticker_mentions": dict(ticker_mentions),
            "quiet_channels": quiet,
            "unmatched_entities": dict(unmatched_all.most_common(50)),
        },
    }


def write_index(index: dict[str, Any], live: bool = False, allow_empty: bool = False) -> Path | None:
    """Write the index. Refuses to persist a zero-brief index unless forced.

    An index with brief_count 0 and every channel in quiet_channels is
    indistinguishable from a genuinely quiet week, and the cockpit tile would
    render "all quiet" while ingestion was dead. That is what happened on
    2026-08-31. A refusal is louder and cannot be misread.
    """
    text = json.dumps(index, indent=2) + "\n"
    if not live:
        print(text)
        print("\n--- DRY RUN --- No file written. Use --live to write.")
        return None
    if not index.get("entries") and not allow_empty:
        print(
            "REFUSED: 0 briefs found — not overwriting the index. "
            "Ingestion has probably failed; check the AI batch run. "
            "Use --allow-empty to override."
        )
        return None
    INDEX_PATH.write_text(text, encoding="utf-8")
    return INDEX_PATH
