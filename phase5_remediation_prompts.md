# Phase 5 Remediation — Prompt File
**Investment Portfolio Manager | Post-Test-Run Fixes**
*Generated: April 2026 | Handoff target: Claude Code*
*Test run date: 2026-04-13 | 42/46 tests passing*

---

## Session Start (Run First Every Session)

```
Read CLAUDE.md, CHANGELOG.md (last 5 entries), and agents/rebuy_analyst.py.
Confirm: which agents are registered in manager.py, what the current composite bundle
hash is in bundles/, and which tests are still failing per tasks/todo.md.
Do not write any code until you have confirmed these three things.
```

---

## Overview: Four Fixes, Strict Order

Execute in this sequence. Each fix has a verification checkpoint — do not move to the
next fix until the checkpoint passes. All fixes are DRY_RUN safe unless explicitly
noted.

```
Fix 1 — Chunked execution (Blocker 1, T2.1, T10.1)       ~3 hours
Fix 2 — Sector grouping in concentration hedger (T5.2)    ~30 minutes
Fix 3 — Correlation pairs coverage (T5.4)                 ~45 minutes
Fix 4 — FMP cache + Schwab quote fallback (T4.1 quality)  ~1 hour
Fix 5 — Van Tharp wiring (T9.3, deferred but low effort)  ~45 minutes
```

Fix 4 is quality-of-life (not a test blocker) but is included here because the
conversation resolved the architecture. Fix 5 is the one deferred item from the
test run.

---

## Fix 1: Chunked Execution for Full-Portfolio Agents

**Fixes:** T2.1 (rebuy dry run), T10.1 (analyze-all full portfolio)
**Root cause:** Gemini Flash output token budget exceeded on 46+ positions.
Single-ticker mode works; full portfolio fails with Pydantic parse error.
**Agents affected:** `rebuy_analyst`, `macro_cycle_agent`, `thesis_screener`,
`bagger_screener`

### Prompt 1-A: Create the shared chunking utility

```
Read agents/rebuy_analyst.py in full before writing any code.
Pay close attention to:
  - The ask_gemini_composite call signature (lines ~234-243)
  - The user_prompt construction (lines ~218-231)
  - The framework_validations dict (pre-computed before the LLM call)
  - The post-LLM framework_validation override loop (lines ~251-261)

Create a new file: agents/utils/chunked_analysis.py

The file must contain exactly one function: run_chunked_analysis()

Here is the complete, correct implementation — copy it exactly, do not
simplify or restructure it:

```python
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CHUNK_SIZE = 15
INTER_CHUNK_SLEEP = 2.0  # seconds between chunks — Gemini rate limit guard


def run_chunked_analysis(
    investable: list[dict],
    bundle_path: Path,
    composite_hash: str,
    build_user_prompt_fn,
    response_schema,
    system_instruction: str,
    portfolio_context: dict,
    ask_gemini_fn,
) -> tuple[list, list, list, list[str]]:
    """
    Splits investable positions into chunks of CHUNK_SIZE, runs each through
    Gemini, and merges the results.

    Returns: (all_candidates, all_excluded, all_coverage_warnings, chunk_errors)

    CRITICAL: composite_hash is the hash from the ORIGINAL bundle, passed in by
    the caller. It is NEVER taken from a chunk response. This preserves provenance.
    """
    chunks = [
        investable[i : i + CHUNK_SIZE]
        for i in range(0, len(investable), CHUNK_SIZE)
    ]

    logger.info(
        "Chunked execution: %d positions → %d chunk(s) of ≤%d",
        len(investable), len(chunks), CHUNK_SIZE,
    )

    all_candidates = []
    all_excluded = []
    all_warnings = []
    chunk_errors = []

    for idx, chunk in enumerate(chunks):
        tickers_in_chunk = [p["ticker"] for p in chunk]
        logger.info("Chunk %d/%d: %s", idx + 1, len(chunks), tickers_in_chunk)

        try:
            user_prompt = build_user_prompt_fn(chunk, portfolio_context)
            result = ask_gemini_fn(
                prompt=user_prompt,
                composite_bundle_path=bundle_path,
                response_schema=response_schema,
                system_instruction=system_instruction,
                max_tokens=8000,
            )

            if result is None:
                msg = f"Chunk {idx + 1}/{len(chunks)} ({tickers_in_chunk}): Gemini returned None"
                logger.warning(msg)
                chunk_errors.append(msg)
            else:
                if hasattr(result, "candidates") and result.candidates:
                    all_candidates.extend(result.candidates)
                if hasattr(result, "excluded_tickers") and result.excluded_tickers:
                    all_excluded.extend(result.excluded_tickers)
                if hasattr(result, "coverage_warnings") and result.coverage_warnings:
                    all_warnings.extend(result.coverage_warnings)

        except Exception as e:
            msg = f"Chunk {idx + 1}/{len(chunks)} failed: {e}"
            logger.error(msg, exc_info=True)
            chunk_errors.append(msg)

        if idx < len(chunks) - 1:
            time.sleep(INTER_CHUNK_SLEEP)

    return all_candidates, all_excluded, all_warnings, chunk_errors
