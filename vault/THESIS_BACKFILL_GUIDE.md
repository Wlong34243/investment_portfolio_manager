# Thesis Quantitative Trigger Backfill Guide

## Why This Matters

The Thesis Screener agent reads two layers from each `_thesis.md` file:

1. **Narrative exit conditions** — prose paragraphs describing when you'd sell.
2. **Quantitative triggers** — machine-readable price/PE/fundamental thresholds.

Without quantitative triggers, the agent can only reason from prose. With them, it can
*check* whether a specific threshold has been breached before recommending TRIM or EXIT.
A fired trigger produces a more defensible verdict than a narrative inference.

Run `python manager.py vault thesis-audit` to see which positions need backfill.

---

## Suggested Backfill Order (by position weight)

Backfill the positions where a wrong call costs the most:

1. **UNH** — largest healthcare position; GARP; P/E and growth triggers most valuable
2. **GOOG** — large tech; GARP; PE ceiling and revenue deceleration triggers
3. **JPIE** — fixed income; skip fwd_pe fields; use price and size ceiling only
4. **AMZN** — growth compounder; use fwd_pe_trim_above and price_add_below
5. **Then by weight descending** — run `python manager.py vault thesis-audit` for the ranked list

---

## What Good Looks Like: Examples by Style

### GARP (e.g., UNH, GOOG, AMZN)

```yaml
triggers:
  fwd_pe_add_below: 18.0        # ADD if forward P/E compresses to your "fat pitch" level
  fwd_pe_trim_above: 32.0       # TRIM if multiple expands above your conviction ceiling
  fwd_pe_historical_median: 24.0  # your 5-year median for reference
  price_add_below: 480.00       # specific dollar entry zone from thesis
  price_trim_above: null        # leave null if P/E ceiling is the better signal
  discount_from_52w_high_add: 0.20  # ADD if 20%+ below 52-week high
  revenue_growth_floor_pct: 8.0    # concern if revenue growth drops below 8% YoY
  operating_margin_floor_pct: 12.0  # concern if operating margin falls below 12%
  style_size_ceiling_pct: 9.0    # your personal max for this position
  current_weight_pct: null       # auto-populated; leave null
```

### FUND — Boring Fundamentals (e.g., JPIE, EPD)

```yaml
triggers:
  fwd_pe_add_below: null         # P/E not the primary signal for boring fundamentals
  fwd_pe_trim_above: null
  fwd_pe_historical_median: null
  price_add_below: 52.00         # ADD if price dips to the "nothing-burger" zone
  price_trim_above: null         # FUND: thesis exit, not valuation exit
  discount_from_52w_high_add: 0.15  # ADD if 15%+ off high with no fundamental reason
  revenue_growth_floor_pct: null
  operating_margin_floor_pct: null
  style_size_ceiling_pct: 5.0    # FUND positions capped at 5% per style guidance
  current_weight_pct: null
```

### THEME (e.g., CRWV, PLTR if you hold these)

```yaml
triggers:
  fwd_pe_add_below: null         # P/E mostly irrelevant for theme positions
  fwd_pe_trim_above: null
  fwd_pe_historical_median: null
  price_add_below: null          # theme positions: thesis breaks or it doesn't
  price_trim_above: null
  discount_from_52w_high_add: 0.30  # ADD only if deeply oversold and theme still live
  revenue_growth_floor_pct: 20.0    # theme must be growing fast or it's dead
  operating_margin_floor_pct: null
  style_size_ceiling_pct: 3.0    # THEME: high-risk, small size ceiling
  current_weight_pct: null
```

### ETF (e.g., QQQM, VOO)

```yaml
triggers:
  fwd_pe_add_below: null         # ETFs are macro-driven; P/E not meaningful
  fwd_pe_trim_above: null
  fwd_pe_historical_median: null
  price_add_below: null          # ETF sizing is target-allocation based, not price-based
  price_trim_above: null
  discount_from_52w_high_add: null
  revenue_growth_floor_pct: null
  operating_margin_floor_pct: null
  style_size_ceiling_pct: 8.0    # your target allocation ceiling for this ETF
  current_weight_pct: null
```

---

## The Honest Null Rule

> "It is better to leave a trigger null than to invent a value.
> A null trigger is a known-missing data point; an invented trigger is a lie the agent will believe."

The `trigger_missing` field in the agent output shows which fields are null for each position.
A long `trigger_missing` list is a data quality signal, not a failure — it tells you exactly
what to backfill next.

Only populate a trigger when you have actual conviction about the threshold. If you wouldn't
act on a price level, don't write it down as a trigger — the agent will cite it.

---

## How to Backfill

1. Open the thesis file: `vault/theses/{TICKER}_thesis.md`
2. Find the `## Quantitative Triggers` section and its `triggers:` YAML block.
3. Replace `null` with your actual threshold for each field you have conviction on.
4. Leave the rest as `null`.
5. Update `last_reviewed` in the frontmatter to today's date.
6. Run `python manager.py vault thesis-audit` to verify.
7. Re-run `python manager.py agent thesis analyze --bundle latest --ticker {TICKER}` to
   see the per_position_verdict improve.

A weekend afternoon of backfill on your top 10 positions will produce more signal quality
improvement than months of prompt tuning.
