"""
Pydantic schemas for the 100-Bagger Screener Agent (Phase 5-F).

Based on Christopher Mayer's "100 Baggers" framework.
Quantitative gate lives at vault/frameworks/100_bagger_framework.json.

bundle_hash is REQUIRED on BaggerScreenerResponse — enforces the audit chain.

Quantitative gate metrics (market_cap_usd, roic_pct, revenue_growth_3yr_cagr_pct,
gross_margin_pct, dividend_payout_ratio_pct) are pre-computed in Python via FMP.
Gemini receives pass/fail flags and raw metrics, and writes narrative only.
"""

from pydantic import BaseModel, Field
from typing import Literal


class BaggerCandidate(BaseModel):
    """100-bagger evaluation for a single position."""
    ticker: str

    # Gate evaluation narratives — Gemini writes; Python provides raw facts
    acorn_evaluation: str = Field(
        ...,
        description=(
            "Narrative on market cap vs the $1B Acorn threshold. "
            "For large-caps, explain why 100x is structurally impossible from this base."
        ),
    )
    roic_evaluation: str = Field(
        ...,
        description=(
            "Narrative on ROIC (or ROE proxy) vs the 18% compounding threshold. "
            "Use pre-computed roic_pct provided in the prompt."
        ),
    )
    growth_evaluation: str = Field(
        ...,
        description=(
            "Narrative on 3-year revenue CAGR vs 10% threshold. "
            "Comment on trajectory: accelerating, stable, or decelerating."
        ),
    )
    margin_evaluation: str = Field(
        ...,
        description=(
            "Narrative on gross margin vs 50% moat indicator threshold. "
            "For capital-intensive sectors, apply the 30% soft threshold."
        ),
    )
    dividend_evaluation: str = Field(
        ...,
        description=(
            "Narrative on dividend payout ratio. 0% = ideal. "
            "> 40% = capital allocation concern. Flag but do not hard-reject on this alone."
        ),
    )

    # Qualitative overlay — Gemini writes from thesis + market context
    twin_engine_assessment: str = Field(
        ...,
        description=(
            "Does the position have BOTH earnings growth potential AND room for multiple expansion? "
            "Comment on current P/E relative to growth rate (PEG context)."
        ),
    )
    coffee_can_verdict: str = Field(
        ...,
        description=(
            "1-2 sentences: would you put this in a coffee can for 10 years? "
            "Assess business durability, competitive position trajectory."
        ),
    )

    # Gate pass/fail summary
    gates_passed: list[str] = Field(
        default_factory=list,
        description="Gate IDs that passed: acorn, roic, revenue_growth, gross_margin, dividend_payout.",
    )
    gates_failed: list[str] = Field(
        default_factory=list,
        description="Gate IDs that failed. Populated from Python pre-computation, not LLM.",
    )

    final_recommendation: Literal["STRONG_BUY", "WATCHLIST", "REJECT"] = Field(
        ...,
        description=(
            "STRONG_BUY: all core gates pass + strong qualitative overlay. "
            "WATCHLIST: fails 1-2 gates (often market cap); monitor for entry. "
            "REJECT: fails ROIC, revenue growth, or market cap hard ceiling."
        ),
    )
    fundamental_reason: str = Field(
        ...,
        description="One sentence summary of why this is or isn't a 100-bagger candidate.",
    )


class BaggerScreenerResponse(BaseModel):
    """Top-level output of the 100-Bagger Screener Agent."""
    bundle_hash: str = Field(
        ...,
        description="composite_hash from the composite bundle. Required for provenance linkage.",
    )
    analysis_timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp of this run.")
    candidates_analyzed: list[BaggerCandidate] = Field(
        default_factory=list,
        description="Per-position 100-bagger gate evaluations.",
    )
    strong_buy_candidates: list[str] = Field(
        default_factory=list,
        description="Tickers with final_recommendation='STRONG_BUY', ordered by conviction.",
    )
    watchlist_candidates: list[str] = Field(
        default_factory=list,
        description="Tickers with final_recommendation='WATCHLIST'.",
    )
    summary_narrative: str = Field(
        ..., min_length=50,
        description="3-5 sentence portfolio-level narrative on 100-bagger potential across holdings.",
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Tickers skipped due to missing FMP data — logged, not silently dropped.",
    )


__all__ = ["BaggerCandidate", "BaggerScreenerResponse"]