```

Also create agents/utils/__init__.py (empty file) if it does not exist.

Verification:
  python -c "from agents.utils.chunked_analysis import run_chunked_analysis; print('OK')"
Must print: OK
```

### Prompt 1-B: Wire chunking into rebuy_analyst.py

```
Read agents/rebuy_analyst.py in full.
Read agents/utils/chunked_analysis.py (just created).
Read agents/schemas/rebuy_schema.py for the RebuyAnalystResponse field names.

Make the following surgical changes to agents/rebuy_analyst.py.
Do NOT modify the Rich table, local file output, Sheet write path, or
the framework_validation override loop.

CHANGE 1: Add import at the top of the file (after existing imports):
  from agents.utils.chunked_analysis import run_chunked_analysis
  from datetime import datetime, timezone

CHANGE 2: Add this helper function BEFORE the analyze() command function
(not inside it):

  def _build_rebuy_chunk_prompt(chunk: list[dict], ctx: dict) -> str:
      """Builds the user prompt for a single chunk of positions."""
      import json
      framework_section = ctx.get("framework_section", "")
      return (
          f"Analyze the following {len(chunk)} position(s) "
          f"for re-buy / add candidates.\n\n"
          f"Portfolio total value: ${ctx['total_value']:,.2f}\n"
          f"Cash (strategic dry powder): ${ctx['cash_manual']:,.2f}\n"
          f"Cash as % of portfolio: "
          f"{ctx['cash_manual'] / ctx['total_value'] * 100:.1f}%\n\n"
          f"Positions:\n{json.dumps(chunk, default=str, indent=2)}\n\n"
          f"Thesis files present for: {ctx['thesis_map_keys']}\n"
          f"Thesis files missing for: {ctx['coverage_warnings']}\n"
          f"{framework_section}\n"
          "Evaluate each position against its thesis file (if present) "
          "and the four investment styles. Produce a RebuyAnalystResponse "
          "JSON object."
      )

CHANGE 3: In the analyze() function, replace the single ask_gemini_composite
call (currently around lines 234-243) and the result = ... assignment with
the following block. Keep everything before (the user_prompt / framework_section
build) and everything after (the framework_validation override loop) UNCHANGED:

  # --- CHUNKED EXECUTION (replaces single ask_gemini_composite call) ---
  console.print(f"[cyan]Calling Gemini on {len(investable)} positions "
                f"(chunked, {CHUNK_SIZE} per batch)...[/]")

  portfolio_context = {
      "total_value": market["total_value"],
      "cash_manual": market["cash_manual"],
      "thesis_map_keys": list(thesis_map.keys()),
      "coverage_warnings": coverage_warnings,
      "framework_section": framework_section,
  }

  from agents.utils.chunked_analysis import CHUNK_SIZE
  with console.status("[cyan]Analyzing in chunks..."):
      all_candidates, all_excluded, all_warnings, chunk_errors = run_chunked_analysis(
          investable=investable,
          bundle_path=bundle_path,
          composite_hash=composite["composite_hash"],
          build_user_prompt_fn=_build_rebuy_chunk_prompt,
          response_schema=RebuyAnalystResponse,
          system_instruction=system_prompt_text,
          portfolio_context=portfolio_context,
          ask_gemini_fn=ask_gemini_composite,
      )

  if not all_candidates and chunk_errors:
      console.print("[red]ERROR: All chunks failed. Check API logs.[/]")
      for err in chunk_errors:
          console.print(f"  [red]• {err}[/]")
      raise typer.Exit(1)

  # Reconstruct result with ORIGINAL composite hash (never from a chunk response)
  result = RebuyAnalystResponse(
      bundle_hash=composite["composite_hash"],
      analysis_timestamp_utc=datetime.now(timezone.utc).isoformat(),
      candidates=all_candidates,
      excluded_tickers=list(set(excluded_tickers + all_excluded)),
      coverage_warnings=list(set(coverage_warnings + all_warnings)),
      analyst_notes=(
          f"Chunked: {len(investable)} positions across "
          f"{-(-len(investable) // CHUNK_SIZE)} batch(es). "
          f"Errors: {', '.join(chunk_errors) if chunk_errors else 'none'}"
      ),
  )
  # --- END CHUNKED EXECUTION ---

  # (The framework_validation override loop that follows is UNCHANGED)

IMPORTANT: The variable `excluded_tickers` is already computed earlier in the
function (it's the list of CASH_TICKERS positions). Keep that line. The merge
above combines it with any chunk-level excluded tickers.

Verification:
  python manager.py agent rebuy analyze --ticker UNH
Must succeed (single-ticker skips chunking but still validates the import).

  python manager.py agent rebuy analyze
Must complete on full portfolio without Pydantic parse errors.
Check: bundles/rebuy_output_<hash>.json exists and candidates list is non-empty.
```

