"""
Pydantic schemas for the Thesis Screener Agent (Phase 5-E).

Based on Gautam Baid's "The Joys of Compounding" management evaluation framework.
Scoring rubric lives at vault/frameworks/joys_of_compounding_framework.json.

bundle_hash is REQUIRED on ThesisScreenerResponse — enforces the audit chain
linking every agent output to the exact composite bundle snapshot it analyzed.

All fields are qualitative narrative. There is no Python pre-computation for this
agent — the Gemini reasoning IS the work. Gemini reads vault thesis files and
earnings transcript snippets, then applies the Baid scoring rubric.
"""

from pydantic import BaseModel, Field
from typing import Literal


class ManagementEvaluation(BaseModel):
    """Gautam Baid framework evaluation for a single position's management team."""
    ticker: str

    linguistic_candor_score: str = Field(
        ...,
        description=(
            "Qualitative assessment of FOG language, restructuring abuse, and owning mistakes. "
            "Lead with level: HIGH, MODERATE, or LOW. Include 1-2 concrete examples from transcript."
        ),
    )
    capital_stewardship_score: str = Field(
        ...,
        description=(
            "Qualitative assessment of ROIC focus, buyback prudence, and M&A discipline. "
            "Lead with level: DISCIPLINED, ADEQUATE, or QUESTIONABLE. Include evidence."
        ),
    )
    alignment_score: str = Field(
        ...,
        description=(
            "Qualitative assessment of skin in the game, insider buying, and salary structures. "
            "Lead with level: STRONG, MODERATE, or WEAK. Include ownership or comp evidence."
        ),
    )
    red_flags_identified: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete behavioral red flags observed: fad-chasing buzzwords, governance issues, "
            "outer-scorecard obsession, stock price fixation. Empty list if none found."
        ),
    )
    inner_scorecard_assessment: str = Field(
        ...,
        description=(
            "One sentence: 'Management exhibits an [INNER / OUTER] scorecard orientation because...' "
            "Inner = sets internal standards; Outer = optimizes for Wall Street appearances."
        ),
    )
    thesis_alignment_warning: str = Field(
        ...,
        description=(
            "Does current management behavior invalidate the core_thesis or trigger an exit_condition "
            "from the vault thesis file? Be specific about which clause, if any, is threatened."
        ),
    )
    pre_mortem_behavioral_check: str = Field(
        ...,
        description=(
            "Result of running all 6 behavioral guardrails (WYSIATI, Disposition Effect, Action Bias, "
            "Anchoring, Envy, Hyperbolic Discounting). State which guardrails were checked and whether "
            "any blocked a downgrade impulse."
        ),
    )
    final_recommendation: Literal["MAINTAIN_CONVICTION", "WATCHLIST_DOWNGRADE", "THESIS_VIOLATED"] = Field(
        ...,
        description=(
            "MAINTAIN_CONVICTION: thesis intact, no action. "
            "WATCHLIST_DOWNGRADE: soft signals, monitor 1-2 quarters. "
            "THESIS_VIOLATED: exit condition triggered, scale-down warranted."
        ),
    )


class ThesisScreenerResponse(BaseModel):
    """Top-level output of the Thesis Screener Agent."""
    bundle_hash: str = Field(
        ...,
        description="composite_hash from the composite bundle. Required for provenance linkage.",
    )
    analysis_timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp of this run.")
    evaluations: list[ManagementEvaluation] = Field(
        default_factory=list,
        description="Per-ticker Gautam Baid framework evaluations.",
    )
    thesis_violations: list[str] = Field(
        default_factory=list,
        description="Tickers with final_recommendation='THESIS_VIOLATED'. Gemini-ordered by urgency.",
    )
    watchlist_downgrades: list[str] = Field(
        default_factory=list,
        description="Tickers with final_recommendation='WATCHLIST_DOWNGRADE'.",
    )
    portfolio_qualitative_summary: str = Field(
        ..., min_length=50,
        description="3-5 sentence portfolio-level narrative on management quality and thesis health.",
    )
    tickers_skipped: list[str] = Field(
        default_factory=list,
        description="Tickers skipped due to missing vault thesis file — logged, not silently dropped.",
    )


__all__ = ["ManagementEvaluation", "ThesisScreenerResponse"]
