# Prompt — Schwab Data Expansion, Phase 2: Price-History Consumer Migration

**Created:** 2026-08-25
**Executor:** Claude Code or Gemini CLI, run locally in `C:\Dev\Investment_Portfolio`
**Phase:** 2 of 4
**Prerequisite:** Phase 1 (`schwab_data_expansion_2026-08-25.md`) complete, checklist
passed with literal output, and the dividend-adjustment question answered.

---

## Why this exists

The 2026-08-25 audit found yfinance supplying price history to at least nine modules:

| Module | Line | Call | What depends on it |
|---|---|---|---|
| `tasks/enrich_atr.py` | 56 | `yf.download(period="1mo")` | ATR column |
| `utils/technicals.py` | 31–32 | `.history(period="1y")` | RSI/MA/technical columns |
| `tasks/enrich_technicals.py` | 350 | `yf.download(...)` | Technicals enrichment |
| `utils/risk.py` | 26, 117 | `yf.download(period="1y", auto_adjust=True)` | Beta, vol, correlation |
| `tasks/dislocation_scan.py` | 100 | `.history(period="3mo")` | Drawdown, 5d return — a live daily screen |
| `tasks/build_valuation_card.py` | 151 | `yf.Ticker(...)` | Valuation_Card inputs → Crosshairs |
| `tasks/build_command_center.py` | 211, 344 | SPY ytd + 1y multi-download | `0_DASHBOARD` KPIs |
| `tasks/derive_rotations.py` | 106 | `yf.download(start=...)` | Rotation clustering |
| `tasks/compute_rotation_attribution.py` | 94 | `yf.download(...)` | **Benchmarked attribution vs SPY/VTI/QQQ** |

An unofficial scraper with no contract, no auth and no support sits under the
`Rotation_Review` attribution numbers, the daily dislocation screen, and the dashboard
KPIs. Schwab is authenticated, contractual, and consistent with the broker the positions
actually live at. That is the case for migrating.

The case for migrating **carefully** is that `compute_rotation_attribution.py` produces
historical numbers that are already on record in `Rotation_Review`. Changing its price
source changes published attribution. That module moves last, and only with an explicit
sign-off on a before/after diff.

---

## Hard constraints

1. Order/trading endpoints remain forbidden. Zero matches for
   `place_order|replace_order|cancel_order|get_orders` at the end of this phase.
2. **yfinance is not removed, uninstalled, or deleted from `requirements.txt`.** It
   becomes the fallback leg. Removing it is a separate decision Bill has not made.
3. **One consumer per commit.** No batch migration. Each consumer gets its own
   before/after evidence before the next one starts.
4. Every migrated call site must route through `PRICE_HISTORY_SOURCE`, never call
   `fetch_price_history()` directly and unconditionally.
5. Do not "improve" a consumer's analytics while migrating it. Source swap only. If a
   consumer's math looks wrong, report it and leave it alone — a source migration that
   also changes a formula is unfalsifiable.
6. Do not touch `utils/etf_holdings.py` (yfinance `funds_data`, not price history) or the
   `yf.Ticker(...).fast_info` **spot-price** lookups in `utils/enrichment.py` and
   `utils/fmp_client.py`. Those are live-price lookups on a different cadence and are out
   of scope for this phase entirely.
7. **Tier 8 is the one quote-derived exception**, and only for the two fields Phase 1
   Step 3b added to `fetch_quotes()`: 52-week high/low and dividend yield. It migrates
   *derived field values*, not spot prices. It runs last, after all seven bar consumers,
   and never before them — a 52-week high sourced from Schwab quotes while drawdown is
   still computed from yfinance bars produces a ratio of two vendors' numbers, which is
   worse than either alone.

---

## Step 0 — Verification gate (STOP on any mismatch)

