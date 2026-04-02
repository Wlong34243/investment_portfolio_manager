# AI Feature Prompts — Claude Code (Final)
## 12 Agents | All Gemini 2.5 Pro | Paste into Claude Code in sequence

---

## Pre-Session Context Prompt

```
Read CLAUDE.md, config.py, CHANGELOG.md, ai_agents, and ai_agents2 project files. Note:
- ALL AI uses Gemini 2.5 Pro via google-genai SDK
- 12 specialized agents, each with a focused domain
- Architecture: LLM → JSON → Python → Sheet (deterministic)
- No auto-trading. Ever.
Confirm you understand before we proceed.
```

---

## Foundation Prompts

### Prompt G-CORE — Gemini 2.5 Pro Core Wrapper

```
Build utils/gemini_client.py — the core wrapper ALL 12 agents call through.

Use google-genai SDK (pip install google-genai).

1. get_gemini_client():
   - from google import genai
   - client = genai.Client(api_key=config.GEMINI_API_KEY)
   - Return None if key empty. Cache client at module level.

2. ask_gemini(prompt: str, system_instruction: str = None, json_mode: bool = False, max_tokens: int = 2000) -> str:
   - client.models.generate_content() with model=config.GEMINI_MODEL
   - If json_mode: append "Respond ONLY with a JSON object. No preamble, no markdown fences." to system instruction; set response_mime_type="application/json"
   - On error: log, return empty string

3. ask_gemini_json(prompt: str, system_instruction: str = None, max_tokens: int = 2000) -> dict:
   - Calls ask_gemini(json_mode=True), parses with json.loads()
   - On parse failure: try extracting JSON from markdown fences
   - On total failure: return {"error": "Failed to parse", "raw": response[:300]}

4. SAFETY_PREAMBLE = "You must NEVER recommend executing specific trades. You provide analysis and considerations only. All buy/sell decisions are the investor's."

Error handling: google.genai exceptions → log + safe defaults. Rate limit → wait 30s, retry once.
Update config.py: add GEMINI_MODEL, GEMINI_MAX_TOKENS, GEMINI_API_KEY.
Update requirements.txt: replace 'anthropic' with 'google-genai'.
```

### Prompt A1 — FMP Client

```
Build utils/fmp_client.py — Financial Modeling Prep API wrapper.

Functions (all cached @st.cache_data with ttl=86400, all with timeout=10, all return safe defaults on failure):

1. get_earnings_calendar(tickers: list[str], days_ahead=14) -> pd.DataFrame
2. get_earnings_transcript(ticker: str, year=None, quarter=None) -> str (truncate to 4000 chars)
3. get_key_metrics(ticker: str) -> dict (pe, pb, forward_pe, roe, debt_to_equity, fcf_per_share)
4. get_historical_pe(ticker: str, years=5) -> pd.DataFrame (year, pe_ratio — for Agent 5)
5. get_company_profile(ticker: str) -> dict (sector, industry, description, market_cap, beta)
6. screen_by_metrics(criteria: dict) -> pd.DataFrame (for Agent 9 — screen stocks by metric thresholds)
   - Endpoint: /v3/stock-screener?apikey={key}&{params}
   - Accept criteria like: marketCapMoreThan, peRatioLowerThan, dividendYieldMoreThan, sector
   - Return: ticker, company_name, market_cap, pe, dividend_yield, sector

Never expose API key in errors. Test block at bottom with AMZN.
```

### Prompt A2 — Finnhub Client

```
Build utils/finnhub_client.py — Finnhub API wrapper.

1. get_company_news(ticker, days_back=7) -> list[dict] (headline, source, datetime, url, summary; limit 10; cache 30min)
2. get_basic_financials(ticker) -> dict (52wkHigh/Low, forwardPE, dividendYield, beta; cache 1hr)
3. get_earnings_surprises(ticker) -> list[dict] (last 4 quarters: period, actual, estimate, surprise)
4. get_market_news(category="general") -> list[dict] (top market headlines; cache 30min — for Agent 10)

All: catch exceptions, return empty defaults, guard st imports.
```

