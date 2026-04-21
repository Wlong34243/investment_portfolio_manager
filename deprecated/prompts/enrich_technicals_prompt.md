# Build Prompt: `tasks/enrich_technicals.py`
## Technical Indicators Enrichment — Murphy TA Signal Layer

**Build order:** Run after `enrich_atr.py` is already wired. This is a parallel
enrichment task that follows the exact same in-place composite bundle injection
pattern. Read `tasks/enrich_atr.py` in full before writing a single line of code.

---

## Context

The project uses a "LLMs synthesize, APIs calculate" rule. All quantitative facts
are pre-computed in Python and injected into the composite bundle before any agent
call. Agents read pre-computed signals as facts — they never compute indicators
themselves.

`enrich_atr.py` already established the pattern:
- Bulk yfinance OHLC download (1 call per ticker, batched)
- Compute metrics in pure Python / pandas
- Inject a new top-level key into the composite bundle JSON in-place
- Safe to append because `load_composite_bundle()` verifies only
  `SHA256(market_hash + vault_hash)` — appended keys do not invalidate the hash

This task adds a second enrichment key: `calculated_technicals`, following the
same structure and safety contract.

---

## Step 1: Read existing files before writing anything

```
Read these files in full before writing any code:

1. tasks/enrich_atr.py          — exact pattern to replicate
2. config.py                    — constants (CASH_TICKERS, ETF skip sets if any)
3. core/bundle.py               — load_composite_bundle(), ContextBundle fields
4. manager.py (snapshot command) — how --enrich-atr is wired; replicate for --enrich-technicals
```

---

## Step 2: Create `tasks/enrich_technicals.py`

### Indicators to compute

All computed from **1 year of daily OHLC** via `yfinance.download()` bulk call.
One download covers all indicators — do not make separate calls per indicator.

**Moving averages (price-based):**
| Field | Calculation |
|---|---|
| `ma_50` | 50-day simple moving average of close |
| `ma_200` | 200-day simple moving average of close |
| `price_vs_ma50_pct` | `(current_price - ma_50) / ma_50 * 100` |
| `price_vs_ma200_pct` | `(current_price - ma_200) / ma_200 * 100` |
| `ma_signal` | `"above_both"` / `"above_200_below_50"` / `"below_both"` — string label |
| `golden_cross` | `bool` — MA50 crossed above MA200 within last 20 trading days |
| `death_cross` | `bool` — MA50 crossed below MA200 within last 20 trading days |

**Momentum oscillators:**
| Field | Calculation |
|---|---|
| `rsi_14` | 14-period RSI (Wilder smoothing: first avg = simple mean of 14 periods; subsequent = EMA-style). Round to 1 decimal. |
| `rsi_signal` | `"overbought"` if rsi_14 > 70, `"oversold"` if rsi_14 < 30, `"neutral"` otherwise |
| `macd_line` | EMA(12) − EMA(26) of close. Round to 4 decimals. |
| `macd_signal_line` | EMA(9) of macd_line. Round to 4 decimals. |
| `macd_histogram` | `macd_line - macd_signal_line`. Round to 4 decimals. |
| `macd_signal` | `"bullish"` if histogram > 0 and crossed above zero within 5 days, `"bearish"` if histogram < 0 and crossed below zero within 5 days, `"neutral"` otherwise |

**Volume:**
| Field | Calculation |
|---|---|
| `volume_20d_avg` | 20-day simple average of daily volume. Round to integer. |
| `volume_ratio` | `current_volume / volume_20d_avg`. Round to 2 decimals. Use most recent complete trading day. |
| `volume_signal` | `"high"` if ratio > 1.5, `"low"` if ratio < 0.5, `"normal"` otherwise |

**Trend summary (composite, Python-only):**
| Field | Calculation |
|---|---|
| `trend_score` | Integer −3 to +3. Start at 0. +1 for each: price above MA50, price above MA200, RSI between 40-70 (momentum healthy), MACD histogram > 0. −1 for each opposite condition. Cap at +3 / −3. |
| `trend_label` | `"strong_uptrend"` (+3), `"uptrend"` (+2/+1), `"neutral"` (0), `"downtrend"` (−1/−2), `"strong_downtrend"` (−3) |

