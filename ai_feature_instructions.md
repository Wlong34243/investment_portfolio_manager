# AI Feature Additions — Work Session Instructions (Final)
## Investment Portfolio Manager | Phase 4 & 5
## All AI: Gemini 2.5 Pro | 12 Agents | Prepared: April 1, 2026

---

## The Vision

The Streamlit app becomes a **two-way conversational brokerage layer** — inspired by Public.com's Agentic Brokerage but built for a self-managed Schwab portfolio. Gemini 2.5 Pro parses your intent, analyzes holdings/risk/tax data, and delivers deterministic proposals — while never executing trades.

---

## Complete Agent Map (12 Agents)

### Core Agents (from original spec)
| # | Agent | Domain | Key Data Sources |
|---|-------|--------|-----------------|
| 1 | **Concentration Hedger** | Risk: monitors tech/healthcare overweight, suggests hedges | Holdings, yfinance MA/beta |
| 2 | **Tax-Aware Rebalancer** | Tax: "Rule of Three" lot-level sell proposals | Holdings, Realized_GL, Target_Allocation |
| 3 | **Yield & Cash Sweeper** | Income: compares cash yield vs ETF yields | CASH_MANUAL, Income_Tracking, yfinance |
| 4 | **Earnings Sentinel** | Research: batch-scans 50+ tickers for upcoming earnings | FMP transcripts, Finnhub calendar |
| 5 | **Valuation & Accumulation** | Value: monitors forward P/E vs 5-year averages | Finnhub valuations, FMP historical PE |
| 6 | **Covered Call Generator** | Options: proposes premium strategies for 100+ share positions | yfinance options chains (GOOG, XOM) |
| 7 | **Beta & Correlation Optimizer** | Risk: detects correlation spikes, diversification erosion | Correlation matrix, stress tests |
| 8 | **Grand Strategist** | Unified: cross-portfolio advisor (liquid + RE) | Both Google Sheets |

### New Agents (inspired by Public.com Agentic Brokerage)
| # | Agent | Domain | Key Data Sources |
|---|-------|--------|-----------------|
| 9 | **Thesis Screener** | Discovery: turns natural language into ranked watchlists | FMP screener, Finnhub financials |
| 10 | **Macro Event Monitor** | Macro: watches CPI/Fed/VIX, proposes conditional rotations | FRED API, Finnhub, news feeds |
| 11 | **Price Movement Narrator** | Context: explains WHY your holdings moved today | Finnhub news, yfinance intraday |
| 12 | **Tax-Loss Harvest Scanner** | Tax: proactively finds harvestable losses + proxy substitutes | Holdings, Realized_GL, FMP profiles |

---

## Prerequisites Checklist

- [ ] **Google AI API key** in `.streamlit/secrets.toml` as `gemini_api_key`
- [ ] **FMP API key** as `fmp_api_key` (free tier: 250 calls/day)
- [ ] **Finnhub API key** as `finnhub_api_key` (free tier: 60 calls/min)
- [ ] **FRED API key** as `fred_api_key` (free, unlimited — needed for Agent 10)
- [ ] Add to `requirements.txt`: `google-genai`, `pandas-ta`, `finnhub-python`, `fredapi`
- [ ] Remove `anthropic` from `requirements.txt`
- [ ] `pip install google-genai pandas-ta finnhub-python fredapi`
- [ ] Realized_GL tab populated (Agents 2, 8, 12)
- [ ] Target_Allocation tab populated (Agent 2)
- [ ] config.py updated (see Config Additions below)

---

## Config Additions (Add Before Starting)

