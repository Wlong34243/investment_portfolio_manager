# Phase 5-J / 5-K: Buy List Agents — Add-Candidate Analyst & New Idea Screener
**Investment Portfolio Manager | CLI Migration Phase 5 Extension**
*Generated: April 2026 | Handoff target: Claude Code or Gemini CLI*

---

## Context & Prerequisites

This file extends `phase5_agent_port_prompts.md`. All invariants from that file apply
here without exception — read it before executing any prompt below.

**Prerequisites (must be complete before starting 5-J):**
- Phase 5-A: Tax agent ✅ (or in progress)
- Phase 5-D: `analyze-all` orchestrator ✅ (5-J and 5-K integrate into it)
- `Agent_Outputs` tab exists in the Sheet with the schema defined in Appendix A of
  `phase5_agent_port_prompts.md`
- `AgentRunManifest` Pydantic model in `agents/schemas/manifest_schema.py` is defined
  (built in 5-D)

**Design decision (recorded here for audit trail):**
The original nine-file agent kit spec (`02_add_candidate_analyst_prompt.md`,
`buy_list_template.md`) targeted markdown file output (`buy_list.md`). That spec
predates the CLI migration. Both agents now write to **Google Sheets (`Agent_Outputs`
tab)**, consistent with every other Phase 5 agent. The markdown buy list template is
retired as an output target. `buy_list_template.md` is kept as reference documentation
only — it informed the data model for these agents.

---

## Invariants (Non-Negotiable — Inherited from Phase 5)

1. **No LLM math.** All weights, dollar sizes, drift %, and staleness days are
   calculated in Python and passed as facts. Gemini writes narrative and candidate
   assessments only.
2. **Pydantic schemas everywhere.** Every `ask_gemini()` call uses `response_schema`.
3. **DRY_RUN gate.** All Sheet writes check `config.DRY_RUN`. Default dry. Live is
   explicit `--live`.
4. **Single-batch gspread writes.** Archive-before-overwrite on `Agent_Outputs`.
5. **SAFETY_PREAMBLE is auto-prepended** by `ask_gemini()`. Do not duplicate it.
6. **`ask_gemini()` returns Pydantic instances.** Use `.model_dump()` before
   serialization.
7. **Agents never browse or fetch.** Python assembles all context. Agents receive a
   dict.
8. **QACDS and CASH_MANUAL excluded** from all analysis and calculations.
9. **Small-step scaling** encoded in every sizing output. No binary entries.
10. **Output lands in `Agent_Outputs` sandbox only.** `Target_Allocation` is Bill's
    manual-only source.
11. **`composite_hash` propagates.** Every agent Pydantic output includes
    `composite_hash: str`.
12. **PII guard.** Strip account numbers before any LLM context build.
13. **Style short codes.** Always use `GARP`, `THEME`, `FUND`, `ETF` (the `short_code`
    values from `styles.json`). Never use long-form style names in code or schemas.

---

## Prompt 5-J: Add-Candidate Analyst

### Files to read first
```
agents/rebuy_analyst.py                    ← exact structural pattern to replicate
agents/schemas/rebuy_schema.py             ← schema module pattern to replicate
core/composite_bundle.py                   ← how to load the composite bundle
02_add_candidate_analyst_prompt.md         ← original spec (logic source only — output
                                              target has changed from markdown to Sheets)
config.py                                  ← DRY_RUN, TAB_AGENT_OUTPUTS, thresholds
CLAUDE.md                                  ← project invariants
```

### Task
Build `agents/add_candidate_analyst.py` as a new bundle-aware CLI agent. Integrate as
`manager.py agent add-candidate analyze`. The agent reads current holdings from the
composite bundle, filters them against thesis status and rotation priority, and
produces a ranked list of add candidates with scaling plans.

---

### Pre-compute in Python (not LLM)

All of the following must be calculated before the Gemini call:

```python
for each holding in composite["market"]["holdings"]:
    # Filter step — compute disqualification reason in Python, not LLM
    if holding["style"] in ("BROAD_INDEX", "BONDS", "CASH"):
        mark excluded_reason = "non_style_bucket"
        continue
    if holding["rotation_priority"] == "high":
        mark excluded_reason = "rotation_candidate"
        continue
    if thesis_status == "broken":
        mark excluded_reason = "broken_thesis"
        continue

    # Weight drift — Python math
    weight_vs_target_pct = current_weight_pct - target_weight_pct
    already_overweight = weight_vs_target_pct > (target_weight_pct * 0.10)
    if already_overweight:
        mark excluded_reason = "overweight"
        continue

    # Staleness — Python date math
    staleness_days = (today - last_thesis_review_date).days
    stale_flag = staleness_days > 120

    # Max starter add size — Python, never LLM
    # GARP core: 3% of dry_powder_available (capped at 5%)
    # FUND: 2.5% of dry_powder_available
    # THEME / ETF: 1.5% of dry_powder_available
    max_starter_add_usd = dry_powder_available * STYLE_ADD_PCT[style]

    # Position state — infer from vault thesis file scaling_state field
    # Values: "starter" | "half" | "full" | "unknown"
    position_state = parse_scaling_state(vault_thesis_file)
```

