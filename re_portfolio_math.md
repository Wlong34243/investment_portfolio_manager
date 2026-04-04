# Real Estate Portfolio Valuation Math

This document outlines the exact mathematical formulas and numerical constants used by the Investment Portfolio Manager's "Net Worth" module to calculate the value of the real estate portfolio and its contribution to total net worth.

## 1. Core Formulas

### Total Net Worth
The total net worth is the sum of liquid investments, real estate equity, and dedicated real estate cash reserves.
$$Total\ Net\ Worth = Liquid\ Assets + RE\ Equity + RE\ Reserves$$

### Real Estate Valuation (Cap Rate Method)
The application primarily uses the **Income Capitalization Approach** to value the real estate portfolio.
$$RE\ Valuation = \frac{Annual\ Net\ Operating\ Income\ (NOI)}{Cap\ Rate}$$
*Note: If NOI is not available or is zero, the system falls back to a manually defined `property_value`.*

### Real Estate Equity
$$RE\ Equity = RE\ Valuation - Total\ RE\ Debt$$

---

## 2. Numerical Constants & Data Points

The following numbers are used in the calculation (Source: `utils/agents/grand_strategist.py`):

| Variable | Value / Source | Description |
| :--- | :--- | :--- |
| **Cap Rate** | **6.0% (0.06)** | The capitalization rate used to convert income to value. |
| **Annual NOI** | **$90,000.00*** | Annual Net Operating Income (Income after expenses, before debt). |
| **Total RE Debt** | **Cell B21** | Total outstanding mortgage/debt balance (fetched from RE Dashboard). |
| **RE Reserves** | **$50,000.00*** | Cash held in real estate reserve accounts for repairs/opex. |
| **Property Value** | **$1,500,000.00*** | Fallback valuation used only if NOI is zero. |
| **Debt Service** | **Cell B20** | Annual principal and interest payments (used for DSCR analysis). |

*\* These values are currently set as placeholders in the `read_re_portfolio_summary()` function and are intended to be dynamically pulled from the RE Property Manager integration.*

---

## 3. Example Calculation

If your portfolio has an **Annual NOI of $90,000** and **$1,000,000 in Debt**:

1.  **Valuation:** $90,000 / 0.06 = \mathbf{\$1,500,000}$
2.  **Equity:** $1,500,000 - \$1,000,000 = \mathbf{\$500,000}$
3.  **Net Worth Contribution:** $\$500,000\ (Equity) + \$50,000\ (Reserves) = \mathbf{\$550,000}$

---

## 4. Source Code Reference
The logic resides in `utils/agents/grand_strategist.py` within the `calculate_net_worth()` function:

```python
cap_rate = 0.06
re_valuation = noi / cap_rate if noi > 0 else prop_val
re_equity = re_valuation - debt
total_nw = liquid_assets + re_equity + reserve
```
