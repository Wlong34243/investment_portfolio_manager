# Phases 2, 3 & 4 — Build Prompts
**Investment Portfolio Manager** | Bill | April 2026  
Run these after Phase 1 is fully complete (app.py running, Sheet has data, DRY_RUN=False).

---

## Session Map

| # | Prompt | Goal | Done When |
|---|--------|------|-----------|
| P2-A | yfinance Enrichment | Live prices, yields, sectors | 50+ positions enriched, no crashes |
| P2-B | Risk Analytics | Beta, stress tests, CAPM | Portfolio beta printed, 5 scenarios run |
| P2-C | Income Dashboard | Blended yield, top generators | Income tab shows KPIs + bar chart |
| P2-D | Writers + Risk Tab UI | Risk tab live, Sheet tabs writing | Risk_Metrics rows in Sheet, UI renders |
| P2-E | Performance Page | Benchmark chart, period returns | Performance page loads with chart |
| G2-A | Gemini: Review risk.py | Beta math peer review | No Critical/High issues remain |
| P2-F | CHANGELOG Phase 2 | Seal Phase 2 | Status line in CHANGELOG |
| P3-A | Realized G/L Parser | Tax lot import from Schwab CSV | ET wash sales parsed, IIPR lots all in |
| P3-B | Tax Page + Wash Sale UI | Tax Intelligence tab live | Wash sale banners visible, LT/ST split |
| G3-A | Gemini: Review tax pipeline | Isolation + accuracy check | No Critical issues in parser |
| P3-C | CHANGELOG Phase 3 | Seal Phase 3 | Status line in CHANGELOG |
| P4-A | FMP API Client | Earnings, news, ratings data | UNH profile + earnings load |
| P4-B | AI Analysis Engine | Claude API bull/bear extraction | JSON analysis returns for UNH/GOOG |
| P4-C | Research Page UI | Per-ticker research panel | Research page loads, graceful if no keys |
| G4-A | Gemini: Review AI pipeline | Key safety + cost control | No key exposure, caching confirmed |
| P4-D | CHANGELOG Phase 4 | Seal Phase 4 | Status line in CHANGELOG |

---

# PHASE 2 — Live Data + Risk Analytics

> ⚠️ Prereq: Phase 1 complete. app.py runs. Sheet has real data. DRY_RUN=False.

---

## P2-A — yfinance Enrichment Module

**Tool:** Claude Code  
**Done when:** 10+ positions show non-null Sector and Dividend_Yield. No crashes on any ticker.

```
Read CLAUDE.md sections: "Architecture Rule #8 yfinance Rate Limiting",
"Known Portfolio Edge Cases", and config.TOP_N_ENRICH.

Build utils/enrichment.py with two functions:

1. enrich_positions(df: pd.DataFrame) -> pd.DataFrame
   - Filter to top config.TOP_N_ENRICH (20) positions by market_value.
     Exclude CASH_TICKERS from enrichment entirely.
   - Bulk download 1yr daily closes in ONE call:
       data = yf.download(tickers_list, period="1y", auto_adjust=True, progress=False)
   - For each ticker extract: current_price, dividend_yield, sector, beta_raw
   - Handle these edge cases WITHOUT crashing:
       CRWV  -- recent IPO, use available history (may be < 1yr)
       BABA  -- ADR, yfinance may return sparse data
       ET    -- LP, yf.Ticker("ET").info["dividendYield"] may differ from pct
       SPY dust (0.00003 shares) -- below config.MIN_ENRICHMENT_QTY, skip
       Any ticker where yf.download returns empty DataFrame -- log warning, skip
   - For positions NOT in top 20: apply get_sector_fast() from csv_parser.py only
   - Cache results in st.session_state["enrichment_cache"] with timestamp.
     Return cached result if age < config.YFINANCE_CACHE_TTL (300s).
   - Return df with columns updated: Price, Sector, Dividend_Yield, Est_Annual_Income
     Est_Annual_Income = market_value * dividend_yield / 100

2. get_live_price(ticker: str) -> float | None
   - Single ticker price lookup via yf.Ticker(ticker).fast_info["last_price"]
   - Wrap entirely in try/except -- return None on ANY error
   - Never raise. Never block pipeline.

RULES:
   - Every yfinance call must be in its own try/except block
   - A single failed ticker must NOT block the entire enrichment run
   - Failed tickers: log ticker name + exception to st.warning() and continue
   - Do not import from RE Property Manager repo (zero cross-project imports)

After writing, run a test:
   python -c "
   import pandas as pd
   from utils.enrichment import enrich_positions
   from utils.csv_parser import parse_schwab_csv, inject_cash_manual
   df = parse_schwab_csv(open('-Positions-2025-12-31-082029.csv','rb').read())
   df = inject_cash_manual(df, 10000)
   df2 = enrich_positions(df)
   print(df2[['Ticker','Market_Value','Dividend_Yield','Sector']].head(10))
   "

Fix any errors. UNH, GOOG, AMZN, XOM should all show non-null sectors and yields.
```