**Config constants to add to `config.py`:**
```python
# Phase 5-J: Add-Candidate sizing
ADD_CANDIDATE_STYLE_PCT = {
    "GARP":  0.030,   # 3% of dry powder as starter add
    "FUND":  0.025,
    "THEME": 0.015,
    "ETF":   0.015,
}
ADD_CANDIDATE_MAX_STARTER_PCT = 0.05   # hard cap: never exceed 5% of dry powder
ADD_CANDIDATE_MAX_CANDIDATES = 15      # rank more strictly if list would be longer
ADD_CANDIDATE_STALE_THRESHOLD_DAYS = 120
```

---

### Context passed to Gemini

Build a lean context dict — do not pass the full composite bundle to the LLM:

```python
agent_context = {
    "portfolio_state": {
        "total_value_usd": total_value,
        "dry_powder_available_usd": dry_powder,
        "position_count": len(holdings),
    },
    "styles": styles_json,              # full styles.json inlined
    "candidates": [                     # Python-filtered and pre-computed
        {
            "ticker": ...,
            "style": ...,               # short_code: GARP | THEME | FUND | ETF
            "rotation_priority": ...,
            "current_weight_pct": ...,
            "target_weight_pct": ...,
            "weight_vs_target_pct": ..., # Python-computed
            "position_state": ...,       # starter | half | full | unknown
            "thesis_status": ...,
            "stale_flag": ...,
            "staleness_days": ...,
            "max_starter_add_usd": ...,  # Python-computed, hard cap applied
            "thesis_excerpt": ...,       # first 400 chars of _thesis.md
        }
    ],
    "excluded": [                        # tell the LLM what was filtered and why
        {"ticker": ..., "reason": ...}
    ],
    "composite_hash": composite_hash,
}
```

---

### Pydantic output schema

Create `agents/schemas/add_candidate_schema.py`:

```python
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
    composite_hash: str
    generated_at: str               # ISO timestamp
    candidates: list[AddCandidate]
    deferred: list[DeferredHolding]
    summary: AddCandidateSummary
```

---

### System prompt for Gemini

```
You are the Add-Candidate Analyst in Bill's investment portfolio workflow.

Your job: review the pre-filtered list of holdings in the context bundle and produce
a ranked list of add candidates with scaling plans. The Python layer has already
applied all eligibility filters and computed position sizes. You assess the qualitative
add case for each candidate and rank them.

Hard rules:
- You do not calculate valuations, price targets, or fair values. All sizing figures
  are provided as pre-computed facts — use them as given.
- You do not predict prices. Triggers are pullback percentages or sentiment conditions.
- You respect thesis status. drift-status candidates get a stale-review note; broken
  is already filtered out by the Python layer.
- Candidates, not recommendations. Every output is a draft for Bill's review.
- Style short codes only: GARP, THEME, FUND, ETF.
- starter_add_size_usd must match the pre-computed value from the bundle exactly.
  Do not invent or adjust sizing.
- scaling_plan must have exactly three tranches: starter, add_1, add_2.
- Never suggest a trigger that is an absolute price. Always use pullback percentages
  or sentiment conditions.
- Output must be valid JSON matching the schema. No prose outside the JSON.
- Maximum 15 candidates. If more qualify, rank strictly and defer the rest.
```

---

### Sheet write target

`Agent_Outputs` tab. Each `AddCandidate` serializes as one row:

```
run_id | run_ts | composite_hash[:16] | agent=add_candidate | signal_type=add_candidate
| ticker | action="Add {style} on {trigger_suggestion}" | rationale=add_case
| scale_step="Starter ${starter_add_size_usd:,.0f} → {add_1.condition} → {add_2.condition}"
| severity=("action" if rank <= 5 else "watch") | dry_run=True/False
```

Summary row appended last:
```
signal_type=summary | ticker=PORTFOLIO | action="N add candidates; $X starter deployment"
| rationale=summary.style_mix as string
```

---

### CLI wire-up

