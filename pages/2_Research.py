import streamlit as st
import pandas as pd
from utils.sheet_readers import get_holdings_current
from utils.column_guard import ensure_display_columns
from utils.fmp_client import get_earnings_transcript, get_company_profile
from utils.finnhub_client import get_company_news
from utils.ai_research import analyze_ticker
import plotly.graph_objects as go
import os
import sys

st.title("🤖 AI Research Hub")

# --- Load Holdings ---
df = get_holdings_current()
df = ensure_display_columns(df)
if df.empty:
    st.info("No holdings found. Upload a CSV on the main page first.")
    st.stop()

# --- Ticker Selector ---
tickers = sorted(df['Ticker'].unique().tolist())
# Filter out cash
tickers = [t for t in tickers if t not in ['CASH_MANUAL', 'QACDS', 'Cash & Cash Investments']]

selected_ticker = st.sidebar.selectbox("Select Ticker", tickers)

# Clear session state for valuation if ticker changes
if st.session_state.get("last_val_ticker") != selected_ticker:
    st.session_state["val_report"] = None
    st.session_state["val_snap"] = None
    st.session_state["last_val_ticker"] = selected_ticker

# Get info for selected ticker
info = df[df['Ticker'] == selected_ticker].iloc[0]

# --- Hero Header ---
st.header(f"{selected_ticker} — {info['Description']}")
st.caption(f"${info['Price']:,.2f} | Weight: {info['Weight']:.1f}% | {info['Asset Class']}")

# --- KPI Cards ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Ticker", selected_ticker)
k2.metric("Price", f"${info['Price']:,.2f}")
k3.metric("Sector", info['Asset Class'])
k4.metric("Portfolio Weight", f"{info['Weight']:.2f}%")

# --- Data Columns ---
transcript = None
news = None

col1, col2 = st.columns(2)

with col1:
    st.subheader("Company Profile & News")
    
    with st.spinner("Fetching profile..."):
        try:
            profile = get_company_profile(selected_ticker)
            if profile:
                st.write(f"**Industry:** {profile.get('industry')}")
                st.write(f"**Market Cap:** ${profile.get('market_cap', 0):,.0f}")
                with st.expander("Business Description"):
                    st.write(profile.get('description'))
            else:
                st.write("No profile found.")
        except Exception as e:
            profile = None
            st.warning(f"Could not fetch profile: {e}")
            
    st.divider()
    
    with st.spinner("Fetching news..."):
        try:
            news = get_company_news(selected_ticker)
            if news:
                for item in news:
                    with st.expander(f"{item['headline']} ({item['datetime']})"):
                        st.write(item['summary'])
                        st.write(f"[Read more]({item['url']})")
            else:
                st.write("No recent news found.")
        except Exception as e:
            news = None
            st.warning(f"Could not fetch news: {e}")

with col2:
    st.subheader("Latest Earnings Transcript")
    with st.spinner("Fetching transcript..."):
        try:
            transcript = get_earnings_transcript(selected_ticker)
            if transcript:
                st.write(f"Length: {len(transcript)} characters")
                st.text_area("Transcript Snippet", transcript, height=500)
            else:
                st.write("No transcript found.")
        except Exception as e:
            transcript = None
            st.warning(f"Could not fetch transcript: {e}")

# --- AI Analysis ---
st.divider()
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("📊 Valuation Monitor")
    from utils.agents.valuation_agent import get_valuation_snapshot, generate_accumulation_plan, generate_rich_valuation_report
    
    if st.button(f"Check Valuation for {selected_ticker}", width='stretch'):
        with st.spinner("Analyzing valuation signals..."):
            val_snap = get_valuation_snapshot(selected_ticker)
            if "error" not in val_snap:
                st.session_state["val_snap"] = val_snap
                st.session_state["val_report"] = generate_rich_valuation_report(selected_ticker, val_snap)
            else:
                st.error(val_snap['error'])

    # Display results from session state if they exist
    if st.session_state.get("val_snap"):
        vs = st.session_state["val_snap"]
        vr = st.session_state.get("val_report", {})
        
        if vr and "error" not in vr:
            # Display AI generated sections directly (they contain the requested headings)
            st.markdown(vr.get('narrative', ''))
            st.markdown(vr.get('verdict', ''))
            st.markdown(vr.get('signals', ''))
            
            with st.expander("📊 Key Metrics Details"):
                st.markdown(vr.get('metrics_summary', ''))
        
        st.divider()
        if vs['is_below_average']:
            st.success(f"**Signal:** {selected_ticker} is trading below its 5-year average.")
            deploy_amt = st.number_input("Deployment Amount ($)", value=5000.0, step=1000.0)
            if st.button("Generate Accumulation Plan"):
                plan = generate_accumulation_plan(selected_ticker, deploy_amt, vs, df)
                st.write(plan.get('analysis'))
                st.info(f"**Action:** {plan.get('shares_to_buy')}")
                st.write(f"**Rationale:** {plan.get('entry_rationale')}")
        else:
            st.warning(f"**Signal:** {selected_ticker} is trading above its historical average.")