### Prompt 1-C: Wire chunking into macro_cycle_agent.py

```
Read agents/macro_cycle_agent.py in full.
Read agents/utils/chunked_analysis.py.

Apply the same chunking pattern as in rebuy_analyst.py.

Key differences for macro_cycle_agent:
  - The response schema is MacroCycleResponse (from agents/schemas/macro_cycle_schema.py)
  - The list field to merge is `positions_analyzed` (not `candidates`)
  - The portfolio-level fields are `rotation_targets` and `portfolio_cycle_summary`
    — these only exist on the first successful chunk's response; preserve the first
    non-None value for portfolio_cycle_summary and merge all rotation_targets lists
  - ATR stops are already pre-computed in composite["calculated_technical_stops"]
    and should be included in the portfolio_context dict passed to the prompt builder

Add the helper function _build_macro_chunk_prompt() following the same pattern
as _build_rebuy_chunk_prompt() in rebuy_analyst.py.

For the result reconstruction, the merge logic for positions_analyzed is:
  result = MacroCycleResponse(
      bundle_hash=composite["composite_hash"],
      analysis_timestamp_utc=...,
      positions_analyzed=all_positions_analyzed,  # merged list
      rotation_targets=list(set(all_rotation_targets)),  # deduplicated
      portfolio_cycle_summary=first_portfolio_summary or "See individual position analyses.",
  )

Verification:
  python manager.py agent macro analyze
Must complete on full portfolio without truncation errors.
```

### Prompt 1-D: Wire chunking into thesis_screener.py and bagger_screener.py