```bash
python manager.py agent add-candidate analyze
python manager.py agent add-candidate analyze --bundle bundles/composite_20260413_....json
python manager.py agent add-candidate analyze --live    # writes to Agent_Outputs tab
```

Register in `manager.py` using the same Typer sub-app pattern as `rebuy_analyst.py`.

---

### `analyze-all` integration

Add `add_candidate` to the `AgentRunManifest` in `agents/schemas/manifest_schema.py`:

```python
class AgentRunManifest(BaseModel):
    ...
    add_candidate_output: AddCandidateOutput | None  # add this field
    ...
```

Add to `manager.py analyze-all --agents` flag valid values:
`rebuy,tax,valuation,concentration,add_candidate`

---

### Verification checklist
- [ ] Dry run produces valid `AddCandidateOutput` Pydantic instance with no Sheet writes
- [ ] `composite_hash` in output matches the loaded bundle file
- [ ] All sizing (`starter_add_size_usd`) computed in Python; Gemini output matches
      pre-computed values — mismatches should raise a validation error
- [ ] No absolute price targets in any `trigger_suggestion` or `condition` field
- [ ] `rotation_priority: high` holdings appear in `deferred`, not `candidates`
- [ ] `thesis_status: broken` holdings appear in `deferred`, not `candidates`
- [ ] Stale holdings (> 120 days) appear in `candidates` with `stale_flag: true` and
      a `notes_for_bill` entry — not silently excluded
- [ ] `--live` writes to `Agent_Outputs`, archive fires before overwrite
- [ ] Style codes are `GARP`, `THEME`, `FUND`, `ETF` throughout — no long-form names
- [ ] `analyze-all` includes `add_candidate` in manifest when `--agents` flag includes it
- [ ] CHANGELOG.md updated with `Status:` line

---

## Prompt 5-K: New Idea Screener

### Files to read first
```
agents/rebuy_analyst.py                    ← exact structural pattern to replicate
agents/schemas/rebuy_schema.py             ← schema module pattern to replicate
agents/add_candidate_analyst.py            ← just built in 5-J; consistent patterns
core/composite_bundle.py                   ← how to load the composite bundle
config.py                                  ← DRY_RUN, TAB_AGENT_OUTPUTS, thresholds
CLAUDE.md                                  ← project invariants
```

### Task
Build `agents/new_idea_screener.py` as a bundle-aware CLI agent. Integrate as
`manager.py agent new-idea analyze`. The agent evaluates a user-supplied list of
candidate tickers against Bill's four styles and current portfolio context, and
produces a structured screen output: fit, no-fit, or needs-more-info for each
candidate. It does not generate buy candidates on its own — Bill supplies the tickers.

**Key design constraint:** This agent is invoked with explicit candidate tickers
supplied at the CLI. It does not scan the market or generate its own watchlist.
Python fetches fundamental and market data for the supplied tickers before the LLM
call; the LLM reasons over what it is given.

---

### Pre-compute in Python (not LLM)

For each ticker in `--tickers` list:

```python
for ticker in candidate_tickers:
    # Market data — from composite bundle market_data if present,
    # else from yfinance (acceptable here since this is on-demand, not Sunday headless)
    current_price = ...
    high_52w = ...
    low_52w = ...
    discount_from_52w_high_pct = (high_52w - current_price) / high_52w * 100
    price_52w_range_position_pct = (current_price - low_52w) / (high_52w - low_52w) * 100

    # Overlap check — is this ticker already in the portfolio?
    already_held = ticker in [h["ticker"] for h in holdings]
    current_weight_pct = holdings_map.get(ticker, {}).get("current_weight_pct", 0.0)

    # Style overlap — does this theme already have heavy representation?
    # Compute sector/style weights from current holdings for context
    style_weights = compute_style_weights(holdings)   # {"GARP": 0.32, "THEME": 0.11, ...}

    # Fundamental data — from FMP via fmp_client (best-effort; log gaps)
    pe_fwd = fmp_client.get_forward_pe(ticker)        # None if unavailable
    pe_trailing = fmp_client.get_trailing_pe(ticker)
    revenue_growth_yoy = fmp_client.get_revenue_growth(ticker)
    gross_margin = fmp_client.get_gross_margin(ticker)
    market_cap = fmp_client.get_market_cap(ticker)

    # Missing data is explicit — never silently omit
    data_gaps = [field for field, val in {...}.items() if val is None]
```

**No yfinance calls inside the agent function itself.** All data fetched by the
caller / CLI command before the agent function is invoked.

