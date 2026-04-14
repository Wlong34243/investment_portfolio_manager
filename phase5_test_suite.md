# Phase 5 Test Suite — Investment Portfolio Manager
**Target runner: Gemini CLI (`gemini --all-files -p "..."` or `gemini -p "..."` per test)**  
**Execution model: Run one test group at a time. Never run all groups in a single call.**  
**All tests default to DRY RUN unless explicitly noted. Never pass `--live` during testing.**

---

## How to Use This File

Each test group below is a self-contained Gemini CLI prompt. Copy the prompt block verbatim, run it, and evaluate the output against the PASS criteria listed. A test FAILS if any PASS criterion is not met. FAIL details should be logged in `tasks/todo.md` as bugs before proceeding.

**Session start before any test group:**
```bash
gemini --all-files -p "Read CLAUDE.md, CHANGELOG.md (last 5 entries), and agents/rebuy_analyst.py. Confirm the CLI migration phase status and tell me which agents are currently registered in manager.py."
```

---

## Group 1 — Infrastructure Integrity (Run First)

These tests validate Phases 1–4 are still solid before any Phase 5 work begins. If any Group 1 test fails, fix it before running Groups 2–7.

### T1.1 — Bundle round-trip integrity
```
Run: python manager.py snapshot --source auto

Then run: python manager.py bundle verify <path from snapshot output>

PASS if:
- Snapshot completes without error
- data_source field is either "schwab" or "csv" (not empty)
- bundle_hash is a 64-char hex string
- verify command prints "PASS Hash verified"
- No enrichment_errors for QACDS or CASH_MANUAL (these should be excluded)

FAIL signals:
- KeyError on any position field
- data_source = None
- verify prints FAIL
```

### T1.2 — Vault bundle coverage
```
Run: python manager.py vault snapshot

PASS if:
- theses_present count >= 45 (we backfilled 51)
- theses_missing count < 10
- vault_hash is a 64-char hex string
- No Python exceptions in output

Log any tickers in theses_missing — these positions will have degraded agent output.
```

### T1.3 — Composite bundle assembly
```
Run: python manager.py bundle composite

PASS if:
- composite_hash is present and non-empty
- market_bundle_hash and vault_bundle_hash are both non-empty and different from each other
- position_count > 40
- vault_doc_count > 40
- theses_missing count matches T1.2 output

FAIL signals:
- composite_hash is None
- position_count = 0
- FileNotFoundError on either sub-bundle
```

### T1.4 — CASH_MANUAL and QACDS exclusion
```
Run: python manager.py snapshot --source auto

Inspect the bundle JSON output. Search for any position where ticker == "CASH_MANUAL" or ticker == "QACDS".

PASS if:
- Both positions exist in the raw positions list (they should be in the data)
- Neither appears in any agent's investable positions list
- Beta calculation excludes both (beta_contribution = 0 for both)
- Allocation percentage denominator does NOT include either

FAIL if:
- CASH_MANUAL or QACDS appears in a positions list that gets passed to an LLM call
- Either contributes to portfolio beta
```

### T1.5 — Schwab API fallback behavior
```
Temporarily rename bundles/ to bundles_backup/ so there are no existing bundles.
Run: python manager.py snapshot --source auto

Then rename bundles_backup/ back to bundles/.

PASS if:
- Command attempts Schwab API first
- If Schwab fails: falls back gracefully with a visible yellow warning panel
- Falls back to CSV if --csv path was provided, OR raises a clean error if not
- Never silently produces a zero-position bundle

FAIL if:
- Python traceback instead of a graceful warning
- bundle produced with position_count = 0
- No fallback warning displayed
```

---

## Group 2 — Re-buy Analyst (Phase 3 Baseline — Must Still Pass)

The Re-buy Analyst is the reference implementation. If it regresses, something in the shared infrastructure broke.

### T2.1 — Dry run produces valid output
```
Run: python manager.py agent rebuy analyze

PASS if:
- No Python exceptions
- Output table shows columns: Ticker | Style | Next Step | Confidence
- At least one candidate classified as scale_in or hold
- bundle_hash in output matches the composite bundle hash from T1.3
- Local files created: bundles/rebuy_output_<hash>.json and bundles/rebuy_output_<hash>.md

FAIL signals:
- Gemini returns None (check API key / quota)
- bundle_hash in output does NOT match composite hash
- No local output files written
- All candidates classified the same way (likely a schema parse failure)
```

