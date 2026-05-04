from pydantic import BaseModel
from typing import Literal

class NewIdeaVerdict(BaseModel):
    ticker: str
    verdict: Literal["fit", "no_fit", "needs_more_info"]
    style_assignment: Literal["GARP", "THEME", "FUND", "ETF"] | None
    # None only when verdict is "no_fit" or "needs_more_info" with no clear style

    fit_rationale: str
    # For "fit": which style and why; what thesis would need to be written
    # For "no_fit": clear reason — wrong style, thesis break pre-entry, portfolio
    #   already saturated in this theme, etc.
    # For "needs_more_info": what specific information is missing before a verdict
    #   can be reached

    portfolio_overlap_note: str
    # If already held: note that this would be an add (redirect to Add-Candidate agent)
    # If same theme as heavy existing position: note the concentration implication
    # Empty string if no overlap concern

    thesis_required_before_entry: str
    # 1-2 sentences on what thesis statement Bill would need to write before this
    # becomes a real candidate. Empty for "no_fit".

    starter_size_usd: float | None
    # Pre-computed by Python for "fit" verdicts. None for no_fit/needs_more_info.

    scale_step_note: str
    # For "fit": "Starter ${X:,.0f}, scale in as thesis validates" style language
    # Empty for no_fit.

    data_gaps_impact: str
    # If data_gaps is non-empty: how the missing data affects the verdict confidence
    # Empty string if no gaps.

class NewIdeaScreenerOutput(BaseModel):
    bundle_hash: str
    generated_at: str
    verdicts: list[NewIdeaVerdict]
    summary: dict[str, int]
    # {"fit": N, "no_fit": N, "needs_more_info": N, "already_held_redirect": N}
    portfolio_note: str
    # 2-3 sentence aggregate note: does the "fit" set improve portfolio diversification,
    # add redundant exposure, or fill a genuine gap? References style_weights from context.
