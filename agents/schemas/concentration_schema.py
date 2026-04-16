"""
Pydantic schemas for the Concentration Hedger Agent (Phase 5-C).

bundle_hash is REQUIRED on the top-level response — enforces the audit chain
linking every agent output to the exact composite bundle snapshot it analyzed.

All numeric fields (weight percentages, beta, stress dollar impacts, correlations)
are pre-computed in Python. Gemini populates hedge_suggestion, scale_step,
summary_narrative, and priority_actions.
"""

from pydantic import BaseModel, Field
from typing import Literal


class CorrelationPair(BaseModel):
    """A pair of highly correlated tickers."""
    ticker_1: str = Field(..., description="First ticker in the pair.")
    ticker_2: str = Field(..., description="Second ticker in the pair.")
    correlation_coefficient: float = Field(..., description="Correlation between -1 and 1.")


class ConcentrationFlag(BaseModel):
    """A single concentration or correlation risk flag."""
    type: Literal["SINGLE_POSITION", "SECTOR", "CORRELATION_PAIR"] = Field(
        ...,
        description="Category of risk: over-weight single position, sector bloat, or highly-correlated pair.",
    )
    target: str = Field(
        ...,
        description="The position or sector flagged (e.g., 'AAPL' or 'Healthcare').",
    )
    current_weight_pct: float = Field(
        ...,
        description="Current portfolio weight % of the flagged position or sector.",
    )
    threshold_pct: float = Field(
        ...,
        description="Threshold that was breached.",
    )
    status: Literal["VIOLATION", "WARNING"] = Field(
        ...,
        description="'VIOLATION' if severe breach; 'WARNING' if moderate.",
    )
    hedge_suggestion: str = Field(
        ..., min_length=20,
        description=(
            "Gemini narrative suggestion: how to reduce this concentration. "
            "E.g. 'Trim UNH 15% over 3 steps; rotate to XLV for sector retention.'"
        ),
    )
    scale_step: str = Field(
        ..., min_length=10,
        description="Small-step sizing language. Never binary. E.g. 'Trim 15-20% over 2-3 sessions'.",
    )


class ConcentrationAgentOutput(BaseModel):
    """Top-level output of the Concentration Hedger Agent."""
    bundle_hash: str = Field(
        ...,
        description="composite_hash from the composite bundle. Required for provenance linkage.",
    )
    generated_at: str = Field(..., description="ISO-8601 UTC timestamp of this run.")
    portfolio_beta: float = Field(
        ...,
        description="Weighted portfolio beta — pre-computed in Python.",
    )
    stress_scenarios: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Dollar impact per stress scenario — pre-computed in Python. "
            "Keys like 'market_down_10pct', values are dollar P&L impact."
        ),
    )
    flags: list[ConcentrationFlag] = Field(
        default_factory=list,
        description="All concentration and correlation flags, ordered by severity then weight.",
    )
    high_correlations: list[CorrelationPair] = Field(
        default_factory=list,
        description="Analyzed pairs with high correlation coefficients (|r| > threshold).",
    )
    summary_narrative: str = Field(
        ..., min_length=50,
        description="3-5 sentence overall risk narrative for the portfolio.",
    )
    priority_actions: list[str] = Field(
        default_factory=list,
        description="Ordered list of tickers to address first — Gemini-ranked by urgency.",
    )


__all__ = ["CorrelationPair", "ConcentrationFlag", "ConcentrationAgentOutput"]