```python
# Gemini 2.5 Pro
GEMINI_MODEL = "gemini-2.5-pro"
GEMINI_MAX_TOKENS = 2000
GEMINI_API_KEY = _secret("gemini_api_key", "")

# FRED (Agent 10)
FRED_API_KEY = _secret("fred_api_key", "")

# Cache TTLs
AI_CACHE_TTL = 3600           # 1hr — Gemini analysis
FMP_CACHE_TTL = 86400         # 24hr — earnings/fundamentals
FINNHUB_CACHE_TTL = 1800      # 30min — news
FRED_CACHE_TTL = 86400        # 24hr — macro data
EARNINGS_LOOKAHEAD_DAYS = 14

# Rebalancing (Agent 2)
REBALANCE_DRIFT_THRESHOLD_PCT = 5.0
WASH_SALE_LOOKBACK_DAYS = 30
WASH_SALE_LOOKAHEAD_DAYS = 30

# Chat
MAX_CHAT_HISTORY = 20
PORTFOLIO_SUMMARY_TOKENS = 500

# Technicals
RSI_PERIOD = 14
MA_SHORT = 50
MA_LONG = 200

# Valuation (Agent 5)
VALUATION_PE_LOOKBACK_YEARS = 5

# Options (Agent 6)
MIN_SHARES_FOR_COVERED_CALL = 100
COVERED_CALL_DTE_RANGE = (30, 60)

# Cross-Portfolio (Agent 8)
RE_RESERVE_ACCOUNT_ID = "8895"

# Price Narrator (Agent 11)
SIGNIFICANT_MOVE_PCT = 3.0

# Tax-Loss Harvesting (Agent 12)
TLH_MIN_LOSS_DOLLARS = 500.0
TLH_LT_TAX_RATE = 0.15
```

---

## Build Sequence (7 Sessions)

### Session 1: Foundation (90 min)
| Step | What | Prompt |
|------|------|--------|
| 1 | Gemini 2.5 Pro core wrapper | G-CORE |
| 2 | FMP client | A1 |
| 3 | Finnhub client | A2 |
| 4 | Technical indicators (pandas-ta) | G1 |
| 5 | Smoke test imports | `streamlit run app.py` |
| 6 | Git commit | `"Foundation: Gemini + FMP + Finnhub + technicals"` |

### Session 2: Agents 1 & 4 — Concentration + Earnings (90 min)
| Step | What | Prompt |
|------|------|--------|
| 7 | Agent 1: Concentration Hedger | AGENT-1 |
| 8 | Agent 4: Earnings Sentinel | AGENT-4 |
| 9 | Research page rebuild | B2 |
| 10 | Dashboard earnings bar | C2 |
| 11 | Git commit | `"Agents 1+4: Hedger + Earnings"` |

### Session 3: Agents 2 & 3 — Tax Rebalancer + Cash Sweeper (90 min)
**Prerequisite:** Target_Allocation tab populated in Sheet

| Step | What | Prompt |
|------|------|--------|
| 12 | Agent 2: Tax-Aware Rebalancer | AGENT-2 |
| 13 | Agent 3: Yield & Cash Sweeper | AGENT-3 |
| 14 | Rebalancing page | D2 |
| 15 | Git commit | `"Agents 2+3: Tax rebalancer + Cash sweeper"` |

### Session 4: Agents 5, 6, 7 + Chat (90 min)
| Step | What | Prompt |
|------|------|--------|
| 16 | Agent 5: Valuation & Accumulation | AGENT-5 |
| 17 | Agent 6: Covered Call Generator | AGENT-6 |
| 18 | Agent 7: Beta & Correlation Optimizer | AGENT-7 |
| 19 | Chat engine + Advisor page | E1 + E2 |
| 20 | Git commit | `"Agents 5-7 + Chat advisor"` |

### Session 5: Agents 9 & 10 — Thesis Screener + Macro Monitor (75 min)
| Step | What | Prompt |
|------|------|--------|
| 21 | Agent 9: Thesis Screener | AGENT-9 |
| 22 | Agent 10: Macro Event Monitor | AGENT-10 |
| 23 | Add to Research page + Dashboard alerts | (within prompts) |
| 24 | Git commit | `"Agents 9+10: Thesis screener + Macro monitor"` |

