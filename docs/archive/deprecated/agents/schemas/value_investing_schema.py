"""
Pydantic schemas for the Value Investing Screener Agent.

Benjamin Graham + Warren Buffett + Christopher H. Browne framework.
Strategy thresholds live in agents/value_investing_strategy.json.

All quantitative gate metrics (pe_ratio, pb_ratio, current_ratio, roe_pct,
debt_to_equity) are pre-computed in Python. Gemini receives raw facts + pass/fail
flags and writes narrative only. No LLM math.
"""

from pydantic import BaseModel, Field
from typing import Literal


class ValueInvestingCandidate(BaseModel):
    """Graham + Buffett + Browne value gate evaluation for a single position."""
    ticker: str

    # --- Graham Gate Narratives (Gemini writes; Python provides raw facts) ---
    pe_evaluation: str = Field(
        ...,
        description=(
            "Narrative on PE ratio vs the Graham max threshold (~10x). "
            "If elevated, contextualize vs sector and earnings quality."
        ),
    )
    pb_evaluation: str = Field(
        ...,
        description=(
            "Narrative on P/B ratio vs Graham's strict 0.66 ceiling and the "
            "practical 1.5 soft threshold. Note asset-heavy vs asset-light businesses."
        ),
    )
    current_ratio_evaluation: str = Field(
        ...,
        description=(
            "Narrative on current ratio vs the 2.0 minimum. "
            "Low values indicate liquidity risk; high values may suggest inefficiency."
        ),
    )
    graham_number_evaluation: str = Field(
        ...,
        description=(
            "Narrative on the Graham Number product (PE × PB). "
            "Should be < 22.5 for a Graham-safe entry. Comment on margin of safety implied."
        ),
    )

    # --- Buffett Gate Narratives ---
    roe_evaluation: str = Field(
        ...,
        description=(
            "Narrative on Return on Equity vs the 15%+ quality threshold. "
            "Consistent ROE over 5+ years is the core Buffett moat signal."
        ),
    )
    debt_to_equity_evaluation: str = Field(
        ...,
        description=(
            "Narrative on D/E ratio vs the 1.0 Buffett ceiling. "
            "Excessive debt amplifies downside and erodes margin of safety."
        ),
    )

    # --- Qualitative Overlay (Gemini writes from thesis + market context) ---
    margin_of_safety_assessment: str = Field(
        ...,
        description=(
            "Does the current price offer a 33%+ margin of safety vs intrinsic value? "
            "Use PE/PB/Graham Number as proxies. Comment on whether the stock is "
            "trading at a discount, fair value, or premium."
        ),
    )
    moat_assessment: str = Field(
        ...,
        description=(
            "1-2 sentences on competitive moat: brand, switching costs, cost advantages, "
            "network effects, or regulatory protection. Use thesis data if available."
        ),
    )

    # --- Gate pass/fail — Python writes the authoritative list; Gemini echoes ---
    gates_passed: list[str] = Field(
        default_factory=list,
        description=(
            "Gate IDs that passed: pe_graham, pb_graham, graham_number, "
            "current_ratio, roe_buffett, debt_equity. Populated by Python."
        ),
    )
    gates_failed: list[str] = Field(
        default_factory=list,
        description="Gate IDs that failed. Always populated from Python pre-computation.",
    )

    final_recommendation: Literal["DEEP_VALUE", "VALUE_WATCH", "FAIRLY_VALUED", "REJECT"] = Field(
        ...,
        description=(
            "DEEP_VALUE: passes graham_number + current_ratio + roe_buffett + debt_equity "
            "(genuine margin-of-safety opportunity). "
            "VALUE_WATCH: passes 3-4 gates — approaching value territory, monitor. "
            "FAIRLY_VALUED: passes 1-2 gates — no meaningful discount to intrinsic value. "
            "REJECT: fails most gates — overvalued or fundamentally impaired."
        ),
    )
    fundamental_reason: str = Field(
        ...,
        description=(
            "One sentence: why this is or isn't a value buy right now, "
            "referencing the most decisive gate result."
        ),
    )


class ValueInvestingResponse(BaseModel):
    """Top-level output of the Value Investing Screener Agent."""
    bundle_hash: str = Field(
        ...,
        description="composite_hash from the composite bundle. Required for audit chain.",
    )
    analysis_timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp of this run.")
    candidates_analyzed: list[ValueInvestingCandidate] = Field(
        default_factory=list,
        description="Per-position Graham + Buffett gate evaluations.",
    )
    deep_value_candidates: list[str] = Field(
        default_factory=list,
        description="Tickers with final_recommendation='DEEP_VALUE', ordered by conviction.",
    )
    value_watch_candidates: list[str] = Field(
        default_factory=list,
        description="Tickers with final_recommendation='VALUE_WATCH'.",
    )
    summary_narrative: str = Field(
        ..., min_length=50,
        description=(
            "3-5 sentence portfolio-level narrative: what fraction of holdings "
            "trade at a discount, which sectors offer the best value right now, "
            "and whether the portfolio is tilted toward growth or value."
        ),
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Tickers skipped due to missing fundamental data — logged, not silently dropped.",
    )


__all__ = ["ValueInvestingCandidate", "ValueInvestingResponse"]