### T2.2 — Single-ticker mode
```
Run: python manager.py agent rebuy analyze --ticker UNH

PASS if:
- Only UNH appears in candidates output
- UNH thesis file content is referenced (scaling_state, rotation_priority)
- framework_validation field is populated (not null) — UNH should have FMP fundamentals
- proposed_next_step is one of: scale_in | hold | watch | exit_watch
- Confidence is one of: high | medium | low

FAIL signals:
- Multiple tickers in output (filtering broke)
- framework_validation is null despite FMP being configured
- proposed_next_step not in allowed enum values
```

### T2.3 — Framework pre-computation override
```
Run: python manager.py agent rebuy analyze --ticker AMZN

Inspect bundles/rebuy_output_<hash>.json for AMZN.

PASS if:
- framework_validation.applicable = true OR framework_validation = null (both valid)
- If applicable: framework_validation.rules_evaluated is a list with >= 3 items
- framework_validation.passes_framework is a boolean, not a string
- proposed_next_step is NOT changed from what the Python framework computed
  (the LLM cannot override the framework_validation — it can only add rationale)

FAIL if:
- framework_validation.passes_framework does not match the rule evaluation arithmetic
- LLM output contradicts the Python pre-computed framework result without justification
```

### T2.4 — Coverage warning for missing thesis
```
Temporarily rename vault/theses/GOOG_thesis.md to vault/theses/GOOG_thesis.md.bak
Run: python manager.py vault snapshot
Run: python manager.py bundle composite
Run: python manager.py agent rebuy analyze --ticker GOOG
Restore: rename vault/theses/GOOG_thesis.md.bak back

PASS if:
- GOOG appears in coverage_warnings list
- Agent still produces output for GOOG (missing thesis = warning, not failure)
- Output notes thesis was absent
- No Python exception

FAIL if:
- Agent crashes on missing thesis
- GOOG silently excluded from output
```

---

## Group 3 — Tax Agent (Phase 5-A)

### T3.1 — TLH candidate identification
```
Run: python manager.py agent tax analyze

Inspect output for tlh_candidates list.

PASS if:
- All unrealized_loss_usd values are NEGATIVE numbers (these are losses)
- Values are Python-computed (check: do they match Holdings_Current Unrealized G/L column?)
- Each candidate has a scale_step field using small-step language (e.g., "trim 20%", not "sell all")
- composite_hash in output matches T1.3

FAIL signals:
- Any tlh_candidate with unrealized_loss_usd > 0 (that's a gain, not a TLH target)
- scale_step says "sell all" or "exit position" (violates small-step invariant)
- Values don't match Holdings_Current sheet (LLM computed them instead of Python)
```

### T3.2 — Wash sale flag accuracy
```
Precondition: At least one ticker in Transactions tab has a buy within 30 days of a sell in the same ticker.

Run: python manager.py agent tax analyze

PASS if:
- That ticker appears with wash_sale_risk = true in tlh_candidates
- The warnings list contains a wash sale notice for that ticker
- Tickers with no recent transactions have wash_sale_risk = false

FAIL signals:
- wash_sale_risk = true for every ticker (false positives — logic broken)
- wash_sale_risk = false for a known wash sale situation
- warnings list is empty despite known wash sale conditions
```

### T3.3 — Rebalancing drift calculation
```
Precondition: Target_Allocation tab has at least 3 asset classes populated.

Run: python manager.py agent tax analyze

PASS if:
- rebalance_actions list is populated
- Each action has direction = "trim" or "add" (not "sell" or "buy")
- drift_pct values are Python-computed — verify one manually: (current_weight - target_weight)
- No rebalance_action exists for CASH_MANUAL or QACDS

FAIL signals:
- rebalance_actions empty despite obvious drift (UNH at 9% weight with 5% threshold)
- Drift percentages don't match the arithmetic
- CASH_MANUAL or QACDS appears in rebalance_actions
```

### T3.4 — Short vs long term classification
```
Run: python manager.py agent tax analyze

For any position held > 365 days:
PASS if: short_term = false

For any position held < 365 days:
PASS if: short_term = true

If tax_treatment_available = false (CSV path):
PASS if: holding_period_days shows a reasonable estimate or is marked "unknown"
FAIL if: all positions marked short_term = true by default when data is unavailable
```

