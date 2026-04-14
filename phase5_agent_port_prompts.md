# Phase 5: Agent Squad Port — Prompt Kit
**Investment Portfolio Manager | CLI Migration Phase 5**
*Generated: April 2026 | Handoff target: Claude Code or Gemini CLI*

---

## Context & Status

Phases 1–4 are complete and stable:
- **Phase 1:** Immutable market bundle (`core/bundle.py`, SHA256-hashed)
- **Phase 2:** Vault bundle + composite bundle (`core/vault_bundle.py`, `core/composite_bundle.py`)
- **Phase 3:** Re-buy Analyst ported to bundle interface (`agents/rebuy_analyst.py`)
- **Phase 4:** Schwab API wired as primary data source (`--source auto`)

**Phase 5 goal:** Port the legacy agent squad from `utils/agents/` (Streamlit-cached, sheet-reading) into `agents/` (bundle-aware, CLI-invokable, Pydantic-validated, sandboxed writes).

**Build sequence (strict — each phase validates the next):**

```
5-A: Tax Intelligence Agent (TLH + rebalancing logic)
5-B: Valuation Agent (P/E analysis + accumulation plan)
5-C: Concentration Hedger (position + sector risk)
5-D: analyze-all orchestrator (manager.py batch command)
5-E: Sunday automation (GitHub Actions headless run)
```

---

## Invariants (Non-Negotiable — Apply to Every Prompt)

Read these before executing any prompt below.

1. **No LLM math.** All yields, drift %, tax dollar estimates, unrealized G/L, beta, and projections are calculated in Python and passed as facts. Gemini writes narrative and recommendations only.
2. **Pydantic schemas everywhere.** Every `ask_gemini()` call uses a `response_schema=YourModel`. Raw JSON string trust is forbidden.
3. **DRY_RUN gate.** All Sheet writes check `config.DRY_RUN` first. New agents default dry. Live flag is explicit `--live`.
4. **Single-batch gspread writes.** Never cell-by-cell. Archive-before-overwrite on any tab that gets a full refresh.
5. **SAFETY_PREAMBLE is auto-prepended** by `ask_gemini()`. Agent prompts must not duplicate it.
6. **`ask_gemini()` returns Pydantic instances** when `response_schema` is provided. Use `.model_dump()` before serialization.
7. **Agents never browse or fetch.** Python assembles all context from the composite bundle. Agents receive a dict; they do not call APIs.
8. **QACDS and CASH_MANUAL are excluded** from all AI analysis, beta, and allocation calculations.
9. **Small-step scaling** is encoded into every sizing recommendation. No binary in/out.
10. **Output lands in `AI_Suggested_Allocation` or `Agent_Outputs` sandbox only.** `Target_Allocation` is Bill's manual-only source.
11. **bundle_hash propagates.** Every agent response Pydantic model must include `composite_hash: str` for provenance linkage.
12. **PII guard.** Strip account numbers and account-level labels before any LLM context build.

---

## Prompt 5-A: Port Tax Intelligence Agent

### File to read first
```
utils/agents/tax_intelligence_agent.py   ← legacy source
```

### Task
Port `tax_intelligence_agent.py` to a bundle-aware CLI tool at `agents/tax_agent.py`, following the exact same pattern established in `agents/rebuy_analyst.py` (Phase 3). Integrate as `manager.py agent tax analyze`.

### Spec

**Pre-compute in Python (not LLM):**
- Unrealized G/L per position: `(current_price - cost_basis) × quantity`
- Holding period: days since acquisition (use `tax_treatment` field from Schwab bundle path; "unknown" on CSV path)
- Short-term vs long-term classification (< 365 days = short-term)
- TLH candidates: positions with unrealized loss > configurable threshold (default: -$500)
- Wash sale risk flag: repurchase within ±30 days of a sale in same ticker (surface from Transactions tab)
- Drift from `Target_Allocation`: `(current_weight - target_weight)` per asset class
- Rebalancing candidates: positions where `|drift| > config.REBALANCE_THRESHOLD_PCT` (default: 5%)

**Pass to Gemini as context facts:**
- TLH candidate table: ticker, unrealized_loss, holding_period_days, short_term_flag, wash_sale_risk
- Rebalancing candidates: ticker, current_weight, target_weight, drift_pct, direction (overweight/underweight)
- Total portfolio value and cash_weight
- Current tax year (derived from bundle timestamp)
- Composite bundle hash