### Prompt G1 — Technical Indicators

```
Build utils/technicals.py using pandas-ta.

1. calculate_technical_indicators(ticker, price_history=None) -> dict
   - RSI(14), SMA50, SMA200, MACD
   - Derived signals: rsi_signal, ma_signal (Golden/Death Cross), price_vs_sma50/200, macd_signal
   - Handle IPOs with <200 days data

2. get_combined_signal_score(technicals) -> dict
   - +1 bullish, -1 bearish, 0 neutral per signal
   - Normalize to -1.0 to 1.0
   - Return: {score, label, components}

Handle ImportError for pandas-ta gracefully.
```

---

## Agents 1-4 (Core: Risk, Tax, Income, Earnings)

### Prompt AGENT-1 — Concentration Hedger

```
Build utils/agents/concentration_hedger.py.

1. scan_concentration_risks(holdings_df) -> list[dict]
   - Positions > SINGLE_POSITION_WARN_PCT, sectors > SECTOR_CONCENTRATION_WARN_PCT
   - Fetch 50-day MA, flag if price < 50MA
   - Return: {ticker, weight, risk_type, price_vs_ma, severity}

2. generate_hedge_suggestions(risks, holdings_df) -> list[dict]
   - Gemini call per flagged risk. System: SAFETY_PREAMBLE + "Portfolio risk advisor. Suggest 2-3 hedging strategies for concentrated positions. Consider: trimming, sector rotation, protective options (educational only), diversification."
   - Return: {ticker, suggestions: [{strategy, description, impact_estimate}]}

3. check_on_page_load(holdings_df) -> list[str]
   - Quick scan, no LLM. Return alert strings for breached thresholds.

Add alerts to Holdings tab above KPIs. "Get Hedging Ideas" button triggers full analysis.
```

### Prompt AGENT-2 — Tax-Aware Rebalancer

```
Build utils/agents/tax_rebalancer.py.

1. get_target_allocation() -> pd.DataFrame (read Target_Allocation tab, cache 300s)
2. calculate_drift(holdings_df, targets_df) -> pd.DataFrame (actual vs target, drift, breach flags)
3. get_tax_lots_for_ticker(ticker) -> pd.DataFrame (lot_date, quantity, cost_basis, unrealized_gl, holding_days, term, wash_sale_risk)
4. check_wash_sale_risk(ticker, realized_gl_df) -> dict (at_risk, last_loss_date, loss_amount, warning)
5. generate_rebalance_proposals(drift_df, holdings_df) -> list[dict]
   - "Rule of Three" per overweight strategy via Gemini.
   - System: SAFETY_PREAMBLE + "Tax-aware rebalancing advisor for a CPA. 3 options per overweight position. Consider LT gains preference, wash sale rules, portfolio impact. Reference specific lots. JSON: {options: [{label, description, tax_impact, lots_to_sell: [{date, quantity, gain_loss, term}], estimated_tax}]}"

NEVER writes to Sheet. Read-only analysis.
```

### Prompt D2 — Rebalancing Page

```
Build pages/rebalancing.py.
1. Header with warning: "Analysis only."
2. Allocation drift: Target vs Actual bar chart + drift table
3. Rebalancing proposals: "Generate Tax-Aware Proposals" button → Rule of Three cards
4. Wash sale monitor: tickers with recent loss sales + window status
5. Holding period dashboard: LT vs ST pie chart + positions approaching 1-year
Handle empty states gracefully.
```

### Prompt AGENT-3 — Yield & Cash Sweeper