### T3.5 — No writes to Target_Allocation
```
Note the current row count and last fingerprint in Target_Allocation tab.
Run: python manager.py agent tax analyze --live

PASS if:
- Target_Allocation row count is IDENTICAL before and after
- Last fingerprint in Target_Allocation is IDENTICAL
- Writes only appear in Agent_Outputs (or Agent_Outputs_Archive if archive ran)

FAIL if:
- Any write occurs to Target_Allocation
- This is an automatic CRITICAL FAIL — stop and fix before continuing
```

---

## Group 4 — Valuation Agent (Phase 5-B)

### T4.1 — P/E sourced from Python, not LLM
```
Run: python manager.py agent valuation analyze --tickers UNH,GOOG,AMZN

For each ticker in output, manually verify pe_fwd against FMP data:
  python -c "from utils.fmp_client import get_fundamentals; import json; print(json.dumps(get_fundamentals('UNH'), indent=2))"

PASS if:
- pe_fwd in agent output matches FMP forward_pe field (within rounding)
- peg in agent output matches FMP peg_ratio field (within rounding)
- Values were NOT generated by Gemini (check: are they exactly from FMP?)

FAIL signals:
- pe_fwd values differ significantly from FMP data
- pe_fwd = null for tickers where FMP has data
- Values appear rounded to suspiciously clean numbers (LLM hallucination pattern)
```

### T4.2 — Accumulation plan uses small-step language
```
Run: python manager.py agent valuation analyze

For every PositionValuation where signal = "accumulate":

PASS if:
- accumulation_plan contains language like: "scale", "step", "tranche", "dip", "%"
- accumulation_plan does NOT say: "buy", "purchase", "add full position", "all-in"
- Each step is <= 25% of the suggested total add

FAIL signals:
- accumulation_plan = null for accumulate signals
- Plan language is binary ("buy X shares")
- No percentage or step reference
```

### T4.3 — Data gaps logged correctly
```
Identify at least 2 tickers with no FMP coverage (likely: CORZ, IREN, CRWV — recent IPOs or small caps).

Run: python manager.py agent valuation analyze

PASS if:
- Those tickers appear in data_gaps list
- They do NOT appear in positions list with null pe_fwd and a fabricated signal
- summary_narrative acknowledges data gaps

FAIL signals:
- Tickers with no FMP data silently dropped from output
- pe_fwd = 0.0 used as a fallback (misleading — should be null)
- LLM generates a signal for a ticker with no real data
```

### T4.4 — Style alignment sourced from vault
```
Run: python manager.py agent valuation analyze --tickers UNH,XBI,JPIE,QQQM

PASS if:
- UNH has style_alignment = "GARP" or "boring_fundamentals" (matches thesis frontmatter)
- XBI has style_alignment = "thematic" or "sector_etf"
- JPIE has style_alignment = "income" or "boring_fundamentals"
- QQQM has style_alignment = "sector_etf" or "thematic"

None of these should be hallucinated — they must trace back to the thesis frontmatter style field.

FAIL signals:
- style_alignment = "unknown" for a ticker with a thesis file
- style_alignment contradicts the thesis frontmatter
```

---

## Group 5 — Concentration Hedger (Phase 5-C)

### T5.1 — UNH concentration flag fires
```
Run: python manager.py agent concentration analyze

PASS if:
- A ConcentrationFlag exists for UNH with flag_type = "single_position"
- current_weight_pct is approximately 9.0 (matches Holdings_Current)
- threshold_pct = 8.0 (from config.CONCENTRATION_SINGLE_THRESHOLD)
- severity = "action" (not "watch" — 9% is over threshold)

FAIL signals:
- UNH not flagged at all
- threshold_pct does not match config value
- weight doesn't match Holdings_Current
```

### T5.2 — Tech sector concentration flag fires
```
Tech cluster: GOOG, AMZN, NVDA, AMD, META, MSFT, DELL, AVGO, CRWD, SNPS, NOW, PANW, IGV, QQQM

Run: python manager.py agent concentration analyze

PASS if:
- A ConcentrationFlag exists with flag_type = "sector" for Technology/Information Technology
- current_weight_pct > 30.0 (this cluster is well over threshold)
- tickers_involved list contains at least 8 of the tech cluster tickers

FAIL signals:
- No sector flag for tech
- Weight computed incorrectly (missing some tech positions)
- ETFs excluded from sector computation (IGV and QQQM belong in tech weight)
```