```
0.1  grep -n "PRICE_HISTORY_SOURCE" config.py
     EXPECT present, defaulting to "yfinance"

0.2  grep -nE "^def (fetch_price_history|fetch_price_history_batch)" utils/schwab_client.py
     EXPECT both present

0.3  ls agent_outputs/schwab_probe/price_history_reconciliation_2026-08-25.md
     EXPECT present. Read it. Record the max relative deviation observed and the
     dividend-adjustment verdict. If that file is absent, Phase 1 did not complete —
     STOP.

0.4  grep -rnE "yf\.download|\.history\(|yf\.Ticker" utils tasks core --include=*.py | grep -v __pycache__
     EXPECT the nine modules in the table above, at approximately the stated lines.
     Record the ACTUAL current line numbers — they are the migration checklist.
     Any module in the table that no longer matches, or any NEW module that does,
     must be reported before proceeding.

0.4b Two findings from the 2026-08-25 audit that this prompt's migration table does
     NOT cover. Restate both in your Step 0 report, then leave them alone:

     (a) utils/risk.py:117 — build_price_histories() runs its own
         yf.download(period="1y", auto_adjust=True). It appears in the audit's
         yfinance inventory but is deliberately NOT one of the eight tiers.
         DO NOT silently add it as a ninth consumer. Its formulas
         (calculate_beta, calculate_var, calculate_correlation_matrix) already
         take price_histories as a PARAMETER, so Phase 4 consumes them by passing
         get_bars() output in — without migrating build_price_histories() itself.
         Confirm that parameterisation still holds and report it.

     (b) Also outside the eight tiers, and staying outside: core/bundle.py's
         1-day history call, and tasks/health.py's SPY ping. Both are liveness
         or snapshot checks, not analytics inputs. Report their line numbers;
         change neither.

0.5  python -c "import pandas as pd; print(pd.__version__)"
     Record it. The 2026-08-08 pandas ≥3.0 string-dtype incident is directly relevant:
     any new numeric coercion in this phase must route through the shared sanitizer,
     never a local stripper.
```

---

## Step 1 — The router

Create `utils/price_history.py`. This is the **only** module that decides which vendor
answers.

```python
def get_bars(
    ticker: str,
    period_days: int = 365,
    interval: str = "daily",
    source: str | None = None,        # None → config.PRICE_HISTORY_SOURCE
    adjusted: bool = True,
) -> pd.DataFrame:
    """
    Canonical OHLCV accessor. Columns: open, high, low, close, volume.
    tz-aware UTC DatetimeIndex, ascending. Empty DataFrame on total failure.

    source semantics:
      "yfinance" — yfinance only (current behaviour)
      "schwab"   — Schwab only; empty on failure, NO silent fallback
      "auto"     — Schwab first, yfinance on empty/exception, with a WARNING
                   naming the ticker and the reason
    """
```

Requirements:

- **One normalised schema.** Lowercase column names, sorted ascending index, tz-aware UTC,
  no duplicate dates. Both legs conform, so consumers cannot tell them apart by shape.
- `adjusted=True` must mean the same thing on both legs. Phase 1 settled what Schwab
  returns; implement whatever reconciliation that verdict requires (a dividend-adjustment
  pass on Schwab bars, or `auto_adjust=False` on yfinance to match — **whichever Phase 1's
  evidence supports**). Do not guess here; cite the Phase 1 finding in the docstring.
- Every return carries `df.attrs["source"]` = `"schwab"` or `"yfinance"`, and
  `df.attrs["adjusted"]` = bool. Consumers that log provenance read these.
- `"auto"` fallback events log at WARNING and increment a counter exposed via
  `pm probe price-source-stats`. A fallback that happens silently every morning is a
  vendor migration that never happened.

---

## Step 2 — Migration order

Ascending risk. Do not reorder.

| # | Consumer | Why here | Sign-off gate |
|---|---|---|---|
| 1 | `tasks/enrich_atr.py` | 1-month window, single derived column, no historical record | Table gate A |
| 2 | `utils/technicals.py` + `tasks/enrich_technicals.py` | Same family; RSI/MA are window functions over the same bars | Table gate A |
| 3 | `tasks/dislocation_scan.py` | Daily screen, output is dated and disposable, but it is **live** and feeds Crosshairs | Table gate B |
| 4 | `tasks/build_valuation_card.py` | Feeds `Trim Target`/`Add Target` → Crosshairs → `0_DASHBOARD` | Table gate B |
| 5 | `tasks/build_command_center.py` | Dashboard KPIs; SPY YTD is a headline number | Table gate B |
| 6 | `tasks/derive_rotations.py` | Clustering inputs; known nested-superset defect, do not attempt to fix it here | Table gate B |
| 7 | `tasks/compute_rotation_attribution.py` | **Changes published `Rotation_Review` numbers** | Table gate C |
| 8 | Quote-derived fields: `dislocation_scan.py` 52-week high, `schwab_client.fetch_positions()` dividend yield | Depends on Phase 1 Step 3b; must follow tiers 1–7 so drawdown numerator and denominator share a vendor | Table gate B, plus the extra conditions below |

