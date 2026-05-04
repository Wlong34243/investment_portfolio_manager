"""
Pydantic schemas for the Re-buy Analyst agent.

bundle_hash is a REQUIRED field on the top-level response. This enforces
the audit chain: every agent output is permanently linked to the exact
composite bundle snapshot it analyzed. ask_gemini_composite() populates
this field automatically — the LLM is instructed to echo it back, and
the client overwrites any hallucinated value with the correct one.
"""

from pydantic import BaseModel, Field
from typing import Literal


class FrameworkRuleResult(BaseModel):
    """Result of evaluating a single framework rule."""
    rule_id: str
    description: str
    passed: bool | None = Field(
        default=None,
        description="True if rule passed, False if failed, None if insufficient data",
    )
    observed_value: str | None = Field(
        default=None,
        description="The actual value observed, as a string",
    )
    severity: Literal["required", "preferred"]
    rationale: str = Field(..., min_length=10)


class FrameworkValidation(BaseModel):
    """
    Framework validation block. Reported alongside the recommendation
    when a framework applies. None when no framework matches.
    """
    framework_id: str
    framework_version: str
    framework_content_sha256: str = Field(
        default="",
        description=(
            "SHA256 of the framework JSON file — part of the audit chain. "
            "Set by the Python pipeline in step 11b; LLM values are overwritten."
        ),
    )
    applicable: bool
    applicability_rationale: str = Field(..., min_length=10)
    rules_evaluated: list[FrameworkRuleResult]
    required_rules_passed: int = Field(..., ge=0)
    required_rules_total: int = Field(..., ge=0)
    preferred_rules_passed: int = Field(..., ge=0)
    preferred_rules_total: int = Field(..., ge=0)
    passes_framework: bool
    insufficient_data_rules: list[str] = Field(default_factory=list)
    framework_score_display: str = Field(
        ...,
        description="Human-readable score like '3/5 required + 1/2 preferred'",
    )


class RebuyCandidate(BaseModel):
    ticker: str
    style: Literal["GARP", "THEME", "FUND", "ETF"]
    thesis_present: bool
    current_scaling_state: str    # as written in thesis file; "unknown" if no thesis
    proposed_next_step: Literal["scale_in", "hold", "watch", "exit_watch"]
    scaling_rationale: str        # qualitative reasoning; no price targets
    rotation_priority: Literal["low", "medium", "high", "unknown"]
    confidence: Literal["low", "medium", "high"]
    notes: str = ""               # optional; any additional context

    # Phase 3c: framework validation (optional — None when no framework applies)
    framework_validation: FrameworkValidation | None = Field(
        default=None,
        description="Structured framework evaluation, or None if no reviewed framework matched",
    )
    framework_influence_notes: str = Field(
        default="",
        description="How the framework score shaped the recommendation. "
                    "Empty string if framework_validation is None.",
    )


class RebuyAnalystResponse(BaseModel):
    bundle_hash: str              # REQUIRED — composite_hash from the bundle
    analysis_timestamp_utc: str  # ISO-8601 UTC
    candidates: list[RebuyCandidate]
    excluded_tickers: list[str]  # tickers skipped (cash, no data, etc.)
    coverage_warnings: list[str] # tickers where thesis was missing
    analyst_notes: str = ""      # top-level observations; no predictions

    # Van Tharp position sizing — Python-computed, never LLM-derived.
    # Keyed by ticker. Populated by the pre-computation loop in rebuy_analyst.py;
    # overwritten (not merged) after result reconstruction.
    van_tharp_sizing_map: dict[str, dict] = Field(
        default_factory=dict,
        description=(
            "Pre-computed Van Tharp sizing for each position with ATR data. "
            "Keys: ticker. Values: compute_van_tharp_sizing() output dict. "
            "Empty when calculated_technical_stops absent from bundle "
            "(run tasks/enrich_atr.py to populate)."
        ),
    )


__all__ = [
    "FrameworkRuleResult", "FrameworkValidation",
    "RebuyCandidate", "RebuyAnalystResponse",
]