> 📝 If BABA returns wrong data or zero yield, catch it and fall back to get_sector_fast("BABA SPONSORED ADR") which returns "International". Do not block the run.

---

## P2-B — Risk Analytics Module

**Tool:** Claude Code  
**Done when:** Portfolio beta prints (expect 0.80–1.10). All 5 stress scenarios run. UNH concentration alert fires.

```
Read CLAUDE.md sections: "Common Pitfalls 12-13", and config.py constants:
STRESS_SCENARIOS, RISK_FREE_RATE, MARKET_PREMIUM, BASE_VOLATILITY,
MIN_BETA_DATA_POINTS, CASH_TICKERS.

Build utils/risk.py -- exact port of Colab V3.2 risk logic:

1. calculate_beta(ticker, price_history, spy_returns) -> float
   - Covariance method ONLY (not regression):
       ticker_returns = price_history[ticker].pct_change().dropna()
       common_idx = ticker_returns.index.intersection(spy_returns.index)
       if len(common_idx) < config.MIN_BETA_DATA_POINTS: return 1.0
       beta = ticker_returns[common_idx].cov(spy_returns[common_idx]) / spy_returns[common_idx].var()
   - CASH_TICKERS always return 0.0
   - CRWV (< 30 data points): return 1.0 fallback, log warning
   - Clamp beta to range [-0.5, 3.5] -- outlier protection

2. calculate_portfolio_beta(df) -> float
   - invested_only = df[~df["Ticker"].isin(config.CASH_TICKERS)]
   - weighted_beta = sum(row.Weight * row.Beta for row in invested_only)
   - divide by sum of weights for invested positions only (not total incl. cash)
   - Return rounded to 4 decimal places

3. build_price_histories(df) -> dict[str, pd.Series]
   - Bulk download top 20 + SPY in single yf.download() call
   - Return dict: {ticker: pd.Series of adjusted close prices}
   - Include "SPY" always. Handle missing tickers gracefully.

4. calculate_correlation_matrix(df, price_histories) -> pd.DataFrame
   - top20 = df[~df["Ticker"].isin(config.CASH_TICKERS)].nlargest(20,"Market_Value")["Ticker"].tolist()
   - Build returns_df = pd.DataFrame of pct_change() for each ticker in top20
   - return returns_df.corr()
   - SPY dust position must NOT appear (filtered by CASH_TICKERS or min weight)

5. run_stress_tests(portfolio_value, portfolio_beta) -> list[dict]
   - For each (name, pct) in config.STRESS_SCENARIOS:
       impact = portfolio_value * portfolio_beta * pct
       new_value = portfolio_value + impact
   - Return: [{"scenario": name, "market_pct": pct, "impact": impact,
               "new_value": new_value, "impact_pct": impact/portfolio_value*100}]

6. capm_projection(portfolio_value, portfolio_beta) -> dict
   - expected_return = config.RISK_FREE_RATE + portfolio_beta * config.MARKET_PREMIUM
   - volatility = portfolio_beta * config.BASE_VOLATILITY
   - Use scipy.stats.norm:
       bad_return  = scipy.stats.norm.ppf(0.10, expected_return, volatility)
       good_return = scipy.stats.norm.ppf(0.90, expected_return, volatility)
   - Return dollar values:
       {"bad": portfolio_value*(1+bad_return),
        "expected": portfolio_value*(1+expected_return),
        "good": portfolio_value*(1+good_return),
        "expected_pct": expected_return*100}

7. concentration_alerts(df) -> list[str]
   - Flag position weight > config.SINGLE_POSITION_WARN_PCT
   - Flag sector weight > config.SECTOR_CONCENTRATION_WARN_PCT
   - UNH at ~9% should generate an alert at threshold 8%

Add a __main__ block that loads the CSV, runs all 6 functions, and prints results.
After writing, run: python utils/risk.py
```

> ⚠️ CRWV must return beta=1.0 with a logged warning — not raise an exception. Test this explicitly.

---

## P2-C — Income Dashboard

**Tool:** Claude Code  
**Done when:** Income tab shows 3 KPI cards, bar chart, ET and JPIE callout boxes.