**Pydantic output schema:**
```python
class TLHCandidate(BaseModel):
    ticker: str
    unrealized_loss_usd: float
    holding_period_days: int
    short_term: bool
    wash_sale_risk: bool
    tlh_rationale: str               # 1-2 sentence Gemini narrative
    suggested_replacement: str | None  # e.g. "VTI as wash-sale-safe SPY substitute"
    scale_step: str                  # "trim 20%" not "sell all"

class RebalanceAction(BaseModel):
    ticker: str
    direction: Literal["trim", "add"]
    drift_pct: float
    scale_step: str                  # small-step language required
    rationale: str

class TaxAgentOutput(BaseModel):
    composite_hash: str
    generated_at: str                # ISO timestamp
    tlh_candidates: list[TLHCandidate]
    rebalance_actions: list[RebalanceAction]
    summary_narrative: str           # 3-5 sentence overall narrative
    warnings: list[str]              # wash sale flags, year-end deadlines
```

**CLI wire-up:**
```bash
python manager.py agent tax analyze
python manager.py agent tax analyze --bundle bundles/composite_20260413_....json
python manager.py agent tax analyze --live   # writes to Agent_Outputs tab
```

**Sheet write target:** `Agent_Outputs` tab, rows tagged `agent=tax`, `run_ts=<ISO>`, `composite_hash=<hash>`. Archive previous rows before overwrite.

### Verification checklist
- [ ] Dry run produces valid Pydantic output with no Sheet writes
- [ ] `composite_hash` in output matches bundle file
- [ ] TLH candidates are pre-calculated in Python; Gemini output contains only narrative/rationale
- [ ] Wash sale flag surfaces correctly for positions with recent transactions
- [ ] `--live` writes to `Agent_Outputs`, not `Target_Allocation`
- [ ] CHANGELOG.md updated with `Status:` line

---

## Prompt 5-B: Port Valuation Agent

### File to read first
```
utils/agents/valuation_agent.py   ← legacy source
```

### Task
Port to `agents/valuation_agent.py`. Integrate as `manager.py agent valuation analyze`.

### Spec

**Pre-compute in Python (not LLM):**
- Forward P/E: `current_price / fwd_eps` — use FMP data via `fmp_client.get_earnings(ticker)`
- Trailing P/E: `current_price / ttm_eps`
- PEG ratio: `pe / earnings_growth_rate` (where available from FMP)
- 52-week range position: `(current_price - low_52w) / (high_52w - low_52w)` — use bundle's price history or Schwab `/pricehistory` data
- Distance from 52-week high: `(high_52w - current_price) / high_52w` as a % discount
- Earnings surprise history: last 2 quarters (FMP)
- Positions missing FMP data: log as enrichment_errors, skip from valuation table

**Pass to Gemini as context facts:**
- Valuation table: ticker, pe_fwd, pe_trailing, peg, price_vs_52w_range, discount_from_high, earnings_surprise_avg
- Bill's investment style tags from `vault/theses/<TICKER>_thesis.md` (GARP / Thematic / Boring Fundamentals / ETF)
- Composite hash

**Pydantic output schema:**
```python
class ValuationSignal(Literal["accumulate", "hold", "trim", "monitor"])

class PositionValuation(BaseModel):
    ticker: str
    pe_fwd: float | None
    peg: float | None
    discount_from_52w_high_pct: float
    signal: ValuationSignal
    accumulation_plan: str | None     # e.g. "Scale in 10% on each 5% pullback"
    rationale: str                    # 2-3 sentences max
    style_alignment: str              # maps to styles.json: GARP / Thematic / etc.

class ValuationAgentOutput(BaseModel):
    composite_hash: str
    generated_at: str
    positions: list[PositionValuation]
    top_accumulation_candidates: list[str]  # tickers only, ordered
    summary_narrative: str
    data_gaps: list[str]              # tickers where FMP data was missing
```

**CLI:**
```bash
python manager.py agent valuation analyze
python manager.py agent valuation analyze --tickers UNH,GOOG,AMZN  # subset mode
```

