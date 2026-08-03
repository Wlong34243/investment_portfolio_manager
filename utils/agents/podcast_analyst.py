"""
Extracts macro allocation strategy from podcast transcripts using Gemini
with Pydantic schema enforcement.
"""

import logging
from pydantic import BaseModel, Field
from typing import List, Optional
from utils.gemini_client import ask_gemini
import config


class SectorTarget(BaseModel):
    asset_class: str = Field(
        description=(
            "The macro asset class or standard GICS sector (e.g., Technology, Utilities, "
            "Industrials, Materials, Real Estate, Fixed Income, Cash). You MAY introduce a "
            "new standard sector if a strong valuation displacement opportunity is presented."
        )
    )
    asset_strategy: str = Field(description="Brief thesis, e.g. 'Defensive AI beneficiaries'")
    target_pct: float = Field(description="Target allocation %. All targets must sum to 100.")
    min_pct: float = Field(description="Lower drift band, usually target_pct - 5")
    max_pct: float = Field(description="Upper drift band, usually target_pct + 5")
    confidence: str = Field(description="High, Medium, or Low")
    notes: str = Field(description="Rationale extracted from podcast")


class PodcastStrategy(BaseModel):
    executive_summary: str = Field(description="2-3 sentence macro thesis")
    target_allocations: List[SectorTarget]
    thesis_screener_prompts: List[str] = Field(
        description="1-2 sentence thesis seeds for downstream agents"
    )
    source_quality: str = Field(
        description="High / Medium / Low — how actionable was this content"
    )
    suggested_title: Optional[str] = Field(
        default=None,
        description=(
            "6-10 word title capturing the lead idea of the source. Only "
            "requested for already-synthesized aggregate digests that carry "
            "no title of their own."
        ),
    )
    cited_sources: List[str] = Field(
        default_factory=list,
        description=(
            "Shows and guests explicitly named or discussed in the source, "
            "as 'Show Name: Guest Name' (guest omitted if not stated). Only "
            "populated for aggregate digests that synthesize other episodes; "
            "leave empty for a single-episode transcript."
        ),
    )


def analyze_podcast(transcript: str, source_name: str = "Unknown Podcast") -> dict | None:
    """
    Send transcript or financial report to Gemini, extract structured allocation strategy.
    Detects if the source is a STAX report and adjusts instructions to derive forward signals.
    Returns dict (model_dump) on success, None on failure.
    """
    is_stax = "STAX" in source_name.upper()
    is_aggregate = "AGGREGATE" in source_name.upper()

    if is_stax:
        role_instruction = (
            "You are a Quantitative Strategist parsing a retail sentiment and flow report (Schwab STAX).\n\n"
            "STAX DATA INTERPRETATION:\n"
            "- STAX is retrospective (last month's flows), but your job is to DERIVE a forward-looking allocation.\n"
            "- If retail is net-buying a sector on a dip, analyze if that signals a 'buy the dip' consensus.\n"
            "- If a sector saw massive outflows, evaluate if it represents a rotation opportunity or a risk to avoid.\n"
            "- Use the flow data to build a GRANULAR sector-by-sector allocation (do not just output Broad Market).\n"
        )
    elif is_aggregate:
        role_instruction = (
            "You are a Chief Investment Officer parsing an already-synthesized third-party "
            "weekly aggregate. The input is NOT a single-episode transcript — it is finished "
            "editorial prose that itself summarizes a pool of podcast episodes and other "
            "sources. Do not re-summarize it; your only job is the structured allocation "
            "table plus two extraction fields.\n\n"
            "AGGREGATE DATA INTERPRETATION:\n"
            "- target_pct values are INFERRED from the digest's stated emphasis (how much space "
            "and conviction it gives a theme), not extracted as published figures — the digest "
            "does not publish percentages.\n"
            "- Where the digest itself carries an unresolved tension or a disagreement between "
            "sources it cites, preserve that as separate SectorTarget rows with the tension "
            "named in notes. Do not average it into a single smoothed figure.\n"
            "- suggested_title: write a 6-10 word title capturing the digest's lead idea. The "
            "source file has no title of its own.\n"
            "- cited_sources: list every show and guest the digest explicitly names or "
            "discusses, as 'Show Name: Guest Name' (omit guest if not stated). This is used "
            "downstream to avoid double-counting a theme that also appears in that episode's "
            "own independently-ingested summary.\n"
        )
    else:
        role_instruction = (
            "You are a Chief Investment Officer parsing an institutional strategy discussion.\n\n"
            "EXTRACT: the core 6-to-12 month macro thesis, sector rotation consensus, and risk positioning.\n"
        )

    system_instruction = (
        f"{role_instruction}\n"
        "IGNORE: sponsor reads, day-trading advice, short-term options flow, meme stock hype, "
        "crypto speculation without institutional backing, and advertisements.\n\n"
        "CONSTRAINTS:\n"
        "- target_pct values across all SectorTarget entries MUST sum to exactly 100.\n"
        "- Use standard GICS sectors or macro asset categories (e.g., Technology, "
        "Healthcare, Energy, Financials, Industrials, Utilities, Materials, "
        "Real Estate, Consumer Discretionary, Consumer Staples, Communication Services, "
        "International, Broad Market, Fixed Income, Cash). You MAY introduce a sector "
        "the investor currently has zero exposure to if the source presents a strong "
        "displacement opportunity.\n"
        "- If the source truly lacks any actionable signals, only then return a single "
        "SectorTarget with asset_class='Broad Market', target_pct=100, confidence='Low'.\n"
        f"- Source: {source_name}"
    )

    prompt = f"Analyze this content and extract a target allocation strategy:\n\n{transcript}"

    result = ask_gemini(
        prompt=prompt,
        system_instruction=system_instruction,
        response_schema=PodcastStrategy,
        max_tokens=getattr(config, "GEMINI_MAX_TOKENS_PODCAST", 8000),
    )

    if result is None:
        logging.error(f"Podcast analysis failed for: {source_name}")
        return None

    return result.model_dump()