```
Read CLAUDE.md "Income" section and config.DEFAULT_CASH_YIELD_PCT.

Add calculate_income_metrics() to pipeline.py (or utils/enrichment.py):

   calculate_income_metrics(df: pd.DataFrame) -> dict
     - projected_annual_income = sum(row.Est_Annual_Income for all non-cash rows)
     - cash_contribution = cash_value * config.DEFAULT_CASH_YIELD_PCT / 100
     - total_income = projected_annual_income + cash_contribution
     - blended_yield_pct = total_income / total_portfolio_value * 100
     - top_generators = df sorted by Est_Annual_Income desc, top 5 rows
     - return all of the above as a dict

Update app.py Income tab (replacing the Phase 1 placeholder):

   KPI row (3 st.metric cards):
     Projected Annual Income | Blended Yield % | Cash Contribution

   Bar chart (Plotly horizontal bar):
     Top 10 income generators by Est_Annual_Income
     Color: gold/amber palette (#F39C12, #E67E22, #D35400)

   Income table:
     Columns: Ticker | Description | Market Value | Yield % | Est Annual Income
     Filter to rows where Dividend_Yield > 0
     Sort by Est_Annual_Income descending

   Special callout boxes (st.info) for:
     ET  -- "Energy Transfer LP: high yield but generates K-1. Consult tax advisor."
     JPIE -- "JPMorgan Income ETF: primary income vehicle. Monthly distributions."

   Monthly breakdown: show total_income / 12 as "Estimated Monthly Income"

Add append_income_snapshot() to pipeline.py:
   - Builds Income_Tracking row from calculate_income_metrics() result
   - Columns: Date | Projected Annual Income | Blended Yield % |
              Top Generator Ticker | Top Generator Income |
              Cash Yield Contribution | Fingerprint
   - Fingerprint: date|projected_annual_income|blended_yield_pct
   - Appends to Income_Tracking tab (dedup by fingerprint)
   - Call this from write_to_sheets() after Holdings tabs
```

> 📝 If yfinance returns zero yield for ET, fall back to a hardcoded 8.5% stub with a note. ET's LP distributions are often misclassified by yfinance.

---

## P2-D — Phase 2 Writers + Risk Tab UI

**Tool:** Claude Code  
**Done when:** Click "Calculate Risk" → spinner → beta, CAPM chart, stress table, heatmap all render. Risk_Metrics tab gains a row.

```
Read PORTFOLIO_SHEET_SCHEMA.md for Risk_Metrics and Income_Tracking tab schemas.

1. Add write_risk_snapshot() to pipeline.py:
   - Accepts: beta_result dict, concentration_alerts list, stress_results list
   - Builds Risk_Metrics row:
       Date | Portfolio Beta | Top Position Conc % | Top Position Ticker |
       Top Sector Conc % | Top Sector | Stress -10% Impact | Fingerprint
   - Fingerprint: date|portfolio_beta|top_position_pct
   - Append to Risk_Metrics tab (dedup by fingerprint)
   - sanitize_for_sheets() before write. time.sleep(1.0) after.

2. Update utils/sheet_readers.py with two new cached readers:
   @st.cache_data(ttl=300)
   def get_risk_metrics() -> pd.DataFrame: ...

   @st.cache_data(ttl=300)
   def get_income_history() -> pd.DataFrame: ...

3. Update app.py Risk tab with:
   a. KPI row: Portfolio Beta | Expected 1yr Return | Worst Case (10th pct) | Best Case (90th pct)
   b. CAPM projection bar chart (bad/expected/good dollar values, horizontal)
   c. Stress test table:
       Columns: Scenario | Market Move | Portfolio Impact | New Value
       Color rows: losses = light red, gains = light green
   d. Correlation matrix heatmap (Plotly imshow, top 20 positions)
       Color scale: RdBu_r (red=negative, blue=positive correlation)
   e. Concentration alert banners (st.warning for each alert string)

4. Wire up the Risk tab:
   Add "Calculate Risk" button in Risk tab.
   On click: build_price_histories() -> calculate_beta() for each position ->
             calculate_portfolio_beta() -> run_stress_tests() -> capm_projection() ->
             write_risk_snapshot() -> st.rerun()
   Wrap in st.spinner("Fetching 1yr price history...")

5. Cache the price download:
   After build_price_histories(), store in st.session_state["price_histories"]
   with timestamp. Reuse if age < 300s.

Confirm all new Sheet writes use sanitize_for_sheets() and batch update.
```

---

## P2-E — Performance Page

**Tool:** Claude Code  
**Done when:** `pages/performance.py` loads in Streamlit. Portfolio chart renders. Benchmark lines visible.

```
Read CLAUDE.md section "Performance Page (pages/performance.py)"
and config.BENCHMARK_TICKERS = ["SPY", "VTI", "QQQM"].

Build pages/performance.py:

1. PAGE HEADER
   Title: "Portfolio Performance"
   Subheader: date range of available snapshots (first to latest in Daily_Snapshots)

2. KPI CARDS (from latest Daily_Snapshots row):
   Total Value | Total Cost | Total Unrealized G/L | Total Unrealized G/L %

3. PERIOD RETURNS TABLE
   Calculate from Daily_Snapshots:
     MTD  = (today_value - first_value_this_month) / first_value_this_month * 100
     QTD  = same logic for quarter start
     YTD  = same logic for Jan 1
     Since inception = (today - first_ever) / first_ever * 100
   Show as formatted table with green/red coloring

4. PORTFOLIO VS BENCHMARK CHART
   Download 1yr closes for SPY, VTI, QQQM via yf.download()
   Normalize all series to 100 at the first Daily_Snapshots date
   Plot: portfolio value line + 3 benchmark lines on same Plotly chart
   Color: portfolio = dark blue, SPY = orange, VTI = teal, QQQM = purple

5. PORTFOLIO VALUE OVER TIME (area chart)
   X = date, Y = Total Value from Daily_Snapshots
   Fill under curve. Hover shows date + value + unrealized G/L

6. CONTRIBUTION MODELING
   Input: monthly_contribution (slider: 0 to 10000, default 2000)
   Input: years_to_project (slider: 1 to 10, default 5)
   Calculate: for each year: value = value * (1 + expected_return) + monthly * 12
   Show as bar chart (year vs projected value)
   Show two scenarios: no contributions vs monthly contributions

Add @st.cache_data(ttl=300) to all Sheet reads in this page.
Benchmark data: cache in st.session_state with 300s TTL.

After building, run: streamlit run app.py
Navigate to Performance page. Verify chart renders.
```

