import streamlit as st
import pandas as pd
import plotly.express as px
from utils.sheet_readers import get_holdings_current, get_realized_gl
from utils.agents.tax_rebalancer import get_target_allocation, calculate_drift, generate_rebalance_proposals, check_wash_sale_risk
import os
import sys

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

st.set_page_config(layout="wide", page_title="Tax-Aware Rebalancing")

# --- Password Gate ---
def check_password():
    if "app_password" not in st.secrets: return True
    if st.session_state.get("password_correct"): return True
    st.error("Please login on the main page first.")
    st.stop()

if not check_password():
    st.stop()

st.title("⚖️ Tax-Aware Rebalancing")
st.info("💡 **Analysis only.** This page suggests actions but does not execute trades or modify your spreadsheet.")

# --- Load Data ---
holdings_df = get_holdings_current()
targets_df = get_target_allocation()
realized_gl_df = get_realized_gl()

if holdings_df.empty:
    st.warning("No holdings data available. Please upload a positions CSV on the main page.")
    st.stop()

if targets_df.empty:
    st.error("Target_Allocation tab not found or empty in Google Sheets. Please define targets to see drift analysis.")
    # Show example format
    with st.expander("Required Target_Allocation Schema"):
        st.write("The 'Target_Allocation' sheet should have two columns:")
        st.code("Category | Target %")
        st.write("Categories must match 'Asset Class' values (e.g., Equities, Alternatives, Cash & Fixed Income).")
    st.stop()

# --- Drift Analysis ---
st.subheader("Allocation Drift")
drift_df = calculate_drift(holdings_df, targets_df)

if not drift_df.empty:
    # Chart
    fig_drift = px.bar(
        drift_df, 
        x='Category', 
        y=['Target %', 'Actual %'], 
        barmode='group',
        title="Target vs Actual Allocation",
        color_discrete_map={'Target %': '#BDC3C7', 'Actual %': '#2E86AB'}
    )
    st.plotly_chart(fig_drift, use_container_width=True)
    
    # Table
    st.table(drift_df.style.format({
        'Target %': '{:.1f}%',
        'Actual %': '{:.1f}%',
        'Drift %': '{:+.1f}%'
    }).apply(lambda x: ['background-color: #FADBD8' if abs(v) > 5 else '' for v in x], subset=['Drift %']))
else:
    st.info("Drift data could not be calculated. Ensure Categories in Target_Allocation match your Holdings.")

# --- Rebalancing Proposals ---
st.divider()
st.subheader("AI Rebalancing Proposals")

if st.button("🧠 Generate Tax-Aware Proposals", use_container_width=True):
    with st.spinner("AI is evaluating tax lots and drift..."):
        proposals = generate_rebalance_proposals(drift_df, holdings_df)
        if proposals:
            for p in proposals:
                st.write(f"### Category: {p['category']}")
                cols = st.columns(3)
                for i, opt in enumerate(p['options']):
                    with cols[i]:
                        st.markdown(f"**{opt['label']}**")
                        st.write(opt['description'])
                        st.info(f"Tax: {opt['tax_impact']}\n\nEst. Cost: {opt['estimated_tax']}")
        else:
            st.success("Your portfolio is within tolerance. No urgent rebalancing needed.")

# --- Wash Sale Monitor ---
st.divider()
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("🚿 Wash Sale Monitor")
    # Scan top 10 positions for recent losses
    tickers_to_check = holdings_df.nlargest(10, 'Weight')['Ticker'].tolist()
    wash_alerts = []
    for t in tickers_to_check:
        risk = check_wash_sale_risk(t, realized_gl_df)
        if risk['at_risk']:
            wash_alerts.append(risk['warning'])
            
    if wash_alerts:
        for alert in wash_alerts:
            st.warning(alert)
    else:
        st.success("No recent losses found in top positions. Wash sale risk is low for current holdings.")

with col_right:
    st.subheader("⏳ Holding Period Dashboard")
    # Placeholder for LT vs ST logic
    # In a real app, we'd look at acquisition dates in holdings_df
    if 'Acquisition Date' in holdings_df.columns:
        # Simple heuristic: if acquisition date < 1yr ago, it's ST
        try:
            holdings_df['Acquisition Date'] = pd.to_datetime(holdings_df['Acquisition Date'], errors='coerce')
            one_year_ago = pd.Timestamp.now() - pd.Timedelta(days=365)
            holdings_df['Term'] = holdings_df['Acquisition Date'].apply(lambda x: 'Long Term' if x < one_year_ago else 'Short Term')
            term_dist = holdings_df.groupby('Term')['Market Value'].sum().reset_index()
            fig_term = px.pie(term_dist, values='Market Value', names='Term', color_discrete_sequence=['#27AE60', '#F1C40F'])
            st.plotly_chart(fig_term, use_container_width=True)
        except:
            st.write("Could not calculate holding periods from available data.")
    else:
        st.info("Acquisition dates not found in current holdings.")