### T5.3 — Beta and stress scenarios are Python-computed
```
Run: python manager.py agent concentration analyze

Manually verify portfolio_beta:
  - Get beta for top 10 positions from Holdings_Current
  - Weighted average: sum(beta_i * weight_i) for all non-cash positions
  - Compare to agent output

PASS if:
- portfolio_beta in output matches manual calculation within 0.05
- stress_scenarios["market_down_10pct"] ≈ total_invested_value × portfolio_beta × -0.10
- stress_scenarios["market_down_20pct"] ≈ total_invested_value × portfolio_beta × -0.20

FAIL signals:
- portfolio_beta differs from manual calculation by > 0.1
- Stress dollar impacts appear rounded to suspiciously clean numbers
- CASH_MANUAL included in beta calculation
```

### T5.4 — High-correlation pairs identified
```
Run: python manager.py agent concentration analyze

Known high-correlation pairs (all tech):
- AMZN / GOOG (both mega-cap tech, r typically > 0.85)
- AMD / NVDA (semiconductor pair, r typically > 0.90)
- CRWD / PANW (cybersecurity pair, r typically > 0.80)

PASS if:
- At least 2 of these 3 pairs appear in flags with flag_type = "correlation_pair"
- correlation value is between -1.0 and 1.0 (it's a Pearson coefficient)
- combined_weight is the sum of both positions' weights

FAIL signals:
- No correlation pairs identified
- Correlation > 1.0 or < -1.0 (math error)
- Pairs identified that are obviously unrelated (JPIE / XOM is not a high-corr pair)
```

### T5.5 — Hedge suggestions use small-step language
```
Run: python manager.py agent concentration analyze

For every flag with severity = "action":

PASS if:
- hedge_suggestion references a percentage trim (e.g., "trim 15% in 3 steps")
- scale_step field is populated with explicit step size
- No suggestion says "sell all" or "exit position"
- Rotation target is suggested when trimming (e.g., "rotate to XLV for sector retention")

FAIL signals:
- hedge_suggestion = null for action-severity flags
- Binary language used ("exit UNH", "sell all tech")
- No rotation context provided
```

---

## Group 6 — Macro Cycle Agent (Phase 5-D)

### T6.1 — ATR computed in Python, not LLM
```
Precondition: tasks/enrich_atr.py exists and has been run, injecting calculated_technical_stops into the bundle.

Run: python manager.py agent macro analyze

PASS if:
- calculated_technical_stops exists in the bundle JSON (check the composite JSON directly)
- Each entry has: ticker, atr_14, stop_loss_level, current_price
- stop_loss_level = current_price - (2.5 × atr_14) within rounding
- Gemini output references these pre-computed values, it does NOT re-calculate ATR

Manual verify one ticker:
  python -c "import yfinance as yf; import pandas as pd; df = yf.download('UNH', period='1mo', interval='1d', progress=False); tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift(1)).abs(), (df['Low']-df['Close'].shift(1)).abs()], axis=1).max(axis=1); print('ATR:', tr.rolling(14).mean().iloc[-1])"
  
Compare to bundle's atr_14 value for UNH.

FAIL signals:
- calculated_technical_stops absent from bundle
- stop_loss_level doesn't match the formula
- Agent calls yfinance directly (this is the invariant violation from the original code)
```

### T6.2 — Paradigm phase is a valid enum value
```
Run: python manager.py agent macro analyze

PASS if:
- Every paradigm_phase value is one of: installation | frenzy | synergy | maturity | unknown
- No paradigm_phase = null
- distribution of phases is reasonable (not every position in "maturity")

FAIL signals:
- Free-text paradigm values (schema not enforced)
- > 80% of positions classified identically (LLM defaulting)
```

### T6.3 — Rotation targets sourced from vault research
```
Run: python manager.py agent macro analyze

PASS if:
- rotation_targets list is non-empty
- At least one rotation target matches a ticker or sector mentioned in vault/research/ notes
- Targets are not from the current portfolio (you can't rotate into something you already hold at full weight)

FAIL signals:
- rotation_targets = []
- Targets are hallucinated (no reference to vault documents)
```

---

## Group 7 — Thesis Screener (Phase 5-E)