```
Build utils/agents/cash_sweeper.py.

1. analyze_cash_position(holdings_df) -> dict (cash_value, cash_yield, alternatives with yield comparison)
2. generate_cash_deployment_suggestion(cash_analysis, holdings_df) -> dict
   - Gemini: SAFETY_PREAMBLE + "Yield optimization advisor. Compare money market vs income ETF yields. Suggest reallocation with amounts. Consider risk difference. JSON: {recommendation, proposed_action, yield_improvement, risk_note}"
3. get_cash_sweep_alert(holdings_df) -> str or None (quick check: if cash > 5% AND any position yields 2x cash)

Add alert to Income tab. "Optimize Cash" button for full analysis.
```

### Prompt AGENT-4 — Earnings Sentinel

```
Build utils/agents/earnings_sentinel.py.

1. scan_upcoming_earnings(holdings_df, days_ahead=14) -> pd.DataFrame
2. generate_earnings_alerts(upcoming_df, holdings_df, max_alerts=5) -> list[dict]
   - Gemini per ticker: 2-sentence pre-earnings alert. Plain text, not JSON.
   - time.sleep(1.5) between calls. Cache 6hr.
3. generate_post_earnings_analysis(ticker, transcript, holdings_df) -> dict
   - Gemini JSON: {bull_points, bear_points, sentiment, key_metrics, portfolio_implication}
4. get_earnings_badge(days_until) -> str ("🔴"/"🟡"/"🟢")
```

### Prompt C2 — Earnings Alerts on Dashboard

```
Add "Upcoming Earnings" section above KPI cards in Holdings tab.
- scan_upcoming_earnings() cached in session_state
- If any within 14 days: st.info bar + expandable calendar table
- "Generate AI Alerts" button for top 5 by weight
```

---

## Agents 5-7 (Value, Options, Correlation)

### Prompt AGENT-5 — Valuation & Accumulation

```
Build utils/agents/valuation_agent.py.

1. get_valuation_snapshot(ticker) -> dict (current_pe, avg_5yr_pe, pe_discount_pct, is_below_average)
2. scan_valuation_opportunities(holdings_df, watchlist=None) -> list[dict] (sorted by discount)
3. generate_accumulation_plan(ticker, deploy_amount, valuation_data, holdings_df) -> dict
   - Gemini JSON: {analysis, shares_to_buy, new_weight_pct, entry_rationale, risk_factors, trigger_condition}

Surface on Research page as "Valuation Monitor" section.
```

### Prompt AGENT-6 — Covered Call Generator

```
Build utils/agents/options_agent.py.

1. find_covered_call_candidates(holdings_df) -> pd.DataFrame (qty >= 100: GOOG 100.27, XOM 101.73)
2. get_options_chain(ticker) -> pd.DataFrame (yfinance options, filter 5-15% OTM, within DTE range)
3. generate_covered_call_proposal(ticker, chain_df, holdings_df) -> dict
   - Gemini JSON: {strategies: [{label, strike, expiry, premium, annualized_yield_pct, max_upside_cap_pct, assignment_probability, recommendation}]}
4. estimate_monthly_premium_potential(holdings_df) -> dict

Surface on Research page for eligible tickers + "Options Income" on Income tab.
Prominent disclaimer: "Educational analysis only. Execute independently."
```

### Prompt AGENT-7 — Beta & Correlation Optimizer

```
Build utils/agents/correlation_optimizer.py.

1. detect_correlation_spikes(holdings_df, price_histories, threshold=0.80) -> list[dict]
   - Rolling 30-day correlation. Specifically check CORZ/IREN vs QQQM.
2. calculate_diversification_benefit(holdings_df, corr_matrix) -> dict (diversification_ratio, effective_positions)
3. generate_optimization_suggestions(spikes, holdings_df) -> dict
   - Gemini JSON: {alerts: [{pair, correlation, suggestion, impact}], overall_assessment, diversification_score}
4. run_background_risk_scan(holdings_df) -> list[str] (quick alerts, no LLM)

Add to Risk tab: background alerts + "Optimize Diversification" button.
```

---

## Agents 9-10 (Discovery + Macro — Public.com inspired)

### Prompt AGENT-9 — Thesis Screener

