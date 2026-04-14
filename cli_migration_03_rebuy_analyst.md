# CLI Migration Phase 3 — Re-Buy Analyst on the Spine (v2)
# Target: Claude Code or Gemini CLI 3 Pro
# Prerequisite: Phase 2 complete. core/vault_bundle.py, core/composite_bundle.py,
# and ask_gemini_composite() exist and round-trip cleanly. 51 thesis files
# live under vault/theses/.
#
# Revision v2 changes (relative to v1):
#   - Column drift detection: config.AGENT_OUTPUTS_COLUMNS is the single
#     source of truth for column indices. Sheet header mismatch raises
#     instead of falling back, preventing silent row-matching bugs.
#   - First-live-write interactive confirmation gate. The first time
#     rebuy_analyst writes to Agent_Outputs, the CLI demands an exact
#     confirmation phrase before proceeding.
#   - Dry run footer is now a prominent panel, not a one-liner.
#   - Explicit --live Approval Gate section with 6 blocking criteria.

## Overview

Phase 3 ports the first real agent from the nine-file agent kit onto the
composite bundle architecture. Every infrastructure decision from Phases 1
and 2 — immutable hashes, content-addressed storage, sandboxed writes,
DRY_RUN defaults, `composite_hash` in response metadata — gets exercised
end-to-end when Re-Buy Analyst produces its first recommendation.

This is the proof that the migration was worth doing.

## Why Re-Buy Analyst is the right first agent

Re-Buy Analyst is the most architecturally demanding of the four agents in
the kit. It needs live market state (price, position weight, unrealized
G/L, scaling room within target allocation), the thesis file for the
specific ticker being analyzed, the canonical style definitions from
`styles.json`, and the small-step scaling rules that govern sizing
guidance. Every channel of the composite bundle gets touched.

If Re-Buy works cleanly, the other three agents in Phase 5 are mostly
variations on the same pattern. Validate on the hardest one first.

## What Phase 3 produces

Phase 3 is split into two landings for the same reason Phase 1 was split
into 1 and 1b: the single-ticker path proves correctness, and the batch
path proves scale. Each gets its own commit and its own rollback point.

- **Phase 3 (this file)**: single-ticker Re-Buy Analyst, end-to-end.
  `manager.py rebuy --ticker UNH --composite latest` runs the agent,
  verifies hashes, writes to the new `Agent_Outputs` tab (sandboxed),
  and returns structured JSON with confidence tiers.