### T7.1 — Thesis content used for alignment check
```
Run: python manager.py agent thesis analyze --ticker UNH

PASS if:
- thesis_alignment_warning references UNH-specific thesis content (not generic language)
- exit_conditions from UNH_thesis.md are checked (not ignored)
- final_recommendation is one of: MAINTAIN_CONVICTION | WATCHLIST_DOWNGRADE | THESIS_VIOLATED

FAIL signals:
- thesis_alignment_warning = "No thesis available" for a ticker with a thesis file
- Response is purely generic (doesn't reference UNH's specific core_thesis)
- final_recommendation not in allowed enum values
```

### T7.2 — Behavioral guardrails fire for potential downgrade
```
Run: python manager.py agent thesis analyze on a ticker with recent negative news but intact long-term thesis (e.g., UNH, GOOG, or AMZN after any earnings miss).

PASS if:
- pre_mortem_behavioral_check field is populated with a specific guardrail referenced
  (WYSIATI / Disposition Effect / Action Bias / Anchoring / Envy / Hyperbolic Discounting)
- If guardrail fires: final_recommendation defaults to MAINTAIN_CONVICTION or explains the override
- Guardrail field is NOT empty boilerplate ("No biases detected")

FAIL signals:
- pre_mortem_behavioral_check = null or empty string
- THESIS_VIOLATED recommended without any guardrail analysis
- Same guardrail text for every ticker (copy-paste, not reasoned)
```

### T7.3 — Missing transcript graceful degradation
```
Precondition: Choose a ticker with no earnings transcript in vault/transcripts/ (e.g., CORZ or IREN).

Run: python manager.py agent thesis analyze --ticker CORZ

PASS if:
- Agent produces output (no crash)
- Output notes that no transcript was available
- linguistic_candor_score reflects limited data ("insufficient data — no transcript")
- final_recommendation is WATCHLIST_DOWNGRADE or MAINTAIN_CONVICTION, not THESIS_VIOLATED
  (can't violate a thesis with no evidence)

FAIL signals:
- Python exception on missing transcript
- Agent hallucinates transcript content
- THESIS_VIOLATED recommended without evidence
```

---

## Group 8 — 100-Bagger Screener (Phase 5-F)

### T8.1 — Quantitative gate applied in Python
```
Run: python manager.py agent bagger analyze

For UNH (large-cap, ~$250B market cap):

PASS if:
- UNH is classified as REJECT
- acorn_evaluation explains market cap > $1B threshold violation
- Python-computed market_cap value appears (not hallucinated)

For any holding with market cap < $1B (if any — check CORZ, IREN):
PASS if:
- Passes the Acorn check
- ROIC evaluation uses FMP data or is marked "insufficient data"

FAIL signals:
- UNH classified as STRONG_BUY or WATCHLIST (market cap > $1B = auto-reject)
- quantitative_summary contains obviously wrong numbers
- All tickers classified REJECT regardless of metrics (schema parse failure)
```

### T8.2 — Schema file is separate from agent file
```
Run: python -c "from agents.schemas.bagger_schema import BaggerCandidate, BaggerScreenerResponse; print('OK')"

PASS if: Imports succeed without error

Run: python -c "import agents.bangers_screener_agent; import inspect; src = inspect.getsource(agents.bangers_screener_agent); assert 'class BaggerCandidate' not in src; print('Schema correctly separated')"

PASS if: BaggerCandidate class is NOT defined inline in the agent file

FAIL signals:
- ImportError on schema module
- Schema class still defined inline in agent file
```

---

## Group 9 — Van Tharp Framework Integration (Phase 5-G)

### T9.1 — Framework loads via framework_selector
```
Run:
  python -c "
import json
from pathlib import Path
fw_path = Path('vault/frameworks/van_tharp_position_sizing.json')
fw = json.loads(fw_path.read_text())
print('framework_id:', fw.get('framework_id'))
print('reviewed_by_bill:', fw.get('reviewed_by_bill'))
print('applies_to_asset_classes:', fw.get('applies_to_asset_classes'))
assert fw.get('reviewed_by_bill') == True, 'Not marked reviewed'
print('PASS')
"

PASS if: All assertions pass and framework_id = "van_tharp_position_sizing"
FAIL if: File not found or reviewed_by_bill = false
```

### T9.2 — No VanTharp.py remains in agents/
```
Run: find agents/ -name "VanTharp.py" -o -name "van_tharp*.py" 2>/dev/null

PASS if: No files found
FAIL if: Python agent file remains (it should be JSON in vault/frameworks/ only)
```