> 📝 With only 1-2 Daily_Snapshots rows, period returns will be limited. Expected — they fill in over time. Do not fake data to fill gaps.

---

## G2-A — Gemini: Peer Review risk.py

**Tool:** Gemini CLI — run from repo root **before** running P2-F.

```bash
gemini --all-files -p "Review utils/risk.py against the requirements in CLAUDE.md:

1. BETA MATH: Uses covariance method, NOT regression.
   cov(ticker_returns, spy_returns) / var(spy_returns)
   Requires MIN_BETA_DATA_POINTS=30 common observations.
   Falls back to beta=1.0 if insufficient data. CASH_TICKERS always return 0.0.

2. PORTFOLIO BETA: Weighted average. Cash excluded from weight denominator.

3. CAPM PROJECTION: Uses scipy.stats.norm.ppf().
   10th percentile = bad case, 90th = good case.
   RISK_FREE_RATE and MARKET_PREMIUM read from config.py, not hardcoded.

4. STRESS TESTS: All 5 scenarios from config.STRESS_SCENARIOS. Beta-adjusted only.

5. CORRELATION: pct_change() on daily adjusted closes. Top 20 by value.
   SPY dust position does NOT appear. CASH_MANUAL does NOT appear.

6. EDGE CASES:
   CRWV -- < 30 data points, should return beta=1.0 with warning logged
   ET   -- LP, should not crash on dividend yield parsing
   UNH  -- 9% weight, concentration alert should fire

Report: file, line number, severity (Critical/High/Medium), exact fix.
Give confidence rating 1-10 on beta calculation correctness.
Give confidence rating 1-10 on CAPM math correctness."
```

> ✅ Fix all Critical and High issues before running P2-F. Target: beta confidence >= 7/10, CAPM confidence >= 7/10.

---

## P2-F — CHANGELOG Phase 2

```
Add a new entry to CHANGELOG.md for today following the exact format of
existing entries.

Include:
  - Files created/modified: utils/enrichment.py, utils/risk.py, pipeline.py,
    app.py (Income + Risk tabs), pages/performance.py,
    utils/sheet_readers.py (new cached readers)
  - Key decisions: bulk yfinance download, covariance beta method,
    scipy.stats.norm for CAPM, session_state price cache
  - Edge cases addressed: CRWV fallback, BABA ADR, ET LP yield, SPY dust skip
  - Deferred: Phase 3 transactions, Phase 4 AI research
  - Status line: "Status: Phase 2 complete. Safe to run: streamlit run app.py.
    Upload CSV -> Process -> Calculate Risk to see full dashboard.
    Risk_Metrics and Income_Tracking tabs accumulating history."
```

---

# PHASE 3 — Transaction History + Tax Intelligence

> **The Schwab Realized G/L file is already in the project:**  
> `All_Accounts_GainLoss_Realized_Details_20260330-220148.csv`
>
> Key observations from the actual file:
> - Covers 2025 tax year (01/01/2025 to 12/31/2025)
> - Multiple account sections: Individual 401(k) ...499, HSA ...217, Individual ...119
> - **ET has multiple wash sale lots with disallowed losses** (real data confirmed)
> - **IIPR has very large losses across many lots** (short and long term)
> - Some sections are empty ("no transactions available") — parser must skip cleanly
> - Dollar amounts have `$` prefix (e.g. `$155.28`) and negatives like `-$3.43`

---

## P3-A — Realized G/L Parser

**Tool:** Claude Code  
**Done when:** `__main__` output shows total lots, ST/LT split, wash sale count (expect multiple ET lots), total disallowed loss amount. IIPR large losses visible.