### Tier 8 — additional conditions

Two call sites, and they are not equally safe.

**8a — `dislocation_scan.py` 52-week high. This is an FMP→Schwab swap, not a defect fix.**

An earlier draft of this prompt speculated that the scanner derived its 52-week high from
the 3-month yfinance window at line ~100 and might therefore be mislabelling a 3-month
high. **That speculation was wrong and is corrected here — verified against the code
2026-08-25:**

- `_price_history_returns()` (line ~94, `period="3mo"`) supplies the **1d / 5d / 20d
  returns only**.
- `week52_high` comes from FMP: `fund = get_fundamentals(...)` at line ~147, then
  `week52_high = fund.get("52w_high")` at ~152, with `drawdown_52w` computed at ~167.

So tier 8a swaps **FMP's `52w_high` for Schwab's quote-payload 52-week high**. The
yfinance 3-month window is untouched by 8a (it is tier 3's concern). Do not go looking
for a mislabelled-window defect; it does not exist.

What the gate must still separate, because two things can move the number:

1. **Vendor disagreement** — FMP and Schwab may simply report different 52-week highs
   (different intraday-vs-close convention, different adjustment, different as-of).
   Report the per-ticker delta between the two sources *before* changing anything.
2. **Resulting `drawdown_from_52w_high` movement**, and specifically **any ticker whose
   flag state flips** across `config.DISLOCATION_MIN_DRAWDOWN_52W`. A name entering or
   leaving the daily screen because the vendor changed is the outcome that matters, and
   it must be listed by name at the gate, not summarised.

FMP's `get_fundamentals()` stays in place for everything else it returns; 8a replaces one
key.

**8b — `fetch_positions()` dividend yield.** This edits a core function that Phase 1
deliberately protected. Conditions: the `'Dividend Yield': 0.0` zero-fill becomes the
Schwab value where present and `None` where absent — **never 0.0**, because a zero yield
and an unknown yield are different facts and downstream income views will read them
differently. Confirm every consumer of that column tolerates `None` before flipping;
list them at the gate. The existing enrichment path stays as the fallback for tickers
Schwab does not price.

Do not migrate tier 8 in one commit. 8a and 8b are separate.

### Table gate A — derived-column consumers

Before flipping, run the consumer both ways on the full current position set and print a
comparison table: ticker, old value, new value, absolute delta, relative delta. Print the
five largest relative deltas in full. Proceed only if nothing exceeds 2% relative, or
Bill accepts the exceptions row by row.

### Table gate B — live pipeline consumers

Table gate A, **plus**:
- a full dry-run of the consumer, with its complete stdout
- explicit statement of whether any Crosshairs row, Valuation_Card level, or dashboard
  KPI changes, and by how much
- **STOP and present.** Bill accepts, overrides, or rejects per row. This is the pattern
  that caught the nested-superset problem on 2026-08-08; it is not ceremony.

### Table gate C — attribution

Table gate B, **plus**:
- recompute attribution for **every** row currently in `Rotation_Review` under both
  sources
- a full diff: rotation ID, 30/90/180-day return old vs new, `Beta_Explained` old vs new,
  `Residual_Pair` old vs new
- any sign flip on `Residual_Pair` is called out individually — that is a rotation whose
  attributed verdict inverts
- an explicit recommendation on what to do with the historical rows: recompute in place,
  or freeze the old and mark the source change with a dated boundary. **Do not choose
  this yourself.** Present both, with the row count affected, and stop.

Note for context, not for action: `CLAUDE.md` records that 69 of 116 `Trade_Log` rows
already fail weight reconciliation because they span accounts descoped on 2026-08-03.
Those rows are already excluded from attribution. Confirm whether the diff above is
computed over the included subset only — if it is not, the diff is measuring the wrong
population.

---

## Step 3 — Per-consumer procedure

For each consumer, in order:

1. Replace the direct yfinance call with `price_history.get_bars(...)`. Preserve the
   existing window semantics exactly — `period="1mo"` becomes `period_days=30`, not
   `period_days=31`, unless you show that yfinance's `1mo` returns a different count and
   say so.
2. Preserve column-name expectations. If the consumer reads `Close` (capitalised,
   yfinance convention) it now reads `close`. **Grep the whole consumer for capitalised
   OHLCV column references before declaring it done** — a missed `df["Close"]` raises at
   runtime, in the morning pipeline, unattended.
3. Handle `df.empty`. Several consumers currently assume yfinance always returns
   something. Empty must degrade to the consumer's existing missing-data path, not to a
   zero. If a consumer has no missing-data path, report that rather than inventing one.
4. Log provenance: one INFO line per consumer run naming `df.attrs["source"]` and the
   ticker count.
5. Run the gate for that consumer's tier. Paste literal output. Stop where the gate says stop.
6. Commit alone, with the gate output in the commit message.

---

## Step 4 — Flip the default

Only after all eight tiers pass their gates (tier 8 included — a default flip while a
quote-derived field still reads from yfinance leaves the vendor split mid-calculation):

- `PRICE_HISTORY_SOURCE` default changes from `"yfinance"` to `"auto"` in `config.py`.
- **Not to `"schwab"`.** `auto` keeps the yfinance leg live as a fallback, and the
  fallback counter makes Schwab's real reliability observable over a few weeks. A flip
  straight to `schwab` trades a known-imperfect vendor for an unmeasured one.
- After 10 trading days on `auto`, review the fallback counter. If it is zero, `schwab`
  becomes defensible. That review is a future decision, not part of this prompt.

---

## Post-build verification checklist

Literal stdout/stderr for every row. No agent-reported PASS tables.

| # | Check | Evidence required |
|---|---|---|
| 1 | Order endpoints absent | `grep -rnE "place_order\|replace_order\|cancel_order\|get_orders" utils tasks core manager.py scripts` → zero |
| 2 | yfinance still installed and importable | `pip show yfinance`; still in `requirements.txt` |
| 3 | Router honours all three modes | `get_bars("AAPL", source=...)` for yfinance/schwab/auto; print `df.attrs["source"]` each time |
| 4 | `auto` actually falls back | Force a Schwab failure (invalid ticker or disabled token) and show the WARNING plus a yfinance-sourced frame |
| 5 | `schwab` does NOT fall back | Same forced failure with `source="schwab"` returns empty, no yfinance call |
| 6 | Capitalised-column sweep | `grep -rn "\[.Close.\]\|\[.Open.\]\|\[.High.\]\|\[.Low.\]\|\[.Volume.\]" tasks utils core` → zero in migrated modules |
| 7 | Gate tables | All eight comparison tables, in migration order, with Bill's per-row decision recorded for gates B and C |
| 7b | Tier 8a | Per-ticker FMP-vs-Schwab 52-week-high delta, plus every ticker whose `DISLOCATION_MIN_DRAWDOWN_52W` flag state flips, named individually |
| 7c | Tier 8b | Consumers of `Dividend Yield` enumerated with `None`-tolerance confirmed; proof the column is never 0.0-filled for an unknown |
| 8 | Attribution diff | The full `Rotation_Review` before/after diff, sign flips called out, decision recorded |
| 9 | Full pipeline dry run | `pm morning --skip-export` complete stdout, all STEPs, no traceback |
| 10 | Full pipeline live | `pm morning --live` stdout, plus the resulting `0_DASHBOARD` KPI row and Crosshairs top 5, compared against the prior day's |
| 11 | Fallback counter | `pm probe price-source-stats` after a full morning run |
| 12 | Config default | `grep -n PRICE_HISTORY_SOURCE config.py` shows `"auto"` |

---

## What this phase explicitly does NOT do

- Does not remove yfinance, from code or from requirements.
- Does not migrate spot-price lookups (`fast_info`) or ETF look-through (`funds_data`).
  Tier 8 migrates two *derived* fields only — 52-week high/low (from FMP) and dividend
  yield — and nothing else.
- Does not migrate `utils/risk.py`'s `build_price_histories()`, `core/bundle.py`'s 1-day
  history call, or `tasks/health.py`'s SPY ping. All three are reported at Step 0 and
  left in place.
- Does not remove FMP's `get_fundamentals()` from `dislocation_scan.py`. Tier 8a replaces
  one key in its return, not the call.
- Does not change any analytic formula, threshold, or window length.
- Does not fix the known `derive_rotations` nested-superset defect. Report it if you
  see it again; leave it.
- Does not rewrite historical `Rotation_Review` rows without an explicit decision at gate C.

---

## Documentation to update on completion

- `CHANGELOG.md` — dated entry, including the attribution decision from gate C
- `state.md` — supersede the "yFinance enrichment" line under Data ingestion
- `CLAUDE.md` — new `utils/price_history.py` row in Key Files; note that yfinance is now
  the fallback leg, not the primary