### T9.3 — 1R position sizing is Python-computed
```
Run: python manager.py agent rebuy analyze

If Van Tharp framework selected for any position, inspect that position's bundle context.

PASS if:
- position_size_units is a number computed as: (portfolio_equity × risk_pct) / (atr × 3.0)
- This computation appears in the bundle JSON before the LLM call
- Gemini output cites the pre-computed value, not a re-derived one

FAIL if:
- LLM computes the position size in its reasoning
- position_size_units is missing from positions where Van Tharp was selected
```

---

## Group 10 — analyze-all Orchestrator (Phase 5-H)

### T10.1 — All agents run sequentially
```
Run: python manager.py analyze-all

PASS if:
- Rich summary table shows 5 rows: rebuy | tax | valuation | concentration | macro (or whichever agents are registered)
- Each row shows status = "complete" or "error" (never hanging)
- All bundle_hash values in the manifest are identical (same composite bundle used for all)
- Run manifest JSON written to bundles/runs/<run_id>.json

FAIL signals:
- Any agent's failure aborts the remaining agents (it should not)
- Different composite hashes in different agent outputs
- No manifest file written
```

### T10.2 — Single batch write in live mode
```
Run: python manager.py analyze-all --live

PASS if:
- Agent_Outputs tab has new rows from this run (tagged with today's run_id)
- Agent_Outputs_Archive tab has the previous rows archived with archived_at timestamp
- Only ONE batch API call to gspread (verify via API quota log or by checking write timing)
- Target_Allocation is UNCHANGED

FAIL signals:
- Multiple sequential writes (cell-by-cell pattern)
- No archive before overwrite
- Any write to Target_Allocation
- API rate limit error (caused by cell-by-cell writes)
```

### T10.3 — One-agent failure does not abort run
```
Temporarily introduce a failure: rename agents/valuation_agent.py to agents/valuation_agent.py.bak

Run: python manager.py analyze-all

Restore: rename .bak back

PASS if:
- Run completes (does not crash)
- manifest.errors contains the valuation failure message
- All other agents (rebuy, tax, concentration, macro) have complete results
- Final summary table shows valuation as "error", others as "complete"

FAIL signals:
- Full Python traceback and abort on valuation failure
- Other agents not run
```

### T10.4 — --agents subset flag
```
Run: python manager.py analyze-all --agents rebuy,tax

PASS if:
- Only rebuy and tax agents run (no valuation, concentration, or macro)
- Summary table shows exactly 2 rows
- Manifest records agents_run = ["rebuy", "tax"]

FAIL signals:
- All agents run regardless of flag
- Unknown agent name causes crash
```

### T10.5 — --fresh-bundle regenerates both bundles
```
Run: python manager.py analyze-all --fresh-bundle

PASS if:
- New market bundle created (timestamp newer than existing bundles)
- New vault bundle created (timestamp newer than existing bundles)
- New composite bundle created linking the new sub-bundles
- All agent outputs reference the NEW composite_hash

FAIL signals:
- Agents use old composite bundle despite --fresh-bundle flag
- Market bundle regenerated but vault bundle not (or vice versa)
```

---

## Group 11 — Sunday Automation (Phase 5-I)

### T11.1 — workflow_dispatch manual trigger
```
In GitHub repo → Actions → weekly_analysis.yml → Run workflow

PASS if:
- Workflow completes with green checkmark
- Run manifest appears as workflow artifact
- Agent_Outputs tab updated in Sheet (check row count and run_id)
- No Streamlit imports in the workflow log (would cause ImportError)

FAIL signals:
- Red X on workflow
- "ModuleNotFoundError: streamlit" in logs
- No artifact uploaded
- Target_Allocation modified
```

### T11.2 — GCP credential resolution in Actions
```
Check workflow logs for the credential resolution step.

PASS if:
- Log shows "Using GCP_SERVICE_ACCOUNT_JSON env var" (not ADC, not local file)
- Sheets write succeeds without authentication error
- Gemini API call succeeds (ADC not required — API key path used in Actions)

FAIL signals:
- AuthenticationError
- "No credentials available" fallback to local file (local file doesn't exist in Actions)
```

### T11.3 — Schwab token expiry fallback in Actions
```
Simulate token expiry: set GCS token to an expired token.
Trigger workflow_dispatch.

PASS if:
- Workflow continues (doesn't abort on Schwab auth failure)
- Log shows "Schwab API fallback to CSV" warning
- Snapshot uses the most recent CSV in the fallback path
- Run manifest records data_source = "csv" with an enrichment_error noting the fallback

FAIL signals:
- Workflow aborts on Schwab failure
- No fallback warning logged
- Silent empty bundle produced
```