**Sheet write target:** `Agent_Outputs` tab, tagged `agent=valuation`.

### Verification checklist
- [ ] P/E, PEG ratios are Python-computed; Gemini only writes signal + rationale
- [ ] Missing FMP data logged in `data_gaps`, not silently dropped
- [ ] `accumulation_plan` uses small-step language (e.g., "10% on each 5% dip"), never "buy all"
- [ ] Style tags sourced from vault thesis files, not hallucinated
- [ ] `--tickers` subset mode works without breaking the full-run path

---

## Prompt 5-C: Port Concentration Hedger

### File to read first
```
utils/agents/concentration_hedger.py   ← legacy source (wired in Risk & Signals tab)
```

### Task
Port to `agents/concentration_hedger.py`. Integrate as `manager.py agent concentration analyze`.

### Spec

**Pre-compute in Python (not LLM):**
- Single-position weight: `position_value / total_portfolio_value` — flag if > `config.CONCENTRATION_SINGLE_THRESHOLD` (default: 8%)
- Sector exposure: sum weights by GICS sector — flag if > `config.CONCENTRATION_SECTOR_THRESHOLD` (default: 30%)
- Correlation pairs: top 20 positions, pairwise Pearson correlation from 1yr daily returns (reuse `utils/risk.py` logic)
- High-correlation pairs: flag if `|r| > 0.85`
- Portfolio beta: weighted beta (reuse existing calculation)
- Stress test scenarios: -10%, -20%, -30% market move impact (beta-adjusted)

**Pass to Gemini:**
- Concentration flags table: ticker, weight_pct, flag_type (single/sector), threshold_used
- High-correlation pairs: [ticker_a, ticker_b, correlation, combined_weight]
- Stress scenario results table (Python-computed dollar impacts)
- Portfolio beta
- Bill's stated rotation priority from thesis files (high/medium/low)
- Composite hash

**Pydantic output schema:**
```python
class ConcentrationFlag(BaseModel):
    flag_type: Literal["single_position", "sector", "correlation_pair"]
    tickers_involved: list[str]
    current_weight_pct: float
    threshold_pct: float
    severity: Literal["watch", "action"]
    hedge_suggestion: str             # e.g. "Trim UNH 15% over 3 steps; rotate to XLV for sector retention"
    scale_step: str

class ConcentrationAgentOutput(BaseModel):
    composite_hash: str
    generated_at: str
    portfolio_beta: float
    stress_scenarios: dict[str, float]  # {"market_down_10pct": -54200.0, ...}
    flags: list[ConcentrationFlag]
    summary_narrative: str
    priority_actions: list[str]        # ordered list of tickers to address first
```

**CLI:**
```bash
python manager.py agent concentration analyze
```

### Verification checklist
- [ ] Beta and stress dollar impacts are Python-computed, not LLM-estimated
- [ ] UNH (~9% weight) surfaces as a concentration flag
- [ ] Tech sector (GOOG, AMZN, NVDA, AMD, META, MSFT, DELL, AVGO, CRWD, SNPS, NOW, PANW) surfaces as sector concentration
- [ ] Hedge suggestions use small-step language
- [ ] Correlation pairs use `utils/risk.py` — do not reimplement

---

## Prompt 5-D: analyze-all Batch Orchestrator

### Files to read first
```
manager.py                          ← add new command here
agents/rebuy_analyst.py             ← existing pattern to follow
agents/tax_agent.py                 ← just built in 5-A
agents/valuation_agent.py           ← just built in 5-B
agents/concentration_hedger.py      ← just built in 5-C
utils/sheet_readers.py              ← for Agent_Outputs write
```

### Task
Add `manager.py analyze-all` command that:
1. Generates a fresh composite bundle (market + vault)
2. Runs Re-buy, Tax, Valuation, and Concentration agents in sequence
3. Collects all four Pydantic outputs
4. Writes everything to `Agent_Outputs` tab in a **single batch transaction**
5. Prints a Rich summary table to stdout

### Spec

**Command signature:**
```bash
python manager.py analyze-all                    # dry run, uses latest existing bundles
python manager.py analyze-all --fresh-bundle     # regenerates market + vault snapshots first
python manager.py analyze-all --live             # enables Sheet write
python manager.py analyze-all --agents rebuy,tax # run subset
```

