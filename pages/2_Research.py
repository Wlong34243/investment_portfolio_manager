import streamlit as st
import pandas as pd
from utils.sheet_readers import get_holdings_current
from utils.fmp_client import get_earnings_transcript, get_company_profile
from utils.finnhub_client import get_company_news
from utils.ai_research import analyze_ticker
import plotly.graph_objects as go
import os
import sys

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

st.set_page_config(layout="wide", page_title="AI Research Hub")

# --- Password Gate ---
def check_password():
    if "app_password" not in st.secrets: return True
    if st.session_state.get("password_correct"): return True
    st.error("Please login on the main page first.")
    st.stop()

if not check_password():
    st.stop()

st.title("🤖 AI Research Hub")

# --- Load Holdings ---
df = get_holdings_current()
if df.empty:
    st.info("No holdings found. Upload a CSV on the main page first.")
    st.stop()

# --- Ticker Selector ---
tickers = sorted(df['Ticker'].unique().tolist())
# Filter out cash
tickers = [t for t in tickers if t not in ['CASH_MANUAL', 'QACDS', 'Cash & Cash Investments']]

selected_ticker = st.sidebar.selectbox("Select Ticker", tickers)

# Get info for selected ticker
info = df[df['Ticker'] == selected_ticker].iloc[0]

# --- KPI Cards ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Ticker", selected_ticker)
k2.metric("Price", f"${info['Price']:,.2f}")
k3.metric("Sector", info['Asset Class'])
k4.metric("Portfolio Weight", f"{info['Weight']:.2f}%")

# --- Data Columns ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Company Profile & News")
    
    with st.spinner("Fetching profile..."):
        profile = get_company_profile(selected_ticker)
        if profile:
            st.write(f"**Industry:** {profile.get('industry')}")
            st.write(f"**Market Cap:** ${profile.get('market_cap', 0):,.0f}")
            with st.expander("Business Description"):
                st.write(profile.get('description'))
        else:
            st.write("No profile found.")
            
    st.divider()
    
    with st.spinner("Fetching news..."):
        news = get_company_news(selected_ticker)
        if news:
            for item in news:
                with st.expander(f"{item['headline']} ({item['datetime']})"):
                    st.write(item['summary'])
                    st.write(f"[Read more]({item['url']})")
        else:
            st.write("No recent news found.")

with col2:
    st.subheader("Latest Earnings Transcript")
    with st.spinner("Fetching transcript..."):
        transcript = get_earnings_transcript(selected_ticker)
        if transcript:
            st.write(f"Length: {len(transcript)} characters")
            st.text_area("Transcript Snippet", transcript, height=500)
        else:
            st.write("No transcript found.")

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
                report = generate_rich_valuation_report(selected_ticker, val_snap)
                
                if "error" not in report:
                    # Lead Narrative
                    st.markdown(f"### {selected_ticker} Valuation Verdict")
                    st.write(report['narrative'])
                    
                    # Key Stats
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Current P/E", f"{val_snap['current_pe']:.2f}")
                    m2.metric("5yr Avg P/E", f"{val_snap['avg_5yr_pe']:.2f}")
                    m3.metric("Discount/Premium", f"{val_snap['pe_discount_pct']:+.1f}%", delta_color="inverse")
                    
                    st.markdown("#### What the market is pricing in")
                    st.write(report['verdict'])
                    
                    st.markdown("#### Valuation signals")
                    st.write(report['signals'])
                    
                    with st.expander("View Key Metrics Details"):
                        st.markdown(report['metrics_summary'])
                
                st.divider()
                if val_snap['is_below_average']:
                    st.success(f"**Signal:** {selected_ticker} is trading below its 5-year average.")
                    deploy_amt = st.number_input("Deployment Amount ($)", value=5000.0, step=1000.0)
                    if st.button("Generate Accumulation Plan"):
                        plan = generate_accumulation_plan(selected_ticker, deploy_amt, val_snap, df)
                        st.write(plan.get('analysis'))
                        st.info(f"**Action:** {plan.get('shares_to_buy')}")
                        st.write(f"**Rationale:** {plan.get('entry_rationale')}")
                else:
                    st.warning(f"**Signal:** {selected_ticker} is trading above its historical average.")
            else:
                st.error(val_snap['error'])

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

thesis_input = st.text_area("Describe your investment thesis (e.g. 'Infrastructure stocks with growing free cash flow')", height=100)
examples = [
    "AI companies with high revenue growth but still undervalued",
    "Dividend aristocrats yielding above 3%",
    "International companies benefiting from weak dollar",
    "Clean energy stocks with low debt to equity"
]
cols = st.columns(len(examples))
for i, ex in enumerate(examples):
    if cols[i].button(ex, key=f"ex_{i}"):
        st.info(f"Copied to clipboard (simulated): {ex}") # Streamlit doesn't easily set text_area value from button without rerun logic

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
    
    # Sentiment Gauge
    score = res.get('sentiment_score', 0.0)
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Sentiment Score (-1 to 1)"},
        gauge = {
            'axis': {'range': [-1, 1]},
            'steps': [
                {'range': [-1, -0.3], 'color': "#E74C3C"},
                {'range': [-0.3, 0.3], 'color': "#F1C40F"},
                {'range': [0.3, 1], 'color': "#2ECC71"}
            ],
            'bar': {'color': "#2C3E50"}
        }
    ))
    st.plotly_chart(fig, width='stretch')
    
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