### Session 6: Agents 11 & 12 — Proactive Insights (75 min)
| Step | What | Prompt |
|------|------|--------|
| 25 | Agent 11: Price Movement Narrator | AGENT-11 |
| 26 | Agent 12: Tax-Loss Harvest Scanner | AGENT-12 |
| 27 | Add to Holdings tab + Tax tab | (within prompts) |
| 28 | Git commit | `"Agents 11+12: Price narrator + TLH scanner"` |

### Session 7: Agent 8 + Net Worth + Deploy (60 min)
| Step | What | Prompt |
|------|------|--------|
| 29 | Agent 8: Grand Strategist | AGENT-8 |
| 30 | Net Worth page | F1 |
| 31 | Update chat engine for Agents 9-12 intents | E1-UPDATE |
| 32 | Deployment prep | F2 |
| 33 | Git push + Streamlit Cloud | — |

---

## Chat Interface Test Scenarios (All 12 Agents)

| Prompt | Expected Agent |
|--------|---------------|
| "What's my tech exposure risk?" | Agent 1 |
| "Trim GOOG to 4%, minimize taxes" | Agent 2 |
| "Is my cash working hard enough?" | Agent 3 |
| "Any earnings coming up?" | Agent 4 |
| "Is AMZN undervalued right now?" | Agent 5 |
| "Can I sell covered calls on GOOG?" | Agent 6 |
| "Are CORZ and IREN still diversifying me?" | Agent 7 |
| "I need $15K for a property roof repair" | Agent 8 |
| "Find me infrastructure stocks with growing free cash flow" | Agent 9 |
| "What happens to my portfolio if the Fed cuts rates?" | Agent 10 |
| "Why did UNH drop 4% today?" | Agent 11 |
| "What tax losses can I harvest right now?" | Agent 12 |
| "Buy 100 shares of AAPL" | **REFUSE** |

---

## Architecture Safety Rules (Non-Negotiable)

1. **No Auto-Trading.** Agents suggest, Bill decides. No brokerage API. Ever.
2. **LLM → JSON → Python.** Gemini outputs structured JSON. Python renders.
3. **Forced JSON output.** All structured Gemini calls use `json_mode=True`.
4. **Cache aggressively.** FMP/FRED: 24hr. Gemini: 1hr. Finnhub: 30min. Technicals: 5min.
5. **Fail gracefully.** API down → "data unavailable," never crash.
6. **Context window management.** Send relevant ticker + summary, not all 50 positions.
7. **RE Sheet is READ ONLY.** Grand Strategist reads only. NEVER writes.
8. **Rate limits tracked.** FMP: 250/day. Finnhub: 60/min. FRED: unlimited.

---

## New Dependencies (requirements.txt)

```
google-genai
pandas-ta
finnhub-python
fredapi
```

Remove: `anthropic`

---

## Post-Build Validation Checklist

- [ ] All Streamlit pages load without errors
- [ ] Agent 1: Fires for UNH at ~9%
- [ ] Agent 2: 3 tax-optimized proposals with lot references
- [ ] Agent 3: Cash yield vs JPIE/ET comparison
- [ ] Agent 4: Upcoming earnings identified
- [ ] Agent 5: Forward P/E vs 5-year average for AMZN
- [ ] Agent 6: GOOG and XOM identified as covered call candidates
- [ ] Agent 7: CORZ/IREN/QQQM correlation detected
- [ ] Agent 8: Cross-portfolio funding plan from both Sheets
- [ ] Agent 9: Natural language thesis → ranked ticker list
- [ ] Agent 10: CPI/Fed rate data fetched, conditional rotation proposed
- [ ] Agent 11: Explains 3%+ moves with news context
- [ ] Agent 12: Finds harvestable losses, suggests proxy substitutes
- [ ] Chat routes all 12 intents correctly
- [ ] Chat refuses trade execution
- [ ] No API keys in UI or error messages
- [ ] All features degrade gracefully
- [ ] CHANGELOG.md updated
- [ ] Streamlit Cloud deployed