### Ticker scoping rules (mirror enrich_atr.py exactly)

```python
SKIP_ASSET_CLASSES = {"CASH_EQUIVALENT", "MMMF", "FIXED_INCOME", "BOND"}
SKIP_TICKERS = {"CASH_MANUAL", "QACDS"}  # match config.CASH_TICKERS

# ETFs are INCLUDED — MA/RSI/MACD are meaningful for ETFs.
# Only skip tickers with no meaningful price series.
```

### Output structure injected into composite bundle

```python
composite["calculated_technicals"] = [
    {
        "ticker": "UNH",
        "as_of_date": "2026-04-17",           # most recent trading day in data
        "current_price": 312.45,
        "ma_50": 298.10,
        "ma_200": 285.60,
        "price_vs_ma50_pct": 4.81,
        "price_vs_ma200_pct": 9.39,
        "ma_signal": "above_both",
        "golden_cross": False,
        "death_cross": False,
        "rsi_14": 58.3,
        "rsi_signal": "neutral",
        "macd_line": 3.2415,
        "macd_signal_line": 2.8901,
        "macd_histogram": 0.3514,
        "macd_signal": "neutral",
        "volume_20d_avg": 3241000,
        "volume_ratio": 0.87,
        "volume_signal": "normal",
        "trend_score": 2,
        "trend_label": "uptrend",
        "data_gap": None                      # or e.g. "insufficient_history"
    },
    # ... one entry per non-skipped position
]
```

`data_gap` must be non-null (a descriptive string) when any indicator could not
be computed, e.g.:
- `"insufficient_history"` — fewer than 200 trading days returned
- `"no_data"` — yfinance returned empty DataFrame
- `"partial"` — MA200 unavailable but MA50/RSI computed (note which fields are None)

When `data_gap` is set, set affected numeric fields to `None` — never use 0 as a
fallback for a missing indicator (0 is a real RSI value).

### Implementation requirements

**Bulk download:** Use `yfinance.download(tickers=ticker_list, period="1y",
interval="1d", group_by="ticker", auto_adjust=True, progress=False)`. One call
for all tickers. Handle the column multi-index that yfinance returns for multiple
tickers (single-ticker calls return a flat DataFrame — guard against both shapes).

**RSI implementation:** Do not use `pandas_ta` or `ta-lib` — implement Wilder RSI
in pure pandas to avoid adding dependencies. The formula:
```python
delta = close.diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)
avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
rs = avg_gain / avg_loss
rsi = 100 - (100 / (1 + rs))
```

**MACD implementation:** Pure pandas EMA:
```python
ema12 = close.ewm(span=12, adjust=False).mean()
ema26 = close.ewm(span=26, adjust=False).mean()
macd = ema12 - ema26
signal = macd.ewm(span=9, adjust=False).mean()
histogram = macd - signal
```

**Cross detection:** For golden/death cross and MACD signal cross, compare the
last 20 rows of the MA series (or 5 rows for MACD). A cross occurred if the sign
of `(MA50 - MA200)` changed from negative to positive (golden) or positive to
negative (death) anywhere in that window.

**Rate limiting:** Add `time.sleep(0.25)` between yfinance downloads if falling
back to per-ticker download (when bulk call fails for a subset). This mirrors the
rate-limiting discipline in `enrich_atr.py`.

**Graceful degradation:** If the bulk download fails entirely, fall back to
per-ticker downloads with a console warning. If a per-ticker download fails,
append a `data_gap` entry for that ticker and continue. Never raise and abort —
the pattern is always "compute what you can, annotate what you couldn't."

### File structure

```python
"""
tasks/enrich_technicals.py
──────────────────────────
Computes Murphy TA indicators (MA, RSI, MACD, volume) for all non-cash positions
and injects `calculated_technicals` into the composite bundle JSON in-place.

Safe to append: load_composite_bundle() verifies SHA256(market_hash + vault_hash).
Appended keys do not invalidate the hash.

Run after enrich_atr.py (shares the same yfinance OHLC data requirement).
Can run standalone or via --enrich-technicals flag on manager.py snapshot.

Usage:
    python tasks/enrich_technicals.py bundles/composite_bundle_<hash>.json
    python manager.py snapshot --enrich-technicals        # after composite exists
    python manager.py snapshot --enrich-atr --enrich-technicals  # both in sequence
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))  # project root import fix
```