---

## Group 12 — Cross-Cutting Invariants (Run After All Groups)

These are system-wide invariants that must hold regardless of which agent ran.

### T12.1 — composite_hash provenance chain
```
From any agent output JSON file, take the bundle_hash (or composite_hash) field.
Locate the corresponding composite bundle file in bundles/.
Verify: python manager.py bundle verify bundles/composite_bundle_<hash>.json

PASS if:
- Every agent output hash traces to a real, verifiable composite bundle
- No agent output references a hash that doesn't exist on disk

FAIL if:
- bundle verify FAILS for any hash found in agent outputs
- Agent output hash is different from the composite bundle used to generate it
```

### T12.2 — No LLM math anywhere
```
From analyze-all output, pick 3 values that should be Python-computed:
  a) A TLH candidate's unrealized_loss_usd
  b) A concentration flag's current_weight_pct
  c) A stress scenario dollar impact

For each, manually verify against Holdings_Current tab math.

PASS if:
- All 3 values match Holdings_Current arithmetic within $1 (rounding only)
- None were generated by Gemini

FAIL signals:
- Values differ by more than $5 from Holdings_Current
- Python-computed values not present in bundle JSON (LLM computed them instead)
```

### T12.3 — DRY_RUN gate never bypassed
```
grep -r "DRY_RUN" agents/ core/ tasks/ | grep -v "\.pyc"

PASS if:
- Every write to gspread is inside an "if live:" or "if not config.DRY_RUN:" block
- No writes occur outside these gates

FAIL if:
- Any gspread write call found outside a DRY_RUN gate
- This is an automatic CRITICAL FAIL
```

### T12.4 — SAFETY_PREAMBLE not duplicated
```
grep -r "SAFETY_PREAMBLE" agents/ | grep -v "ask_gemini"

PASS if:
- SAFETY_PREAMBLE is never referenced in any agent system_instruction string
- It only appears in gemini_client.py where it is auto-prepended

FAIL if:
- Any agent file contains the text "SAFETY_PREAMBLE" in its system_instruction
- (Would cause it to be prepended twice)
```

### T12.5 — Small-step invariant audit
```
From analyze-all output, collect all fields containing action/sizing language:
  - scale_step (all agents)
  - accumulation_plan (valuation agent)
  - hedge_suggestion (concentration hedger)
  - tlh_candidates[*].scale_step (tax agent)
  - rotation_priority (rebuy analyst)

grep for any of these patterns in agent output JSON files:
  "sell all" | "exit position" | "liquidate" | "buy all" | "full position"

PASS if:
- Zero matches found

FAIL signals:
- Any binary entry/exit language
- scale_step = "100%" or "full" anywhere
```

### T12.6 — Agent_Outputs schema compliance
```
Run: python manager.py analyze-all --live

Fetch Agent_Outputs tab as a dataframe and validate:
  - Column A (run_id): UUID format, all rows in this run share the same value
  - Column C (composite_hash): exactly 16 chars (truncated hash)
  - Column D (agent): only values from registered agent names
  - Column J (severity): only values: info | watch | action
  - Column K (dry_run): boolean TRUE/FALSE

PASS if: All column validations pass for all new rows
FAIL signals:
  - NULL values in run_id, agent, or severity columns
  - severity = "critical" or other non-enum value
  - dry_run column missing or not boolean
```

---

## Test Execution Log Template

Copy this into `tasks/todo.md` when running tests:

```
## Phase 5 Test Run — [DATE]

Bundle hash used: _______________

| Group | Test | Result | Notes |
|-------|------|--------|-------|
| G1 | T1.1 Bundle integrity | PASS/FAIL | |
| G1 | T1.2 Vault coverage | PASS/FAIL | |
| G1 | T1.3 Composite assembly | PASS/FAIL | |
| G1 | T1.4 Cash exclusion | PASS/FAIL | |
| G1 | T1.5 Fallback behavior | PASS/FAIL | |
| G2 | T2.1 Rebuy dry run | PASS/FAIL | |
| G2 | T2.2 Single ticker | PASS/FAIL | |
| G2 | T2.3 Framework override | PASS/FAIL | |
| G2 | T2.4 Missing thesis | PASS/FAIL | |
| G3 | T3.1 TLH candidates | PASS/FAIL | |
| G3 | T3.2 Wash sale flags | PASS/FAIL | |
| G3 | T3.3 Rebalancing drift | PASS/FAIL | |
| G3 | T3.4 Short/long term | PASS/FAIL | |
| G3 | T3.5 No Target_Alloc writes | PASS/FAIL | |
| G4 | T4.1 P/E from Python | PASS/FAIL | |
| G4 | T4.2 Small-step accum | PASS/FAIL | |
| G4 | T4.3 Data gaps | PASS/FAIL | |
| G4 | T4.4 Style from vault | PASS/FAIL | |
| G5 | T5.1 UNH flag fires | PASS/FAIL | |
| G5 | T5.2 Tech sector flag | PASS/FAIL | |
| G5 | T5.3 Beta Python-computed | PASS/FAIL | |
| G5 | T5.4 Corr pairs | PASS/FAIL | |
| G5 | T5.5 Hedge small-step | PASS/FAIL | |
| G6 | T6.1 ATR Python-computed | PASS/FAIL | |
| G6 | T6.2 Paradigm enum | PASS/FAIL | |
| G6 | T6.3 Rotation from vault | PASS/FAIL | |
| G7 | T7.1 Thesis content used | PASS/FAIL | |
| G7 | T7.2 Guardrails fire | PASS/FAIL | |
| G7 | T7.3 Missing transcript | PASS/FAIL | |
| G8 | T8.1 Quant gate Python | PASS/FAIL | |
| G8 | T8.2 Schema separated | PASS/FAIL | |
| G9 | T9.1 Framework loads | PASS/FAIL | |
| G9 | T9.2 No VanTharp.py | PASS/FAIL | |
| G9 | T9.3 1R Python-computed | PASS/FAIL | |
| G10 | T10.1 All agents run | PASS/FAIL | |
| G10 | T10.2 Single batch write | PASS/FAIL | |
| G10 | T10.3 Failure isolation | PASS/FAIL | |
| G10 | T10.4 Subset flag | PASS/FAIL | |
| G10 | T10.5 Fresh bundle | PASS/FAIL | |
| G11 | T11.1 workflow_dispatch | PASS/FAIL | |
| G11 | T11.2 GCP creds in Actions | PASS/FAIL | |
| G11 | T11.3 Token expiry fallback | PASS/FAIL | |
| G12 | T12.1 Hash provenance | PASS/FAIL | |
| G12 | T12.2 No LLM math | PASS/FAIL | |
| G12 | T12.3 DRY_RUN gate | PASS/FAIL | |
| G12 | T12.4 SAFETY_PREAMBLE | PASS/FAIL | |
| G12 | T12.5 Small-step audit | PASS/FAIL | |
| G12 | T12.6 Agent_Outputs schema | PASS/FAIL | |

Blockers: _______________
Next action: _______________
```

---

## Gemini CLI Batch Test Commands

Use these composite prompts for Gemini to run entire groups at once:

**Infrastructure (Groups 1–2):**
```bash
gemini --all-files -p "You are a QA engineer. Run the tests in phase5_test_suite.md Groups 1 and 2. For each test: (1) execute the command, (2) evaluate against the PASS criteria, (3) report PASS or FAIL with the specific evidence. Stop on any CRITICAL FAIL."
```

**Agent correctness (Groups 3–8):**
```bash
gemini --all-files -p "You are a QA engineer. Run phase5_test_suite.md Groups 3 through 8. Focus specifically on verifying that all numeric values (P/E, beta, unrealized G/L, ATR stops) are Python-computed and not LLM-generated. Report any case where a numeric value in agent output cannot be traced to a Python calculation in the bundle."
```

**Orchestration and automation (Groups 9–11):**
```bash
gemini --all-files -p "You are a QA engineer. Run phase5_test_suite.md Groups 9, 10, and 11. Pay special attention to T10.2 (single batch write) and T10.3 (failure isolation). These are the most likely failure points in the orchestrator."
```

**Cross-cutting invariants (Group 12):**
```bash
gemini --all-files -p "You are a QA engineer. Run phase5_test_suite.md Group 12 cross-cutting invariant tests. These are system-wide: T12.3 (DRY_RUN gate) and T12.4 (SAFETY_PREAMBLE duplication) are automatic CRITICAL FAILs if they fail. T12.2 (no LLM math) requires you to manually verify 3 numeric values against the Holdings_Current tab. Report all results."
```
