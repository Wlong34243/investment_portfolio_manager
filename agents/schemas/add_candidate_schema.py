from pydantic import BaseModel
from typing import Literal

class AddTranche(BaseModel):
    tranche: Literal["starter", "add_1", "add_2"]
    size_usd: float
    condition: str          # pullback % or sentiment condition — never an absolute price

class AddCandidate(BaseModel):
    ticker: str
    rank: int
    style: Literal["GARP", "THEME", "FUND", "ETF"]
    rotation_priority: Literal["low", "medium", "high"]
    current_weight_pct: float
    target_weight_pct: float
    position_state: Literal["starter", "half", "full", "unknown"]
    thesis_status: str
    stale_flag: bool
    staleness_days: int
    add_case: str           # 2-3 sentences: why this is a strong add candidate
    trigger_suggestion: str # pullback % or condition — never an absolute price
    starter_add_size_usd: float     # from Python pre-computation, not LLM invention
    scaling_plan: list[AddTranche]  # exactly 3 tranches
    notes_for_bill: str             # empty string if no special notes

class DeferredHolding(BaseModel):
    ticker: str
    reason: str

class AddCandidateSummary(BaseModel):
    total_candidates: int
    total_deferred: int
    total_flagged_stale: int
    total_suggested_starter_deployment_usd: float
    style_mix: dict[str, int]       # {"GARP": 4, "FUND": 2, ...}

class AddCandidateOutput(BaseModel):
    bundle_hash: str
    generated_at: str               # ISO timestamp
    candidates: list[AddCandidate]
    deferred: list[DeferredHolding]
    summary: AddCandidateSummary