---

## Step 3: Wire `--enrich-technicals` into `manager.py`

In `manager.py`, the `snapshot` command already has `--enrich-atr`. Add
`--enrich-technicals` as a parallel optional flag with identical wiring:

```python
enrich_technicals: bool = typer.Option(
    False, "--enrich-technicals",
    help="After building the snapshot, inject Murphy TA indicators (MA/RSI/MACD/volume) "
         "into the latest composite bundle. Requires composite bundle to exist.",
)
```

Execution block (add after the existing `--enrich-atr` block, same pattern):
```python
if enrich_technicals:
    from tasks.enrich_technicals import enrich_composite_bundle as _enrich_technicals
    # ... resolve composite path (identical to enrich_atr block) ...
    # Console output:
    #   "Technical indicators computed for N position(s)."
    #   List any tickers with data_gap != None as warnings
    #   Print trend_score distribution: N strong_uptrend, N uptrend, N neutral, etc.
```

Both flags can be passed together:
```bash
python manager.py snapshot --enrich-atr --enrich-technicals
```

---

## Step 4: Wire into `analyze_all.py`

In `agents/analyze_all.py`, the `--fresh-bundle` path calls `enrich_atr` after
building the composite. Add `enrich_technicals` in the same block, after `enrich_atr`:

```python
# After enrich_atr call:
from tasks.enrich_technicals import enrich_composite_bundle as _enrich_technicals
with console.status("[cyan]Enriching: Murphy TA indicators..."):
    _enrich_technicals(composite_path)
```

This ensures that on every Sunday GitHub Actions run, all agents have fresh
MA/RSI/MACD/volume data alongside fresh ATR stops.

---

## Step 5: Update `config.py`

Add technical indicator threshold constants after the existing concentration/
correlation thresholds:

```python
# ---------------------------------------------------------------------------
# Technical Indicator Thresholds (Murphy TA)
# ---------------------------------------------------------------------------
TA_RSI_OVERBOUGHT      = 70    # RSI above this → "overbought"
TA_RSI_OVERSOLD        = 30    # RSI below this → "oversold"
TA_VOLUME_HIGH_RATIO   = 1.5   # volume_ratio above this → "high"
TA_VOLUME_LOW_RATIO    = 0.5   # volume_ratio below this → "low"
TA_CROSS_LOOKBACK_DAYS = 20    # days to look back for golden/death cross detection
TA_MACD_CROSS_LOOKBACK = 5     # days to look back for MACD signal cross
```

---

## Step 6: Update agent system prompts to consume `calculated_technicals`

After the task is wired, update four agent system prompts to reference the new
fields. The update is additive — add a short section to each prompt explaining
what fields are available and how to use them as coloring context, not as primary
signals.

### Agents to update and guidance for each

**`agents/prompts/valuation_agent_system.txt`**
Add a section: "Technical Context (from calculated_technicals)". Instruct the
agent: "If a position has rsi_signal='overbought' and trend_label='strong_uptrend',
treat the accumulate signal with more caution — momentum may have run ahead of
value. If rsi_signal='oversold' and price_vs_ma200_pct < -10, this strengthens an
accumulate signal — technical conditions align with the valuation case."

**`agents/prompts/rebuy_analyst_system.txt`** (or equivalent)
Add a section: "Technical Entry Conditions". Instruct the agent: "Prefer re-buy
entry when price_vs_ma50_pct > -5 (not overextended below MA) and rsi_14 is
between 35-60 (momentum not yet exhausted). Flag entries where rsi_signal=
'overbought' as requiring smaller first step. volume_signal='high' on a down day
strengthens conviction for a re-buy; 'high' on an up day suggests chasing."