```
Read the Public.com "Generated Assets" concept: users type a natural language investment thesis and AI screens thousands of stocks to build a ranked list.

Build utils/agents/thesis_screener.py:

1. parse_thesis_to_criteria(thesis: str) -> dict
   - Call Gemini 2.5 Pro via ask_gemini_json():
     System: SAFETY_PREAMBLE + "You are a quantitative stock screener. The investor has described an investment thesis in plain English. Translate it into concrete screening criteria that can be passed to a stock screening API. Respond ONLY with JSON: {sector: str or null, min_market_cap: float or null, max_pe: float or null, min_dividend_yield: float or null, min_revenue_growth: float or null, min_roe: float or null, max_debt_to_equity: float or null, keywords: [str], description: str}"
   - User prompt: the raw thesis string
   - Return parsed criteria dict

2. screen_stocks(criteria: dict) -> pd.DataFrame
   - Call fmp_client.screen_by_metrics() with the translated criteria
   - If FMP returns <3 results, broaden criteria (remove one constraint) and retry once
   - Return top 20 results sorted by market cap descending
   - Add columns: in_portfolio (bool — already held?), current_weight (if held)

3. rank_and_explain(thesis: str, screened_df: pd.DataFrame, holdings_df: pd.DataFrame) -> dict
   - Call Gemini 2.5 Pro via ask_gemini_json():
     System: SAFETY_PREAMBLE + "You are an investment research analyst. The investor described a thesis and we've screened for matching stocks. Rank the top 5 candidates and explain why each fits the thesis. Note which ones the investor already holds. Respond ONLY with JSON: {thesis_summary: str, ranked_picks: [{rank: int, ticker: str, company: str, rationale: str, already_held: bool, suggested_weight: str}], portfolio_overlap_note: str}"
   - Return parsed dict

4. Build UI: Add a "Thesis Screener" section to the Research page.
   - st.text_area("Describe your investment thesis")
   - Examples shown as clickable chips:
     "Infrastructure stocks with growing free cash flow"
     "AI companies with high revenue growth but still undervalued"
     "Dividend aristocrats yielding above 3%"
     "International companies benefiting from weak dollar"
   - "Screen Stocks" button → shows ranked table with rationale
   - Cache results in session_state with 1hr TTL
```

### Prompt AGENT-10 — Macro Event Monitor

```
Read Public.com's conditional triggers: "If CPI is >4%, sell consumer staples and rotate into tech" and "If the Fed cuts rates, trim bank stocks."

Build utils/agents/macro_monitor.py:

1. get_fred_client():
   - from fredapi import Fred
   - Fred(api_key=config.FRED_API_KEY)
   - Return None if key empty

2. get_macro_snapshot() -> dict
   - Fetch from FRED API (cache 24hr):
     - CPI: series_id='CPIAUCSL' (latest value + 1yr trend direction)
     - Fed Funds Rate: series_id='FEDFUNDS'
     - 10Y Treasury: series_id='DGS10'
     - Unemployment: series_id='UNRATE'
     - VIX: from yfinance ('^VIX' latest close)
   - Return: {cpi: float, cpi_trend: str, fed_rate: float, treasury_10y: float, unemployment: float, vix: float, vix_signal: str}

3. detect_macro_triggers(macro_data: dict, holdings_df: pd.DataFrame) -> list[dict]
   - Rule-based checks (no LLM):
     - VIX > 25 → "Elevated volatility: review hedging strategies"
     - VIX > 35 → "Crisis-level volatility: consider defensive rotation"
     - CPI rising + CPI > 3.5% → "Inflation elevated: favor energy, commodities"
     - Fed rate decreased from last reading → "Rate cut detected: evaluate bank exposure, favor growth"
     - 10Y yield > 5% → "High yield environment: bonds competitive with equities"
   - Return list: {trigger, description, severity, relevant_sectors}

4. generate_macro_strategy(triggers: list[dict], holdings_df: pd.DataFrame) -> dict
   - Call Gemini 2.5 Pro via ask_gemini_json():
     System: SAFETY_PREAMBLE + "You are a macro-economic investment strategist. The investor holds a diversified portfolio of ~$480K. Given current macro conditions and detected triggers, suggest portfolio positioning adjustments. Reference the investor's actual sector exposures and specific holdings. Respond ONLY with JSON: {macro_outlook: str, risk_level: str ('Low'/'Moderate'/'Elevated'/'High'), sector_rotations: [{from_sector: str, to_sector: str, rationale: str, specific_holdings_affected: [str]}], defensive_moves: [str], opportunity_plays: [str]}"
   - Return parsed dict

5. Build UI: Add "Macro Dashboard" section to either Holdings tab or a dedicated area.
   - KPI cards: CPI, Fed Rate, 10Y Yield, VIX (with color coding)
   - If any triggers fire: show alert bar with descriptions
   - "Generate Macro Strategy" button → Gemini analysis
   - Cache macro data in session_state with 24hr TTL

Also add 'fredapi' to requirements.txt and FRED_API_KEY to config.py.
```

