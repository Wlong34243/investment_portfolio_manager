import os
from pathlib import Path

TEMPLATE = """---
ticker: {TICKER}
style: {STYLE}
framework_preference: {FRAMEWORK}
entry_date: 2026-05-03
last_reviewed: 2026-05-03
current_allocation: 0.0%
cost_basis: 0.0
time_horizon: 3 to 5 years
triggers:
  fwd_pe_add_below: null
  fwd_pe_trim_above: null
  fwd_pe_historical_median: null
  price_add_below: null
  price_trim_above: null
  discount_from_52w_high_add: null
  revenue_growth_floor_pct: null
  operating_margin_floor_pct: null
  style_size_ceiling_pct: {CEILING}
  current_weight_pct: null
---
# {TICKER} — Investment Thesis

## Core Thesis
[Placeholder for {TICKER} qualitative thesis. Position identified as part of the {STYLE} bucket.]

## Position Sizing & Action Zones
- Add zone: TBD
- Hold zone: TBD
- Trim zone: TBD

## Quantitative Triggers

```yaml
triggers:
  # Valuation triggers
  fwd_pe_add_below: null
  fwd_pe_trim_above: null
  fwd_pe_historical_median: null
  
  # Price/technical triggers
  price_add_below: null
  price_trim_above: null
  discount_from_52w_high_add: null
  
  # Fundamental triggers
  revenue_growth_floor_pct: null
  operating_margin_floor_pct: null
  
  # Position management
  style_size_ceiling_pct: {CEILING}
  current_weight_pct: null
```

<!-- region:position_state -->
**Current Allocation:** 0.00%
**Cost Basis:** $0.00
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** {STYLE}
**Size Ceiling:** {CEILING}%
**Drift:** 0.00%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
No recent transactions.
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-05-03: Initial thesis shell generated.
<!-- endregion:change_log -->
"""

MISSING_TICKERS = {
    "APA": {"style": "THEME", "ceiling": 3.0, "framework": "lynch_garp_v1"},
    "BX": {"style": "GARP", "ceiling": 9.0, "framework": "lynch_garp_v1"},
    "GILD": {"style": "FUND", "ceiling": 5.0, "framework": "lynch_garp_v1"},
    "GLD": {"style": "ETF", "ceiling": 8.0, "framework": "lynch_garp_v1"},
    "LRCX": {"style": "GARP", "ceiling": 9.0, "framework": "lynch_garp_v1"}
}

def main():
    theses_dir = Path("vault/theses")
    theses_dir.mkdir(parents=True, exist_ok=True)
    
    for ticker, info in MISSING_TICKERS.items():
        file_path = theses_dir / f"{ticker}_thesis.md"
        if file_path.exists():
            print(f"Skipping {ticker}, already exists.")
            continue
            
        content = TEMPLATE.format(
            TICKER=ticker,
            STYLE=info["style"],
            CEILING=info["ceiling"],
            FRAMEWORK=info["framework"]
        )
        file_path.write_text(content, encoding="utf-8")
        print(f"Generated {file_path}")

if __name__ == "__main__":
    main()