**Execution flow:**
```
1. [if --fresh-bundle] run snapshot() + vault_snapshot() + bundle_composite()
2. Resolve latest composite bundle path
3. Run each agent function (not subprocess — direct Python call)
4. Collect outputs into AgentRunManifest Pydantic model
5. Serialize to single list of rows
6. [if --live] single batch write to Agent_Outputs tab with archive-before-overwrite
7. Print Rich summary table: agent | status | findings_count | top_action | composite_hash[:8]
8. Write run manifest JSON to bundles/runs/ directory (always, even in dry run)
```

**Pydantic manifest:**
```python
class AgentRunManifest(BaseModel):
    run_id: str                       # UUID
    run_ts: str                       # ISO
    composite_hash: str
    agents_run: list[str]
    rebuy_output: RebuyAgentOutput | None
    tax_output: TaxAgentOutput | None
    valuation_output: ValuationAgentOutput | None
    concentration_output: ConcentrationAgentOutput | None
    errors: list[str]                 # per-agent failures don't abort the run
    dry_run: bool
```

**Failure handling:** If one agent fails, log the error in `manifest.errors` and continue. The run is a partial success, not an abort. This is critical — a yfinance timeout on one ticker should not kill the full Sunday run.

**Agent_Outputs tab schema:**
```
run_id | run_ts | composite_hash | agent | signal_type | ticker | action | rationale | scale_step | severity
```
Each agent serializes its output as N rows in this format. Single `batch_update()` call for all rows across all agents.

### Verification checklist
- [ ] Dry run completes without any Sheet writes
- [ ] Single batch write (not one per agent)
- [ ] One agent failure does not abort others
- [ ] Run manifest JSON written to `bundles/runs/` in all modes
- [ ] Rich summary table shows per-agent status and top action
- [ ] `--agents` subset flag works

---

## Prompt 5-E: Sunday Headless Automation

### Files to read first
```
.github/workflows/podcast_sync.yml  ← existing workflow pattern to replicate
manager.py                          ← entry point
```

### Task
Add a GitHub Actions workflow `.github/workflows/weekly_analysis.yml` that runs `manager.py analyze-all --fresh-bundle --live` every Sunday at 6:00 PM EST (23:00 UTC). No browser, no Streamlit, fully headless.

### Spec

**Trigger:**
```yaml
on:
  schedule:
    - cron: '0 23 * * 0'   # Sunday 23:00 UTC = 6:00 PM EST
  workflow_dispatch:         # manual trigger for testing
```

**Environment:**
- Python 3.11
- Secrets required: `GCP_SERVICE_ACCOUNT_JSON`, `GEMINI_API_KEY` (ADC is primary locally; GitHub Actions uses service account JSON)
- No Streamlit secrets — use `GCP_SERVICE_ACCOUNT_JSON` env var (already supported by `sheet_readers.py` resolution chain)

**Steps:**
1. Checkout repo
2. Set up Python 3.11
3. Install dependencies: `pip install -r requirements.txt`
4. Write GCP credentials: `echo "$GCP_SERVICE_ACCOUNT_JSON" > /tmp/gcp_creds.json`
5. Set env: `GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp_creds.json`
6. Run: `python manager.py analyze-all --fresh-bundle --live`
7. Upload run manifest as workflow artifact (retain 30 days)
8. On failure: send notification (GitHub Actions default email is sufficient for now)

**Failure policy:** Workflow failure should NOT retry automatically — a failed Sunday run should surface visibly. Add `continue-on-error: false` explicitly.

**Data source note:** The `--fresh-bundle` flag runs `snapshot --source auto`, which tries Schwab API first. If the Schwab token has expired (7-day refresh window), the snapshot falls back to the most recent CSV in the repo fallback path. The CHANGELOG should document what happens on fallback (no crash, loud warning in logs, partial bundle used).

### Verification checklist
- [ ] `workflow_dispatch` trigger tested manually before enabling cron
- [ ] Credentials written to `/tmp/` not committed to repo
- [ ] `GCP_SERVICE_ACCOUNT_JSON` secret set in GitHub repo settings
- [ ] Run manifest uploaded as artifact
- [ ] Schwab token expiry handled gracefully (CSV fallback, not crash)
- [ ] Workflow does not import any Streamlit modules (would cause import error in Actions)