```
Read CLAUDE.md "Common Pitfalls", PORTFOLIO_SHEET_SCHEMA.md Transactions tab,
and examine the actual realized G/L file in the project:
  All_Accounts_GainLoss_Realized_Details_20260330-220148.csv

This file has a DIFFERENT structure from the positions CSV:
  - Row 1: report title with date range
  - Row 2: account section label (e.g. "Individual 401(k) ...499")
  - Row 3: column headers (Symbol, Name, Closed Date, Opened Date, Quantity,
           Proceeds Per Share, Cost Per Share, Proceeds, Cost Basis (CB),
           Gain/Loss ($), Gain/Loss (%), Long Term Gain/Loss, Short Term Gain/Loss,
           Term, Unadjusted Cost Basis, Wash Sale?, Disallowed Loss,
           Transaction Closed Date, ... 25 columns total)
  - Data rows: one lot per row
  - Section breaks: blank row then next account label then headers again
  - Some sections say "There are no transactions available..." -- skip

Build utils/gl_parser.py with:

1. parse_realized_gl(file_bytes: bytes) -> pd.DataFrame
   a. Read with header=None, encoding="utf-8-sig"
   b. Scan for rows containing "Symbol" to find header rows (multiple sections)
   c. For each section, extract lot rows until next blank/section break
   d. Skip sections that contain "no transactions available"
   e. Extract account_type from the label row above each header
   f. Apply clean_numeric() to all dollar/quantity columns
      NOTE: Dollar amounts have "$" prefix AND may be "-$3.43" for negatives
   g. Parse dates: Closed Date, Opened Date to datetime
   h. Map "Wash Sale?" column: "Yes" -> True, "No" -> False
   i. Map "Term" column: "Short Term" -> "ST", "Long Term" -> "LT"
   j. Calculate holding_days = (closed_date - opened_date).days
   k. Return DataFrame with GL_COLUMNS schema (add to config.py)

GL_COLUMNS (add to config.py):
  ticker, name, account_type, closed_date, opened_date, quantity,
  proceeds_per_share, cost_per_share, proceeds, cost_basis,
  gain_loss_dollars, gain_loss_pct, lt_gain_loss, st_gain_loss, term,
  unadjusted_cost_basis, wash_sale, disallowed_loss, holding_days, fingerprint

2. build_gl_fingerprint(row) -> str
   fingerprint = ticker|opened_date|closed_date|quantity|proceeds
   If duplicate (rare), append account_type to fingerprint.

3. Add append_gl_records() to pipeline.py:
   - Accepts gl_df from parse_realized_gl()
   - Reads existing fingerprints from Transactions tab
   - Filters to new rows only
   - sanitize_for_sheets() -> batch append -> time.sleep(1.0)
   - Return count of rows appended

After writing, run:
   python utils/gl_parser.py All_Accounts_GainLoss_Realized_Details_20260330-220148.csv

(add __main__ block that prints: total lots, ST lots, LT lots, wash sale count,
 disallowed loss total, top 5 losses, top 5 gains)
```

> ⚠️ Dollar amounts in this file use `$` prefix. `clean_numeric()` must strip `$` before parsing. Test: `clean_numeric("$155.28")` should return `155.28`, `clean_numeric("-$3.43")` should return `-3.43`.

---

## P3-B — Tax Page + Wash Sale UI

**Tool:** Claude Code  
**Done when:** Upload the actual G/L CSV → wash sale banner appears → LT/ST KPI cards show correct totals → IIPR visible as large loser.

```
Read CLAUDE.md "Tax Awareness" principle and Common Pitfall #6.
Read PORTFOLIO_SHEET_SCHEMA.md Transactions tab schema.

Build pages/tax.py:

1. PAGE HEADER
   Title: "Tax Intelligence & Realized G/L"
   Subheader: "Tax year: 2025  |  Based on Schwab Realized G/L export"

2. FILE UPLOADER
   st.file_uploader("Upload Schwab Realized G/L CSV", type=["csv"])
   On upload: parse_realized_gl() -> append_gl_records() -> st.rerun()

3. SUMMARY KPI ROW (from Transactions tab data):
   Total Realized Gain | Total Realized Loss | Net Realized G/L |
   LT Net G/L | ST Net G/L | Wash Sales (count) | Disallowed Losses
   Color: green for gains, red for losses

4. TAX TREATMENT BREAKDOWN
   Pie chart: LT gains vs ST gains vs LT losses vs ST losses
   Note: "Long-term gains taxed at preferential rates. Short-term at ordinary income."

5. WASH SALE ALERT PANEL
   Filter to rows where wash_sale == True
   Show st.warning banner: "X wash sale lots found. Disallowed losses: $Y"
   Display table: Ticker | Opened | Closed | Loss | Disallowed | Account
   Note: "Disallowed losses are added to cost basis of replacement shares."
   Flag ET specifically: ET had multiple wash sale lots in 2025.

6. HOLDING PERIOD TABLE
   Closed lots grouped by term (LT / ST):
     Columns: Ticker | Account | Opened | Closed | Days Held | Proceeds | G/L | Term
   Sort by gain_loss_dollars ascending (biggest losses first for harvesting review)
   Add filter: show All / LT only / ST only / Wash Sales only

7. REALIZED G/L BY TICKER
   Group by ticker, sum gain_loss_dollars
   Horizontal bar chart: green for net gains, red for net losses
   Show top 10 winners and top 10 losers side by side

8. TAX LOT SUMMARY BY ACCOUNT
   Group by account_type, sum ST and LT gain/loss
   Show as table with subtotals

Add Tax page to app.py navigation:
   st.page_link("pages/tax.py", label="Tax & G/L", icon="🧾")

All Sheet reads in this page must use @st.cache_data(ttl=300).
```

