"""
Extracts macro allocation strategy from podcast transcripts using Gemini
with Pydantic schema enforcement.
"""

import logging
from pydantic import BaseModel, Field
from typing import List
from utils.gemini_client import ask_gemini


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


def analyze_podcast(transcript: str, source_name: str = "Unknown Podcast") -> dict | None:
    """
    Send transcript to Gemini, extract structured allocation strategy.
    Returns dict (model_dump) on success, None on failure.
    """
    system_instruction = (
        "You are a Chief Investment Officer parsing an institutional strategy discussion.\n\n"
        "IGNORE: sponsor reads, day-trading advice, short-term options flow, meme stock hype, "
        "crypto speculation without institutional backing, and advertisements.\n\n"
        "EXTRACT: the core 6-to-12 month macro thesis, sector rotation consensus, "
        "and risk positioning.\n\n"
        "CONSTRAINTS:\n"
        "- target_pct values across all SectorTarget entries MUST sum to exactly 100.\n"
        "- Use standard GICS sectors or macro asset categories (e.g., Technology, "
        "Healthcare, Energy, Financials, Industrials, Utilities, Materials, "
        "Real Estate, Consumer Discretionary, Consumer Staples, Communication Services, "
        "International, Broad Market, Fixed Income, Cash). You MAY introduce a sector "
        "the investor currently has zero exposure to if the podcast presents a strong "
        "valuation displacement opportunity — that is the purpose of this analysis.\n"
        "- If the podcast lacks actionable allocation guidance, return a single "
        "SectorTarget with asset_class='Broad Market', target_pct=100, confidence='Low', "
        "and notes explaining why.\n"
        f"- Source: {source_name}"
    )

    prompt = f"Analyze this podcast transcript and extract a target allocation strategy:\n\n{transcript}"

    result = ask_gemini(
        prompt=prompt,
        system_instruction=system_instruction,
        response_schema=PodcastStrategy,
        max_tokens=4000,
    )

    if result is None:
        logging.error(f"Podcast analysis failed for: {source_name}")
        return None

    return result.model_dump()
