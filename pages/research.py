import streamlit as st
import pandas as pd
from utils.sheet_readers import get_holdings_current
from utils.fmp_client import get_earnings_transcripts, get_company_news
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
    st.subheader("Recent News")
    with st.spinner("Fetching news..."):
        news = get_company_news(selected_ticker)
        if news:
            for item in news:
                with st.expander(f"{item['title']} ({item['date']})"):
                    st.write(item['text'])
                    st.write(f"[Read more]({item['url']})")
        else:
            st.write("No recent news found.")

with col2:
    st.subheader("Earnings Transcripts")
    with st.spinner("Fetching transcripts..."):
        transcripts = get_earnings_transcripts(selected_ticker)
        if transcripts:
            for item in transcripts:
                with st.expander(f"Q{item['quarter']} {item['year']} ({item['date']})"):
                    st.write(f"Length: {len(item['content'])} characters")
                    st.text_area("Snippet", item['content'][:2000] + "...", height=200)
        else:
            st.write("No transcripts found.")

# --- AI Analysis ---
st.divider()
if st.button(f"Analyze {selected_ticker} with Claude 3.5 Sonnet", use_container_width=True):
    with st.spinner("Claude is reviewing transcripts and news..."):
        # Combine data for analysis
        analysis = analyze_ticker(selected_ticker, transcripts, news)
        
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
                {'range': 0.3, 1], 'color': "#2ECC71"}
            ],
            'bar': {'color': "#2C3E50"}
        }
    ))
    st.plotly_chart(fig, use_container_width=True)
    
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
