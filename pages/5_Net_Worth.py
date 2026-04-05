import streamlit as st
import pandas as pd
import plotly.express as px
from utils.sheet_readers import get_holdings_current
from utils.agents.grand_strategist import read_re_portfolio_summary, calculate_net_worth, build_unified_context, answer_cross_portfolio_question
import os
import sys

# --- Password Gate ---
def check_password():
    if "app_password" not in st.secrets: return True
    if st.session_state.get("password_correct"): return True
    st.error("Please login on the main page first.")
    st.stop()

if not check_password():
    st.stop()

st.title("🏦 Unified Net Worth")

# --- Load Data ---
holdings_df = get_holdings_current()
re_data = read_re_portfolio_summary()

if holdings_df.empty:
    st.warning("Please upload your investment portfolio on the main page to see net worth.")
    st.stop()

nw = calculate_net_worth(holdings_df, re_data)

# --- KPI Row ---
st.header(f"Total Net Worth: ${nw['total']:,.0f}")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Liquid Assets", f"${nw['liquid']:,.0f}")
if re_data:
    k2.metric("RE Equity", f"${nw['re_equity']:,.0f}")
    k3.metric("Total Debt", f"${nw['debt']:,.0f}", delta_color="inverse")
    k4.metric("RE Reserves", f"${nw['reserve']:,.0f}")
else:
    k2.info("RE Data Inaccessible")

# --- Charts ---
c1, c2 = st.columns(2)

with c1:
    st.subheader("Asset Distribution")
    dist_data = [
        {"Asset": "Liquid (Stocks/Cash)", "Value": nw['liquid']},
    ]
    if re_data:
        dist_data.append({"Asset": "Real Estate Equity", "Value": nw['re_equity']})
        dist_data.append({"Asset": "RE Cash Reserves", "Value": nw['reserve']})
        
    df_dist = pd.DataFrame(dist_data)
    fig_pie = px.pie(df_dist, values='Value', names='Asset', color_discrete_sequence=['#2E86AB', '#27AE60', '#F1C40F'])
    st.plotly_chart(fig_pie, width='stretch')

with c2:
    st.subheader("Grand Strategist Q&A")
    question = st.text_input("Ask a cross-portfolio question (e.g., 'How to fund a $20k roof repair?')")
    if st.button("Consult AI Strategist"):
        with st.spinner("AI is evaluating both portfolios..."):
            context = build_unified_context(holdings_df, re_data)
            ans = answer_cross_portfolio_question(question, context, holdings_df)
            if "error" not in ans:
                st.write(ans['analysis'])
                st.success(f"**Recommendation:** {ans['recommendation']}")
                
                if ans.get('funding_sources'):
                    st.write("**Suggested Funding:**")
                    for src in ans['funding_sources']:
                        st.write(f"- {src['source']}: ${src['amount']:,.0f} ({src['tax_impact']})")
            else:
                st.error(ans['error'])

# --- RE Details ---
if re_data:
    st.divider()
    st.subheader("Real Estate Fundamental Analysis")
    col_a, col_b = st.columns(2)
    with col_a:
        st.write(f"**Market Valuation (6% Cap):** `${nw['re_valuation']:,.0f}`")
        st.write(f"**Annual NOI:** `${re_data['noi']:,.0f}`")
    with col_b:
        st.write(f"**Annual Debt Service:** `${re_data['debt_service']:,.0f}`")
        ds_ratio = re_data['noi'] / re_data['debt_service'] if re_data['debt_service'] > 0 else 0
        st.write(f"**Debt Service Coverage Ratio (DSCR):** `{ds_ratio:.2f}x`")
