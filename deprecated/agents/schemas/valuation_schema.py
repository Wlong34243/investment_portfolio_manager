"""
Pydantic schemas for the Valuation Agent (Phase 5-B).

bundle_hash is REQUIRED on the top-level response — enforces the audit chain
linking every agent output to the exact composite bundle snapshot it analyzed.

All numeric fields (pe_fwd, peg, discount_from_52w_high_pct) are pre-computed
in Python. Gemini populates signal, accumulation_plan, rationale, style_alignment.
"""

from pydantic import BaseModel, Field
from typing import Literal


class PositionValuation(BaseModel):
    """Valuation assessment for a single position."""
    ticker: str
    pe_fwd: float | None = Field(
        default=None,
        description="Forward P/E ratio — pre-computed in Python. None if unavailable.",
    )
    pe_trailing: float | None = Field(
        default=None,
        description="Trailing twelve-month P/E — pre-computed in Python. None if unavailable.",
    )
    peg: float | None = Field(
        default=None,
        description="PEG ratio (P/E ÷ earnings growth %) — pre-computed in Python. None if unavailable.",
    )
    price_vs_52w_range: float | None = Field(
        default=None,
        description=(
            "(current_price - low_52w) / (high_52w - low_52w). "
            "0 = at 52w low, 1 = at 52w high. Pre-computed in Python."
        ),
    )
    discount_from_52w_high_pct: float = Field(
        ...,
        description="% below 52-week high. 0 = at high, positive = discounted. Pre-computed in Python.",
    )
    signal: Literal["ADD", "HOLD", "TRIM", "MONITOR", "EXIT"] = Field(
        ...,
        description=(
            "Uppercase valuation signal aligned with Thesis Screener vocabulary. "
            "ADD: significantly undervalued vs hist or asymmetric add spot. "
            "HOLD: fair value or neutral trend. "
            "TRIM: overvalued or profit-taking spot. "
            "MONITOR: data gaps or trend transition. "
            "EXIT: extreme overvaluation or thesis breach (if known)."
        ),
    )
    accumulation_plan: str | None = Field(
        default=None,
        description=(
            "Small-step scaling plan when signal='ADD'. "
            "E.g. 'Scale in 10% on each 5% pullback, targeting 3 tranches'. "
            "Must be None when signal != 'ADD'."
        ),
    )
    rationale: str = Field(
        ..., min_length=30, max_length=600,
        description=(
            "Narrative tying metrics to recommendation. MUST explicitly cite pre-computed numbers: "
            "current P/E vs historical, 52w range position, and % discount from high."
        ),
    )
    style_alignment: str = Field(
        ...,
        description="Investment style tag from thesis frontmatter: GARP / THEME / FUND / ETF / Unknown.",
    )


class ValuationAgentOutput(BaseModel):
    """Top-level output of the Valuation Agent."""
    bundle_hash: str = Field(
        ...,
        description="composite_hash from the composite bundle. Required for provenance linkage.",
    )
    generated_at: str = Field(..., description="ISO-8601 UTC timestamp of this run.")
    positions: list[PositionValuation] = Field(
        default_factory=list,
        description="Per-position valuation assessments.",
    )
    top_accumulation_candidates: list[str] = Field(
        default_factory=list,
        description="Tickers with signal='accumulate', ordered by conviction (Gemini-ranked).",
    )
    summary_narrative: str = Field(
        ..., min_length=50,
        description="3-5 sentence overall portfolio valuation narrative.",
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Tickers skipped due to missing FMP data — logged, not silently dropped.",
    )


__all__ = ["PositionValuation", "ValuationAgentOutput"]