---

## Agents 11-12 (Proactive Insights)

### Prompt AGENT-11 — Price Movement Narrator

```
Read the ai_agents project context. We are adding Agent 11: "The Price Movement Narrator".
Read utils/finnhub_client.py for the get_company_news() function.
Read config.py. Add SIGNIFICANT_MOVE_PCT = 3.0 if it doesn't exist.

Build utils/agents/price_narrator.py:

1. detect_significant_moves(holdings_df: pd.DataFrame, threshold_pct: float = None) -> list[dict]
   - Fallback threshold_pct to config.SIGNIFICANT_MOVE_PCT
   - Scan holdings_df for positions where absolute value of 'Daily Change %' >= threshold_pct
   - Return list of dicts: {ticker, change_pct, market_value, day_pnl}
   - Sort by absolute day_pnl descending (biggest dollar impact first)

2. generate_movement_explanation(ticker: str, change_pct: float, date_str: str) -> dict
   - Call finnhub_client.get_company_news(ticker, days_back=2)
   - If no news, return {"explanation": "No recent news detected to explain this movement.", "catalyst_type": "Unknown"}
   - Call Gemini 2.5 Pro via ask_gemini_json():
     System: SAFETY_PREAMBLE + "You are a sharp, concise financial analyst. Given a stock ticker, its daily percentage change, and recent news headlines, explain exactly WHY the stock moved today in 2 sentences maximum. Identify the catalyst (e.g., Earnings, Macro, Analyst Downgrade, Sector Sympathy). Respond ONLY with JSON: {explanation: str, catalyst_type: str, confidence: str ('High', 'Medium', 'Low')}"
   - Return parsed dict

3. batch_analyze_daily_moves(holdings_df: pd.DataFrame) -> list[dict]
   - Get significant moves from detect_significant_moves()
   - Loop through top 3 biggest movers (limit to 3 to save API calls/time)
   - Call generate_movement_explanation() for each
   - Add time.sleep(1.0) between calls
   - Return combined list of {ticker, change_pct, explanation, catalyst_type}
   - Cache in session_state with 4hr TTL

Add a "Daily Movers" section to the top of the Performance/Holdings tab in app.py. If any stock moves > 3%, show a collapsible info box with the AI explanation.
```

### Prompt AGENT-12 — Tax-Loss Harvest Scanner

