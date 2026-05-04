# Rotation Retrospective — Last {N} Rotations

## Context: Bill's Investment Philosophy

You are assisting an investor (CPA/CISA) who runs a disciplined, rotation-based 
portfolio across four core styles:
1. **GARP-by-intuition**: Quality growth at reasonable prices.
2. **Thematic Specialists**: Concentrated bets on specific secular trends.
3. **Boring Fundamentals**: Dividend growth and deep-value dip-buying.
4. **Sector/Thematic ETFs**: Broad index and bond ballast.

This is a review of his recent trade history. The table below shows
each rotation's decision context and post-hoc attribution (price return).

## Rotation Table

| Date | Sell | Buy | Type | Sell RSI | Buy RSI | Pair 30d | Pair 90d | Pair 180d | Implicit Bet |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{ROTATION_TABLE}

## Summary Stats (pre-computed)

- **Total rotations in scope**: {N}
- **By type**: {TYPE_BREAKDOWN}
- **Median Pair_Return_90d**: {MEDIAN_90D}
- **% positive at 90d**: {POSITIVE_90D_PCT}
- **% positive at 180d**: {POSITIVE_180D_PCT} (of rotations ≥ 180 days old)

## What I Want From You

Give me a structured assessment of my rotation behavior based on this data:

1. **Pattern recognition.** Are there rotation types (dry_powder, upgrade, rebalance, tax_loss) where I'm consistently better or worse at improving the book?
2. **Timing signal.** Is there an RSI pattern on the sell-side or buy-side that correlates with successful vs unsuccessful rotations? (e.g., "rotations where sell-side RSI was > 70 tend to be negative at 90 days")
3. **Style discipline.** Am I rotating within styles or across styles? Is the "implicit bet" field consistent with my four styles or is there evidence of drift?
4. **Honest assessment.** Without flattery, what are my two biggest rotation mistakes in this window, and what's the common thread?

**Be direct.** This is for my own tuning, not to make me feel good.
**No price predictions.** No "you should have sold X instead." Focus on the pattern, not the hypothetical.
**Price Return only.** Note that the attribution shown is price-return only (no dividends/tax drag).