- **Phase 3b (follow-up, written against Phase 3's final state)**: batch
  mode. `manager.py rebuy --all` iterates over every current position
  with rate limiting and writes a batch of outputs.

## Key Design Decisions

1. **Agent outputs live in a new tab, not `AI_Suggested_Allocation`.**
   That tab is the podcast pipeline's. Mixing agent outputs there would
   blur what's a macro allocation signal vs. a per-position re-buy
   recommendation. New tab: `Agent_Outputs`.

2. **Sandbox-only, always.** Re-Buy Analyst writes to `Agent_Outputs`
   and nowhere else. `Target_Allocation` is manual-only forever. This
   is enforced in the agent module itself — a `grep` for
   `Target_Allocation` in `agents/` must return zero matches.

3. **Model pinned to `gemini-2.5-pro`.** Per the ADC migration CHANGELOG
   entry, `gemini-2.5-pro` is accessible via Vertex AI and already wired
   into `ask_gemini_composite()`. Re-Buy Analyst is the agent where
   reasoning quality matters most — it's synthesizing thesis text,
   price context, and scaling rules into a recommendation Bill will
   actually act on. Pro is worth the cost here. The other three agents
   in Phase 5 can stay on Flash.

4. **Confidence tiers are input-quality signals, not analyst conviction.**
   The agent does NOT express its own confidence in its recommendation.
   It reports a confidence tier that reflects whether its inputs were
   complete:
   - `high`: thesis file present AND price is from yfinance live AND
     position has >30 days of price history
   - `medium`: thesis present but price is CSV fallback, OR price live
     but thesis missing
   - `low`: both thesis and live price missing (e.g., new IPO with no
     thesis yet)
   This discipline prevents the agent from confabulating conviction it
   doesn't have.

5. **No price targets, no market predictions, small-step scaling
   required.** These are the agent kit hard rules from project memory.
   The system prompt enforces them structurally and the Pydantic schema
   does NOT include fields for price targets or market direction.
   The agent physically cannot return those values.

6. **`thesis_available: false` is not a failure.** A position without a
   thesis file still gets analyzed, but the response records
   `thesis_available: false`, the confidence tier drops, and the
   rationale explicitly notes the missing thesis.

7. **Rotation source is required.** Every Re-Buy recommendation must
   name the position being sold to fund the buy, OR explicitly mark
   `rotation_source: "cash"` with a justification. Exits are rotations;
   this is encoded in the schema.

8. **Archive-before-overwrite on `Agent_Outputs`.** Same pattern as the
   podcast pipeline. Previous rows for the same (agent, ticker) pair
   are archived to the `Logs` tab before being replaced.

9. **Column drift detection is loud.** `config.AGENT_OUTPUTS_COLUMNS`
   is the single source of truth for column positions. If the live
   sheet header ever disagrees (manual edit, reorder, new column
   inserted), the archive logic RAISES rather than falling back to
   hardcoded indices. A silent wrong answer is worse than a loud
   failure, especially for audit-trail code.

10. **First-live-write interactive confirmation gate.** The first time
    `rebuy_analyst` ever writes to `Agent_Outputs`, the CLI demands an
    exact confirmation phrase before proceeding. This is deliberate
    friction at the exact moment the audit trail becomes real. After
    the first row exists, the gate no-ops.

11. **Ticker-to-thesis resolution is case-insensitive and exact.**
    `UNH_thesis.md` matches ticker `UNH`, `unh`, or `Unh`. No fuzzy
    matching — if the file isn't named correctly, the agent reports
    `thesis_available: false` and runs with lower confidence.

---

## Pre-flight Checklist

Before running these prompts, confirm:
- [ ] `core/bundle.py`, `core/vault_bundle.py`, `core/composite_bundle.py`
      all import cleanly
- [ ] `ask_gemini_composite()` exists in `utils/gemini_client.py` and
      stamps `composite_hash` into response metadata
- [ ] At least one composite bundle exists under `bundles/` and
      `manager.py bundle verify` reports it clean
- [ ] `vault/theses/` contains thesis files matching the naming
      convention `<TICKER>_thesis.md`
- [ ] `styles.json` is loaded into the vault bundle
- [ ] `config.GEMINI_MODEL == "gemini-2.5-pro"`
- [ ] ADC auth is active (`gcloud auth application-default print-access-token`)
- [ ] `Agent_Outputs` tab does NOT yet exist on the Portfolio Sheet
      (Prompt 2 creates it)

---

## Prompt 1 of 6: Create the Pydantic schemas and helpers

```text
Read these files before writing code:
- utils/gemini_client.py  (for ask_gemini_composite signature)
- core/composite_bundle.py  (for load_composite and document resolution)
- core/vault_bundle.py  (for resolve_document / read_document)

Create a new directory agents/ (at the repo root) with an empty __init__.py
if it doesn't already exist. Note: this is distinct from utils/agents/
which holds the legacy Streamlit-era agents. The new agents/ directory is
the bundle-aware agent home.

Create: agents/rebuy_analyst.py

Module docstring:
    """
    Re-Buy Analyst — evaluates whether to add to an existing position
    by scaling in, given the position's thesis, current market state,
    and Bill's four-style investment framework.

    Hard rules (enforced in schema, system prompt, and post-validation):
      - No price targets
      - No market predictions
      - Small-step scaling only — no binary "buy full position" advice
      - Rotation source must be named (another ticker, or explicit cash)
      - Sandbox output only — writes to Agent_Outputs, never to
        Target_Allocation or Holdings_Current

    All outputs carry the composite_hash of the bundle they were
    generated from, creating a permanent audit chain from snapshot to
    conclusion.
    """

Imports:
    from __future__ import annotations

    import json
    import logging
    from pathlib import Path
    from typing import Literal

    from pydantic import BaseModel, Field, field_validator

    from core.composite_bundle import load_composite
    from core.vault_bundle import resolve_document, read_document
    from utils.gemini_client import ask_gemini_composite

    logger = logging.getLogger(__name__)

Constants:
    AGENT_NAME = "rebuy_analyst"
    AGENT_VERSION = "1.0.0"

Define the response schema. IMPORTANT: the schema structurally excludes
price targets and market predictions. If you find yourself about to add a
`target_price` or `market_view` field, stop — the hard rules are enforced
at the schema level on purpose.

    class ScalingStep(BaseModel):
        """A single step in a scaling plan. Small-step scaling is required."""
        step_number: int = Field(..., ge=1, le=5,
            description="Step ordinal (1-5 max — no binary entries)")
        trigger_condition: str = Field(..., min_length=10,
            description="What market condition triggers this step (e.g., "
                        "'price drops 5% from current', 'thesis check-in "
                        "after earnings')")
        dollar_amount: float = Field(..., gt=0,
            description="USD amount to deploy at this step")
        rationale: str = Field(..., min_length=20,
            description="Why this size at this trigger")


    class RebuyAnalysis(BaseModel):
        """Re-Buy Analyst output schema. Structurally excludes price targets."""

        # Provenance — required, verified post-LLM
        composite_hash: str = Field(..., min_length=64, max_length=64,
            description="SHA256 hash of the composite bundle consumed")
        agent_name: Literal["rebuy_analyst"] = "rebuy_analyst"
        agent_version: str = Field(default=AGENT_VERSION)

        # Input quality signals
        ticker: str = Field(..., min_length=1, max_length=10)
        thesis_available: bool
        price_source: Literal["yfinance_live", "csv_fallback", "manual"]
        confidence_tier: Literal["high", "medium", "low"]
        confidence_rationale: str = Field(..., min_length=20,
            description="Why this confidence tier — reflects input quality, "
                        "NOT analyst conviction in the recommendation")

        # The recommendation
        recommendation: Literal["scale_in", "hold", "do_not_add", "insufficient_context"]
        recommendation_rationale: str = Field(..., min_length=50)

        # Scaling plan — required when recommendation is scale_in
        scaling_plan: list[ScalingStep] = Field(default_factory=list)

        # Rotation source — required when recommendation is scale_in
        rotation_source: str | None = Field(default=None,
            description="Ticker being sold to fund this add, OR the literal "
                        "string 'cash' with justification in rotation_rationale")
        rotation_rationale: str | None = Field(default=None)

        # Thesis drift check
        thesis_drift_flag: bool = Field(default=False,
            description="True if the current position behavior contradicts "
                        "the stated thesis")
        thesis_drift_notes: str = Field(default="")

        # Style alignment
        style: Literal["garp", "thematic", "boring", "etf", "unclassified"]
        style_alignment_notes: str = Field(..., min_length=20)

        @field_validator("scaling_plan")
        @classmethod
        def validate_scaling_plan_size(cls, v):
            if len(v) > 5:
                raise ValueError("Scaling plan cannot exceed 5 steps "
                                 "(small-step scaling rule)")
            return v

Write the `resolve_thesis` helper:

    def resolve_thesis(composite_data: dict, ticker: str) -> dict | None:
        """
        Find the thesis document for a ticker in a composite bundle.

        Returns the document record, or None if no thesis exists.
        Case-insensitive on ticker.
        """
        vault = composite_data.get("vault", {})
        docs = vault.get("documents", [])
        matches = resolve_document(
            {"documents": docs},
            doc_type="thesis",
            ticker=ticker,
        )
        return matches[0] if matches else None

Write the `classify_confidence` helper:

    def classify_confidence(
        thesis_available: bool,
        price_source: str,
        has_price_history: bool,
    ) -> tuple[str, str]:
        """
        Classify input quality into a confidence tier.

        Returns (tier, rationale). Pure function — no LLM call.
        """
        if thesis_available and price_source == "yfinance_live" and has_price_history:
            return (
                "high",
                "Thesis file present, live price from yfinance, "
                "sufficient price history for context.",
            )
        if not thesis_available and price_source != "yfinance_live":
            return (
                "low",
                "Thesis missing AND price is not live. Agent is operating "
                "with minimal context; treat recommendation as directional only.",
            )
        missing = []
        if not thesis_available:
            missing.append("thesis file")
        if price_source != "yfinance_live":
            missing.append("live price (using csv_fallback)")
        if not has_price_history:
            missing.append("sufficient price history")
        return (
            "medium",
            f"Partial context: missing {', '.join(missing)}. "
            f"Recommendation should be weighted against this gap.",
        )

Do NOT:
- Add price_target, target_price, market_view, or any field implying
  future-price prediction to the schema
- Import streamlit
- Write to Google Sheets from this module
- Use string matching on ticker names beyond case normalization
```

---

## Prompt 2 of 6: Create the Agent_Outputs tab with verified column order

```text
Read config.py and create_portfolio_sheet.py before making changes.

=== EDIT 1: config.py ===

Add the following constants to config.py, after the existing
TAB_AI_SUGGESTED_ALLOCATION block:

    # Agent_Outputs — Phase 3+ agent recommendations (sandbox)
    TAB_AGENT_OUTPUTS = "Agent_Outputs"

    # IMPORTANT: This list is the SINGLE SOURCE OF TRUTH for column
    # positions in Agent_Outputs. The write path in manager.py derives
    # column indices from this list rather than reading the live sheet
    # header. If this list is ever reordered, create_portfolio_sheet.py
    # must be re-run to repair the sheet header.
    AGENT_OUTPUTS_COLUMNS = [
        'Date',               # 0
        'Agent',              # 1
        'Agent_Version',      # 2
        'Ticker',             # 3
        'Composite_Hash',     # 4
        'Recommendation',     # 5
        'Confidence_Tier',    # 6
        'Price_Source',       # 7
        'Thesis_Available',   # 8
        'Style',              # 9
        'Rotation_Source',    # 10
        'Scaling_Step_Count', # 11
        'Rationale',          # 12
        'Full_Response_JSON', # 13
        'Fingerprint',        # 14
    ]

    AGENT_OUTPUTS_COL_MAP = {
        'date': 'Date',
        'agent': 'Agent',
        'agent_version': 'Agent_Version',
        'ticker': 'Ticker',
        'composite_hash': 'Composite_Hash',
        'recommendation': 'Recommendation',
        'confidence_tier': 'Confidence_Tier',
        'price_source': 'Price_Source',
        'thesis_available': 'Thesis_Available',
        'style': 'Style',
        'rotation_source': 'Rotation_Source',
        'scaling_step_count': 'Scaling_Step_Count',
        'rationale': 'Rationale',
        'full_response_json': 'Full_Response_JSON',
        'fingerprint': 'Fingerprint',
    }

=== EDIT 2: create_portfolio_sheet.py ===

Add to the SCHEMA dict, using config.AGENT_OUTPUTS_COLUMNS as the source
of truth rather than duplicating the list:

    import config
    # ... in the SCHEMA dict definition:
    "Agent_Outputs": config.AGENT_OUTPUTS_COLUMNS,

Add "Agent_Outputs" to the TABS_TO_FREEZE list.

=== EDIT 3: PORTFOLIO_SHEET_SCHEMA.md ===

Add a new section for Agent_Outputs. Place it immediately AFTER
AI_Suggested_Allocation and BEFORE Risk_Metrics. Include the
column-by-column schema, fingerprint format (`date|agent|ticker`),
and write pattern (archive-before-overwrite on the Logs tab).

Also add a note: "Column order is authoritative in
config.AGENT_OUTPUTS_COLUMNS. Do not reorder columns manually in the
Google Sheet — the archive logic will refuse to run on drift."

=== VERIFICATION ===

Run the creator:
    python create_portfolio_sheet.py

Then verify the live sheet header matches config. This check is the
proof that Edit 1 and Edit 2 are in sync:

    python -c "
    import config
    from utils.sheet_readers import get_gspread_client
    client = get_gspread_client()
    ws = client.open_by_key(config.PORTFOLIO_SHEET_ID).worksheet(
        config.TAB_AGENT_OUTPUTS
    )
    header = ws.row_values(1)
    assert header == config.AGENT_OUTPUTS_COLUMNS, (
        f'Header drift!\n'
        f'  Sheet:  {header}\n'
        f'  Config: {config.AGENT_OUTPUTS_COLUMNS}'
    )
    print(f'Agent_Outputs header matches config: {len(header)} columns')
    "

    python -c "import config; print(config.TAB_AGENT_OUTPUTS)"
    # Must print: Agent_Outputs

Do NOT:
- Modify any existing tab schemas
- Touch AI_Suggested_Allocation or Target_Allocation
- Hardcode the column list anywhere except config.AGENT_OUTPUTS_COLUMNS
```

---

## Prompt 3 of 6: Implement the agent system prompt and analyze_rebuy function

```text
Read agents/rebuy_analyst.py (from Prompt 1) before adding the
system prompt and the main function.

Append to agents/rebuy_analyst.py:

Define the system prompt as a module-level constant. This is the hardest
and most iterated part of the agent — it encodes Bill's investment
philosophy into machine-readable rules.

    REBUY_SYSTEM_PROMPT = \"\"\"You are the Re-Buy Analyst for Bill's personal investment portfolio.
Your job is to evaluate whether to add to an EXISTING position by scaling
in, given the position's thesis, current market state, and Bill's
four-style investment framework.

## Hard rules — violating any of these is a failure

1. **No price targets.** You do not predict where any security's price
   is going. You do not recommend buying "until X dollars" or "if the
   price reaches Y." Scaling triggers are condition-based (e.g., "after
   the next earnings print", "if the position drops 5% from current
   cost basis"), not price-based.

2. **No market predictions.** You do not speculate on the direction of
   the S&P, the Fed, rates, or any macro variable. If a thesis hinges
   on a macro view, report that as part of thesis drift analysis, but
   do not add your own macro layer.

3. **Small-step scaling only.** Re-buy recommendations must come as a
   plan of 1 to 5 small steps, each with a distinct trigger and dollar
   amount. Never recommend a single large add.

4. **Rotation source is mandatory.** Every scale_in recommendation
   must name the ticker being sold to fund the add, OR explicitly mark
   the source as "cash" with a justification for deploying dry powder
   now vs. later.

5. **Sandbox output only.** You write recommendations to Agent_Outputs.
   You never write to Target_Allocation or Holdings_Current. Bill
   reviews and promotes manually.

## Bill's four investment styles

You will receive the full styles.json from the composite bundle. Use
these definitions to classify which style the target ticker falls under
and assess alignment. The four styles are:
  - garp: GARP-by-intuition (undervalued companies with strong
    product/market understanding)
  - thematic: Thematic specialists (buying market position over company
    quality)
  - boring: Boring fundamentals + dip-buying on fear-driven discounts
  - etf: Sector/Thematic ETFs as macro expressions

## How to reason

1. **Read the thesis first.** If a thesis file is present for this
   ticker, read it carefully. Your recommendation must either align
   with the thesis OR flag thesis drift (thesis_drift_flag=true) with
   explicit notes on what has changed.

2. **Check input quality.** You will be told the price_source
   (yfinance_live | csv_fallback | manual) and whether the thesis is
   available. The confidence_tier field is computed by the caller
   based on input quality. Propagate it exactly as given.

3. **Choose one of four recommendations:**
   - scale_in: add to the position via a small-step plan
   - hold: do nothing, the position is appropriately sized
   - do_not_add: actively avoid adding (thesis drift, overconcentration,
     better rotations available)
   - insufficient_context: you cannot make a recommendation without
     more information

4. **Build a scaling plan if and only if recommendation is scale_in.**
   1 to 5 steps. Each step has a trigger_condition, a dollar_amount,
   and a rationale. Total deployment should be small relative to the
   current position size — this is scaling, not doubling down.

5. **Name the rotation source.** If scale_in, what are you selling to
   fund this? If cash, justify deploying now.

## Output format

Return ONLY valid JSON matching the RebuyAnalysis schema. You MUST
include the composite_hash field with the exact hash provided in the
context preamble. The post-processor will verify this matches and will
overwrite your value if it drifts, so stamp it accurately.
\"\"\"

Implement the main function:

    def analyze_rebuy(
        ticker: str,
        composite_path: Path,
        vault_root: Path,
    ) -> RebuyAnalysis:
        \"\"\"
        Run the Re-Buy Analyst against a ticker, consuming a composite
        bundle for all context.

        Raises:
            FileNotFoundError: composite bundle missing
            ValueError: composite hash verification failed (tampered)
            ValueError: ticker not in current holdings
            ValueError: LLM response failed schema validation after retries
        \"\"\"
        ticker = ticker.upper().strip()
        composite_path = Path(composite_path)

        # Load and verify the composite bundle. This raises on any hash
        # mismatch — market, vault, OR composite.
        composite_data = load_composite(composite_path)
        market = composite_data["market"]
        vault = composite_data["vault"]
        composite_hash = composite_data["composite"]["bundle_hash"]

        # Locate the position in market state
        positions = market.get("positions", [])
        position = next(
            (p for p in positions if p.get("ticker", "").upper() == ticker),
            None,
        )
        if position is None:
            available = sorted({p.get("ticker", "") for p in positions})[:20]
            raise ValueError(
                f"Ticker {ticker} not found in composite market bundle. "
                f"Available tickers: {available}..."
            )

        # Resolve thesis
        thesis_doc = resolve_thesis(composite_data, ticker)
        thesis_available = thesis_doc is not None
        thesis_text = ""
        if thesis_doc is not None:
            try:
                thesis_text = read_document(vault_root, thesis_doc)
            except ValueError as e:
                logger.warning(
                    "Thesis for %s failed content hash check: %s", ticker, e
                )
                thesis_available = False

        # Classify input quality
        price_source = position.get("price_source", "csv_fallback")
        has_price_history = position.get("market_value", 0) > 0  # simple proxy
        confidence_tier, confidence_rationale = classify_confidence(
            thesis_available=thesis_available,
            price_source=price_source,
            has_price_history=has_price_history,
        )

        # Build the user prompt. The system prompt is passed separately
        # to ask_gemini_composite; this prompt contains the task-specific
        # context.
        user_prompt = _build_user_prompt(
            ticker=ticker,
            position=position,
            thesis_text=thesis_text,
            thesis_available=thesis_available,
            confidence_tier=confidence_tier,
            confidence_rationale=confidence_rationale,
            styles_json=vault.get("styles_json", {}),
        )

        # Call Gemini via the composite-aware wrapper
        response = ask_gemini_composite(
            prompt=user_prompt,
            composite_path=composite_path,
            response_schema=RebuyAnalysis,
            system_instruction=REBUY_SYSTEM_PROMPT,
            max_tokens=4000,
        )

        if response is None:
            raise ValueError(
                f"ask_gemini_composite returned None for ticker {ticker}. "
                "Check logs for API errors."
            )

        # Post-validation: force the correct hash and input signals.
        # The LLM may hallucinate the hash; we trust the file, not the LLM.
        response.composite_hash = composite_hash
        response.ticker = ticker
        response.thesis_available = thesis_available
        response.price_source = price_source
        response.confidence_tier = confidence_tier
        response.confidence_rationale = confidence_rationale

        return response


    def _build_user_prompt(
        ticker: str,
        position: dict,
        thesis_text: str,
        thesis_available: bool,
        confidence_tier: str,
        confidence_rationale: str,
        styles_json: dict,
    ) -> str:
        \"\"\"Assemble the task-specific user prompt.\"\"\"
        thesis_block = (
            f"## Thesis for {ticker}\\n\\n{thesis_text}"
            if thesis_available
            else f"## Thesis for {ticker}\\n\\n[NO THESIS FILE — operating "
                 f"with minimal context. confidence_tier will be downgraded.]"
        )

        position_block = (
            f"## Current Position: {ticker}\\n"
            f"- Quantity: {position.get('quantity')}\\n"
            f"- Price: ${position.get('price')} "
            f"(source: {position.get('price_source')})\\n"
            f"- Market Value: ${position.get('market_value', 0):,.2f}\\n"
            f"- Cost Basis: ${position.get('cost_basis', 0):,.2f}\\n"
            f"- Weight: {position.get('weight_pct', 0):.2f}% of portfolio\\n"
            f"- Asset Class: {position.get('asset_class', 'unknown')}\\n"
            f"- Asset Strategy: {position.get('asset_strategy', 'unknown')}\\n"
        )

        styles_block = (
            "## Bill's Investment Styles (from styles.json)\\n\\n"
            f"{json.dumps(styles_json, indent=2)}"
        )

        input_quality_block = (
            f"## Input Quality\\n"
            f"- Confidence tier: {confidence_tier}\\n"
            f"- Rationale: {confidence_rationale}\\n"
            f"- Thesis available: {thesis_available}\\n"
            f"- Price source: {position.get('price_source')}\\n"
            f"\\nYou must propagate confidence_tier={confidence_tier} and "
            f"thesis_available={thesis_available} into your response.\\n"
        )

        task_block = (
            f"## Task\\n\\n"
            f"Analyze whether to scale into {ticker} given the current "
            f"position, thesis, and input quality above. Return a "
            f"RebuyAnalysis JSON object. Remember the hard rules: no price "
            f"targets, no market predictions, small-step scaling only, "
            f"rotation source required for scale_in, sandbox output only.\\n"
        )

        return "\\n\\n".join([
            position_block,
            thesis_block,
            styles_block,
            input_quality_block,
            task_block,
        ])

Do NOT:
- Inline the composite data into the prompt (ask_gemini_composite
  already does that via its own bundle preamble)
- Call the LLM from _build_user_prompt
- Trust the LLM's returned composite_hash — always overwrite with
  the verified file hash
```

---

## Prompt 4 of 6: Add the `rebuy` subcommand with drift detection and first-live gate

```text
Read manager.py before making changes. The `vault-snapshot` and `compose`
subcommands from Phase 2 are the pattern to mirror.

Add a new subcommand AFTER the existing `compose` subcommand:

    @app.command()
    def rebuy(
        ticker: str = typer.Option(..., "--ticker", help="Ticker to analyze"),
        composite: str = typer.Option("latest", "--composite",
            help="Composite bundle path or 'latest'"),
        vault_root: Path = typer.Option(
            Path("vault"), "--vault-root",
            help="Path to vault directory (for reading thesis files)",
            exists=True, file_okay=False, dir_okay=True, resolve_path=True,
        ),
        live: bool = typer.Option(False, "--live",
            help="Enable live mode — writes to Agent_Outputs tab."),
    ):
        \"\"\"Run Re-Buy Analyst against a ticker, using a composite bundle.\"\"\"
        from agents.rebuy_analyst import analyze_rebuy, AGENT_NAME, AGENT_VERSION
        from core.composite_bundle import COMPOSITE_BUNDLE_DIR

        # Banner
        if live:
            console.print(Panel.fit(
                "[bold white on red] LIVE MODE — Agent_Outputs write enabled [/]",
                border_style="red",
            ))
        else:
            console.print(Panel.fit(
                "[bold black on yellow] DRY RUN — No Sheet writes. [/]",
                border_style="yellow",
            ))

        # Resolve composite path
        if composite == "latest":
            composites = sorted(COMPOSITE_BUNDLE_DIR.glob("composite_bundle_*.json"))
            if not composites:
                console.print("[red]No composite bundles found. Run "
                              "`manager.py compose` first.[/]")
                raise typer.Exit(code=1)
            composite_path = composites[-1]
        else:
            composite_path = Path(composite)

        console.print(f"[cyan]Composite:[/] {composite_path.name}")
        console.print(f"[cyan]Ticker:[/] {ticker.upper()}")

        # Run the agent
        with console.status(f"[cyan]Running Re-Buy Analyst on {ticker.upper()}..."):
            try:
                result = analyze_rebuy(
                    ticker=ticker,
                    composite_path=composite_path,
                    vault_root=vault_root,
                )
            except ValueError as e:
                console.print(f"[red]Agent failed:[/] {e}")
                raise typer.Exit(code=1)

        # Summary table
        table = Table(title=f"Re-Buy Analysis: {result.ticker}",
                      show_header=False, box=None)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_row("Composite Hash", f"[green]{result.composite_hash[:16]}...[/]")
        table.add_row("Recommendation", f"[bold]{result.recommendation}[/]")
        table.add_row("Confidence", result.confidence_tier)
        table.add_row("Thesis Available", str(result.thesis_available))
        table.add_row("Price Source", result.price_source)
        table.add_row("Style", result.style)
        if result.rotation_source:
            table.add_row("Rotation Source", result.rotation_source)
        table.add_row("Scaling Steps", str(len(result.scaling_plan)))
        table.add_row("Thesis Drift", "⚠ YES" if result.thesis_drift_flag else "no")
        console.print(table)

        # Rationale panel
        console.print(Panel(
            result.recommendation_rationale,
            title="Rationale",
            border_style="cyan",
        ))

        # Scaling plan table if present
        if result.scaling_plan:
            plan_table = Table(title="Scaling Plan")
            plan_table.add_column("Step", style="cyan")
            plan_table.add_column("Trigger", style="white")
            plan_table.add_column("Amount", style="green", justify="right")
            plan_table.add_column("Rationale", style="white")
            for step in result.scaling_plan:
                plan_table.add_row(
                    str(step.step_number),
                    step.trigger_condition,
                    f"${step.dollar_amount:,.2f}",
                    step.rationale[:80] + ("..." if len(step.rationale) > 80 else ""),
                )
            console.print(plan_table)

        # Dry-run gate — prominent footer, not a one-liner
        if not live:
            console.print(Panel.fit(
                "[bold yellow]DRY RUN COMPLETE — NOTHING WRITTEN[/]\\n\\n"
                "Review the output above. If the rationale, confidence, and\\n"
                "scaling plan match your reasoning, re-run with --live to commit\\n"
                "this analysis to the Agent_Outputs audit trail.",
                border_style="yellow",
            ))
            return

        # Live write path
        console.print("\\n[cyan]Writing to Agent_Outputs...[/]")
        _write_agent_output_to_sheet(result)
        console.print("[green]✓ Written to Agent_Outputs[/]")


    def _write_agent_output_to_sheet(result):
        \"\"\"
        Archive-before-overwrite write to Agent_Outputs tab, with loud
        column drift detection and a first-live-write confirmation gate.

        config.AGENT_OUTPUTS_COLUMNS is the single source of truth for
        column positions. If the live sheet header disagrees, this
        function raises RuntimeError rather than falling back to
        hardcoded indices — silent row-matching bugs in audit-trail
        code are worse than loud failures.
        \"\"\"
        import time
        from datetime import datetime
        import json as _json
        import config
        from agents.rebuy_analyst import AGENT_NAME, AGENT_VERSION
        from utils.sheet_readers import get_gspread_client

        # Derive column indices from config — the single source of truth.
        try:
            expected_agent_col = config.AGENT_OUTPUTS_COLUMNS.index("Agent")
            expected_ticker_col = config.AGENT_OUTPUTS_COLUMNS.index("Ticker")
        except ValueError as e:
            raise RuntimeError(
                f"config.AGENT_OUTPUTS_COLUMNS is missing a required column: {e}. "
                "The archive logic cannot proceed without Agent and Ticker columns."
            )

        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_AGENT_OUTPUTS)

        existing = ws.get_all_values()
        header = existing[0] if existing else []

        # Verify the live sheet header matches config. If not, the sheet
        # has drifted and we must refuse to archive rather than risk
        # matching the wrong rows.
        if not header:
            raise RuntimeError(
                "Agent_Outputs tab has no header row. Run "
                "create_portfolio_sheet.py to repair."
            )
        try:
            live_agent_col = header.index("Agent")
            live_ticker_col = header.index("Ticker")
        except ValueError:
            raise RuntimeError(
                f"Agent_Outputs header is missing Agent or Ticker column. "
                f"Header: {header}. Refusing to archive to prevent "
                f"row mismatch. Run create_portfolio_sheet.py to repair."
            )
        if (live_agent_col, live_ticker_col) != (expected_agent_col, expected_ticker_col):
            raise RuntimeError(
                f"Agent_Outputs column order drift detected.\\n"
                f"  Config expects: Agent at col {expected_agent_col}, "
                f"Ticker at col {expected_ticker_col}\\n"
                f"  Sheet has:      Agent at col {live_agent_col}, "
                f"Ticker at col {live_ticker_col}\\n"
                f"Run create_portfolio_sheet.py to repair, or fix manually. "
                f"Refusing to archive."
            )

        agent_col = expected_agent_col
        ticker_col = expected_ticker_col

        # --- First-live-write confirmation gate ---
        # If this is the first time rebuy_analyst will write to the tab,
        # demand an exact confirmation phrase. After the first row exists,
        # this gate no-ops.
        has_prior_rebuy = any(
            len(row) > max(agent_col, ticker_col)
            and row[agent_col] == AGENT_NAME
            for row in existing[1:]
        )
        if not has_prior_rebuy:
            console.print(Panel.fit(
                "[bold yellow]⚠ FIRST LIVE WRITE OF REBUY_ANALYST[/]\\n\\n"
                "This is the first time this agent will write to Agent_Outputs.\\n"
                "Once written, this row is part of your audit trail.\\n\\n"
                f"Ticker: [cyan]{result.ticker}[/]\\n"
                f"Recommendation: [cyan]{result.recommendation}[/]\\n"
                f"Confidence: [cyan]{result.confidence_tier}[/]\\n\\n"
                "Have you reviewed the DRY RUN output for this ticker and\\n"
                "confirmed the rationale, confidence tier, and scaling plan\\n"
                "match your reasoning?",
                border_style="yellow",
            ))
            confirmation = typer.prompt(
                "Type 'I have reviewed the dry run' to proceed",
                default="",
            )
            if confirmation.strip() != "I have reviewed the dry run":
                console.print("[red]Confirmation not received. Aborting. "
                              "No rows written.[/]")
                raise typer.Exit(code=1)

        today = datetime.now().strftime("%Y-%m-%d")
        fingerprint = f"{today}|{AGENT_NAME}|{result.ticker}"

        # Archive existing rows for this (agent, ticker) to Logs
        if len(existing) > 1:
            matching = [
                row for row in existing[1:]
                if len(row) > max(agent_col, ticker_col)
                and row[agent_col] == AGENT_NAME
                and row[ticker_col] == result.ticker
            ]
            if matching:
                ws_logs = spreadsheet.worksheet("Logs")
                log_rows = [
                    [datetime.now().isoformat(), "INFO", "Rebuy_Analyst",
                     f"Archived row for {result.ticker}", _json.dumps(row)[:500]]
                    for row in matching
                ]
                ws_logs.append_rows(log_rows, value_input_option="USER_ENTERED")
                time.sleep(1.0)
                # Rewrite the sheet with the matching rows removed
                kept = [header] + [
                    row for row in existing[1:]
                    if not (
                        len(row) > max(agent_col, ticker_col)
                        and row[agent_col] == AGENT_NAME
                        and row[ticker_col] == result.ticker
                    )
                ]
                ws.clear()
                ws.update("A1", kept, value_input_option="USER_ENTERED")
                time.sleep(1.0)

        # Build the new row in exact config column order
        new_row = [
            today,                                     # Date
            AGENT_NAME,                                # Agent
            AGENT_VERSION,                             # Agent_Version
            result.ticker,                             # Ticker
            result.composite_hash,                     # Composite_Hash
            result.recommendation,                     # Recommendation
            result.confidence_tier,                    # Confidence_Tier
            result.price_source,                       # Price_Source
            str(result.thesis_available),              # Thesis_Available
            result.style,                              # Style
            result.rotation_source or "",              # Rotation_Source
            len(result.scaling_plan),                  # Scaling_Step_Count
            result.recommendation_rationale[:500],     # Rationale
            result.model_dump_json()[:45000],          # Full_Response_JSON
            fingerprint,                               # Fingerprint
        ]
        assert len(new_row) == len(config.AGENT_OUTPUTS_COLUMNS), (
            f"Row length {len(new_row)} does not match "
            f"{len(config.AGENT_OUTPUTS_COLUMNS)} columns in config"
        )
        ws.append_row(new_row, value_input_option="USER_ENTERED")

Do NOT:
- Modify existing subcommands
- Write to any tab other than Agent_Outputs and Logs
- Skip the archive step or the drift detection
- Use cell-by-cell writes — use append_row, batch updates, and clear+update
- Import streamlit anywhere
- Bypass the first-live-write confirmation gate
```

---

## Prompt 5 of 6: Create smoke tests

```text
Read tests/test_vault_bundle_smoke.py before writing (pattern reference).

Create: tests/test_rebuy_analyst_smoke.py

Contents:

    \"\"\"Smoke tests for agents/rebuy_analyst.py.

    These tests verify structural correctness: schema enforcement, hash
    verification, ticker resolution, and confidence classification.
    They do NOT make real Gemini calls — the LLM call is mocked.
    \"\"\"
    import json
    from pathlib import Path
    from unittest.mock import patch

    import pytest
    from pydantic import ValidationError

    from agents.rebuy_analyst import (
        RebuyAnalysis,
        ScalingStep,
        classify_confidence,
        resolve_thesis,
        analyze_rebuy,
    )


    def test_schema_rejects_price_target_field():
        valid_data = {
            "composite_hash": "a" * 64,
            "ticker": "UNH",
            "thesis_available": True,
            "price_source": "yfinance_live",
            "confidence_tier": "high",
            "confidence_rationale": "All inputs present and verified.",
            "recommendation": "hold",
            "recommendation_rationale": "Position correctly sized; thesis intact; no drift.",
            "style": "garp",
            "style_alignment_notes": "Classic GARP: quality compounder at reasonable price.",
        }
        m = RebuyAnalysis(**valid_data)
        assert m.ticker == "UNH"

        # Adding price_target as extra field — Pydantic v2 ignores unknown
        # fields silently by default. Verify it is NOT on the model.
        m2 = RebuyAnalysis(**{**valid_data, "price_target": 650.00})
        assert not hasattr(m2, "price_target")


    def test_scaling_plan_max_five_steps():
        steps = [
            ScalingStep(
                step_number=min(i, 5),
                trigger_condition=f"trigger condition for step {i}",
                dollar_amount=1000.0 * i,
                rationale=f"rationale for step {i} explaining reasoning",
            )
            for i in range(1, 7)  # 6 steps — too many
        ]
        with pytest.raises(ValidationError):
            RebuyAnalysis(
                composite_hash="a" * 64,
                ticker="UNH",
                thesis_available=True,
                price_source="yfinance_live",
                confidence_tier="high",
                confidence_rationale="All inputs present.",
                recommendation="scale_in",
                recommendation_rationale="Strong setup for scaling in per thesis.",
                scaling_plan=steps,
                rotation_source="cash",
                rotation_rationale="Strategic dry powder deployment.",
                style="garp",
                style_alignment_notes="Classic GARP compounder.",
            )


    def test_classify_confidence_high():
        tier, _ = classify_confidence(
            thesis_available=True,
            price_source="yfinance_live",
            has_price_history=True,
        )
        assert tier == "high"


    def test_classify_confidence_low():
        tier, _ = classify_confidence(
            thesis_available=False,
            price_source="csv_fallback",
            has_price_history=True,
        )
        assert tier == "low"


    def test_classify_confidence_medium_missing_thesis():
        tier, _ = classify_confidence(
            thesis_available=False,
            price_source="yfinance_live",
            has_price_history=True,
        )
        assert tier == "medium"


    def test_resolve_thesis_case_insensitive():
        composite_data = {
            "vault": {
                "documents": [
                    {
                        "path": "theses/UNH_thesis.md",
                        "doc_type": "thesis",
                        "ticker": "UNH",
                        "content_sha256": "b" * 64,
                        "size_bytes": 100,
                        "modified_utc": "2026-04-12T00:00:00Z",
                    }
                ]
            }
        }
        assert resolve_thesis(composite_data, "UNH") is not None
        assert resolve_thesis(composite_data, "unh") is not None
        assert resolve_thesis(composite_data, "Unh") is not None
        assert resolve_thesis(composite_data, "GOOG") is None


    def test_analyze_rebuy_raises_on_missing_ticker(tmp_path):
        fake_composite_data = {
            "composite": {"bundle_hash": "c" * 64},
            "market": {
                "positions": [
                    {"ticker": "UNH", "price": 500, "quantity": 10,
                     "market_value": 5000, "cost_basis": 4500,
                     "weight_pct": 5.0, "price_source": "yfinance_live"}
                ]
            },
            "vault": {"documents": [], "styles_json": {}},
        }
        fake_composite_path = tmp_path / "composite_fake.json"
        fake_composite_path.write_text(json.dumps(fake_composite_data))

        with patch("agents.rebuy_analyst.load_composite",
                   return_value=fake_composite_data):
            with pytest.raises(ValueError, match="not found"):
                analyze_rebuy(
                    ticker="NONEXISTENT",
                    composite_path=fake_composite_path,
                    vault_root=tmp_path,
                )


    def test_analyze_rebuy_overrides_llm_hash(tmp_path):
        \"\"\"Agent must overwrite the LLM's returned hash with the verified one.\"\"\"
        real_hash = "c" * 64
        lying_hash = "d" * 64

        fake_composite_data = {
            "composite": {"bundle_hash": real_hash},
            "market": {
                "positions": [
                    {"ticker": "UNH", "price": 500, "quantity": 10,
                     "market_value": 5000, "cost_basis": 4500,
                     "weight_pct": 5.0, "price_source": "yfinance_live"}
                ]
            },
            "vault": {"documents": [], "styles_json": {}},
        }
        fake_composite_path = tmp_path / "composite_fake.json"
        fake_composite_path.write_text(json.dumps(fake_composite_data))

        fake_response = RebuyAnalysis(
            composite_hash=lying_hash,
            ticker="UNH",
            thesis_available=False,
            price_source="yfinance_live",
            confidence_tier="medium",
            confidence_rationale="Thesis missing but price live.",
            recommendation="hold",
            recommendation_rationale="No change warranted; position appropriately sized.",
            style="garp",
            style_alignment_notes="UNH is a classic GARP compounder in healthcare.",
        )

        with patch("agents.rebuy_analyst.load_composite",
                   return_value=fake_composite_data), \\
             patch("agents.rebuy_analyst.ask_gemini_composite",
                   return_value=fake_response):
            result = analyze_rebuy(
                ticker="UNH",
                composite_path=fake_composite_path,
                vault_root=tmp_path,
            )
        assert result.composite_hash == real_hash

Verify:
    python -m pytest tests/test_rebuy_analyst_smoke.py -v

All seven tests must pass.
```

---

## Prompt 6 of 6: CHANGELOG, CLAUDE.md, and live DRY RUN verification

```text
1. Add a new entry to the TOP of CHANGELOG.md:

   ## [Unreleased] — CLI Migration Phase 3: Re-Buy Analyst on the Spine

   ### Added
   - `agents/rebuy_analyst.py` — First bundle-aware agent. Pydantic
     schema structurally excludes price targets and market predictions.
     Small-step scaling (1-5 steps) is a schema-level constraint.
     Rotation source mandatory on scale_in. Confidence tier reflects
     input quality, not analyst conviction.
   - `agents/__init__.py` — New bundle-aware agent package (distinct
     from legacy `utils/agents/`)
   - `manager.py rebuy --ticker X` subcommand with DRY_RUN default and
     `--live` flag
   - `Agent_Outputs` tab in the Portfolio Sheet — sandbox for all
     future bundle-aware agents
   - Column drift detection: `config.AGENT_OUTPUTS_COLUMNS` is the
     single source of truth; sheet header mismatch raises
     `RuntimeError` instead of falling back to hardcoded indices
   - First-live-write interactive confirmation gate: requires an
     exact confirmation phrase the first time rebuy_analyst writes
     to Agent_Outputs, then no-ops
   - `tests/test_rebuy_analyst_smoke.py` — Seven smoke tests covering
     schema enforcement, confidence classification, ticker resolution,
     hash override, and missing-ticker errors
   - `config.TAB_AGENT_OUTPUTS`, `AGENT_OUTPUTS_COLUMNS`,
     `AGENT_OUTPUTS_COL_MAP`

   ### Architecture Decision
   The Re-Buy Analyst is the first agent to run on the composite
   bundle architecture. Every Phase 1-2 decision gets exercised:
   immutable hashing, content-addressed vault documents, sandboxed
   output, composite_hash stamped into response metadata.

   Hard rules are enforced in three layers: the Pydantic schema
   structurally excludes forbidden fields (price_target, market_view),
   the system prompt repeats the rules in natural language, and the
   agent post-processes the response to overwrite any LLM hash drift
   with the verified file hash (trust the file, not the LLM).

   Confidence tier is explicitly an INPUT QUALITY signal (thesis
   present? price live? history sufficient?), never analyst
   conviction. This prevents the agent from confabulating certainty
   it does not have.

   Column drift detection was added after v1 review. The archive
   logic previously had a hardcoded fallback (agent_col=1, ticker_col=3)
   that would silently archive the wrong rows if columns were ever
   reordered. v2 makes `config.AGENT_OUTPUTS_COLUMNS` authoritative
   and raises on drift.

   First-live-write confirmation gate was added to concentrate
   friction at the moment the audit trail becomes real. Typing a
   long phrase by hand is annoying on purpose — you cannot
   reflexively mash Enter through it.

   ### Unchanged
   - `core/bundle.py`, `core/vault_bundle.py`, `core/composite_bundle.py`
   - `ask_gemini_composite()` in utils/gemini_client.py
   - `AI_Suggested_Allocation` (podcast pipeline's tab — unrelated)
   - `Target_Allocation` (manual-only, forever)
   - Streamlit app — still runs in parallel

   **Status:** `manager.py rebuy` defaults to DRY RUN. The `--live`
   flag is required for Agent_Outputs writes AND the first such
   write requires typed confirmation. Safe to use against any
   composite bundle produced by Phase 2.

2. Update CLAUDE.md — CLI Migration Status section:

   - Phase 1: COMPLETE
   - Phase 1b: COMPLETE
   - Phase 2: COMPLETE — vault, composite, 51 thesis files backfilled
   - Phase 3: COMPLETE — Re-Buy Analyst single-ticker path
   - Phase 3b: NEXT — batch mode (`manager.py rebuy --all`)

   Also add to the Repo Structure tree:
       agents/
       ├── __init__.py
       └── rebuy_analyst.py          # Phase 3 — first bundle-aware agent

3. Run the smoke tests and the DRY RUN integration check:

   # Smoke tests must pass
   python -m pytest tests/test_rebuy_analyst_smoke.py -v

   # Live integration — DRY RUN against a real ticker with a thesis
   python manager.py rebuy --ticker UNH --composite latest

   # DO NOT run --live yet. See the --live Approval Gate section.
```

---

## The --live Approval Gate

The `--live` flag is NOT part of the build-and-verify loop. It is a
separate, deliberate act that happens after the build is complete and
the system prompt has been calibrated against real dry run output.

**Do not pass `--live` until ALL of the following are true:**

1. **At least 3 different tickers have been dry-run tested.** One
   core position (UNH), one speculative (CRWV or similar), one boring
   (JPIE or similar). The four-style classification must look correct
   for all three.

2. **The recommendation rationale for each tested ticker reads like
   Bill's own reasoning.** Not generic AI-speak. Not hedged
   non-commitment. Grounded in the specific thesis and the specific
   market state.

3. **Confidence tiers match expectations.** UNH with a good thesis
   and live price should come back `high`. A ticker with a missing
   thesis should come back `medium` or `low`. If the tiers don't
   match reality, the classify_confidence logic needs fixing before
   any write happens.

4. **Scaling plan sizes feel right.** On a 5% position, scaling steps
   should be small-dollar relative to the position size. If the agent
   recommends $5,000 scaling steps on a $10,000 position, that's not
   small-step scaling, that's doubling down, and the system prompt
   needs more constraint.

5. **The rotation source is named and plausible.** If every
   recommendation says `rotation_source: "cash"`, the agent isn't
   reasoning about rotations, it's just spending dry powder. The
   system prompt needs to push harder on rotation thinking.

6. **Bill explicitly reviews at least one full output and says "yes,
   this is what I would have reasoned."** Not "close enough." Not
   "mostly right." The actual thing.

Only then: pass `--live` for a single ticker (start with UNH), clear
the first-live-write confirmation gate, verify the row landed in
Agent_Outputs correctly, inspect the Full_Response_JSON field, and
confirm the Logs tab captured no unexpected archive activity.

If any of the six criteria above are not met, the correct action is
to iterate on `REBUY_SYSTEM_PROMPT` in `agents/rebuy_analyst.py` and
re-run dry runs. **This is not a failure — it is the process.**

---

## Post-Build Verification

```bash
# 1. Imports clean
python -c "from agents.rebuy_analyst import analyze_rebuy, RebuyAnalysis; print('OK')"

# 2. Subcommand exists
python manager.py rebuy --help

# 3. Smoke tests pass
python -m pytest tests/test_rebuy_analyst_smoke.py -v

# 4. Config column order is authoritative
python -c "
import config
assert config.AGENT_OUTPUTS_COLUMNS.index('Agent') == 1
assert config.AGENT_OUTPUTS_COLUMNS.index('Ticker') == 3
print('Column indices verified')
"

# 5. Sheet header matches config
python -c "
import config
from utils.sheet_readers import get_gspread_client
client = get_gspread_client()
ws = client.open_by_key(config.PORTFOLIO_SHEET_ID).worksheet(
    config.TAB_AGENT_OUTPUTS
)
header = ws.row_values(1)
assert header == config.AGENT_OUTPUTS_COLUMNS, (
    f'Header drift!\n  Sheet:  {header}\n  Config: {config.AGENT_OUTPUTS_COLUMNS}'
)
print(f'Agent_Outputs header matches config: {len(header)} columns')
"

# 6. Sandbox guarantee — agents/ has no forbidden tab references
grep -rn "Target_Allocation\|TARGET_ALLOCATION\|Holdings_Current\|AI_Suggested_Allocation" agents/ && \
    echo "FAIL: agents/ references forbidden tabs" || \
    echo "Clean: no forbidden tab references in agents/"

# 7. No Streamlit imports
grep -rn "import streamlit\|from streamlit" agents/ && \
    echo "FAIL: streamlit found in agents/" || \
    echo "Clean: no streamlit in agents/"

# 8. DRY RUN calibration — UNH (core position, thesis known cold)
python manager.py rebuy --ticker UNH --composite latest

# 9. DRY RUN calibration — a speculative ticker
python manager.py rebuy --ticker CRWV --composite latest

# 10. DRY RUN calibration — a boring income ticker
python manager.py rebuy --ticker JPIE --composite latest

# DO NOT run --live until the six --live Approval Gate criteria above
# are ALL met. The system prompt will almost certainly need 2-4
# iterations before the outputs feel right. That is the normal
# calibration loop, not a failure.
```

Checks 1-7 must pass to consider the build complete. Checks 8-10 are
calibration runs, not pass/fail — they produce output that you review
by hand against the Approval Gate criteria.

---

## Gemini CLI Peer Review

```bash
gemini -p "Review the Phase 3 v2 Re-Buy Analyst implementation:
agents/rebuy_analyst.py, the rebuy subcommand in manager.py, and
tests/test_rebuy_analyst_smoke.py. Check specifically:

1) Is the RebuyAnalysis schema STRUCTURALLY unable to include
   price_target, target_price, market_view, or any future-price
   prediction field?

2) Does analyze_rebuy() call load_composite() which triggers hash
   verification on BOTH child bundles AND the composite wrapper
   BEFORE calling the LLM?

3) Does analyze_rebuy() overwrite the LLM's returned composite_hash
   with the verified one from the file, rather than trusting the LLM?

4) Is the confidence_tier computed by a pure Python function
   (classify_confidence) rather than being generated by the LLM?

5) Does the scaling_plan field have a maximum length of 5 enforced
   by a validator, not just documented in the description?

6) Does the rebuy subcommand default to DRY RUN and require an
   explicit --live flag to write to Agent_Outputs?

7) Does _write_agent_output_to_sheet() archive existing rows for the
   same (agent, ticker) pair to the Logs tab before writing the new
   row?

8) Does _write_agent_output_to_sheet() derive agent_col and ticker_col
   from config.AGENT_OUTPUTS_COLUMNS (the single source of truth)
   rather than hardcoding them as 1 and 3?

9) Does _write_agent_output_to_sheet() RAISE RuntimeError when the
   live sheet header disagrees with config, rather than silently
   falling back to hardcoded indices?

10) Does _write_agent_output_to_sheet() include a first-live-write
    confirmation gate that requires typing the exact phrase 'I have
    reviewed the dry run' before the first rebuy_analyst row is
    written? And does that gate no-op on subsequent writes?

11) Does the agents/ directory contain ZERO references to
    Target_Allocation, Holdings_Current, AI_Suggested_Allocation, or
    any tab other than Agent_Outputs and Logs?

12) Is the system prompt free of any language that could be
    interpreted as requesting price predictions or market timing calls?

13) Are there ZERO streamlit imports anywhere in agents/ or in the
    new code added to manager.py?

14) Does the dry-run output use a prominent Panel footer rather than
    a one-line 'Use --live' message?"
```

---

## Commit After Green

Once all seven structural checks pass, at least three calibration runs
have been reviewed, AND the six --live Approval Gate criteria are met:

```bash
git add agents/ manager.py config.py create_portfolio_sheet.py \
        PORTFOLIO_SHEET_SCHEMA.md tests/test_rebuy_analyst_smoke.py \
        CHANGELOG.md CLAUDE.md
git commit -m "Phase 3: Re-Buy Analyst on the composite bundle spine

- agents/rebuy_analyst.py: first bundle-aware agent
- Pydantic schema structurally excludes price targets
- Small-step scaling (1-5 steps) enforced by validator
- Confidence tier reflects input quality, not analyst conviction
- Hash override: verified file hash always wins over LLM claim
- Agent_Outputs tab created as sandbox for future agents
- manager.py rebuy subcommand with DRY_RUN default
- Column drift detection: config.AGENT_OUTPUTS_COLUMNS is the
  single source of truth; sheet header mismatch raises instead
  of falling back, preventing silent row-matching bugs
- First-live-write interactive confirmation gate for rebuy_analyst
  (one-time friction at the exact moment the audit trail becomes real)
- Seven smoke tests, all passing
- Calibrated against UNH, CRWV, JPIE dry runs
- Live --live write verified against Agent_Outputs tab

Every Phase 1-2 architectural decision gets exercised here:
immutable hashing, content-addressed vault docs, sandboxed output,
composite_hash in response metadata. The spine works end-to-end.

Unblocks Phase 3b (batch mode) and Phase 4 (Schwab API source swap)."
```

Then the next planning session can begin drafting
`cli_migration_03b_rebuy_batch.md` against the known-good Phase 3 state.

---

## What Phase 3 explicitly does NOT do

- No batch mode. Phase 3b handles that.
- No other agents. Add-Candidate, New Idea Screener, and List Coherence
  are all Phase 5.
- No retrieval beyond the composite bundle.
- No agent-to-agent calls.
- No Schwab API integration. That's Phase 4.
- No visual layer for reviewing Agent_Outputs beyond the raw Sheet tab.
- No modifications to core/bundle.py, core/vault_bundle.py, or
  core/composite_bundle.py.
- No changes to the Streamlit app.

---

## Expected iteration loop

The system prompt in Prompt 3 will likely need 2-4 revisions before
Re-Buy Analyst outputs feel right. The loop looks like:

1. Run `manager.py rebuy --ticker <real ticker> --composite latest`
2. Read the output carefully. Does it match how Bill would actually
   think about scaling in?
3. If no: identify the specific failure mode. Common ones:
   - Recommendation ignores the thesis
   - Scaling plan steps are too large
   - Confidence tier disagrees with obvious input quality
   - Style classification is wrong
   - Rationale is generic AI-speak rather than grounded in the thesis
4. Edit the system prompt to address that specific failure
5. Re-run and compare

Plan for this loop. Phase 3 is only done when Bill can point at an
output and say "yes, that is how I would have reasoned about it."
That is the real success criterion, and it cannot be unit-tested — it
requires human judgment on real outputs from real tickers.

Start with UNH (largest position, thesis known cold) as the calibration
ticker. Once the prompt produces good output for UNH, test it against
something speculative like CRWV and something boring like JPIE to make
sure the style classification and scaling guidance travel across the
four styles.