```
Read agents/thesis_screener.py and agents/bagger_screener.py in full.
Read agents/utils/chunked_analysis.py.

Apply the same chunking pattern to both files.

For thesis_screener.py:
  - Merge field: `evaluations` (list of ManagementEvaluation)
  - No portfolio-level summary fields to merge

For bagger_screener.py:
  - Merge fields: `strong_buy_candidates`, `watchlist_candidates` (both lists)
  - `data_gaps` should be merged and deduplicated across all chunks

For both, follow the exact same helper function pattern established in rebuy_analyst.py.

Verification:
  python manager.py agent thesis analyze
  python manager.py agent bagger analyze
Both must complete on full portfolio without parse errors.

Then run the full orchestrator:
  python manager.py analyze-all

PASS if: Rich summary table shows all agents completing (status = complete or partial,
never hanging). Manifest written to bundles/runs/.

Update CHANGELOG.md with a new entry:
  ## [Unreleased] — Phase 5 Remediation: Chunked Execution
  ### Changed
  - agents/utils/chunked_analysis.py — new shared utility
  - agents/rebuy_analyst.py, agents/macro_cycle_agent.py,
    agents/thesis_screener.py, agents/bagger_screener.py — chunked execution,
    CHUNK_SIZE=15, composite_hash provenance preserved from original bundle
  Status: Full portfolio (46+ positions) completes without Pydantic parse errors.
```

---

## Fix 2: Concentration Hedger — Sector Grouping

**Fixes:** T5.2 (tech sector concentration flag not firing)
**Root cause:** `agents/concentration_hedger.py` groups positions by `asset_class`
field (values: "Equity", "ETF", "Fixed Income") instead of GICS `sector` field
(values: "Technology", "Healthcare", "Energy", etc.).
**Expected result after fix:** Tech cluster fires as ~35-40% sector weight, well
over the 30% threshold.

### Prompt 2-A: Fix sector grouping

```
Read agents/concentration_hedger.py in full.

Find the section that computes sector concentration — look for groupby("asset_class")
or equivalent logic that aggregates position weights by category.

Confirm by reading the market bundle JSON what field names are available on each
position. The yfinance-enriched sector field is present as `sector` (GICS sector
string, e.g., "Technology", "Healthcare", "Energy", "Financials").

Make this targeted change: in the sector aggregation calculation, change the
grouping key from `asset_class` to `sector`.

There is one nuance to handle: ETFs do not have a `sector` field from yfinance
(broad ETFs return None or ""). For ETFs with a null/empty sector, use the
following fallback mapping before the groupby:

  SECTOR_FALLBACK = {
      "QQQM": "Technology",    # Nasdaq 100 — predominantly tech
      "IGV":  "Technology",    # Software ETF
      "XBI":  "Health Care",
      "XLV":  "Health Care",
      "XLF":  "Financials",
      "IFRA": "Industrials",
      "VEA":  "International",
      "VEU":  "International",
      "EEM":  "International",
      "EWZ":  "International",
      "EFG":  "International",
      "JPIE": "Fixed Income",
      "QACDS":"Cash",
  }

  # Apply fallback before groupby
  def resolve_sector(pos: dict) -> str:
      if pos.get("sector") and pos["sector"] not in ("", "N/A", None):
          return pos["sector"]
      return SECTOR_FALLBACK.get(pos["ticker"], "Other")

The groupby should then use resolve_sector(pos) for each position.

Do NOT change the threshold value (config.CONCENTRATION_SECTOR_THRESHOLD = 0.30),
flag type, severity logic, or any downstream processing.

Verification:
  python manager.py agent concentration analyze

PASS if:
  - A ConcentrationFlag appears for "Technology" sector
  - current_weight_pct for Technology is > 30.0
  - tickers_involved includes GOOG, AMZN, and at least 4 other tech names
  - UNH is NOT in the Technology sector flag (it belongs in Health Care)
  - A separate ConcentrationFlag appears for UNH as single_position (T5.1 still passes)

Update CHANGELOG.md:
  ## [Unreleased] — Phase 5 Remediation: Concentration Hedger Sector Fix
  ### Changed
  - agents/concentration_hedger.py — sector grouping now uses GICS sector field
    with ETF fallback mapping; was incorrectly grouping by asset_class
  Status: T5.2 now passes. Tech cluster correctly identified as ~35%+ sector weight.
```