**Config constants to add to `config.py`:**
```python
# Phase 5-K: New Idea Screener
NEW_IDEA_MAX_CANDIDATES_PER_RUN = 10   # hard cap on --tickers list length
NEW_IDEA_STARTER_SIZE_PCT = 0.015      # 1.5% of dry powder as default starter
NEW_IDEA_MAX_STARTER_PCT = 0.025       # hard cap: 2.5% of dry powder for new ideas
```

---

### Context passed to Gemini

```python
agent_context = {
    "portfolio_state": {
        "total_value_usd": total_value,
        "dry_powder_available_usd": dry_powder,
        "position_count": len(holdings),
        "style_weights": style_weights,     # current portfolio style mix
    },
    "styles": styles_json,                  # full styles.json inlined
    "current_holdings_tickers": [h["ticker"] for h in holdings],  # overlap check
    "candidates": [
        {
            "ticker": ...,
            "already_held": ...,            # bool
            "current_weight_pct": ...,      # 0.0 if not held
            "discount_from_52w_high_pct": ...,
            "price_52w_range_position_pct": ...,
            "pe_fwd": ...,                  # None if unavailable
            "pe_trailing": ...,
            "revenue_growth_yoy": ...,
            "gross_margin": ...,
            "market_cap": ...,
            "data_gaps": [...],             # fields that are None
            "user_note": ...,               # optional note from --note CLI flag
        }
    ],
    "composite_hash": composite_hash,
}
```

---

### Pydantic output schema

Create `agents/schemas/new_idea_schema.py`:

```python
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
    composite_hash: str
    generated_at: str
    verdicts: list[NewIdeaVerdict]
    summary: dict[str, int]
    # {"fit": N, "no_fit": N, "needs_more_info": N, "already_held_redirect": N}
    portfolio_note: str
    # 2-3 sentence aggregate note: does the "fit" set improve portfolio diversification,
    # add redundant exposure, or fill a genuine gap? References style_weights from context.
```

---

### System prompt for Gemini

```
You are the New Idea Screener in Bill's investment portfolio workflow.

Your job: evaluate each candidate ticker in the context bundle against Bill's four
investment styles and current portfolio context. Assign a verdict — fit, no_fit, or
needs_more_info — for each candidate. You are a filter, not a buy list generator.

Hard rules:
- You do not generate candidates. Bill supplies the tickers; you evaluate them.
- You do not calculate valuations, price targets, or fair values. All quantitative
  data is provided as pre-computed facts.
- You do not predict prices or market direction.
- Every "fit" verdict must name a specific style from Bill's four: GARP, THEME,
  FUND, ETF. A ticker that does not fit any of the four styles is a "no_fit".
- If a ticker is already held, flag it as a redirect to the Add-Candidate agent —
  not a new idea.
- starter_size_usd must match the pre-computed value from the bundle. Do not invent
  sizing figures.
- Candidates, not recommendations. Every output is a draft for Bill's review.
- Style short codes only: GARP, THEME, FUND, ETF.
- Output must be valid JSON matching the schema. No prose outside the JSON.
- portfolio_note should specifically call out if the "fit" set would increase
  concentration in a style that already dominates the portfolio.
```

---

### CLI wire-up

```bash
# Basic: evaluate specific tickers
python manager.py agent new-idea analyze --tickers NVDA,TSM,ASML

# With optional note per ticker (parsed as JSON string)
python manager.py agent new-idea analyze \
    --tickers NVDA,TSM \
    --notes '{"NVDA": "AI infrastructure play", "TSM": "foundry exposure"}'

# Live write
python manager.py agent new-idea analyze --tickers NVDA,TSM --live

# Using a specific bundle
python manager.py agent new-idea analyze \
    --tickers NVDA,TSM \
    --bundle bundles/composite_20260413_....json
```

**Validation at CLI entry point (before any data fetch):**
- Reject if `--tickers` list is empty
- Reject if `--tickers` list exceeds `config.NEW_IDEA_MAX_CANDIDATES_PER_RUN` (10)
- Warn (do not reject) if any ticker is already in current holdings — note that
  Add-Candidate agent is the right tool for held positions

---

### Sheet write target

`Agent_Outputs` tab. Each `NewIdeaVerdict` serializes as one row:

```
run_id | run_ts | composite_hash[:16] | agent=new_idea_screener
| signal_type=("new_idea_fit" if verdict=="fit" else "new_idea_screen")
| ticker | action=("Fit: {style_assignment}" or "No fit" or "Needs info")
| rationale=fit_rationale (truncated to 500 chars if needed)
| scale_step=scale_step_note
| severity=("watch" if verdict=="fit" else "info")
| dry_run=True/False
```