---

## Appendix A: Agent_Outputs Tab Schema

Add to `PORTFOLIO_SHEET_SCHEMA.md`:

```
Tab: Agent_Outputs
Write pattern: Archive-before-overwrite per analyze-all run
Fingerprint: run_id|agent|ticker (dedup within a run_id)

Columns:
  A: run_id          (UUID, groups all rows from one analyze-all invocation)
  B: run_ts          (ISO timestamp)
  C: composite_hash  (first 16 chars)
  D: agent           (rebuy | tax | valuation | concentration)
  E: signal_type     (tlh_candidate | rebalance | accumulate | trim | flag)
  F: ticker          (or "PORTFOLIO" for portfolio-level signals)
  G: action          (short imperative: "Trim 15% over 3 steps")
  H: rationale       (Gemini narrative, 1-3 sentences)
  I: scale_step      (explicit sizing language)
  J: severity        (info | watch | action)
  K: dry_run         (TRUE/FALSE — always record whether the run was live)
```

**Archive pattern:**
Before any write, copy all current rows to `Agent_Outputs_Archive` tab with `archived_at` timestamp prepended. Then overwrite `Agent_Outputs` with the new run.

---

## Appendix B: Config Constants to Add

Add to `config.py`:

```python
# Phase 5: Concentration thresholds
CONCENTRATION_SINGLE_THRESHOLD = 0.08    # 8% single-position flag
CONCENTRATION_SECTOR_THRESHOLD = 0.30    # 30% sector flag
CORRELATION_FLAG_THRESHOLD = 0.85        # |r| above this = high-correlation pair

# Phase 5: TLH threshold
TLH_LOSS_THRESHOLD_USD = -500.0          # minimum unrealized loss to surface as TLH candidate

# Phase 5: Rebalancing threshold
REBALANCE_THRESHOLD_PCT = 5.0            # drift % to trigger rebalance action

# Phase 5: Agent_Outputs tab
TAB_AGENT_OUTPUTS = "Agent_Outputs"
TAB_AGENT_OUTPUTS_ARCHIVE = "Agent_Outputs_Archive"
```

---

## Appendix C: manager.py Agent Registration Pattern

Each new agent is registered in `manager.py` by importing its Typer sub-app, matching the Phase 3 pattern:

```python
# Existing (Phase 3)
from agents.rebuy_analyst import app as rebuy_app
agent_app.add_typer(rebuy_app, name="rebuy")

# Add in Phase 5
from agents.tax_agent import app as tax_app
from agents.valuation_agent import app as valuation_app
from agents.concentration_hedger import app as concentration_app

agent_app.add_typer(tax_app, name="tax")
agent_app.add_typer(valuation_app, name="valuation")
agent_app.add_typer(concentration_app, name="concentration")
```

The `analyze-all` command is a top-level `manager.py` command (not nested under `agent`) since it orchestrates across agents:

```python
@app.command("analyze-all")
def analyze_all(
    fresh_bundle: bool = typer.Option(False, "--fresh-bundle"),
    agents: str = typer.Option("rebuy,tax,valuation,concentration", "--agents"),
    live: bool = typer.Option(False, "--live"),
):
    ...
```

---

## Appendix D: New Agents Added (April 2026)

Five additional files were reviewed and integrated into the build plan:
- `agents/rebuy_analyst.py` — COMPLETE. This is the gold standard pattern.
- `agents/framework_selector.py` — COMPLETE. Sophisticated pre-computation pipeline.
- `agents/macro_cycle_agent.py` — Structurally sound. One violation: yfinance ATR called live inside agent. Must fix before port (see Prompt 5-D).
- `agents/bangers_screener_agent.py` — Structurally sound. Two fixes needed: replace `append_rows` with `batch_update`, remove hardcoded `fp_col_idx = 12`.
- `VanTharp.py` — This is not an agent. It is a position sizing framework JSON. Route to `vault/frameworks/van_tharp_position_sizing.json` and wire into `framework_selector.py`.

**Updated build sequence:**

