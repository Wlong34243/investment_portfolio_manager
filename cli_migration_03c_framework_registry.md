# CLI Migration Phase 3c — Framework Registry + Lynch GARP
# Target: Claude Code or Gemini CLI 3 Pro
# Prerequisite: Phase 3 complete. agents/rebuy_analyst.py landed green,
# calibrated against UNH/CRWV/JPIE dry runs, and at least one --live
# row sits in Agent_Outputs with the first-live-write gate cleared.

## Overview

Phase 3 gave Re-Buy Analyst a single, thesis-driven reasoning path.
Phase 3c adds a **framework registry** layer: versioned, reviewed JSON
files in the vault that encode specific investment frameworks (Lynch
GARP, Graham Deep Value, O'Neil CANSLIM, etc.). The agent selects the
right framework for a ticker at analysis time, evaluates the ticker
against the framework's rules, and reports a structured
`framework_validation` block in its output.

Phase 3c lands the registry plus ONE framework — **Peter Lynch GARP**
— against ONE ticker — **UNH** — as the minimum viable proof. Scaling
to more frameworks and more tickers is a future phase.

## Why this is a separate phase, not a Phase 3 extension

Phase 3 proved the single-ticker thesis-driven path. Phase 3c adds a
new reasoning layer on top of that. Landing them together would mean
debugging two things at once: "is the thesis-driven path working" AND
"is the framework registry working." Landing them sequentially means
every issue has exactly one cause. Same discipline as 1 → 1b and
3 → 3b.

## The core insight

Frameworks are **data**, not **prompt text**. Every framework lives as
a reviewed JSON file under `vault/frameworks/`. The agent:

1. Loads the composite bundle (which now includes all reviewed frameworks)
2. Selects the applicable framework for the ticker based on style,
   asset class, and optional thesis frontmatter
3. Evaluates the ticker's fundamentals against the framework's rules
4. Reports `framework_validation` alongside the recommendation

The system prompt gets ONE new paragraph. The Pydantic schema gets new
OPTIONAL fields. The existing Phase 3 hard rules are untouched:
no price targets, no market predictions, small-step scaling,
sandbox-only output.

## Key Design Decisions

1. **Frameworks are JSON, not prompt text.** Every framework is a file
   under `vault/frameworks/<framework_id>_v<N>.json`. Content-hashed
   by the vault bundler, same audit chain as thesis files.

2. **Frameworks must be reviewed before use.** Every framework JSON
   has a `reviewed_by_bill: bool` field. Unreviewed frameworks are
   loaded into the vault bundle but ignored by the selector. This
   closes the "NotebookLM hallucinates a rule and it becomes
   machine-enforced truth" failure mode.

3. **Framework selection is deterministic, not LLM-driven.** A Python
   function `select_framework(ticker, position, thesis, frameworks)`
   picks the right framework based on explicit rules:
   - Thesis frontmatter `framework_preference` wins if present
   - Otherwise match on asset class + style from thesis frontmatter
   - Otherwise match on asset class alone
   - If nothing applies, return `None` (no framework, agent falls back
     to Phase 3 pure-thesis reasoning)

4. **Rule evaluation is deterministic where possible.** A Python
   function `evaluate_framework_rules(position, fundamentals, framework)`
   checks each rule against structured data (P/E, PEG, debt/equity,
   earnings growth rate, etc.) and returns a structured
   `FrameworkValidation` object BEFORE the LLM is called. The LLM
   receives the pre-computed rule results and explains them — it
   does not perform the arithmetic.

5. **Missing fundamentals data is handled explicitly.** If the
   framework requires `trailing_pe` and the position data doesn't
   have it, the rule is marked `passed=None` (insufficient data) and
   listed in `insufficient_data_rules`. This is not a failure — it's
   a known unknown that downgrades confidence.

6. **Framework validation is INFORMATIONAL in v1, not blocking.**
   The framework score is reported alongside the recommendation. The
   LLM may still produce a `scale_in` recommendation on a ticker that
   scored 2/5 on GARP, but the rationale must explain why. This is
   the right default for v1 because it lets you see whether the
   agent respects framework signals without forcing it to. If the
   agent systematically ignores framework failures, tighten to
   blocking in v2.

7. **Thesis frontmatter is YAML, backward-compatible.** A `_thesis.md`
   file with no frontmatter still works. Frontmatter adds explicit
   style declaration and framework preference. A script loops through
   existing theses and adds minimal frontmatter in one pass.

8. **One framework, one ticker for MVP.** Phase 3c ships Lynch GARP
   evaluated against UNH. No other frameworks, no other tickers. Once
   UNH/Lynch produces good output, the same agent can be run against
   other tickers (it'll auto-select `None` for non-matching ones) and
   other frameworks can be added as JSON files. That scaling is
   Phase 3d, not 3c.

9. **Fundamentals data source for v1 is FMP.** The existing
   `fmp_client.py` already pulls trailing P/E, PEG, debt/equity,
   5yr earnings growth. Reuse it; do not add a new data source. FMP
   subscription limits are handled by marking rules as
   insufficient_data when a field comes back None.

---

## Pre-flight Checklist

Before running these prompts, confirm:
- [ ] Phase 3 is committed and green. `manager.py rebuy --ticker UNH`
      produces valid dry run output.
- [ ] At least one successful --live row exists in `Agent_Outputs`
      (first-live-write gate has been cleared).
- [ ] `utils/fmp_client.py` exists and can fetch fundamentals
      (trailing P/E, PEG, debt/equity, earnings growth rate) for UNH.
      Test with: `python -c "from utils.fmp_client import get_fundamentals; print(get_fundamentals('UNH'))"`
- [ ] `vault/theses/UNH_thesis.md` exists and contains meaningful
      thesis text.
- [ ] `core/vault_bundle.py` imports cleanly.

---

## Prompt 1 of 7: Create the Lynch GARP framework JSON

```text
Create: vault/frameworks/lynch_garp_v1.json

The framework must follow this exact structure. Do not deviate — the
loader in Prompt 3 depends on these field names.

{
  "framework_id": "lynch_garp_v1",
  "framework_version": "1.0.0",
  "name": "Peter Lynch GARP (Growth at a Reasonable Price)",
  "source": "One Up On Wall Street (Peter Lynch, 1989) + extracted rules from Bill's NotebookLM analysis",
  "extracted_by": "Claude Opus via NotebookLM Lynch framework",
  "extraction_date": "2026-04-12",
  "reviewed_by_bill": false,
  "applies_to_styles": ["garp", "boring"],
  "applies_to_asset_classes": ["Equities", "Equity"],
  "excludes_conditions": [
    "no_earnings",
    "new_ipo_under_3_years",
    "asset_class_is_etf"
  ],
  "philosophy": "Don't overpay for growth. A P/E ratio is only meaningful relative to the company's growth rate. The sweet spot is sustainable 15-25% growth at a PEG below 1.0, funded by a strong balance sheet.",
  "rules": [
    {
      "rule_id": "peg_in_buy_zone",
      "description": "PEG ratio is in the buy zone",
      "required_fields": ["peg_ratio"],
      "severity": "required",
      "check_type": "range",
      "target_min": 0.5,
      "target_max": 1.0,
      "interpretation": {
        "pass": "PEG between 0.5 and 1.0 — undervalued relative to growth",
        "fail_high": "PEG above 1.0 — paying too much for growth",
        "fail_low": "PEG below 0.5 — check for earnings cliff or one-time boost"
      }
    },
    {
      "rule_id": "peg_not_overvalued",
      "description": "PEG ratio is not in the avoid zone",
      "required_fields": ["peg_ratio"],
      "severity": "required",
      "check_type": "threshold_max",
      "target_max": 2.0,
      "interpretation": {
        "pass": "PEG below 2.0 — not in Lynch's avoid zone",
        "fail": "PEG above 2.0 — overvalued in Lynch framework, high risk of multiple compression"
      }
    },
    {
      "rule_id": "earnings_growth_sweet_spot",
      "description": "Earnings growth is in the 15-25% sustainable sweet spot",
      "required_fields": ["earnings_growth_rate_3yr"],
      "severity": "required",
      "check_type": "range",
      "target_min": 0.15,
      "target_max": 0.25,
      "interpretation": {
        "pass": "Growth in Lynch's sustainable sweet spot",
        "fail_low": "Growth under 15% — stalwart territory, limited upside",
        "fail_high": "Growth above 25% — high deceleration risk, attracts competition"
      }
    },
    {
      "rule_id": "pe_not_priced_for_perfection",
      "description": "P/E ratio is below 20 (not priced for perfection)",
      "required_fields": ["trailing_pe"],
      "severity": "preferred",
      "check_type": "threshold_max",
      "target_max": 20.0,
      "interpretation": {
        "pass": "P/E below 20 — reasonable absolute valuation",
        "fail": "P/E above 20 — may still qualify if PEG is favorable, but elevated risk"
      }
    },
    {
      "rule_id": "debt_to_equity_conservative",
      "description": "Debt-to-equity ratio is below 0.30 (strong balance sheet)",
      "required_fields": ["debt_to_equity"],
      "severity": "preferred",
      "check_type": "threshold_max",
      "target_max": 0.30,
      "interpretation": {
        "pass": "Balance sheet meets Lynch's conservative threshold",
        "fail": "Debt load may amplify downside in a downturn"
      }
    }
  ],
  "passing_threshold": {
    "required_rules_passed_minimum": 2,
    "preferred_rules_passed_minimum": 1,
    "total_rules": 5
  },
  "notes": "v1 is deliberately strict on PEG (two separate rules) because PEG is the mathematical anchor of the framework. The inventory/receivables check from Lynch's book is not included in v1 because it requires line-item balance sheet access that FMP's free tier doesn't expose. Add in v2 if the data source is upgraded."
}

After writing the file, run:
   python -c "
   import json
   with open('vault/frameworks/lynch_garp_v1.json') as f:
       data = json.load(f)
   assert data['framework_id'] == 'lynch_garp_v1'
   assert len(data['rules']) == 5
   required = [r for r in data['rules'] if r['severity'] == 'required']
   preferred = [r for r in data['rules'] if r['severity'] == 'preferred']
   assert len(required) == 3
   assert len(preferred) == 2
   print('Lynch GARP framework JSON is valid')
   "

IMPORTANT: reviewed_by_bill is set to false. Bill must manually flip
this to true in the file after reviewing it. The selector in Prompt 4
will ignore any framework where reviewed_by_bill is false, so the
Phase 3c verification loop will produce 'no framework applies'
output until Bill reviews.

Do NOT:
- Add price targets to any rule
- Add more than 5 rules in v1 (start minimal)
- Set reviewed_by_bill to true automatically
```

---

## Prompt 2 of 7: Extend core/vault_bundle.py to load frameworks

```text
Read core/vault_bundle.py before making changes. The pattern to mirror
is how styles.json is already special-cased.

Modify core/vault_bundle.py:

=== EDIT 1: Add a frameworks field to the VaultBundle dataclass ===

Find the @dataclass VaultBundle definition and add a new field AFTER
styles_json and BEFORE excluded:

    frameworks: list[dict]       # parsed framework JSON files from
                                 # frameworks/ subdirectory

=== EDIT 2: Add a framework loader helper ===

Add a new function immediately after _load_styles_json():

    def _load_frameworks(vault_root: Path) -> list[dict]:
        \"\"\"
        Load all framework JSON files from vault/frameworks/.

        Returns a list of dicts. Each dict is the parsed JSON plus two
        audit fields added by the loader:
          - _framework_file_path: relative path for provenance
          - _framework_content_sha256: SHA256 of file contents for
            tamper detection

        Malformed framework JSON raises ValueError — frameworks are too
        important to fail silently.
        \"\"\"
        frameworks_dir = vault_root / "frameworks"
        if not frameworks_dir.exists():
            return []

        frameworks = []
        for path in sorted(frameworks_dir.glob("*.json")):
            try:
                with open(path, "rb") as f:
                    content_bytes = f.read()
                data = json.loads(content_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(
                    f"Framework file {path.name} is malformed: {e}. "
                    "Frameworks must be valid JSON."
                )

            # Minimal schema validation — the framework must have an id
            # and a version. Everything else is framework-specific.
            if "framework_id" not in data:
                raise ValueError(
                    f"Framework file {path.name} is missing required "
                    f"field 'framework_id'."
                )
            if "framework_version" not in data:
                raise ValueError(
                    f"Framework file {path.name} is missing required "
                    f"field 'framework_version'."
                )

            data["_framework_file_path"] = str(path.relative_to(vault_root))
            data["_framework_content_sha256"] = hashlib.sha256(
                content_bytes
            ).hexdigest()
            frameworks.append(data)

        return frameworks

=== EDIT 3: Call the loader in build_vault_bundle ===

Find the line in build_vault_bundle() that calls _load_styles_json and
add a frameworks load immediately after:

    styles_json = _load_styles_json(vault_root)
    frameworks = _load_frameworks(vault_root)  # NEW

Then find the payload dict construction and add frameworks:

    payload = {
        "schema_version": VAULT_SCHEMA_VERSION,
        "timestamp_utc": timestamp_utc,
        "vault_root": str(vault_root),
        "documents": documents,
        "document_count": len(documents),
        "styles_json": styles_json,
        "frameworks": frameworks,   # NEW
        "excluded": excluded,
        "environment": _capture_environment(),
    }

=== EDIT 4: Update _should_skip so frameworks dir is NOT excluded ===

The current EXCLUDED_DIRS set should NOT include "frameworks". Verify
it doesn't, and if frameworks/ is anywhere in the exclusion logic,
remove it. The markdown walk should skip over framework JSON files
naturally because they aren't .md files (the existing not_markdown
rule handles this), but the directory itself must be walkable.

=== EDIT 5: Update __all__ and module docstring ===

No changes to __all__ — frameworks are accessed via the bundle dict,
not as a separate export. Update the module docstring to mention:

    "V2+ scope also includes styles.json and framework JSON files
    under frameworks/ subdirectory. Frameworks carry their own
    content hashes for tamper detection."

=== VERIFICATION ===

   python -c "
   from pathlib import Path
   from core.vault_bundle import build_vault_bundle
   b = build_vault_bundle(Path('vault'))
   assert hasattr(b, 'frameworks'), 'VaultBundle must have frameworks field'
   assert isinstance(b.frameworks, list)
   lynch = next((f for f in b.frameworks if f['framework_id'] == 'lynch_garp_v1'), None)
   assert lynch is not None, 'Lynch GARP framework not loaded'
   assert lynch['_framework_content_sha256'], 'Content hash missing'
   print(f'Loaded {len(b.frameworks)} framework(s). Lynch GARP hash: {lynch[\"_framework_content_sha256\"][:16]}...')
   "

   # Rebuild vault bundle and compose a fresh composite
   python manager.py vault-snapshot --root vault
   python manager.py compose --market latest --vault latest

Do NOT:
- Inline framework content into the markdown document list
- Skip the content hash
- Silently swallow malformed JSON — raise loudly
- Add "frameworks" to EXCLUDED_DIRS
```

---

## Prompt 3 of 7: Create agents/framework_selector.py

```text
Read agents/rebuy_analyst.py before writing this module — the types
and patterns must be consistent.

Create: agents/framework_selector.py

Module docstring:
    \"\"\"
    Framework Selector — deterministic selection of the appropriate
    investment framework for a ticker.

    Selection is pure Python, no LLM. The LLM only gets the PRE-COMPUTED
    rule results, never the raw rule list. This keeps framework
    application auditable: given the same inputs, the same framework
    is always selected, and the rule evaluation always produces the
    same result.
    \"\"\"

Imports:
    from __future__ import annotations

    import logging
    import re
    from dataclasses import dataclass
    from pathlib import Path
    from typing import Literal

    import yaml  # requires PyYAML — add to requirements.txt if not present

    logger = logging.getLogger(__name__)

Dataclasses:

    @dataclass
    class ThesisFrontmatter:
        ticker: str | None = None
        style: str | None = None                  # garp | thematic | boring | etf
        framework_preference: str | None = None   # framework_id
        entry_date: str | None = None
        last_reviewed: str | None = None


Functions:

1. parse_thesis_frontmatter(thesis_text: str) -> ThesisFrontmatter
   Parse YAML frontmatter from the top of a thesis markdown file.
   Frontmatter is delimited by --- markers. If no frontmatter is
   present, return an empty ThesisFrontmatter (all None fields).
   Malformed YAML logs a warning and returns an empty frontmatter —
   this is backward-compatible with unfrontmattered thesis files.

   Implementation:
     lines = thesis_text.splitlines()
     if not lines or lines[0].strip() != "---":
         return ThesisFrontmatter()
     try:
         end_idx = lines[1:].index("---") + 1
     except ValueError:
         return ThesisFrontmatter()
     yaml_text = "\\n".join(lines[1:end_idx])
     try:
         data = yaml.safe_load(yaml_text) or {}
     except yaml.YAMLError as e:
         logger.warning("Malformed thesis frontmatter: %s", e)
         return ThesisFrontmatter()
     return ThesisFrontmatter(
         ticker=data.get("ticker"),
         style=data.get("style"),
         framework_preference=data.get("framework_preference"),
         entry_date=data.get("entry_date"),
         last_reviewed=data.get("last_reviewed"),
     )


2. select_framework(
       ticker: str,
       position: dict,
       thesis_frontmatter: ThesisFrontmatter,
       frameworks: list[dict],
   ) -> dict | None

   Returns the applicable framework dict, or None if no framework
   applies. Selection order:

   a. Only consider frameworks where reviewed_by_bill is True.
      Log an INFO line for each skipped unreviewed framework.

   b. If thesis_frontmatter.framework_preference is set, look for a
      framework with matching framework_id. If found and applicable,
      return it. If found but not applicable (style mismatch, asset
      class exclusion), log a warning and fall through.

   c. Otherwise, filter frameworks by:
      - Asset class match (position.asset_class in
        framework.applies_to_asset_classes)
      - Style match (thesis_frontmatter.style in
        framework.applies_to_styles) IF thesis_frontmatter.style is set
      - No exclusion conditions triggered
        (see _check_exclusions below)

   d. If exactly one framework matches, return it. If multiple match,
      prefer the one with the highest framework_version (string sort
      for now — semantic versioning later). Log which was selected
      and which were rejected.

   e. If zero match, return None.


3. _check_exclusions(position: dict, framework: dict) -> str | None

   Return a reason string if the position triggers any of the
   framework's exclusion conditions, else None.

   Supported conditions (v1):
     - "no_earnings": check if position has missing/zero
       trailing earnings (requires eps_ttm field on the position)
     - "new_ipo_under_3_years": check entry_date or a future
       inception_date field — for v1, treat as always-not-excluded
       unless we have the data
     - "asset_class_is_etf": check if position.asset_class.lower() in
       ("etf", "fund", "index fund")

   If an exclusion references a field the position doesn't carry,
   log a DEBUG line and return None (don't exclude on missing data).


4. evaluate_framework_rules(
       position: dict,
       fundamentals: dict,
       framework: dict,
   ) -> dict

   Evaluate each rule in the framework against the position's
   fundamentals. Returns a dict matching the FrameworkValidation
   Pydantic schema (see Prompt 4):

   {
     "framework_id": str,
     "framework_version": str,
     "framework_content_sha256": str,
     "applicable": True,
     "applicability_rationale": str,
     "rules_evaluated": [
       {
         "rule_id": str,
         "description": str,
         "passed": bool | None,
         "observed_value": str | None,
         "severity": "required" | "preferred",
         "rationale": str,
       },
       ...
     ],
     "required_rules_passed": int,
     "required_rules_total": int,
     "preferred_rules_passed": int,
     "preferred_rules_total": int,
     "passes_framework": bool,
     "insufficient_data_rules": list[str],
   }

   For each rule:
     - Check each required_field is present in fundamentals and not None.
       If any are missing, passed=None, add rule_id to
       insufficient_data_rules, rationale="Missing field X".
     - For check_type "range": pass if target_min <= value <= target_max
     - For check_type "threshold_max": pass if value <= target_max
     - For check_type "threshold_min": pass if value >= target_min
     - For check_type "equal": pass if value == target_value

   Observed_value is the raw value formatted as a string (e.g. "0.87"
   for a PEG ratio).

   passes_framework is True if:
     - required_rules_passed >= passing_threshold.required_rules_passed_minimum
     - AND preferred_rules_passed >= passing_threshold.preferred_rules_passed_minimum

   Missing data rules do NOT count as passes or fails — they are
   neutral. But if too many required rules are neutral, passes_framework
   is False because required_rules_passed won't hit the minimum.


5. Add PyYAML to requirements.txt if not already present:
   pyyaml>=6.0


=== VERIFICATION ===

   python -c "
   from agents.framework_selector import parse_thesis_frontmatter

   sample = '''---
   ticker: UNH
   style: garp
   framework_preference: lynch_garp_v1
   ---

   # UNH Thesis
   Body text here.
   '''
   fm = parse_thesis_frontmatter(sample)
   assert fm.ticker == 'UNH'
   assert fm.style == 'garp'
   assert fm.framework_preference == 'lynch_garp_v1'

   empty = parse_thesis_frontmatter('# UNH Thesis\\n\\nNo frontmatter.')
   assert empty.ticker is None
   print('Frontmatter parser OK')
   "

Do NOT:
- Let the LLM perform rule evaluation
- Skip the missing-data handling — it is the most common case in
  practice and must be explicit
- Hardcode framework IDs in the selector
- Cross-import from rebuy_analyst (framework_selector must be
  reusable by Add-Candidate, New Idea Screener, and List Coherence
  in Phase 5)
```

---

## Prompt 4 of 7: Extend the Pydantic schema in agents/rebuy_analyst.py

```text
Read agents/rebuy_analyst.py before making changes. The existing
RebuyAnalysis schema must be extended, NOT replaced.

Add these new Pydantic models BEFORE the existing RebuyAnalysis class:

    class FrameworkRuleResult(BaseModel):
        \"\"\"Result of evaluating a single framework rule.\"\"\"
        rule_id: str
        description: str
        passed: bool | None = Field(
            default=None,
            description="True if rule passed, False if failed, "
                        "None if insufficient data"
        )
        observed_value: str | None = Field(
            default=None,
            description="The actual value observed, as a string"
        )
        severity: Literal["required", "preferred"]
        rationale: str = Field(..., min_length=10)


    class FrameworkValidation(BaseModel):
        \"\"\"
        Framework validation block. Reported alongside the recommendation
        when a framework applies. None when no framework matches.
        \"\"\"
        framework_id: str
        framework_version: str
        framework_content_sha256: str = Field(
            ...,
            min_length=64,
            max_length=64,
            description="SHA256 of the framework JSON file — part of "
                        "the audit chain"
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
            description="Human-readable score like '3/5 required + 1/2 preferred'"
        )

Then modify the existing RebuyAnalysis class:

    class RebuyAnalysis(BaseModel):
        # ... all existing fields preserved unchanged ...

        # NEW: framework validation (optional — None when no framework applies)
        framework_validation: FrameworkValidation | None = Field(
            default=None,
            description="Structured framework evaluation, or None if no "
                        "reviewed framework matched this ticker"
        )

        # NEW: agent must explain how framework score influenced the recommendation
        framework_influence_notes: str = Field(
            default="",
            description="How the framework score shaped the recommendation. "
                        "Empty string if framework_validation is None."
        )

Do NOT:
- Remove or modify any existing field in RebuyAnalysis
- Add price targets via the framework (the schema structurally cannot
  hold them — verify this)
- Make framework_validation required (it must be optional for tickers
  where no framework applies)
```

---

## Prompt 5 of 7: Update analyze_rebuy to use the framework pipeline

```text
Read agents/rebuy_analyst.py (post-Prompt 4 edits) before modifying.

Modify the analyze_rebuy function to add framework evaluation BEFORE
the LLM call, then pass the pre-computed validation into the prompt.

=== EDIT 1: Import the new helpers ===

At the top of the file:

    from agents.framework_selector import (
        parse_thesis_frontmatter,
        select_framework,
        evaluate_framework_rules,
    )
    from utils.fmp_client import get_fundamentals  # or whatever the
                                                    # existing entry point is

=== EDIT 2: Add framework pipeline steps in analyze_rebuy ===

Find this block in analyze_rebuy:

    # Classify input quality
    price_source = position.get("price_source", "csv_fallback")
    has_price_history = position.get("market_value", 0) > 0
    confidence_tier, confidence_rationale = classify_confidence(...)

Insert BEFORE it:

    # --- Framework pipeline (Phase 3c) ---
    frameworks = vault.get("frameworks", [])
    thesis_frontmatter = parse_thesis_frontmatter(thesis_text) if thesis_text else \\
                         parse_thesis_frontmatter("")

    selected_framework = select_framework(
        ticker=ticker,
        position=position,
        thesis_frontmatter=thesis_frontmatter,
        frameworks=frameworks,
    )

    framework_validation_dict = None
    if selected_framework is not None:
        # Fetch fundamentals — only when a framework applies
        try:
            fundamentals = get_fundamentals(ticker) or {}
        except Exception as e:
            logger.warning(
                "Failed to fetch fundamentals for %s: %s", ticker, e
            )
            fundamentals = {}

        framework_validation_dict = evaluate_framework_rules(
            position=position,
            fundamentals=fundamentals,
            framework=selected_framework,
        )

        # Log the score to console for visibility during dry runs
        logger.info(
            "Framework %s evaluated: %s",
            selected_framework["framework_id"],
            framework_validation_dict.get("framework_score_display"),
        )
    else:
        logger.info(
            "No framework applies to %s — falling back to thesis-only reasoning",
            ticker,
        )

=== EDIT 3: Pass the framework into the user prompt ===

Find _build_user_prompt and add a new parameter and block.

Update the signature:

    def _build_user_prompt(
        ticker: str,
        position: dict,
        thesis_text: str,
        thesis_available: bool,
        confidence_tier: str,
        confidence_rationale: str,
        styles_json: dict,
        framework_validation: dict | None,   # NEW
    ) -> str:

Add this block to the prompt, placed AFTER input_quality_block and
BEFORE task_block:

    framework_block = ""
    if framework_validation is not None:
        framework_block = (
            f"## Framework Evaluation (PRE-COMPUTED — use as-is, do not re-derive)\\n\\n"
            f"Framework: {framework_validation['framework_id']} "
            f"v{framework_validation['framework_version']}\\n"
            f"Score: {framework_validation['framework_score_display']}\\n"
            f"Passes framework: {framework_validation['passes_framework']}\\n\\n"
            f"### Rule Results\\n\\n"
        )
        for rule in framework_validation['rules_evaluated']:
            status = "✓" if rule['passed'] is True else (
                "✗" if rule['passed'] is False else "?"
            )
            framework_block += (
                f"{status} [{rule['severity']}] {rule['description']}: "
                f"{rule['rationale']}\\n"
            )
        if framework_validation.get('insufficient_data_rules'):
            framework_block += (
                f"\\nRules with insufficient data: "
                f"{framework_validation['insufficient_data_rules']}\\n"
            )
        framework_block += (
            f"\\nYou MUST include a framework_validation block in your "
            f"response that mirrors these results, and you MUST fill in "
            f"framework_influence_notes explaining how this score shaped "
            f"your recommendation. The framework score is INFORMATIONAL — "
            f"you may still recommend scale_in on a partial pass, but "
            f"you must explain why.\\n"
        )
    else:
        framework_block = (
            "## Framework Evaluation\\n\\n"
            "No reviewed framework matches this ticker's asset class and "
            "style. Reason from the thesis alone. Set framework_validation "
            "to null and framework_influence_notes to empty string.\\n"
        )

And update the return statement to include framework_block in the
join list:

    return "\\n\\n".join([
        position_block,
        thesis_block,
        styles_block,
        input_quality_block,
        framework_block,   # NEW
        task_block,
    ])

=== EDIT 4: Update the call to _build_user_prompt ===

Find the call to _build_user_prompt in analyze_rebuy and add the
framework_validation argument:

    user_prompt = _build_user_prompt(
        ticker=ticker,
        position=position,
        thesis_text=thesis_text,
        thesis_available=thesis_available,
        confidence_tier=confidence_tier,
        confidence_rationale=confidence_rationale,
        styles_json=vault.get("styles_json", {}),
        framework_validation=framework_validation_dict,   # NEW
    )

=== EDIT 5: Force the framework_validation field on the response ===

After the post-LLM hash override block, add:

    # Force framework_validation from the pre-computed dict, overriding
    # anything the LLM claimed. Trust the computation, not the LLM.
    if framework_validation_dict is not None:
        from agents.rebuy_analyst import FrameworkValidation
        response.framework_validation = FrameworkValidation(
            **framework_validation_dict
        )
    else:
        response.framework_validation = None

=== EDIT 6: Update the REBUY_SYSTEM_PROMPT ===

Find the "How to reason" section and add a new step between step 2
and step 3:

    3. **Respect pre-computed framework evaluation if present.** You
       may receive a framework evaluation block with rule-by-rule
       results. These are computed in deterministic Python, not by
       you — do not try to re-derive them. Your job is to explain how
       the framework score influences your recommendation, and to
       fill in the framework_influence_notes field accordingly.
       Framework validation is INFORMATIONAL in v1: you may still
       recommend scale_in on a partial framework pass, but you must
       justify it explicitly. A clean framework pass is a strong
       positive signal. A clean framework fail is a strong negative
       signal. Framework irrelevance (no framework applies) means
       reason from thesis alone.

Renumber the existing steps 3-5 to 4-6.

Do NOT:
- Let the LLM compute rule results
- Trust any framework_validation the LLM returns — always overwrite
- Skip the framework pipeline if frameworks is empty (handle gracefully)
- Fetch fundamentals when no framework applies (avoid the FMP call)
```

---

## Prompt 6 of 7: Add thesis frontmatter and write the UNH test case

```text
=== EDIT 1: Create a tiny utility to add frontmatter to existing theses ===

Create: scripts/add_thesis_frontmatter.py

    \"\"\"
    One-time utility: add YAML frontmatter to existing thesis files.

    Idempotent: skips files that already have frontmatter. Infers ticker
    from filename (<TICKER>_thesis.md). Leaves style and
    framework_preference blank unless overridden via a mapping dict.

    Usage:
        python scripts/add_thesis_frontmatter.py --dry-run
        python scripts/add_thesis_frontmatter.py --live
    \"\"\"
    import argparse
    from pathlib import Path
    import re

    THESIS_DIR = Path("vault/theses")

    # Explicit style overrides for known tickers. Leave others blank —
    # Bill can fill them in during review.
    STYLE_OVERRIDES = {
        "UNH": ("garp", "lynch_garp_v1"),
        # Add more as calibration proceeds.
    }

    def has_frontmatter(text: str) -> bool:
        lines = text.splitlines()
        return bool(lines) and lines[0].strip() == "---"

    def build_frontmatter(ticker: str) -> str:
        style, framework = STYLE_OVERRIDES.get(ticker, ("", ""))
        return (
            f"---\\n"
            f"ticker: {ticker}\\n"
            f"style: {style}\\n"
            f"framework_preference: {framework}\\n"
            f"entry_date:\\n"
            f"last_reviewed:\\n"
            f"---\\n\\n"
        )

    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        args = parser.parse_args()
        live = args.live and not args.dry_run

        pattern = re.compile(r"^([A-Z][A-Z0-9.\\-]{0,9})_thesis\\.md$")
        updated = 0
        skipped = 0
        for path in sorted(THESIS_DIR.glob("*_thesis.md")):
            m = pattern.match(path.name)
            if not m:
                continue
            ticker = m.group(1).upper()
            text = path.read_text(encoding="utf-8")
            if has_frontmatter(text):
                skipped += 1
                continue
            new_text = build_frontmatter(ticker) + text
            if live:
                path.write_text(new_text, encoding="utf-8")
            updated += 1
            print(f"{'[live]' if live else '[dry]'} {path.name}: added frontmatter")

        print(f"\\nSummary: {updated} updated, {skipped} already had frontmatter")

    if __name__ == "__main__":
        main()

Run it dry first, then live:
    python scripts/add_thesis_frontmatter.py --dry-run
    python scripts/add_thesis_frontmatter.py --live

Verify UNH_thesis.md now starts with:
    ---
    ticker: UNH
    style: garp
    framework_preference: lynch_garp_v1
    ...


=== EDIT 2: Manually flip reviewed_by_bill to true for Lynch GARP ===

Open vault/frameworks/lynch_garp_v1.json in an editor. Read the rules.
If they match your understanding of Lynch's framework, change:

    "reviewed_by_bill": false

to:

    "reviewed_by_bill": true

This is the manual checkpoint — don't automate it. The whole point of
the review flag is that a human has eyeballed the extracted rules.


=== EDIT 3: Rebuild the composite bundle ===

   python manager.py vault-snapshot --root vault
   python manager.py compose --market latest --vault latest
```

---

## Prompt 7 of 7: Smoke tests, CHANGELOG, dry-run verification

```text
=== EDIT 1: Extend tests/test_rebuy_analyst_smoke.py ===

Add these new tests alongside the existing Phase 3 tests:

    def test_framework_validation_is_optional():
        \"\"\"A response without framework_validation must still validate.\"\"\"
        m = RebuyAnalysis(
            composite_hash="a" * 64,
            ticker="UNH",
            thesis_available=True,
            price_source="yfinance_live",
            confidence_tier="high",
            confidence_rationale="All inputs present.",
            recommendation="hold",
            recommendation_rationale="Position correctly sized; thesis intact.",
            style="garp",
            style_alignment_notes="Classic GARP compounder.",
        )
        assert m.framework_validation is None


    def test_framework_validation_structural_integrity():
        from agents.rebuy_analyst import FrameworkValidation, FrameworkRuleResult
        fv = FrameworkValidation(
            framework_id="lynch_garp_v1",
            framework_version="1.0.0",
            framework_content_sha256="b" * 64,
            applicable=True,
            applicability_rationale="UNH matches garp style and Equities asset class.",
            rules_evaluated=[
                FrameworkRuleResult(
                    rule_id="peg_in_buy_zone",
                    description="PEG ratio is in the buy zone",
                    passed=True,
                    observed_value="0.87",
                    severity="required",
                    rationale="PEG of 0.87 is within Lynch's 0.5-1.0 buy zone",
                ),
            ],
            required_rules_passed=1,
            required_rules_total=3,
            preferred_rules_passed=0,
            preferred_rules_total=2,
            passes_framework=False,
            insufficient_data_rules=[],
            framework_score_display="1/3 required + 0/2 preferred",
        )
        assert fv.framework_id == "lynch_garp_v1"


    def test_framework_selector_skips_unreviewed():
        from agents.framework_selector import select_framework, ThesisFrontmatter
        frameworks = [{
            "framework_id": "lynch_garp_v1",
            "framework_version": "1.0.0",
            "reviewed_by_bill": False,   # unreviewed!
            "applies_to_styles": ["garp"],
            "applies_to_asset_classes": ["Equities"],
            "excludes_conditions": [],
        }]
        position = {"ticker": "UNH", "asset_class": "Equities"}
        fm = ThesisFrontmatter(ticker="UNH", style="garp")
        result = select_framework("UNH", position, fm, frameworks)
        assert result is None, "Unreviewed framework must not be selected"


    def test_framework_selector_respects_frontmatter_preference():
        from agents.framework_selector import select_framework, ThesisFrontmatter
        frameworks = [
            {
                "framework_id": "lynch_garp_v1",
                "framework_version": "1.0.0",
                "reviewed_by_bill": True,
                "applies_to_styles": ["garp"],
                "applies_to_asset_classes": ["Equities"],
                "excludes_conditions": [],
            },
            {
                "framework_id": "graham_deep_value_v1",
                "framework_version": "1.0.0",
                "reviewed_by_bill": True,
                "applies_to_styles": ["boring"],
                "applies_to_asset_classes": ["Equities"],
                "excludes_conditions": [],
            },
        ]
        position = {"ticker": "UNH", "asset_class": "Equities"}
        fm = ThesisFrontmatter(
            ticker="UNH", style="garp",
            framework_preference="lynch_garp_v1",
        )
        result = select_framework("UNH", position, fm, frameworks)
        assert result is not None
        assert result["framework_id"] == "lynch_garp_v1"


    def test_evaluate_framework_rules_handles_missing_data():
        from agents.framework_selector import evaluate_framework_rules
        framework = {
            "framework_id": "lynch_garp_v1",
            "framework_version": "1.0.0",
            "_framework_content_sha256": "c" * 64,
            "applies_to_styles": ["garp"],
            "applies_to_asset_classes": ["Equities"],
            "rules": [{
                "rule_id": "peg_in_buy_zone",
                "description": "PEG ratio is in the buy zone",
                "required_fields": ["peg_ratio"],
                "severity": "required",
                "check_type": "range",
                "target_min": 0.5,
                "target_max": 1.0,
            }],
            "passing_threshold": {
                "required_rules_passed_minimum": 1,
                "preferred_rules_passed_minimum": 0,
                "total_rules": 1,
            },
        }
        position = {"ticker": "UNH", "asset_class": "Equities"}
        fundamentals = {}  # no peg_ratio available
        result = evaluate_framework_rules(position, fundamentals, framework)
        assert result["rules_evaluated"][0]["passed"] is None
        assert "peg_in_buy_zone" in result["insufficient_data_rules"]
        assert result["required_rules_passed"] == 0

Run:
    python -m pytest tests/test_rebuy_analyst_smoke.py -v

All existing tests plus the five new framework tests must pass.


=== EDIT 2: CHANGELOG.md ===

Add at the top:

    ## [Unreleased] — CLI Migration Phase 3c: Framework Registry + Lynch GARP

    ### Added
    - `vault/frameworks/lynch_garp_v1.json` — first reviewed investment
      framework, extracted from Peter Lynch's One Up On Wall Street via
      NotebookLM and hand-reviewed
    - `core/vault_bundle.py` — new `frameworks` field, `_load_frameworks`
      helper, content-hash tamper detection per framework file
    - `agents/framework_selector.py` — deterministic framework selection
      and rule evaluation (no LLM, pure Python)
    - `agents/rebuy_analyst.py` — FrameworkValidation and
      FrameworkRuleResult Pydantic schemas; new framework_validation
      and framework_influence_notes fields on RebuyAnalysis
    - `scripts/add_thesis_frontmatter.py` — one-time utility for
      adding YAML frontmatter to existing thesis files
    - Thesis frontmatter schema: ticker, style, framework_preference,
      entry_date, last_reviewed
    - Five new smoke tests covering optional framework_validation,
      unreviewed framework skipping, frontmatter preference, missing
      data handling

    ### Architecture Decision
    Frameworks are DATA, not prompt text. Each framework lives as a
    reviewed JSON file under `vault/frameworks/`, gets content-hashed
    by the vault bundler, and is selected for a ticker at analysis
    time by a deterministic Python function. Rule evaluation also
    happens in Python — the LLM receives pre-computed results and
    explains them, it does not perform the arithmetic.

    This closes a failure mode where hardcoding a framework into
    the Re-Buy Analyst system prompt would have forced a single
    investment philosophy onto the full 50+ position portfolio,
    producing nonsense for any ticker the framework didn't fit.

    Framework validation is INFORMATIONAL in v1. The LLM may still
    recommend scale_in on a partial framework pass, but must explain
    why in framework_influence_notes. Tighten to blocking in v2 only
    if the agent systematically ignores framework failures.

    NotebookLM-extracted frameworks require explicit human review
    (reviewed_by_bill: true) before the selector uses them. This
    closes the "hallucinated rule becomes machine-enforced truth"
    failure mode.

    ### Unchanged
    - Phase 3 single-ticker Re-Buy path
    - Agent_Outputs schema (framework_validation is stored inside
      the Full_Response_JSON field, not as a separate column in v1)
    - All other tabs
    - The Streamlit app

    **Status:** Phase 3c defaults to DRY RUN. Lynch GARP framework
    is calibrated against UNH only. Running rebuy on other tickers
    will produce framework_validation=None (no applicable framework),
    which is safe — the agent falls back to Phase 3 thesis-only
    reasoning.


=== EDIT 3: Update CLAUDE.md CLI Migration Status ===

- Phase 3: COMPLETE
- Phase 3b: (status as of your landing)
- Phase 3c: COMPLETE — framework registry + Lynch GARP + UNH MVP
- Phase 3d: FUTURE — additional frameworks (Graham, CANSLIM) and
  rollout to more tickers


=== EDIT 4: Dry-run verification against UNH ===

    # Sanity: all new smoke tests pass
    python -m pytest tests/test_rebuy_analyst_smoke.py -v

    # Rebuild bundles with the new framework loaded
    python manager.py vault-snapshot --root vault
    python manager.py compose --market latest --vault latest

    # Dry run against UNH — expect framework_validation to populate
    python manager.py rebuy --ticker UNH --composite latest

    # The output should include a Framework Evaluation section
    # showing how UNH scored against Lynch's five rules. Expect some
    # rules to come back as insufficient_data if FMP doesn't return
    # all fields — that's the correct behavior.

    # Dry run against a ticker that should NOT match Lynch (CRWV is
    # speculative, no earnings). Expect framework_validation=None and
    # a clean fallback to thesis-only reasoning.
    python manager.py rebuy --ticker CRWV --composite latest

    # DO NOT run --live yet. The calibration loop below must pass first.
```

---

## The Phase 3c Calibration Gate

Do not run `--live` until ALL of these are true:

1. **Lynch GARP applies to UNH and produces a plausible score.** The
   rule results table shows concrete values (PEG, growth rate, P/E,
   debt/equity) with clear pass/fail/insufficient-data status. If
   every rule comes back insufficient_data, FMP isn't returning the
   fields — fix that before proceeding.

2. **The recommendation rationale references the framework score.**
   If the agent scores UNH at 2/3 required rules but still recommends
   scale_in, the framework_influence_notes field must explain the
   rationale. Generic "despite the mixed framework signal" is not
   enough — look for specific references to which rules failed and why
   the rationale still supports adding.

3. **CRWV falls back cleanly.** framework_validation must be None,
   framework_influence_notes must be empty string, and the
   recommendation must come from thesis-only reasoning. If CRWV picks
   up the Lynch framework and gets scored against GARP metrics, the
   selector logic is broken — the exclusion for no_earnings or the
   style filter isn't working.

4. **The Lynch framework content hash appears in the response's
   framework_validation block.** If it doesn't, the audit chain is
   broken.

5. **Rebuilding the composite bundle with a modified framework JSON
   produces a different vault bundle hash.** (Tamper detection sanity
   check: edit lynch_garp_v1.json trivially, re-run vault-snapshot,
   compare hashes.)

6. **Bill reviews at least one full output and explicitly says "yes,
   this is how Peter Lynch would have reasoned about UNH."** Not
   "close enough." The actual thing.

---

## Gemini CLI Peer Review

```bash
gemini -p "Review the Phase 3c framework registry implementation:
agents/framework_selector.py, the extensions to core/vault_bundle.py,
agents/rebuy_analyst.py schema changes, and
vault/frameworks/lynch_garp_v1.json.

Check specifically:

1) Is rule evaluation done in deterministic Python, not by the LLM?
   The LLM should receive PRE-COMPUTED rule results and never perform
   the arithmetic itself.

2) Does select_framework() refuse to return any framework where
   reviewed_by_bill is False, regardless of other match criteria?

3) Does the framework loader in core/vault_bundle.py raise ValueError
   on malformed JSON rather than silently skipping?

4) Does each framework carry a content SHA256 hash that propagates
   into FrameworkValidation.framework_content_sha256 in the response?

5) Does the RebuyAnalysis schema make framework_validation OPTIONAL
   (default None) so tickers without an applicable framework still
   produce valid responses?

6) Does evaluate_framework_rules() handle missing fundamentals data
   by marking the rule passed=None and adding it to
   insufficient_data_rules, rather than crashing or defaulting to
   False?

7) Is the Lynch framework JSON free of any price_target fields or
   any rule that would generate a price prediction?

8) Does parse_thesis_frontmatter() handle files WITHOUT frontmatter
   gracefully, returning an empty ThesisFrontmatter instead of raising?

9) Is framework_validation forced from the pre-computed dict AFTER
   the LLM response, overriding anything the LLM may have claimed
   (same discipline as the composite_hash override from Phase 3)?

10) Can an ETF or speculative ticker (CRWV) bypass the framework
    pipeline cleanly, with framework_validation=None and the agent
    falling back to thesis-only reasoning?"
```

---

## Commit After Green

Once all smoke tests pass, the calibration gate is cleared, and Gemini's
peer review is clean:

```bash
git add vault/frameworks/lynch_garp_v1.json \
        core/vault_bundle.py \
        agents/framework_selector.py \
        agents/rebuy_analyst.py \
        scripts/add_thesis_frontmatter.py \
        vault/theses/ \
        tests/test_rebuy_analyst_smoke.py \
        requirements.txt \
        CHANGELOG.md \
        CLAUDE.md
git commit -m "Phase 3c: framework registry + Lynch GARP MVP

- Frameworks live as reviewed JSON files in vault/frameworks/
- core/vault_bundle.py loads frameworks with content hashing
- agents/framework_selector.py: deterministic selection + rule eval
- agents/rebuy_analyst.py: FrameworkValidation schema, optional field
- vault/frameworks/lynch_garp_v1.json: first framework, hand-reviewed
- Thesis frontmatter: YAML, backward-compatible
- UNH scored against Lynch GARP in dry run, calibration gate cleared

LLMs synthesize, Python calculates — the framework pipeline extends
this principle to rule evaluation. The LLM receives pre-computed
rule results and explains them; it does not perform the arithmetic.
reviewed_by_bill gate prevents NotebookLM hallucinations from
becoming machine-enforced truth.

Framework validation is INFORMATIONAL in v1. Tighten to blocking
in v2 only if the agent systematically ignores framework failures.

Unblocks Phase 3d (additional frameworks + rollout)."
```

---

## What Phase 3c explicitly does NOT do

- **Options trading frameworks.** The Van Der Post algorithmic options
  trading material belongs in a FUTURE phase specifically for covered
  call scanning and options-yield strategy. It is not an equity
  fundamental framework and does not fit the current schema. Do not
  inject any of that material into rebuy_analyst.
- **Additional frameworks beyond Lynch GARP.** Graham, CANSLIM, Dogs
  of the Dow, O'Shaughnessy — all deferred to Phase 3d.
- **Rollout to all 51 positions.** Phase 3c calibrates on UNH only.
  Running rebuy on other tickers will produce framework_validation=None
  unless they match the garp style.
- **Blocking framework validation.** V1 is informational. V2 decides
  whether to tighten.
- **Backfilling thesis frontmatter for all 51 positions.** The script
  adds blank frontmatter so the files are frontmatter-aware, but
  Bill fills in style and framework_preference only as he rolls out
  to each position.
- **New data sources.** FMP only. No new API integrations.
- **Changes to the Phase 3 base behavior.** If no framework applies,
  the agent runs exactly as it did in Phase 3.

---

## A note on the Van Der Post options material

The Algorithmic Trading Pro material in your project resources is
genuinely interesting and has real architectural implications — but
not for Phase 3c. Options strategies need:

- A different Pydantic schema (Greeks, IV rank, expiry, strike,
  premium)
- A different data source (Schwab /chains endpoint or similar)
- A different validation philosophy (IV rank thresholds and theta
  decay, not fundamental ratios)
- A different execution discipline (covered calls on existing
  positions, cash-secured puts for entry)

When you're ready to build the options layer, it should be its own
agent (`agents/options_analyst.py`) with its own framework registry
entry type, NOT a bolt-on to rebuy_analyst. The right time is after
Phase 4 (Schwab API live) because you'll need the `/chains` endpoint
data. Flag it for a dedicated phase — probably 8a per the master
plan — not for injection into the re-buy pipeline.

The Lynch extraction is the correct starting point because it
matches the fundamental reasoning Re-Buy Analyst already does. Keep
them separate.