**`agents/prompts/macro_cycle_agent_system.txt`** (or equivalent)
Add a section: "Technical Trend Confirmation". Instruct the agent: "Use
trend_label as confirmation of the Perez cycle phase assessment. A position
assessed as Early Deployment phase should ideally show 'uptrend' or
'strong_uptrend'. A Maturity phase position showing 'above_both' with
golden_cross=True is a caution flag — technically extended. death_cross=True on
any position is a TRIM trigger regardless of cycle phase."

**`agents/prompts/add_candidate_system.txt`**
Add a section: "Technical Add Conditions". Instruct the agent: "Prefer add
candidates where ma_signal='above_both' (healthy trend structure) and
rsi_signal='neutral' (not chasing). Downgrade candidates with trend_score <= -1
from add to watchlist."

### Prompt update format
In each prompt file, add the new section **after** the existing pre-computation
fields list and **before** the output schema section. Keep it to 8-12 lines per
agent — this is coloring context, not the primary analytical framework.

---

## Step 7: Update `CLAUDE.md`

Add to the "Bundle Enrichment Tasks" section (or create it if it doesn't exist):

```markdown
### Bundle Enrichment Tasks

| Task | Command | Key injected | Notes |
|---|---|---|---|
| `tasks/enrich_atr.py` | `snapshot --enrich-atr` | `calculated_technical_stops` | ATR 14-day stops, Van Tharp input |
| `tasks/enrich_technicals.py` | `snapshot --enrich-technicals` | `calculated_technicals` | MA50/200, RSI-14, MACD, volume |

Both tasks append to the composite bundle JSON without invalidating the hash.
Run order: `enrich_atr` first (Van Tharp sizing depends on it), then `enrich_technicals`.
Both are included in `analyze_all --fresh-bundle` automatically.
```

---

## Verification Checklist

Run these after implementation to confirm correctness:

```
T1: python tasks/enrich_technicals.py bundles/composite_bundle_<latest>.json
    → Prints "Technical indicators computed for N position(s)."
    → No uncaught exceptions

T2: Inspect output JSON:
    composite["calculated_technicals"][0].keys() contains all 17 required fields
    No field is 0 where None was expected for missing data

T3: UNH sanity check (known stable large-cap):
    ma_50 and ma_200 are non-null floats
    rsi_14 is between 0 and 100
    trend_score is between -3 and +3

T4: python manager.py snapshot --enrich-technicals
    (with a composite bundle already present)
    → Summary line printed: N strong_uptrend, N uptrend, etc.
    → Any data_gap tickers printed as warnings

T5: python manager.py snapshot --enrich-atr --enrich-technicals
    → Both enrichments complete without interfering with each other
    → Composite bundle contains both "calculated_technical_stops"
       and "calculated_technicals" keys

T6: python manager.py analyze-all --fresh-bundle (dry run)
    → Console shows both ATR and technical enrichment steps complete
    → No KeyError when agents read calculated_technicals

T7: ETF coverage — QQQM, IGV, XBI, VEA should all have entries
    (ETFs are included, not skipped)

T8: Cash skip — CASH_MANUAL and QACDS must NOT appear in calculated_technicals

T9: Graceful degradation — rename a ticker to something invalid in a test run
    → data_gap is set to "no_data" for that entry
    → All other tickers still computed successfully
    → Script exits with code 0 (not 1)
```

---

## Gemini Peer Review Step

After implementation and verification, run:

```bash
gemini -p "Review tasks/enrich_technicals.py against these criteria:
1. RSI Wilder smoothing: uses ewm(alpha=1/14, min_periods=14, adjust=False) — not rolling mean
2. MACD: ema12=span(12), ema26=span(26), signal=span(9), all adjust=False
3. No pandas_ta or ta-lib imports
4. bulk yfinance download with group_by='ticker' — handles multi-index column shape
5. data_gap is a string or None — never 0 or False for missing data
6. CASH_MANUAL and QACDS are skipped
7. ETFs (QQQM, IGV, XBI) are included
8. sys.path.insert(0, ...) at top
9. time.sleep(0.25) in per-ticker fallback path
10. enrich_composite_bundle() function signature matches enrich_atr.py

Flag any deviations."
```
