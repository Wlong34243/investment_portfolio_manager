"""
AI-track research brief extractor — mechanism-only, no allocation surface.

Sibling to podcast_analyst.py; output goes to data/ai_briefs/, not the bundle.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

import config
from utils.gemini_client import ask_gemini

logger = logging.getLogger(__name__)

CLAIM_TYPES = frozenset({"capability", "benchmark", "release", "cost", "policy", "opinion"})
SPECIFICITY_TYPES = frozenset({"named_figure", "qualitative"})
NOVELTY_TYPES = frozenset({"new_result", "incremental", "explainer", "commentary"})
SOURCE_QUALITY = frozenset({"High", "Medium", "Low"})

ALLOC_KEY = re.compile(r"alloc|target_pct|min_pct|max_pct|weight", re.I)
TRADE_NEAR_TICKER = re.compile(
    r"\b(buy|sell|overweight|underweight|price target|long|short)\b",
    re.I,
)
TICKER_TOKEN = re.compile(r"\$?[A-Z]{1,5}\b")
# Uppercase tokens that appear constantly in AI transcripts but are not tickers.
NON_TICKER_TOKENS = frozenset(
    {
        "AI", "ML", "RL", "LLM", "GPT", "API", "CPU", "GPU", "TPU", "NLP", "CV", "RAG",
        "US", "UK", "EU", "IT", "OR", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF",
        "IN", "IS", "ME", "MY", "NO", "OF", "ON", "SO", "TO", "UP", "WE", "ID", "OS",
    }
)
NON_TRADE_LONG_SHORT = re.compile(
    r"\blong(?:[\s-](?:context|term|running|horizon|sequence|form|standing|lived|range|memory|window|chain)|context)\b|"
    r"\bshort(?:[\s-](?:context|term|running|horizon|sequence|form|standing|lived|range|memory|window|chain|training|run))\b",
    re.I,
)
PORTFOLIO_PCT = re.compile(
    r"(\d+(?:\.\d+)?\s*%).{0,40}(portfolio|allocation|position|exposure)|"
    r"(portfolio|allocation|position|exposure).{0,40}(\d+(?:\.\d+)?\s*%)",
    re.I,
)


class Claim(BaseModel):
    claim: str = Field(description="One sentence, as the source states it")
    claim_type: str = Field(description="capability | benchmark | release | cost | policy | opinion")
    specificity: str = Field(description="named_figure | qualitative")
    attributed_to: str = Field(
        default="",
        description="Speaker or organization the source attributes it to; empty if unattributed",
    )


class AIResearchBrief(BaseModel):
    headline: str = Field(description="6-10 words, the lead idea")
    summary: str = Field(description="3-5 sentences, mechanism-level")
    claims: list[Claim] = Field(default_factory=list)
    named_systems: list[str] = Field(default_factory=list)
    named_orgs: list[str] = Field(default_factory=list)
    benchmarks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    novelty: str = Field(description="new_result | incremental | explainer | commentary")
    source_quality: str = Field(description="High | Medium | Low")


def _system_instruction(source_name: str) -> str:
    return (
        "You are a technical analyst summarising an AI-research video for a reader who tracks "
        "capability progress. You are NOT an investment analyst.\n\n"
        "RULES:\n"
        "- Never name a public company as an investment implication. Naming Nvidia as the maker "
        "of a chip the source discusses is a fact. 'This is bullish for Nvidia' is forbidden.\n"
        "- No allocation, portfolio percentages, buy/sell/overweight/underweight, price targets, "
        "or market forecasts.\n"
        "- claims are extracted AS THE SOURCE STATES THEM, not endorsed.\n"
        "- novelty must be honest: most uploads are explainer or commentary, not new_result.\n"
        "- Ignore sponsor reads, course promotions, Patreon appeals, channel self-promotion.\n"
        "- If the transcript has no AI-technical content, return novelty=commentary, "
        "source_quality=Low, empty claims. Do not manufacture content.\n"
        f"- Source: {source_name}"
    )


def analyze_ai_research(transcript: str, source_name: str = "Unknown AI Channel") -> dict | None:
    prompt = f"Summarise this AI-research video transcript:\n\n{transcript}"
    result = ask_gemini(
        prompt=prompt,
        system_instruction=_system_instruction(source_name),
        response_schema=AIResearchBrief,
        max_tokens=getattr(config, "GEMINI_MAX_TOKENS_PODCAST", 8000),
    )
    if result is None:
        logger.error("AI research analysis failed for: %s", source_name)
        return None
    return result.model_dump()


def _proximity_violation(text: str, org_names: list[str]) -> str | None:
    for m in TRADE_NEAR_TICKER.finditer(text):
        trade_word = m.group(0)
        if trade_word.lower() in ("long", "short"):
            snippet_start = max(0, m.start() - 20)
            snippet_end = min(len(text), m.end() + 40)
            if NON_TRADE_LONG_SHORT.search(text[snippet_start:snippet_end]):
                continue
        start = max(0, m.start() - 60)
        end = min(len(text), m.end() + 60)
        window = text[start:end]
        window_lower = window.lower()
        for tick in TICKER_TOKEN.finditer(window):
            token = tick.group(0).lstrip("$")
            if token in NON_TICKER_TOKENS:
                continue
            return f"rule 2: trade language near ticker in: {trade_word!r}"
        for org in org_names:
            if org and len(org) > 2 and org.lower() in window_lower:
                return f"rule 2: trade language near org {org!r}: {trade_word!r}"
    return None


def validate_brief(brief: dict[str, Any]) -> list[str]:
    """Return list of violation messages; empty means OK to write."""
    violations: list[str] = []

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                if ALLOC_KEY.search(k):
                    violations.append(f"rule 1: forbidden key {p!r}")
                walk(v, p)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{path}[{i}]")
        elif isinstance(obj, str):
            if path.endswith("claim") or path == "summary" or path == "headline":
                orgs = brief.get("named_orgs") or []
                hit = _proximity_violation(obj, orgs)
                if hit:
                    violations.append(hit)
            if PORTFOLIO_PCT.search(obj):
                violations.append(f"rule 3: portfolio allocation % language in {path!r}")

    walk(brief)

    novelty = brief.get("novelty")
    quality = brief.get("source_quality")
    claims = brief.get("claims") or []

    if not claims and not (novelty == "commentary" and quality == "Low"):
        violations.append("rule 4: claims empty without commentary/Low escape hatch")

    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            violations.append(f"rule 5: claim[{i}] not an object")
            continue
        ct = c.get("claim_type")
        sp = c.get("specificity")
        if ct not in CLAIM_TYPES:
            violations.append(f"rule 5: claim[{i}] invalid claim_type {ct!r}")
        if sp not in SPECIFICITY_TYPES:
            violations.append(f"rule 5: claim[{i}] invalid specificity {sp!r}")

    if novelty not in NOVELTY_TYPES:
        violations.append(f"rule 5: invalid novelty {novelty!r}")
    if quality not in SOURCE_QUALITY:
        violations.append(f"rule 5: invalid source_quality {quality!r}")

    return violations


def brief_to_markdown(
    brief: dict[str, Any],
    *,
    source_name: str,
    video_id: str,
    transcript_sha256: str,
    source_ref: str | None = None,
    source_kind: str = "YouTube transcript",
) -> str:
    """Render a brief. `source_ref` overrides the YouTube URL line for non-YouTube
    sources (e.g. a Spotify Studio ai-dispatch file); `source_kind` names the input
    type in the PROVENANCE stamp. Defaults preserve the YouTube behaviour exactly.
    """
    from datetime import datetime

    ingested = datetime.now().strftime("%Y-%m-%d")
    channel = source_name.split(":")[0].strip() if ":" in source_name else source_name
    ref = source_ref or f"https://www.youtube.com/watch?v={video_id}"
    ref_label = "Video" if source_ref is None else "Source file"

    lines = [
        f"# {brief.get('headline', 'Untitled')}",
        "",
        f"**Source:** {channel}",
        f"**{ref_label}:** {ref}",
        f"**Published:** unknown   **Ingested:** {ingested}",
        f"**Novelty:** {brief.get('novelty')}   **Source quality:** {brief.get('source_quality')}",
        "",
        f"*PROVENANCE: Model-generated brief. Gemini summary of a {source_kind} from {channel}. "
        f"Not reviewed. source_ref: {video_id}. transcript_sha256: {transcript_sha256}.*",
        "",
        "## Summary",
        brief.get("summary", ""),
        "",
        "## Claims",
        "| # | Claim | Type | Specificity | Attributed to |",
        "|---|---|---|---|---|",
    ]
    for i, c in enumerate(brief.get("claims") or [], 1):
        if isinstance(c, dict):
            lines.append(
                f"| {i} | {c.get('claim', '')} | {c.get('claim_type', '')} | "
                f"{c.get('specificity', '')} | {c.get('attributed_to', '')} |"
            )

    def _section(title: str, items: list) -> None:
        lines.extend(["", f"## {title}"])
        for item in items or []:
            lines.append(f"- {item}")

    _section("Named systems", brief.get("named_systems"))
    _section("Named organizations", brief.get("named_orgs"))
    _section("Reported benchmarks", brief.get("benchmarks"))
    _section("Open questions", brief.get("open_questions"))

    lines.extend(
        [
            "",
            "*AI_BRIEF_VERIFICATION: PENDING (manual). No figure in this brief has been checked against a primary "
            "source. Treat every benchmark number and capability claim as unconfirmed.*",
        ]
    )
    return "\n".join(lines) + "\n"