---

## Fix 3: Correlation Pairs — Coverage Gap

**Fixes:** T5.4 (AMZN/GOOG correlation pair not surfaced)
**Root cause:** Likely one of: (a) 1-year yfinance download producing NaN rows for
some tickers which excludes them from the matrix, or (b) top-N position selection
threshold excluding mid-weight positions.
**Diagnostic step required before fix.**

### Prompt 3-A: Diagnose then fix

```
Read agents/concentration_hedger.py — specifically the correlation matrix
computation section.

STEP 1 — Diagnose: Run this diagnostic before touching any code:

  python -c "
  import yfinance as yf
  import pandas as pd
  tickers = ['GOOG', 'AMZN', 'NVDA', 'AMD', 'CRWD', 'PANW']
  df = yf.download(tickers, period='1y', interval='1d', progress=False)['Close']
  print('Shape:', df.shape)
  print('NaN count per ticker:')
  print(df.isna().sum())
  print()
  returns = df.pct_change().dropna()
  print('Returns rows after dropna:', len(returns))
  print('Correlation matrix:')
  print(returns.corr().round(2))
  "

Report what you find. Expected: GOOG and AMZN correlation > 0.80.

STEP 2 — Fix based on diagnosis:

CASE A (most likely): NaN rows are causing dropna() to exclude some tickers.
  Fix: Change the dropna() call to drop rows where ALL values are NaN, not ANY:
    returns = df.pct_change().dropna(how='all')
  Then for the correlation calculation, compute pairwise correlation using
  min_periods=100 to require at least 100 common data points:
    corr_matrix = returns.corr(min_periods=100)
  Tickers with < 100 data points in common will show NaN in the matrix —
  skip NaN pairs rather than treating them as zero correlation.

CASE B: Top-N selection is excluding AMZN or GOOG.
  Fix: Ensure the top-N selection for the correlation matrix is based on
  market value, not weight, and uses at least the top 20 positions
  (or all positions if the portfolio has fewer than 20 non-cash positions).
  AMZN at $25K and GOOG at $27K are both firmly in the top 10 by value.

Apply whichever fix (or both if both issues are present).

Verification:
  python manager.py agent concentration analyze

PASS if:
  - At least 2 of these 3 pairs appear in flags with flag_type = "correlation_pair":
      AMZN/GOOG, AMD/NVDA, CRWD/PANW
  - All correlation values are between -1.0 and 1.0 (never NaN in the output)
  - combined_weight for each pair is the sum of both positions' weights

Update CHANGELOG.md:
  ## [Unreleased] — Phase 5 Remediation: Correlation Matrix Fix
  ### Changed
  - agents/concentration_hedger.py — correlation uses pairwise min_periods=100;
    dropna(how='all') prevents NaN contamination from recent IPOs
  Status: T5.4 now passes. AMZN/GOOG and AMD/NVDA correlation pairs surfaced.
```

---

## Fix 4: FMP Cache + Schwab Quote Fallback

**Fixes:** T4.1 quality improvement (FMP 402 rate-limit causing null P/E values)
**Not a test blocker** — valuation agent already handles missing data gracefully —
but FMP calls on every `analyze-all` run will exhaust the free tier over time.
**Two-part fix:** (1) local JSON cache with 7-day TTL, (2) use Schwab quote data
for the fields it already provides.

### Prompt 4-A: Add FMP local cache