```
Read the ai_agents project context. We are adding Agent 12: "The Tax-Loss Harvest Scanner".
Read config.py for WASH_SALE_LOOKBACK_DAYS (30).
Read utils/fmp_client.py for get_company_profile() (to find sector peers).

Build utils/agents/tax_harvester.py:

1. scan_harvest_opportunities(holdings_df: pd.DataFrame, min_loss_dollars: float = 500.0) -> pd.DataFrame
   - Filter holdings_df for positions where Unrealized_GL <= -min_loss_dollars
   - Calculate 'Tax_Asset_Value' assuming a 15% long-term cap gains offset rate (Unrealized_GL * 0.15)
   - Return sorted by absolute Unrealized_GL descending

2. verify_wash_sale_clearance(ticker: str, realized_gl_df: pd.DataFrame) -> bool
   - Check if the ticker was sold at a loss in the past 30 days in Realized_GL
   - Return True if clear (safe to harvest), False if in wash sale window

3. generate_harvest_proposal(ticker: str, loss_amount: float, tax_asset: float, profile: dict) -> dict
   - Call Gemini 2.5 Pro via ask_gemini_json():
     System: SAFETY_PREAMBLE + "You are a tax-loss harvesting advisor for a CPA. The investor holds a position with a significant unrealized loss. Suggest 2 highly correlated but legally distinct proxy securities (ETFs or competitor stocks) the investor could buy to maintain market exposure for 31 days while avoiding the IRS wash-sale rule. Respond ONLY with JSON: {harvest_rationale: str, estimated_tax_savings: float, proxy_options: [{ticker: str, description: str, correlation_rationale: str}], risks: [str]}"
   - User Prompt: Feed ticker, loss amount, estimated tax asset, and company profile/sector data.
   - Return parsed dict

4. build_tlh_report(holdings_df: pd.DataFrame, realized_gl_df: pd.DataFrame) -> list[dict]
   - Get opportunities from scan_harvest_opportunities()
   - Filter out any that fail verify_wash_sale_clearance()
   - For the top 3 biggest cleared losses, fetch FMP profile and call generate_harvest_proposal()
   - Return list of full proposal dicts

Build a new section on the Tax tab in app.py called "Proactive Tax-Loss Harvesting".
Show a table of current harvestable losses.
Add a button: "Scan for TLH Substitutes" that runs build_tlh_report() and displays the Rule of Three proxy options for each losing position.
```

---

## Agent 8: Grand Strategist + Net Worth

### Prompt AGENT-8 — Grand Strategist

```
Build utils/agents/grand_strategist.py.

1. read_re_portfolio_summary() -> dict
   - Read RE Dashboard Sheet (1DXuY1iBo2GqZCCSZ7OrUa4iaunb5s8Kf1Rms8Z237rQ) READ ONLY
   - Specific cells: property value, NOI, debt (B21), debt service (B20), reserve
   - Cache 1hr. Return None on failure.

2. build_unified_context(holdings_df, re_data) -> str (under 1000 tokens)

3. answer_cross_portfolio_question(question, context, holdings_df) -> dict
   - Gemini JSON: {analysis, recommendation, funding_sources: [{source, amount, tax_impact, notes}], total_available, shortfall}

4. calculate_net_worth(holdings_df, re_data) -> dict

NEVER write to RE Dashboard. Only gspread .get() calls.
```

### Prompt F1 — Net Worth Page

```
Build pages/net_worth.py using grand_strategist.read_re_portfolio_summary() and calculate_net_worth().
Big number: total net worth. KPI cards: Liquid | RE Equity | Debt | Reserve.
Pie chart: liquid vs RE. Bar chart: income sources. Graceful degradation if RE Sheet inaccessible.
```

---

## Chat Engine (Updated for 12 Agents)

### Prompt E1 — Build Chat Engine

