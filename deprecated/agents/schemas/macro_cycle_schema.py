"""
Pydantic schemas for the Macro-Cycle Rotation Agent (Phase 5-D port).

Enforces Carlota Perez's framework for detecting paradigm maturity and
ATR-based technical sell triggers.

ATR stops are pre-computed by tasks/enrich_atr.py (Python-only).
Gemini writes paradigm_phase, maturity_signals, final_recommendation,
fundamental_reason_to_sell, technical_trigger_summary, and portfolio_cycle_summary.

bundle_hash is REQUIRED on MacroCycleResponse — enforces provenance linkage.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional


class ATRStopLoss(BaseModel):
    """ATR-based stop-loss data for a single position — pre-computed in Python."""
    ticker: str
    atr_14: float = Field(..., description="14-day Average True Range — computed by tasks/enrich_atr.py.")
    stop_loss_level: float = Field(
        ...,
        description="Stop-loss price = current_price - (2.5 × ATR). Pre-computed in Python.",
    )
    current_price: float = Field(..., description="Price at time of enrichment.")
    pct_from_stop: float = Field(
        ...,
        description="(current_price - stop_loss_level) / current_price. Distance to stop as a fraction.",
    )


class PositionCycleAnalysis(BaseModel):
    """Carlota Perez macro-cycle analysis for a single position."""
    ticker: str
    paradigm_phase: Literal["installation", "frenzy", "synergy", "maturity", "unknown"] = Field(
        ...,
        description=(
            "Which phase of the Perez techno-economic super-cycle this asset currently occupies. "
            "'unknown' when insufficient data."
        ),
    )
    maturity_signals: list[str] = Field(
        default_factory=list,
        description="Observable signals from the Maturity checklist (saturation, M&A, idle money, etc.).",
    )
    stop_loss: Optional[ATRStopLoss] = Field(
        default=None,
        description="Pre-computed ATR stop from tasks/enrich_atr.py. None if enrichment was not run.",
    )
    final_recommendation: Literal["HOLD", "TRIM_25PCT", "TRIM_50PCT", "EXIT", "MONITOR"] = Field(
        ...,
        description=(
            "Reconciles fundamental maturity signals with technical ATR trigger. "
            "TRIM_25PCT / TRIM_50PCT encode staged sizing language per invariant."
        ),
    )
    rotation_priority: Literal["high", "medium", "low"] = Field(
        ...,
        description="Urgency of rotating capital out of this position.",
    )
    fundamental_reason_to_sell: str = Field(
        ..., min_length=20,
        description="2-3 sentence narrative on why fundamentals signal maturity or rotation.",
    )
    technical_trigger_summary: str = Field(
        ..., min_length=10,
        description="1-2 sentence summary of ATR stop status and technical signal.",
    )


class MacroCycleResponse(BaseModel):
    """Top-level output of the Macro-Cycle Rotation Agent."""
    bundle_hash: str = Field(
        ...,
        description="composite_hash from the composite bundle. Required for provenance linkage.",
    )
    analysis_timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp.")
    paradigm_phase: Literal["installation", "frenzy", "synergy", "maturity", "unknown"] = Field(
        ...,
        description="Authoritative phase for the entire portfolio paradigm.",
    )
    positions_analyzed: list[PositionCycleAnalysis] = Field(
        default_factory=list,
        description="Per-position Carlota Perez framework assessments.",
    )
    rotation_targets: list[str] = Field(
        default_factory=list,
        description="Suggested rotation destinations (ETFs, sectors, or specific tickers) when capital is freed.",
    )
    portfolio_cycle_summary: str = Field(
        ..., min_length=50,
        description="3-5 sentence portfolio-level narrative on overall paradigm positioning.",
    )


# Keep MacroCycleAnalysis as alias for backward compatibility during transition
MacroCycleAnalysis = PositionCycleAnalysis


__all__ = [
    "ATRStopLoss",
    "PositionCycleAnalysis",
    "MacroCycleAnalysis",   # alias
    "MacroCycleResponse",
]
