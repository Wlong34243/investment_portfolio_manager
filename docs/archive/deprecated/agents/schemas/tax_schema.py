"""
Pydantic schemas for the Tax Intelligence Agent.

bundle_hash is REQUIRED on the top-level response — enforces the audit chain
linking every agent output to the exact composite bundle snapshot it analyzed.
ask_gemini_composite() populates this field; any hallucinated value is overwritten
by the Python caller.

composite_hash == bundle_hash here: the tax agent operates on composite bundles,
so bundle_hash carries the composite_hash value (not a sub-bundle hash).
"""

from pydantic import BaseModel, Field
from typing import Literal


class TLHCandidate(BaseModel):
    """A single position flagged as a tax-loss harvesting candidate."""
    ticker: str
    unrealized_loss_usd: float = Field(
        ..., ge=0,
        description="Absolute value of unrealized loss in USD — pre-computed in Python.",
    )
    holding_period_days: int = Field(
        ...,
        description="Days held. -1 if acquisition date is unknown.",
    )
    short_term: bool = Field(
        ...,
        description="True if holding_period_days < 365 (short-term capital gain rate applies).",
    )
    wash_sale_risk: bool = Field(
        ...,
        description="True if a BUY of this ticker was detected in the last 30 days.",
    )
    tlh_rationale: str = Field(
        ..., min_length=20,
        description="1-2 sentence narrative explaining why harvesting this loss is worthwhile.",
    )
    suggested_replacement: str | None = Field(
        default=None,
        description="Wash-sale-safe proxy (ETF or correlated peer). Null if not applicable.",
    )
    scale_step: str = Field(
        ..., min_length=10,
        description="Small-step sizing language, e.g. 'Trim 25% over 2 sessions'. Never 'sell all'.",
    )


class RebalanceAction(BaseModel):
    """A rebalancing action for a position in a drifted asset class."""
    ticker: str = Field(
        ...,
        description="Representative ticker for the action. Use asset class name if no single ticker applies.",
    )
    direction: Literal["trim", "add"]
    drift_pct: float = Field(
        ...,
        description="Asset-class drift in percentage points — pre-computed in Python.",
    )
    scale_step: str = Field(
        ..., min_length=10,
        description="Small-step sizing language. Never binary 'buy all' or 'sell all'.",
    )
    rationale: str = Field(
        ..., min_length=20,
        description="1-2 sentence narrative explaining the rebalancing rationale.",
    )


class TaxAgentOutput(BaseModel):
    """Top-level output of the Tax Intelligence Agent."""
    bundle_hash: str = Field(
        ...,
        description="composite_hash from the composite bundle. Required for provenance linkage.",
    )
    generated_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp of this run.",
    )
    tlh_candidates: list[TLHCandidate] = Field(
        default_factory=list,
        description="Positions with unrealized losses exceeding the TLH threshold.",
    )
    rebalance_actions: list[RebalanceAction] = Field(
        default_factory=list,
        description="Asset classes with drift exceeding the rebalancing threshold.",
    )
    summary_narrative: str = Field(
        ..., min_length=50,
        description="3-5 sentence overall narrative on the portfolio's tax picture.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Wash sale flags, year-end deadlines, or other time-sensitive alerts.",
    )


__all__ = ["TLHCandidate", "RebalanceAction", "TaxAgentOutput"]