```
5-A  Tax agent              (legacy squad — per original prompts, unchanged)
5-B  Valuation agent        (legacy squad — per original prompts, unchanged)
5-C  Concentration hedger   (legacy squad — per original prompts, unchanged)
5-D  Macro-cycle agent      (new — fix yfinance violation first, then port)
5-E  100-Bagger screener    (new — create schema file, fix batch writes, then port)
5-F  Van Tharp framework    (move JSON to vault/frameworks/, wire into framework_selector)
5-G  analyze-all            (orchestrator — runs after all agents exist)
5-H  Sunday GitHub Actions  (automation — runs after analyze-all validated)
```

---

## Prompt 5-D: Port Macro-Cycle Agent

### Files to read first
```
agents/macro_cycle_agent.py         ← source to port
agents/rebuy_analyst.py             ← pattern to follow
agents/schemas/rebuy_schema.py      ← schema pattern to follow
```

### Pre-port fix required
Move ATR calculation OUT of the agent and into a bundle enrichment step:

1. Create `tasks/enrich_atr.py` with the `calculate_atr(ticker, period=14)` function currently in `macro_cycle_agent.py`. This script reads the latest market bundle, computes ATR for all non-cash positions via yfinance, and writes `calculated_technical_stops` back as an enriched field in the bundle JSON.
2. Update `manager.py snapshot` to optionally call this enrichment: `python manager.py snapshot --enrich-atr`.
3. The `macro_cycle_agent.py` port reads `composite["calculated_technical_stops"]` from the bundle. It NEVER calls yfinance directly.

### Schema to create: `agents/schemas/macro_cycle_schema.py`
```python
from pydantic import BaseModel, Field
from typing import Literal

class ATRStopLoss(BaseModel):
    ticker: str
    atr_14: float
    stop_loss_level: float
    current_price: float
    pct_from_stop: float              # (current_price - stop_loss_level) / current_price

class PositionCycleAnalysis(BaseModel):
    ticker: str
    paradigm_phase: Literal["installation", "frenzy", "synergy", "maturity", "unknown"]
    maturity_signals: list[str]
    stop_loss: ATRStopLoss | None
    final_recommendation: Literal["HOLD", "TRIM_25PCT", "TRIM_50PCT", "EXIT", "MONITOR"]
    rotation_priority: Literal["high", "medium", "low"]
    fundamental_reason_to_sell: str
    technical_trigger_summary: str

class MacroCycleResponse(BaseModel):
    bundle_hash: str
    analysis_timestamp_utc: str
    positions_analyzed: list[PositionCycleAnalysis]
    rotation_targets: list[str]       # tickers to rotate into (from vault research notes)
    portfolio_cycle_summary: str
```

### CLI
```bash
python manager.py agent macro analyze
python manager.py agent macro analyze --bundle bundles/composite_20260413_....json
python manager.py agent macro analyze --live
```

### Verification checklist
- [ ] `enrich_atr.py` task exists; ATR computed in Python before any LLM call
- [ ] Agent reads `calculated_technical_stops` from bundle, does NOT call yfinance
- [ ] `agents/schemas/macro_cycle_schema.py` exists and is importable
- [ ] `append_rows` replaced with `batch_update` + archive-before-overwrite
- [ ] Fingerprint uses `len(headers) - 1` not hardcoded col index
- [ ] DRY RUN produces valid Pydantic output with no Sheet writes

---

## Prompt 5-E: Port 100-Bagger Screener

### Files to read first
```
agents/bangers_screener_agent.py    ← source (use the more complete version)
agents/100bangers.py                ← earlier version for reference only
agents/rebuy_analyst.py             ← pattern to follow
```

### Pre-port fixes required
1. Replace `ws.append_rows(new_rows, ...)` with single `ws.batch_update(...)` call inside an archive-before-overwrite block (same as `rebuy_analyst.py` live write path).
2. Remove `fp_col_idx = 12` hardcoding. Use `len(headers) - 1` dynamically.
3. The `SYSTEM_INSTRUCTION` currently tells Gemini to "read `100_baggers_framework.json` from the vault bundle." Make sure this file exists at `vault/research/100_baggers_framework.json` or remove the reference. Missing vault files cause silent context gaps.

### Framework wiring
The Christopher Mayer quantitative gate (ROIC > 18%, Market Cap < $1B, Revenue Growth > 10%, Gross Margin > 50%) maps directly to `framework_selector.py` rules. Create `vault/frameworks/100_bagger_framework.json` with these as `required` rules. `framework_selector.py` will then pre-evaluate them against FMP fundamentals before the LLM call. The LLM only writes narrative rationale — it does NOT re-evaluate the thresholds.