with col_b:
    st.subheader("💰 Options Income")
    from utils.agents.options_agent import get_options_chain, generate_covered_call_proposal, OPTIONS_DISCLAIMER
    st.caption(OPTIONS_DISCLAIMER)
    
    if info['Quantity'] >= 100:
        if st.button(f"Scan Covered Calls for {selected_ticker}", width='stretch'):
            with st.spinner("Fetching option chain (OTM 5-15%)..."):
                chain = get_options_chain(selected_ticker)
                if not chain.empty:
                    proposal = generate_covered_call_proposal(selected_ticker, chain, df)
                    if "error" not in proposal:
                        for strat in proposal['strategies']:
                            with st.expander(f"{strat['label']} (Strike {strat['strike']})"):
                                st.write(f"**Premium:** ${strat['premium']:.2f}")
                                st.write(f"**Yield:** {strat['annualized_yield_pct']:.1f}% annualized")
                                st.write(f"**Assignment Risk:** {strat['assignment_probability']}")
                                st.info(strat['recommendation'])
                    else:
                        st.error(proposal['error'])
                else:
                    st.info("No suitable OTM calls found for the next ~45 days.")
    else:
        st.info(f"You need at least 100 shares of {selected_ticker} to sell covered calls. (Current: {info['Quantity']})")

# --- Thesis Screener (Agent 9) ---
st.divider()
st.subheader("🔭 AI Thesis Screener")
from utils.agents.thesis_screener import parse_thesis_to_criteria, screen_stocks, rank_and_explain

if "thesis_text" not in st.session_state:
    st.session_state["thesis_text"] = ""

examples = [
    "AI companies with high revenue growth but still undervalued",
    "Dividend aristocrats yielding above 3%",
    "International companies benefiting from weak dollar",
    "Clean energy stocks with low debt to equity"
]
cols = st.columns(len(examples))
for i, ex in enumerate(examples):
    if cols[i].button(ex, key=f"ex_{i}"):
        st.session_state["thesis_text"] = ex
        st.rerun()

thesis_input = st.text_area("Describe your investment thesis (e.g. 'Infrastructure stocks with growing free cash flow')", 
                            value=st.session_state["thesis_text"], height=100)

if st.button("🔍 Screen Stocks for this Thesis", width='stretch'):
    if not thesis_input:
        st.warning("Please enter a thesis first.")
    else:
        with st.spinner("Translating thesis to quantitative criteria..."):
            criteria = parse_thesis_to_criteria(thesis_input)
            if "error" not in criteria:
                with st.spinner(f"Screening market..."):
                    screened_df = screen_stocks(criteria, df)
                    if not screened_df.empty:
                        with st.spinner("Ranking top 5 candidates..."):
                            ranked = rank_and_explain(thesis_input, screened_df, df)
                            if "error" not in ranked:
                                st.success(f"**Thesis Summary:** {ranked['thesis_summary']}")
                                for pick in ranked['ranked_picks']:
                                    with st.expander(f"#{pick['rank']} {pick['ticker']} - {pick['company']} ({'Already Held' if pick['already_held'] else 'New Opportunity'})"):
                                        st.write(f"**Rationale:** {pick['rationale']}")
                                        st.write(f"**Suggested Weight:** {pick['suggested_weight']}")
                                st.info(ranked['portfolio_overlap_note'])
                            else:
                                st.error(ranked['error'])
                    else:
                        st.info("No stocks matched these criteria. Try a broader thesis.")
            else:
                st.error(criteria['error'])

# --- AI Deep Analysis ---
st.divider()
if st.button(f"Deep Analysis with Gemini 3.1 Pro", width='stretch'):
    if not transcript and not news:
        st.warning("No transcript or news data available for this ticker. Fetch data above first.")
    else:
        with st.spinner("Gemini is reviewing transcripts and news..."):
            # Combine data for analysis
            analysis = analyze_ticker(selected_ticker, transcript, news)
            
            if "error" in analysis:
                st.error(f"AI Analysis failed: {analysis['error']}")
            else:
                st.session_state[f"analysis_{selected_ticker}"] = analysis

if f"analysis_{selected_ticker}" in st.session_state:
    res = st.session_state[f"analysis_{selected_ticker}"]
    
    st.header(f"AI Equity Research: {selected_ticker}")
    
    # Sentiment Metric
    score = res.get('sentiment_score', 0.0)
    sentiment_label = "Bullish" if score > 0.3 else "Bearish" if score < -0.3 else "Neutral"
    st.metric("AI Sentiment", f"{score:.2f}", sentiment_label)
    
    # Summary
    st.subheader("Executive Summary")
    st.write(res.get('summary', ''))
    
    # Bull vs Bear
    b1, b2 = st.columns(2)
    with b1:
        st.success("### 🐂 Bull Case")
        for point in res.get('bull_cases', []):
            st.write(f"- {point}")
            
    with b2:
        st.error("### 🐻 Bear Risks")
        for point in res.get('bear_risks', []):
            st.write(f"- {point}")