Summary row appended last:
```
signal_type=summary | ticker=PORTFOLIO
| action="{fit_count} fit, {no_fit_count} no fit, {needs_info_count} needs more info"
| rationale=portfolio_note
```

---

### `analyze-all` integration

Add `new_idea_screener` to `AgentRunManifest`:

```python
class AgentRunManifest(BaseModel):
    ...
    new_idea_output: NewIdeaScreenerOutput | None   # add this field
    ...
```

**Note:** `analyze-all` runs `new_idea_screener` only if `--tickers` is provided.
Without a ticker list, this agent is skipped silently (not an error):

```bash
python manager.py analyze-all --agents new_idea_screener --tickers NVDA,TSM --live
```

This is intentional — unlike the other agents that run fully automatically from the
bundle, the New Idea Screener requires Bill to supply candidates. It cannot generate
its own watchlist.

---

### Verification checklist
- [ ] Dry run produces valid `NewIdeaScreenerOutput` with no Sheet writes
- [ ] `composite_hash` in output matches the loaded bundle file
- [ ] All quantitative data (`pe_fwd`, `discount_from_52w_high_pct`, etc.) fetched
      in Python before the Gemini call — agent function receives only a pre-built dict
- [ ] Already-held tickers surface in output as `"already_held_redirect"` in summary
      count, not as "fit" or "no_fit"
- [ ] `starter_size_usd` matches Python pre-computation; LLM cannot override it
- [ ] No absolute price targets anywhere in output
- [ ] Style codes are `GARP`, `THEME`, `FUND`, `ETF` throughout
- [ ] `--tickers` list > 10 is rejected at CLI entry with clear error message
- [ ] Empty `--tickers` is rejected at CLI entry
- [ ] Missing FMP data logged in `data_gaps` and surfaced in `data_gaps_impact` —
      never silently dropped
- [ ] `analyze-all` skips this agent gracefully when `--tickers` not provided
- [ ] `--live` writes to `Agent_Outputs`, archive fires before overwrite
- [ ] CHANGELOG.md updated with `Status:` line

---

## Updated `analyze-all` Agent Registry

After 5-J and 5-K are complete, update `manager.py` analyze-all valid agent list:

```
rebuy | tax | valuation | concentration | add_candidate | new_idea_screener
```

And update `AgentRunManifest` in `agents/schemas/manifest_schema.py` to include
both new output fields (as done in the integration sections above).

---

## Updated `PORTFOLIO_SHEET_SCHEMA.md` Additions

Add to the `Agent_Outputs` tab `agent` field valid values list:

```
agent field valid values (updated):
  rebuy | tax | valuation | concentration | add_candidate | new_idea_screener
```

Add to the `signal_type` field valid values list:

```
signal_type valid values (updated):
  tlh_candidate | rebalance | accumulate | trim | flag
  | add_candidate | new_idea_fit | new_idea_screen | summary
```

---

## Updated Full Build Sequence (all agents)

```
5-A  Tax agent                    ← legacy port
5-B  Valuation agent              ← legacy port
5-C  Concentration hedger         ← legacy port
5-D  Macro-cycle agent            ← new
5-E  Thesis screener              ← new (mechanical hardening)
5-F  100-Bagger screener          ← new
5-G  Van Tharp framework          ← vault/frameworks/ routing
5-H  analyze-all orchestrator     ← batch command
5-I  Sunday GitHub Actions        ← automation
5-J  Add-Candidate Analyst        ← this file ← NEW
5-K  New Idea Screener            ← this file ← NEW
```

---

## Appendix: Handoff Instructions for Claude Code

When handing this file to Claude Code, use this session-start prompt:

```
Read phase5_JK_buy_list_agents_prompts.md in full before writing any code.
Then read the following files in order:
  1. CLAUDE.md
  2. CHANGELOG.md (last 3 entries)
  3. phase5_agent_port_prompts.md     ← invariants and patterns
  4. agents/rebuy_analyst.py          ← exact structural pattern to replicate
  5. agents/schemas/rebuy_schema.py   ← schema module pattern
  6. core/composite_bundle.py         ← bundle loading
  7. 02_add_candidate_analyst_prompt.md  ← logic reference for 5-J (output target
                                          has changed to Sheets — see this file)
  8. config.py

Execute in strict order: 5-J → 5-K.
Do not start 5-K until 5-J verification checklist is complete.
Update CHANGELOG.md with a Status: line after each sub-phase.
DRY_RUN defaults true. Never write to Target_Allocation.
Style codes are always GARP, THEME, FUND, ETF — never long-form names.
Agents never call external APIs directly. Python pre-computes; LLM reasons.
```