### Schema file: `agents/schemas/bagger_schema.py`
Move `BaggerCandidate` and `BaggerScreenerResponse` from the inline agent file into a proper schema module, matching the `agents/schemas/rebuy_schema.py` pattern.

### CLI
```bash
python manager.py agent bagger analyze
python manager.py agent bagger analyze --live
```

### Verification checklist
- [ ] `vault/frameworks/100_bagger_framework.json` created with Christopher Mayer rules as `framework_selector.py` format
- [ ] `agents/schemas/bagger_schema.py` created (not inline in agent file)
- [ ] `append_rows` replaced with `batch_update` + archive
- [ ] Fingerprint col index dynamic, not hardcoded
- [ ] Framework quantitative gate evaluated in Python; Gemini writes narrative only

---

## Prompt 5-F: Van Tharp Position Sizing Framework

### Task
Van Tharp's rules (`VanTharp.py`) are a position sizing framework, not an agent. Move them to the vault and wire them into `framework_selector.py`.

### Steps
1. Rename and move: `VanTharp.py` → `vault/frameworks/van_tharp_position_sizing.json` (it's already JSON content)
2. Add required metadata fields so `framework_selector.py` can load it:
```json
{
  "framework_id": "van_tharp_position_sizing",
  "framework_version": "1.0",
  "reviewed_by_bill": true,
  "applies_to_asset_classes": ["equity", "etf"],
  "applies_to_styles": ["garp", "thematic", "boring", "speculative"],
  "description": "Van Tharp R-multiple position sizing: 1R = ATR × 3.0, size = (equity × risk_pct) / 1R",
  ...existing content...
}
```
3. Add a `van_tharp` rule set to the position sizing section of the Re-buy Analyst and future agents: when `framework_selector` selects Van Tharp, the pre-computation step calculates `1R`, `position_size_units`, and `trailing_stop` in Python using ATR from `calculated_technical_stops`. These values are passed as facts to the agent; Gemini never computes position sizes.
4. Add to CLAUDE.md: "Van Tharp position sizing framework lives in `vault/frameworks/van_tharp_position_sizing.json`. Agents read pre-computed R-multiples and position sizes from the bundle; they do NOT calculate these."

### Verification checklist
- [ ] `vault/frameworks/van_tharp_position_sizing.json` exists with correct schema metadata
- [ ] `framework_selector.py` can load and select it
- [ ] No Python file named `VanTharp.py` remains in agents/
- [ ] CLAUDE.md updated with routing note

---

## Appendix E: Handoff Instructions for Claude Code

When handing this file to Claude Code, use this session-start prompt:

```
Read phase5_agent_port_prompts.md in full before writing any code.
Then read the following files in order:
  1. CLAUDE.md
  2. CHANGELOG.md (last 3 entries)
  3. agents/rebuy_analyst.py        ← the exact pattern to replicate
  4. agents/framework_selector.py   ← already complete, do not modify
  5. utils/agents/tax_intelligence_agent.py  ← legacy source for 5-A
  6. config.py

Execute sub-phases in strict order: 5-A → 5-B → 5-C → 5-D → 5-E → 5-F → 5-G → 5-H → 5-I → 5-J.
Do not start the next sub-phase until the current one's verification checklist is complete.
Update CHANGELOG.md with a Status: line after each sub-phase.
DRY_RUN defaults true everywhere. Never write to Target_Allocation.
Agents never call yfinance, FMP, or any external API directly. Python pre-computes; LLM reasons.
```

---

## Prompt 5-E: Thesis Screener Agent (Gautam Baid Framework)

### Source file
```
agents/Thesis_Screener_Agent.py   ← already written, needs hardening only
```

### Assessment
This agent is structurally sound and nearly correct. It is primarily qualitative — reading earnings transcripts and thesis files from the vault bundle, evaluating management quality, and cross-referencing against exit conditions. Unlike the quantitative agents, there is minimal Python pre-computation needed. The Gemini reasoning IS the work here. The fixes are mechanical:

**Pre-port fixes (same pattern as other agents):**
1. Replace `ws.append_rows(new_rows, ...)` with `batch_update` + archive-before-overwrite
2. Replace hardcoded `fp_col_idx = 12` with `len(headers) - 1`
3. Move inline Pydantic schemas (`ManagementEvaluation`, `ThesisScreenerResponse`) to `agents/schemas/thesis_screener_schema.py`
4. Wire into `manager.py agent thesis analyze` using the standard Typer sub-app pattern
5. The `SYSTEM_INSTRUCTION` references `joys_of_compounding_framework.json` from the vault bundle — create `vault/frameworks/joys_of_compounding_framework.json` summarizing the Gautam Baid scoring rubric so the vault bundle actually contains it

### Why this fits Phase 5 (not Phase 6)
The thesis screener only needs vault data (thesis files + earnings transcripts) and market bundle (position metadata). No external API beyond what's already in the bundle. It is ready to port now.

### Vault dependency
The Behavioral Guardrails (WYSIATI, Disposition Effect, Action Bias, Anchoring, Envy, Hyperbolic Discounting) should live as structured rules in `vault/frameworks/joys_of_compounding_framework.json`. This makes them auditable and version-controlled, not just embedded in a system prompt string.

### CLI
```bash
python manager.py agent thesis analyze
python manager.py agent thesis analyze --ticker UNH
python manager.py agent thesis analyze --live
```

### Pydantic schema (move to `agents/schemas/thesis_screener_schema.py`)
The existing `ManagementEvaluation` and `ThesisScreenerResponse` classes are well-designed. Move them to the schema file unchanged. Add `composite_hash: str` to `ThesisScreenerResponse` for provenance.

### Verification checklist
- [ ] `agents/schemas/thesis_screener_schema.py` created with `composite_hash` added
- [ ] `vault/frameworks/joys_of_compounding_framework.json` created with Baid scoring rubric
- [ ] `append_rows` replaced with `batch_update` + archive
- [ ] Fingerprint col index dynamic
- [ ] `manager.py agent thesis analyze` wired and working
- [ ] Dry run produces valid output referencing thesis files from vault bundle
- [ ] `--ticker` single-position mode works

---

## Updated Full Build Sequence (all agents accounted for)

```
5-A  Tax agent              ← legacy port
5-B  Valuation agent        ← legacy port
5-C  Concentration hedger   ← legacy port
5-D  Macro-cycle agent      ← new (fix yfinance violation first)
5-E  Thesis screener        ← new (mechanical hardening only)
5-F  100-Bagger screener    ← new (create schema file, fix batch writes)
5-G  Van Tharp framework    ← vault/frameworks/ routing
5-H  analyze-all            ← orchestrator (runs 5-A through 5-F)
5-I  Sunday GitHub Actions  ← automation
```

---

## Phase 6+ Deferred Items (Do Not Build Now)

These are explicitly out of scope for Phase 5. Log them but do not implement:

- **Options Agent** — structurally correct and already written (`agents/Options_agent.py`). Blocked on one hard dependency: requires `options_chains` data from the Schwab `/chains` endpoint, which is not yet wired into the bundle pipeline. The agent itself already checks for this (`if "options_chains" not in composite.get("market_data", {})`). Pre-port fixes to do when unblocked: (1) replace `append_rows` with `batch_update` + archive, (2) replace hardcoded `fp_col_idx = 12`, (3) move schemas to `agents/schemas/options_schema.py`, (4) create `vault/frameworks/natenberg_options_framework.json`. The Relative Volatility Rank (RVR) computation — ranking IV percentile 1–10 against 52-week IV history — must be pre-computed in Python from Schwab chain data before the LLM call. Greeks (delta, theta, gamma) come from the chain data, not from Gemini. Expected value break-even math is Python. Gemini writes narrative and final recommendation only.
- **Macro Monitor agent port** — depends on FRED API integration not yet wired to bundle
- **Grand Strategist agent** — requires RE Dashboard cross-reference; deferred until unified net worth view is scoped
- **Looker Studio dashboard** — Phase 6; Sheets is already the readable surface
- **Trade_Log rotation tracking** — important but separate from agent kit; spec separately
- **STAX sync (`tasks/stax_sync.py`)** — prompt file exists; execute after Phase 5 is stable