```
Build utils/chat_engine.py routing to all 12 agents.

1. build_portfolio_summary(holdings_df, income_metrics=None, risk_data=None) -> str (under 800 tokens)

2. build_system_prompt(portfolio_summary) -> str (SAFETY_PREAMBLE + portfolio data + routing hints for all 12 agents)

3. detect_intent(user_message) -> str
   Keyword classifier:
   - "hedge"/"concentration"/"exposure"/"tech" → "concentration" (Agent 1)
   - "rebalance"/"trim"/"tax"/"wash sale"/"lots" → "rebalancing" (Agent 2)
   - "cash"/"sweep"/"idle"/"money market" → "cash_sweep" (Agent 3)
   - "earnings"/"report"/"quarter"/"transcript" → "earnings" (Agent 4)
   - "valuation"/"P/E"/"accumulate"/"cheap"/"watch"/"undervalued" → "valuation" (Agent 5)
   - "covered call"/"options"/"premium" → "options" (Agent 6)
   - "correlation"/"diversification"/"beta" → "correlation" (Agent 7)
   - "property"/"real estate"/"reserve"/"net worth"/"roof"/"repair" → "grand_strategy" (Agent 8)
   - "screen"/"find me"/"thesis"/"stocks like"/"infrastructure"/"growing" → "thesis" (Agent 9)
   - "fed"/"rate cut"/"CPI"/"inflation"/"VIX"/"macro"/"economy" → "macro" (Agent 10)
   - "why did"/"dropped"/"jumped"/"moved"/"today" → "price_move" (Agent 11)
   - "harvest"/"tax loss"/"TLH"/"losses"/"write off" → "tax_harvest" (Agent 12)
   - Default: "general"

4. enrich_context_for_intent(intent, holdings_df) -> str
   - "rebalancing" → drift summary
   - "cash_sweep" → cash analysis
   - "earnings" → upcoming earnings
   - "grand_strategy" → RE portfolio summary
   - "macro" → macro snapshot
   - "price_move" → significant moves
   - "tax_harvest" → harvestable losses summary

5. chat(user_message, history, system_prompt) -> str
```

### Prompt E2 — Advisor Page

```
Build pages/advisor.py — Streamlit chat interface.

Chat UI with st.chat_message + st.chat_input. Show detected intent badge.
Sidebar: Clear Chat, Refresh Data, message count.

Suggested prompts (12 chips, one per agent):
- "What's my tech exposure risk?" (1)
- "Trim GOOG to 4%, minimize taxes" (2)
- "Is my cash working hard enough?" (3)
- "Any earnings coming up?" (4)
- "Which stocks look undervalued?" (5)
- "Can I sell covered calls?" (6)
- "Am I actually diversified?" (7)
- "Fund a $15K property repair" (8)
- "Find infrastructure stocks with growing FCF" (9)
- "What if the Fed cuts rates?" (10)
- "Why did UNH drop today?" (11)
- "What tax losses can I harvest?" (12)
```

---

## Deployment

### Prompt F2 — Deploy

```
Prepare for Streamlit Cloud:
1. requirements.txt: streamlit, gspread, google-auth, pandas, yfinance, scipy, plotly, google-genai, pandas-ta, finnhub-python, fredapi, requests, openpyxl
2. Rename pages/ with numeric prefixes for ordering
3. .streamlit/config.toml with theme
4. .gitignore verified
5. CHANGELOG.md updated with all 12 agents
6. git push origin main
```

---

## Post-Build Audits

### Audit: Full Integration

```
1. Import all 12 agent modules + gemini_client + fmp_client + finnhub_client + technicals — verify no errors
2. Verify graceful degradation when each API key is empty
3. Verify cache TTLs: FMP/FRED 86400, Gemini 3600, Finnhub 1800, technicals 300
4. grep for "anthropic" — should be ZERO
5. grep for brokerage execution functions — should be ZERO
6. Verify json_mode=True on all structured Gemini calls
7. Verify time.sleep() between batch API calls
8. Verify SAFETY_PREAMBLE in every agent system prompt
9. Verify detect_intent() handles all 12 agent keywords
```

### Audit: Security

```
1. API keys in print()/st.write()?
2. Keys in error messages?
3. System prompts visible in UI?
4. RE Dashboard data over-exposed?
5. User input → Sheet queries without sanitization?
6. Options disclaimer present and prominent?
```

### Audit: Prompt Quality

```
Review every Gemini system prompt across all 12 agents:
1. SAFETY_PREAMBLE present?
2. Output format specified (JSON vs text)?
3. Portfolio context included?
4. Persona appropriate?
5. Prompt injection resistant? (unusual ticker names)
6. Could generate harmful advice?
```