> ⚠️ Wash sale rows must be visually prominent — use `st.warning()` or a colored callout, not just a number in a table. Bill is a CPA. This matters.

> 📝 IIPR: large losses across many lots in 2024-2025. Surface this clearly. May be a tax-loss harvesting candidate worth flagging.

---

## G3-A — Gemini: Review Tax Pipeline

**Tool:** Gemini CLI — run from repo root after P3-B.

```bash
gemini --all-files -p "Review utils/gl_parser.py and pages/tax.py.

Check utils/gl_parser.py:
1. Does parse_realized_gl() correctly handle ALL of these in the actual CSV?
   - Multiple account sections (Individual 401k, HSA, Individual ...119, etc.)
   - Sections that say 'no transactions available' -- must be skipped cleanly
   - Blank rows between sections -- must not crash
   - Dollar amounts with '$' prefix -- must clean correctly
   - Negative values shown as '-$3.43' -- must parse as -3.43
   - Wash Sale? column: 'Yes' rows with Disallowed Loss amounts
   - ET wash sale lots specifically (multiple in the actual file)
   - IIPR large loss positions (many lots, confirm all parsed)
2. Is build_gl_fingerprint() unique per lot?
3. Does append_gl_records() correctly dedup on fingerprint before appending?

Check pages/tax.py:
4. Are wash sale alerts visually prominent (not buried in a table)?
5. Is the LT vs ST distinction clear to a CPA-level user?
6. Is there any path where a crash in the G/L parser breaks the main Holdings tab?
   (Must be fully isolated -- G/L parse failure must not affect Phase 1/2 features)

Rate each: Critical / High / Medium / Low.
Provide exact line-number fixes for anything Critical or High."
```

---

## P3-C — CHANGELOG Phase 3

```
Add a new entry to CHANGELOG.md for today following the exact format.

Include:
  - Files created/modified: utils/gl_parser.py, pipeline.py (append_gl_records),
    pages/tax.py, config.py (GL_COLUMNS added)
  - Key decisions: lot-level parsing, fingerprint uniqueness, wash sale surfacing
  - Real data notes: ET wash sales confirmed, IIPR large losses parsed correctly
  - Deferred: Phase 4 AI research
  - Status line: "Status: Phase 3 complete. Safe to run: streamlit run app.py.
    Upload Positions CSV for Holdings/Risk/Income.
    Upload Realized G/L CSV in Tax tab for wash sale analysis."
```

---

# PHASE 4 — AI Research Assistant

> **Two API keys required for full functionality. Both are optional — app must work without them.**
>
> 1. **Financial Modeling Prep (FMP)** — earnings transcripts, analyst ratings, news  
>    Get key: financialmodelingprep.com/developer/docs  
>    Add to secrets.toml: `fmp_api_key = "YOUR_KEY"`
>
> 2. **Anthropic Claude API** — bull/bear thesis extraction  
>    Get key: console.anthropic.com  
>    Add to secrets.toml: `anthropic_api_key = "YOUR_KEY"`
>
> Without keys: Research page shows graceful placeholders. Phases 1-3 are unaffected.

---

## P4-A — FMP API Client

**Tool:** Claude Code  
**Done when:** UNH profile + earnings load with key set. All functions return None (not crash) without key.

```
Read CLAUDE.md "Research Page" section and config.py FMP_API_KEY.

Build utils/fmp_client.py:

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
API key from config.FMP_API_KEY (st.secrets["fmp_api_key"])

1. get_earnings_transcript(ticker: str, year: int, quarter: int) -> str | None
   Endpoint: GET /earning_call_transcript/{ticker}?quarter={q}&year={y}&apikey=...
   Return the transcript text field, or None if not available.
   Wrap in try/except. Log st.warning on failure.

2. get_latest_earnings(ticker: str) -> dict | None
   Endpoint: GET /earnings-surprises/{ticker}?apikey=...
   Return most recent: {date, eps_actual, eps_estimated, revenue}
   Calculate eps_surprise_pct = (actual - estimated) / abs(estimated) * 100

3. get_analyst_ratings(ticker: str) -> dict | None
   Endpoint: GET /grade/{ticker}?limit=10&apikey=...
   Return: {buy_count, hold_count, sell_count, latest_action, latest_firm}

4. get_company_profile(ticker: str) -> dict | None
   Endpoint: GET /profile/{ticker}?apikey=...
   Return: {description, ceo, employees, sector, industry, exchange}

5. get_news(ticker: str, limit: int = 5) -> list[dict]
   Endpoint: GET /stock_news?tickers={ticker}&limit={limit}&apikey=...
   Return list of: {title, date, url, summary}

CACHING:
   Cache key: f"{function_name}_{ticker}_{date.today()}"
   Store in st.session_state. TTL: 3600s for transcripts, 300s for news.

RATE LIMITING:
   Add call counter in st.session_state["fmp_call_count"].
   If count > 200: show st.warning("Approaching FMP daily limit") and cache-only mode.

If FMP API key is not set: stub all functions to return None and log a warning.
The app must not crash when FMP is unavailable.

After writing, test with UNH:
   python -c "
   from utils.fmp_client import get_company_profile, get_latest_earnings, get_news
   print(get_company_profile('UNH'))
   print(get_latest_earnings('UNH'))
   print(get_news('UNH', limit=3))
   "
```