```
Read utils/fmp_client.py in full.

Add a file-based cache with a 7-day TTL. The cache lives in data/fmp_cache/
(create the directory if it doesn't exist; add data/fmp_cache/ to .gitignore).

Add this caching wrapper around the FMP API call in get_fundamentals():

  import json
  from pathlib import Path
  from datetime import datetime, timedelta

  FMP_CACHE_DIR = Path("data/fmp_cache")
  FMP_CACHE_TTL_DAYS = 7

  def _get_fmp_cached(ticker: str) -> dict | None:
      """
      Returns cached FMP data for ticker if < 7 days old, else calls FMP.
      Returns None if FMP call fails (rate limit, network error, etc.).
      """
      FMP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
      cache_path = FMP_CACHE_DIR / f"{ticker.upper()}.json"

      # Check cache freshness
      if cache_path.exists():
          age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
          if age < timedelta(days=FMP_CACHE_TTL_DAYS):
              try:
                  return json.loads(cache_path.read_text())
              except Exception:
                  pass  # corrupted cache — fall through to API call

      # Cache miss or stale — call FMP
      try:
          data = _call_fmp_api(ticker)  # your existing FMP call logic
          if data:
              cache_path.write_text(json.dumps(data))
          return data
      except Exception as e:
          logger.warning("FMP API call failed for %s: %s", ticker, e)
          return None

Refactor get_fundamentals() to call _get_fmp_cached() instead of calling the
FMP API directly.

Ensure the cache handles the 402 Payment Required response gracefully — it
should log a warning and return None (not raise), exactly as today.

Add to .gitignore:
  data/fmp_cache/

Verification:
  # First call — hits FMP (or returns None on 402)
  python -c "from utils.fmp_client import get_fundamentals; print(get_fundamentals('AAPL'))"

  # Second call immediately after — must hit cache (verify by checking file timestamp)
  python -c "
  import time; time.sleep(1)
  from utils.fmp_client import get_fundamentals
  from pathlib import Path
  result = get_fundamentals('AAPL')
  cache = Path('data/fmp_cache/AAPL.json')
  print('Cache exists:', cache.exists())
  print('Cache age (seconds):', time.time() - cache.stat().st_mtime if cache.exists() else 'N/A')
  "
```

### Prompt 4-B: Wire Schwab quote data as tier-1 source for fundamentals

```
Read utils/fmp_client.py after the cache changes above.
Read core/bundle.py to understand what fields are on each position in the
market bundle (look for the quote enrichment section from Schwab).

The goal: for fields that Schwab's /marketdata/v1/quotes already provides,
use the bundle data instead of calling FMP. This reduces FMP calls by ~50%.

Modify get_fundamentals() to accept an optional bundle_quote parameter:

  def get_fundamentals(ticker: str, bundle_quote: dict = None) -> dict:
      result = {}

      # Tier 1: Schwab quote fields (already in the market bundle, zero API cost)
      if bundle_quote:
          result["pe_trailing"]  = bundle_quote.get("peRatio")
          result["eps_ttm"]      = bundle_quote.get("eps")
          result["market_cap"]   = bundle_quote.get("marketCap")
          result["div_yield"]    = bundle_quote.get("dividendYield")
          result["high_52w"]     = bundle_quote.get("52WeekHigh")
          result["low_52w"]      = bundle_quote.get("52WeekLow")

      # Tier 2: FMP for fields Schwab doesn't have (via local cache)
      fmp_data = _get_fmp_cached(ticker)
      if fmp_data:
          result["pe_fwd"]              = fmp_data.get("forwardPE")
          result["peg"]                 = fmp_data.get("pegRatio")
          result["revenue_growth_3yr"]  = fmp_data.get("revenueGrowth")
          result["gross_margin"]        = fmp_data.get("grossProfitMargin")
          result["roic"]                = fmp_data.get("returnOnInvestedCapital")

      return result if result else None

Then in agents/valuation_agent.py and agents/bagger_screener.py, update the
get_fundamentals() call to pass the position's quote data from the bundle:

  # In the pre-computation loop, find the Schwab quote for this ticker
  bundle_quotes = {
      q["ticker"]: q
      for q in composite.get("market_data", {}).get("quotes", [])
  }
  fundamentals = get_fundamentals(ticker, bundle_quote=bundle_quotes.get(ticker))

Note: if the bundle uses a different path to quotes (e.g., composite["quotes"]
or market["quotes"]), read the actual bundle JSON first to confirm the field path
before writing the code.

Verification:
  python manager.py agent valuation analyze --tickers AMZN,GOOG

PASS if:
  - pe_trailing is populated from Schwab data (not null) for both tickers
  - pe_fwd is populated from FMP cache if available, null if FMP is rate-limited
  - data_gaps list contains only tickers where BOTH Schwab AND FMP returned nothing

Update CHANGELOG.md:
  ## [Unreleased] — Phase 5 Remediation: FMP Cache + Schwab Quote Fallback
  ### Changed
  - utils/fmp_client.py — 7-day local JSON cache in data/fmp_cache/;
    get_fundamentals() now accepts bundle_quote for Schwab-sourced fields
  - agents/valuation_agent.py, agents/bagger_screener.py — pass bundle quotes
    to get_fundamentals() as tier-1 source
  Status: FMP calls reduced ~50%. Trailing P/E, EPS, market cap sourced from
  Schwab quotes already in bundle. FMP only called for forward P/E, PEG, ROIC.
```

