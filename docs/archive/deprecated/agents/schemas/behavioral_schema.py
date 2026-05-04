"""
Pydantic schemas for the Behavioral Finance Auditor agent.
"""

from pydantic import BaseModel, Field


class BehavioralAudit(BaseModel):
    action_analyzed: str = Field(
        description="The specific portfolio pattern or recent action being audited (e.g., 'SGOV is 9% of portfolio despite 10-year horizon')."
    )
    time_horizon_alignment: str = Field(
        description="Is the investor playing their own long-term game, or chasing short-term momentum?"
    )
    volatility_tolerance: str = Field(
        description="Is the investor treating volatility as a fee (acceptable cost) or a fine (punishment to avoid)?"
    )
    compounding_check: str = Field(
        description="Does this action or pattern interrupt a compounding sequence unnecessarily?"
    )
    margin_of_safety: str = Field(
        description="Is there room for error, or does this position or action require perfect execution?"
    )
    final_verdict: str = Field(
        description="Strictly one of: 'REASONABLE', 'CAUTION', 'IRRATIONAL'"
    )
    housel_principle: str = Field(
        description="The principle_id from the framework this audit maps to (e.g., 'nothing_is_free', 'confounding_compounding')."
    )
    housel_quote: str = Field(
        description="One sentence from the framework's principle summary that most directly applies."
    )


class BehavioralAuditorResponse(BaseModel):
    bundle_hash: str = Field(
        description="Echo the composite_hash from the bundle context exactly."
    )
    overall_behavioral_score: str = Field(
        description="Portfolio-level behavioral summary: 'DISCIPLINED', 'MIXED', or 'AT_RISK'."
    )
    summary_narrative: str = Field(
        description="2-3 sentences on the investor's dominant behavioral pattern this period."
    )
    audits: list[BehavioralAudit] = Field(
        description="3 to 7 behavioral audit findings. Quality over quantity."
    )
    top_risk: str = Field(
        description="The single most important behavioral risk to address, in one sentence."
    )