> 📝 FMP free tier: ~250 calls/day. With 50+ positions, the call counter matters — without caching you'll hit the limit quickly.

---

## P4-B — AI Analysis Engine

**Tool:** Claude Code  
**Done when:** `analyze_earnings_transcript()` returns valid JSON with all 6 keys. Returns placeholder dict (not crash) without API key.

```
Read CLAUDE.md "Research Page" section. Read config.py ANTHROPIC_API_KEY.

Build utils/ai_research.py:

1. analyze_earnings_transcript(ticker, transcript, company_profile) -> dict | None
   Call Claude API (claude-sonnet-4-20250514) with:
   
   System prompt:
     "You are a buy-side equity analyst. Analyze this earnings call transcript.
      Be concise and factual. Focus on what matters for a long-term investor."
   
   User prompt:
     "Ticker: {ticker}
      Company: {company_profile['description'][:500]}
      
      TRANSCRIPT:
      {transcript[:8000]}
      
      Respond in JSON only (no markdown, no code fences) with these exact keys:
        bull_thesis: string (3-5 sentences, strongest bull case from the call)
        bear_thesis: string (3-5 sentences, main risks and concerns mentioned)
        key_metrics: list of strings (up to 5 specific metrics cited by management)
        guidance_sentiment: one of [positive, neutral, negative, mixed]
        analyst_tone_score: integer 1-10 (1=very negative, 10=very positive)
        summary: string (2-3 sentence plain-English summary)"
   
   Parse JSON response. Handle JSON parse errors -- return None and log warning.

2. score_position(ticker, holdings_row, ai_analysis, latest_earnings) -> dict
   eps_beat = 1 if eps_surprise_pct > 5 else (-1 if eps_surprise_pct < -5 else 0)
   ai_score = (ai_analysis["analyst_tone_score"] - 5) / 5  # normalize to -1 to +1
   momentum = 1 if unrealized_pct > 10 else (-1 if unrealized_pct < -10 else 0)
   composite_score = (eps_beat + ai_score + momentum) / 3  # range -1 to +1
   signal_label: "Strong Buy" / "Buy" / "Hold" / "Watch" / "Review"
   Return: {composite_score, eps_beat, ai_score, momentum, signal_label}

IMPORTANT: These are research signals only, not trading recommendations.
Every score display must include: "For informational purposes only.
All investment decisions are Bill's."

API key handling:
   If ANTHROPIC_API_KEY is empty: return placeholder dict with all fields
   set to "API key not configured". App must not crash when key is missing.
```

> ⚠️ Hard-limit transcript to first 8000 characters to control Claude API costs. Never pass entire raw transcript.  
> 📝 Model string: `claude-sonnet-4-20250514` — use Sonnet, not Opus or Haiku.

---

## P4-C — Research Page UI

**Tool:** Claude Code  
**Done when:** Research page loads. Ticker dropdown populates. Company profile shows for UNH/GOOG. Graceful "not configured" message if no API keys.

```
Read CLAUDE.md "Research Page (pages/research.py)" section.

Build pages/research.py:

1. PAGE HEADER
   Title: "AI Research Panel"
   Subheader: "Earnings analysis, news, and signals -- for informational use only"
   st.warning("These are AI-generated research summaries, not investment advice.
               All decisions are yours.")

2. TICKER SELECTOR
   st.selectbox: populate from Holdings_Current (tickers sorted by weight)
   Show current stats for selected ticker:
     Market Value | Weight | Unrealized G/L% | Sector | Dividend Yield

3. COMPANY OVERVIEW
   Call get_company_profile(ticker)
   Show: description (first 300 chars), sector, industry, exchange
   Analyst ratings: Buy/Hold/Sell counts as a horizontal bar

4. LATEST EARNINGS
   Call get_latest_earnings(ticker)
   Show: EPS Actual | EPS Estimated | Surprise% | Revenue
   Color: green if beat, red if miss

5. AI EARNINGS ANALYSIS
   "Analyze Latest Earnings Call" button
   On click:
     a. get_earnings_transcript(ticker, year, quarter)
     b. analyze_earnings_transcript(ticker, transcript, profile)
     c. Use st.spinner("Analyzing earnings call...")
   Show results:
     Left column:  Bull Thesis (green callout box)
     Right column: Bear Thesis (red callout box)
     Below: Key Metrics (bullet list), Guidance Sentiment badge, Tone Score
     Below: Plain English Summary

6. SIGNAL SCORE
   Call score_position() and display composite signal
   Colored badge: green=Buy, grey=Hold, red=Review
   Component breakdown (EPS beat, AI score, momentum) in small table
   ALWAYS show disclaimer under score: "For informational purposes only."

7. NEWS FEED
   Call get_news(ticker, limit=5)
   Card list: headline, date, source, 1-sentence summary, link button

8. RESEARCH HISTORY
   Store each analysis in st.session_state["research_cache"][ticker]
   Show "Last analyzed: {timestamp}" and allow re-run

Add Research page to app.py navigation.
All external API calls wrapped in try/except.
If any API call fails: show "Data unavailable" message rather than crashing.

After building, run: streamlit run app.py
Navigate to Research. Select UNH or GOOG.
Verify company profile loads even if AI key not configured.
```