---

## Fix 5: Van Tharp Position Sizing — Wire into Agents

**Fixes:** T9.3 (`compute_van_tharp_sizing()` exists but not called by any agent)
**Status:** compute_van_tharp_sizing() was verified correct (640 units / $7.50 1R
on test case). Needs to run in the pre-computation step of rebuy_analyst.py and
add_candidate_analyst.py before any LLM call.

### Prompt 5-A: Wire Van Tharp into rebuy_analyst pre-computation

```
Read agents/rebuy_analyst.py in full.
Read agents/framework_selector.py — specifically compute_van_tharp_sizing().
Read the composite bundle JSON to confirm the field path for
calculated_technical_stops (e.g., composite["calculated_technical_stops"]).

In agents/rebuy_analyst.py, add Van Tharp sizing to the pre-computation loop
that already runs after the framework_validations loop.

Add this block AFTER the existing framework_validations loop (around line 188),
BEFORE the user_prompt construction:

  # Van Tharp position sizing — pre-computed, never LLM-derived
  from agents.framework_selector import compute_van_tharp_sizing
  van_tharp_stops = {
      s["ticker"]: s
      for s in composite.get("calculated_technical_stops", [])
  }
  van_tharp_sizing: dict[str, dict] = {}

  for pos in investable:
      t = pos["ticker"]
      atr_data = van_tharp_stops.get(t)
      if atr_data and atr_data.get("atr_14") and atr_data["atr_14"] > 0:
          sizing = compute_van_tharp_sizing(
              entry_price=pos.get("current_price", 0.0),
              atr_14=atr_data["atr_14"],
              portfolio_equity=market["total_value"],
          )
          if sizing.get("sizing_valid"):
              van_tharp_sizing[t] = sizing
              logger.info("Van Tharp sizing for %s: %s units, 1R=$%.2f",
                          t, sizing.get("position_size_units"),
                          sizing.get("per_share_risk_1r", 0))
          else:
              logger.debug("Van Tharp sizing invalid for %s: %s",
                           t, sizing.get("sizing_note"))

  # Inject Van Tharp sizing into each position dict for the LLM context
  for pos in investable:
      if pos["ticker"] in van_tharp_sizing:
          pos["van_tharp_sizing"] = van_tharp_sizing[pos["ticker"]]

This ensures each position dict passed to the LLM contains pre-computed fields:
  position_size_units, stop_loss_price, per_share_risk_1r, r_multiple_2r, r_multiple_3r

The LLM sees these as facts in the bundle and references them in sizing rationale.
It does NOT compute them.

Verification:
  python manager.py agent rebuy analyze --ticker UNH

PASS if:
  - console output shows "Van Tharp sizing for UNH: X units, 1R=$Y.YY"
  - bundles/rebuy_output_<hash>.json contains van_tharp_sizing field on UNH's
    position data
  - No Python exceptions

Update CLAUDE.md (append to the Vault Frameworks section):
  Van Tharp sizing is pre-computed in rebuy_analyst.py and add_candidate_analyst.py
  before any LLM call. Agents cite sizing values from the bundle — they never
  calculate position sizes themselves.

Update CHANGELOG.md:
  ## [Unreleased] — Phase 5 Remediation: Van Tharp Sizing Wired
  ### Changed
  - agents/rebuy_analyst.py — compute_van_tharp_sizing() called in pre-computation
    loop; sizing injected into each position dict before LLM context build
  Status: T9.3 now passes. Position size, stop loss, and 1R/2R/3R targets
  pre-computed in Python and visible to LLM as bundle facts.
```

