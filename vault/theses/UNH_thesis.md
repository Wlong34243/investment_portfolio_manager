---
ticker: UNH
style: GARP / Defensive Compounder
framework_preference: lynch_garp_v1, psychology_of_money
entry_date: 2026-04-20
last_reviewed: 2026-04-20
current_allocation: TBD
cost_basis: 296.97
time_horizon: 3 to 5 years
triggers:
  fwd_pe_add_below: 14                # add when market prices in "permanently impaired"
  fwd_pe_trim_above: 20               # trim if multiple fully normalizes ahead of fundamentals
  fwd_pe_historical_median: null
  price_add_below: 280                # reload if panic + no structural break
  price_trim_above: 380               # reconsider size as valuation closes gap to prior range
  discount_from_52w_high_add: null
  revenue_growth_floor_pct: 5         # this is a defensive compounder, not a hyper-growth story
  operating_margin_floor_pct: null    # more about normalization trajectory than level in any one quarter
  style_size_ceiling_pct: 7.0         # defensive, but still single-name/regulatory risk
  current_weight_pct: null
---

# UNH — Investment Thesis

## Core Thesis (“Quality On Sale” View)

I am buying a dominant, defensive healthcare compounder after a **forced repricing**, not a structural collapse. The stock fell from the low-$600s to the high-$200s as regulatory and legal noise spiked, compressing the multiple to ~15x trailing earnings at entry, well below its historical range.[file:1] The bet is that UnitedHealth remains a high-quality franchise temporarily priced like a damaged one, with upside driven by earnings normalization, margin recovery, and continued cash generation rather than heroic growth assumptions.[file:1]

Over a 3–5 year horizon, I expect mid-single-digit revenue growth and steady EPS compounding as margins normalize, buybacks continue, and regulatory noise gradually clears.[file:1] This is primarily a **re-rating plus compounding** setup: I do not need explosive top-line growth to earn acceptable returns, just a path back to “boring, premium-multiple healthcare.”[file:1]

## Valuation & GARP Targets (Peter Lynch Framework)

I am underwriting UNH as a GARP-style, boring-fundamentals compounder bought during a sentiment and regulatory panic. At a ~15x trailing P/E at entry, the market is pricing in a long period of subpar profitability and persistent overhangs relative to the company’s long-term record.[file:1] My lens:

- Target revenue growth: low-to-mid single digits, consistent with a mature, defensive healthcare franchise.[file:1]  
- Target EPS growth: high-single-digit to low-double-digit CAGR via margin normalization, modest growth, and capital returns.[file:1]  
- Acceptable PEG: ~1.2–1.5x on normalized EPS growth, reflecting the quality and resilience of the business.[file:1]  
- P/E ceiling tolerance: willing to hold into a high-teens to ~20x forward P/E if margin recovery and earnings compounding are on track; above that, I will trim if valuation outruns fundamentals.  
- Base-case IRR: high-single-digit to low-teens annualized, driven by a mix of EPS growth, modest multiple expansion, and dividends.[file:1]  

## Position Sizing & Action Zones

UNH is a **defensive core** position, not a trading line; sizing is constrained by single-name regulatory risk even though the business is diversified. Entry was initiated after a >50% drawdown from the highs, with a cost basis around $296.97.[file:1] Key zones:

- Add zone (“panic quality”): Below ~$280 or at a forward P/E in the low-teens if the drawdown is clearly driven by regulatory headlines or macro, not by evidence of a structural break in profitability.[file:1]  
- Hold zone: Forward P/E in the mid-teens with evidence of gradual margin stabilization and no escalation into existential regulatory remedies.  
- Trim zone: A clean re-rating into a high-teens to ~20x forward P/E if that move is driven more by relief and multiple expansion than by sustainable upward revisions to earnings power.  

## Behavioral Guardrails (Psychology / Housel Lens)

I will mentally underwrite a 25–30% drawdown from cost basis if it is driven by regulatory headlines, election noise, or generalized healthcare-sector de-rating rather than a clear structural impairment to UNH’s business model.[file:1] I will not panic-sell into political or DOJ headline spikes alone.

I will hold and ignore grinding, range-bound price action as long as the thesis datapoints are moving in the right direction: margins stabilizing or improving, legal/regulatory issues trending toward resolution, and no sign of permanent earnings impairment.[file:1] I will only change my mind on the core thesis if new information points to a lasting cap on profitability or a structural change to the franchise’s economics.

## Key Quantitative & Qualitative KPIs

The core of the thesis is **normalization**, not acceleration; my KPIs are about direction and durability, not quarterly perfection.[file:1]

- Profitability: Operating margins and medical cost trends show a path back toward historical ranges over 4–8 quarters, even if choppy quarter-to-quarter.[file:1]  
- Legal / regulatory trajectory: DOJ and political processes move toward fines, settlements, or manageable remedies rather than open-ended investigations that threaten core economics.[file:1]  
- Cash generation & returns: Strong free cash flow conversion, continued dividend growth, and a rational buyback program that takes advantage of any extended period of depressed multiples.[file:1]  
- Franchise health: No evidence that regulatory noise is causing structural loss of scale, network advantages, or Optum/UnitedHealthcare cross-franchise synergies.[file:1]  

## Hard Exit Conditions

I will exit or materially reduce the position if the thesis breaks in a **structural**, not cyclical, way:[file:1]

1. DOJ action or regulation leads to binding structural remedies that permanently impair the economics of the core franchise (forced breakup, severe pricing constraints, or restrictions that dismantle key synergies).  
2. Margins fail to show any credible recovery trajectory over 4–6+ quarters, indicating that the prior profitability profile is not coming back.[file:1]  
3. Clear evidence emerges that UNH is losing its competitive edge (scale, network, data, integrated services) in a way that cannot be solved with time or capital.  
4. A clearly superior risk-adjusted opportunity appears where capital can earn a higher long-term IRR, and UNH still trades at a compressed but no-longer-“dirt cheap” multiple.[file:1] 

## Quantitative Triggers

<!-- Machine-readable triggers. Keep the YAML block EXACT — parsers depend on it.
     Use null for fields that don't apply to this position's style. -->

```yaml
triggers:
  # Valuation triggers (GARP, FUND)
  fwd_pe_add_below: 14
  fwd_pe_trim_above: 20
  fwd_pe_historical_median: null

  # Price/technical triggers (all styles)
  price_add_below: 280.0
  price_trim_above: 380.0
  discount_from_52w_high_add: null

  # Fundamental triggers (GARP, FUND)
  revenue_growth_floor_pct: 5
  operating_margin_floor_pct: null

  # Position management
  style_size_ceiling_pct: 7.0
  current_weight_pct: null
```