> ⚠️ Signal score disclaimer ("For informational purposes only") must be visible every time a score is shown. Non-negotiable.

---

## G4-A — Gemini: Review AI Pipeline

**Tool:** Gemini CLI — run from repo root after P4-C, before P4-D.

```bash
gemini --all-files -p "Review utils/ai_research.py, utils/fmp_client.py, and pages/research.py:

1. API KEY SAFETY:
   - Is the Anthropic API key ever printed, logged, or exposed in UI?
   - Is the FMP API key ever visible in URL params or st.write output?

2. CRASH ISOLATION:
   - If FMP returns 401 (invalid key), does the page crash or show graceful message?
   - If Claude API returns 500, does the page crash or show graceful message?
   - If transcript is empty string, does analyze_earnings_transcript() crash?
   - If selected ticker has no FMP data (e.g. CRWV), is that handled?

3. DISCLAIMER COMPLIANCE:
   - Is 'For informational purposes only' visible near every score/signal?
   - Is there any path where a signal could be mistaken for a buy/sell order?

4. COST CONTROL:
   - Is the Claude API call limited to transcript[:8000] to control token costs?
   - Is caching preventing redundant Claude API calls for same ticker same day?
   - Is the FMP call counter working?

5. DATA QUALITY:
   - Is the JSON parsing of Claude's response robust to markdown fences?
   - Could the analyst_tone_score be out of range 1-10?
   - Is the composite signal formula correct?

Rate each: Critical / High / Medium / Low.
Flag anything that could incur unexpected API costs or expose keys."
```

---

## P4-D — CHANGELOG Phase 4

```
Add a new entry to CHANGELOG.md for today following the exact format.

Include:
  - Files created/modified: utils/fmp_client.py, utils/ai_research.py,
    pages/research.py, app.py (navigation updated)
  - Key decisions: 1hr cache for transcripts, 8000-char transcript limit,
    composite signal formula, graceful degradation when API keys missing
  - Security: API keys never logged or displayed
  - Known limitations: FMP free tier 250 calls/day, transcript availability varies
  - Deferred: Phase 5 rebalancing and deployment
  - Status line: "Status: Phase 4 complete. Safe to run: streamlit run app.py.
    All pages operational: Holdings, Income, Risk, Performance, Tax, Research.
    Set fmp_api_key and anthropic_api_key in secrets.toml for full AI features.
    Without keys: Research page shows graceful placeholders."
```

---

# Phase 5 Preview — Rebalancing + Deploy

| Prompt | Goal | Done When |
|--------|------|-----------|
| P5-A: Target Allocation + Drift Alerts | Read Target_Allocation tab, show drift vs actual | Rebalancing suggestions visible for overweight positions |
| P5-B: Unified Net Worth View | READ ONLY pull from RE Sheet | RE NOI + Liquid portfolio + Reserve shown together |
| P5-C: Deploy to Streamlit Cloud | Push to GitHub, configure secrets | Live URL accessible, password gate working |

**P5-A notes:** Target_Allocation tab is manual entry by Bill. App reads targets and shows drift. Alert fires when actual weight deviates > `config.rebalance_threshold_pct` (default 5%). Flag if rebalancing would trigger ST capital gains.

**P5-B notes:** Cross-reference with RE Sheet (READ ONLY). Never write to RE Sheet. Import only. Combined net worth = RE + Liquid + Reserve.

**P5-C notes:** Add all secrets.toml values in Streamlit Cloud dashboard under App Settings > Secrets. Set `DRY_RUN=False` in config.py before deploying. Test password gate on live URL before sharing.

---

## Agent Architecture Notes (Future Phase 5+)

From the `agents` planning file — design principles to keep in mind when building Phase 4/5:

- **Dynamic Prompt Injection:** Design LLM prompts to fetch Config and Target_Allocation from the Sheet first. AI reads the rules from the board before looking at the pieces.
- **Pipeline Phases as Agent Boundaries:** Treat Phase 1-3 Python scripts as "Tools" future agents can call. An orchestrator won't need to learn gspread — it calls the function you already built.
- **Fingerprints for Grounded Reasoning:** Instruct AI to cite specific fingerprint rows when making observations (e.g., "Based on risk snapshot 2026-03-29|0.85|9.0..."). Forces the model to use deterministic data, not hallucinate.
- **LangGraph vs CrewAI:** LangGraph for strict state machines (safer for financial data). CrewAI for autonomous multi-agent debate. LangGraph is likely the better choice here.