---

## Post-Remediation Verification

Run this after all five fixes are complete:

### Full test re-run prompt for Gemini CLI

```bash
gemini --all-files -p "
Run the following targeted re-tests from phase5_test_suite.md.
These are the tests that were failing on the 2026-04-13 run:

T2.1: Run python manager.py agent rebuy analyze (full portfolio, not single ticker).
      PASS if: completes without Pydantic parse error, candidates list is non-empty.

T5.2: Run python manager.py agent concentration analyze.
      PASS if: ConcentrationFlag exists for Technology sector with weight > 30%.

T5.4: Run python manager.py agent concentration analyze.
      PASS if: At least 2 of (AMZN/GOOG, AMD/NVDA, CRWD/PANW) appear as correlation pairs.

T9.3: Run python manager.py agent rebuy analyze --ticker UNH.
      PASS if: van_tharp_sizing field present in bundles/rebuy_output_<hash>.json for UNH.

T10.1: Run python manager.py analyze-all.
       PASS if: All 7 agents complete (no hanging), manifest written to bundles/runs/.

Also confirm these previously-passing tests have not regressed:
T1.4: CASH_MANUAL excluded from investable positions.
T3.5: Target_Allocation unchanged after --live run.
T12.3: DRY_RUN gate present on all writes (grep check).
T12.5: No binary entry/exit language in agent outputs.

Report: PASS/FAIL for each test, with specific evidence.
"
```

### Final commit sequence

```bash
git add agents/utils/__init__.py
git add agents/utils/chunked_analysis.py
git add agents/rebuy_analyst.py
git add agents/macro_cycle_agent.py
git add agents/thesis_screener.py
git add agents/bagger_screener.py
git add agents/concentration_hedger.py
git add agents/valuation_agent.py
git add agents/bagger_screener.py
git add utils/fmp_client.py
git add CHANGELOG.md CLAUDE.md
git add .gitignore
git commit -m "fix: Phase 5 remediation — chunked execution, sector grouping, correlation, FMP cache, Van Tharp wiring"
```

---

## What This Unlocks for Phase 6

Once all five fixes pass, the system is in this state:

- Full portfolio analysis (46+ positions) runs reliably end-to-end
- Tech sector concentration surfaces correctly every Sunday run
- Correlation pairs are accurate across all major holdings
- FMP calls are reduced to once-per-ticker-per-week via local cache
- Van Tharp sizing appears as pre-computed facts in agent reasoning

Phase 6 can then begin cleanly. The known Phase 6 work from the conversation:
- Options Agent unblock (requires Schwab /chains endpoint data in bundle)
- Macro Monitor port (requires FRED API wired into bundle enrichment)
- Looker Studio dashboard (Sheets is already the readable surface — connect directly)
- Trade_Log rotation tracking (linked sell-buy pairs as the unit of analysis)
- Grand Strategist (requires RE Dashboard cross-reference for unified net worth)
