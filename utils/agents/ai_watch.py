"""
AI Watch — cross-source read of AI briefs (sandbox agent).

Python gathers counts; single Gemini call narrates. Output: agent_outputs/ai_watch/ only.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

import config
from utils.gemini_client import ask_gemini
from utils.agents.ai_research_analyst import validate_brief

logger = logging.getLogger(__name__)

BRIEFS_DIR = Path("data/ai_briefs")
OUTPUT_DIR = Path("agent_outputs/ai_watch")


@dataclass
class AIWatchInput:
    window_days: int
    briefs_by_channel: dict[str, int] = field(default_factory=dict)
    zero_brief_channels: list[str] = field(default_factory=list)
    claim_inventory: list[dict[str, Any]] = field(default_factory=list)
    named_systems: dict[str, list[str]] = field(default_factory=dict)
    theme_clusters: list[dict[str, Any]] = field(default_factory=list)
    new_results: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)


class AIWatchNarration(BaseModel):
    what_is_new: str = Field(description="Section 1 prose")
    themes_this_period: str = Field(description="Section 2 prose")
    contested: str = Field(description="Section 3 prose")
    unverified_specifics: str = Field(description="Section 4 prose")
    quiet_channels: str = Field(description="Section 5 prose")


def _brief_date(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.name[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _channel_from_json(data: dict, path: Path) -> str:
    if data.get("channel"):
        return str(data["channel"])
    parts = path.stem.split("_")
    if len(parts) >= 2:
        return parts[1].replace("_", " ")
    return "unknown"


def gather(days: int = 7) -> AIWatchInput:
    from utils.channel_registry import load_channels

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    ai_channels = [c["name"] for c in load_channels("ai")]

    by_channel: Counter[str] = Counter()
    claims: list[dict[str, Any]] = []
    systems: dict[str, set[str]] = defaultdict(set)
    new_results: list[dict[str, Any]] = []
    figure_claims: list[dict[str, Any]] = []
    source_files: list[str] = []

    for path in sorted(BRIEFS_DIR.glob("*.json")):
        bd = _brief_date(path)
        if bd and bd < cutoff:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ch = _channel_from_json(data, path)
        by_channel[ch] += 1
        source_files.append(path.as_posix())

        for c in data.get("claims") or []:
            if not isinstance(c, dict):
                continue
            claims.append(
                {
                    "claim": c.get("claim"),
                    "claim_type": c.get("claim_type"),
                    "specificity": c.get("specificity"),
                    "attributed_to": c.get("attributed_to"),
                    "source": path.name,
                }
            )
            if c.get("specificity") == "named_figure":
                figure_claims.append({"claim": c.get("claim"), "source": path.name})

        for sys_name in data.get("named_systems") or []:
            if sys_name:
                systems[sys_name].add(path.name)

        if data.get("novelty") == "new_result":
            new_results.append(
                {"headline": data.get("headline"), "source": path.name, "channel": ch}
            )

    zero_brief = [c for c in ai_channels if by_channel.get(c, 0) == 0]

    # Theme clusters: systems appearing in >=2 briefs
    clusters = []
    for sys_name, srcs in systems.items():
        if len(srcs) >= 2:
            clusters.append({"system": sys_name, "sources": sorted(srcs), "count": len(srcs)})

    # Contradiction candidates: same benchmark keyword in named_figure claims (heuristic)
    contradictions: list[dict[str, Any]] = []
    bench_claims = [c for c in claims if c.get("claim_type") == "benchmark"]
    by_snippet: dict[str, list] = defaultdict(list)
    for c in bench_claims:
        key = (c.get("claim") or "")[:40].lower()
        by_snippet[key].append(c)
    for key, group in by_snippet.items():
        if len(group) >= 2 and len({g.get("claim") for g in group}) > 1:
            contradictions.append({"topic": key, "claims": group})

    return AIWatchInput(
        window_days=days,
        briefs_by_channel=dict(by_channel),
        zero_brief_channels=zero_brief,
        claim_inventory=claims,
        named_systems={k: sorted(v) for k, v in systems.items()},
        theme_clusters=clusters,
        new_results=new_results,
        contradictions=contradictions,
        source_files=source_files,
    )


def _gather_prompt(g: AIWatchInput) -> str:
    payload = {
        "window_days": g.window_days,
        "briefs_by_channel": g.briefs_by_channel,
        "zero_brief_channels": g.zero_brief_channels,
        "claim_count": len(g.claim_inventory),
        "named_systems_frequency": {k: len(v) for k, v in g.named_systems.items()},
        "theme_clusters": g.theme_clusters,
        "new_results": g.new_results,
        "contradictions": g.contradictions,
        "named_figure_claims": [
            c for c in g.claim_inventory if c.get("specificity") == "named_figure"
        ],
    }
    return (
        "Write an AI Watch report using ONLY the counts and lists below. "
        "Do not invent numbers. Count each theme once across sources; name every source.\n"
        "No tickers, no buy/sell, no portfolio advice.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )


def _system_instruction() -> str:
    return (
        "You are narrating a structured AI capability watch report for a technical reader.\n"
        "Use exactly these five sections in order:\n"
        "1. What is new — new_result briefs only\n"
        "2. Themes this period — deduplicated clusters; label single-source themes\n"
        "3. Contested — show both figures, do not adjudicate\n"
        "4. Unverified specifics — every named_figure claim flagged unchecked\n"
        "5. Quiet channels — zero-brief channels and single-source systems\n"
        "Never recommend trades or cite portfolio positions."
    )


def run(days: int = 7, live: bool = False) -> Path | None:
    g = gather(days)
    if not g.source_files:
        print("No AI briefs in window — nothing to analyse.")
        return None

    result = ask_gemini(
        prompt=_gather_prompt(g),
        system_instruction=_system_instruction(),
        response_schema=AIWatchNarration,
        max_tokens=getattr(config, "GEMINI_MAX_TOKENS_PODCAST", 8000),
    )
    if result is None:
        logger.error("AI Watch narration failed")
        return None

    sections = result.model_dump()
    body = "\n\n".join(
        [
            f"## What is new\n{sections['what_is_new']}",
            f"## Themes this period\n{sections['themes_this_period']}",
            f"## Contested\n{sections['contested']}",
            f"## Unverified specifics\n{sections['unverified_specifics']}",
            f"## Quiet channels\n{sections['quiet_channels']}",
        ]
    )
    full_text = f"# AI Watch ({days}-day window)\n\n{body}\n"
    # Rule-2 backstop on output
    fake_brief = {"headline": "x", "summary": full_text, "claims": [], "named_orgs": [], "novelty": "commentary", "source_quality": "Low"}
    violations = validate_brief(fake_brief)
    if violations:
        print("OUTPUT VALIDATION FAILED:")
        for v in violations:
            print(f"  - {v}")
        return None

    provenance = (
        f"*PROVENANCE: Model-generated AI Watch report. Sources: {', '.join(g.source_files)}. "
        f"Window: {days} days. Not reviewed.*\n\n"
    )
    report = provenance + full_text

    if not live:
        print(report)
        print("\n--- DRY RUN --- No file written. Use --live to write.")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_ai_watch.md"
    out.write_text(report, encoding="utf-8")
    print(f"Wrote {out}")
    return out
