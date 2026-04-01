import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.sheet_readers import get_gspread_client

st.set_page_config(layout="wide", page_title="Tax Intelligence")

# --- Password Gate ---
def check_password():
    if "app_password" not in st.secrets: return True
    if st.session_state.get("password_correct"): return True
    st.error("Please login on the main page first.")
    st.stop()

if not check_password():
    st.stop()

# --- Data Loading ---
@st.cache_data(ttl=300)
def get_realized_gl() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_REALIZED_GL)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df['Closed Date'] = pd.to_datetime(df['Closed Date'])
            df['Opened Date'] = pd.to_datetime(df['Opened Date'])
        return df
    except Exception:
        return pd.DataFrame()

gl_df = get_realized_gl()

# --- Page Header ---
st.title("⚖️ Tax Intelligence")

if gl_df.empty:
    st.info("No realized G/L records found. Upload a Realized G/L CSV on the main page to begin.")
    st.stop()

# Filter to current year
current_year = st.sidebar.selectbox("Year", sorted(gl_df['Closed Date'].dt.year.unique(), reverse=True))
ytd_df = gl_df[gl_df['Closed Date'].dt.year == current_year]

# --- KPI Cards ---
total_gl = ytd_df['Gain Loss $'].sum()
st_gl = ytd_df[ytd_df['Term'] == 'Short Term']['Gain Loss $'].sum()
lt_gl = ytd_df[ytd_df['Term'] == 'Long Term']['Gain Loss $'].sum()
wash_disallowed = ytd_df[ytd_df['Wash Sale'] == True]['Disallowed Loss'].sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric(f"{current_year} Realized G/L", f"${total_gl:,.2f}")
k2.metric("Short Term", f"${st_gl:,.2f}")
k3.metric("Long Term", f"${lt_gl:,.2f}")
k4.metric("Wash Sale Disallowed", f"${wash_disallowed:,.2f}", delta_color="inverse")

# --- Breakdown ---
st.subheader("Term Breakdown")
c1, c2 = st.columns(2)

with c1:
    term_summary = ytd_df.groupby('Term')['Gain Loss $'].sum().reset_index()
    fig_term = px.pie(term_summary, values='Gain Loss $', names='Term', title="G/L by Term",
                     color_discrete_map={"Short Term": "#E74C3C", "Long Term": "#2ECC71"})
    st.plotly_chart(fig_term, use_container_width=True)

with c2:
    # Monthly G/L
    ytd_df['Month'] = ytd_df['Closed Date'].dt.strftime('%b')
    monthly_gl = ytd_df.groupby(['Month', 'Term'])['Gain Loss $'].sum().reset_index()
    # Sort by month
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    monthly_gl['Month'] = pd.Categorical(monthly_gl['Month'], categories=months, ordered=True)
    monthly_gl = monthly_gl.sort_values('Month')
    
    fig_month = px.bar(monthly_gl, x='Month', y='Gain Loss $', color='Term', title="Monthly Realized G/L",
                      color_discrete_map={"Short Term": "#E74C3C", "Long Term": "#2ECC71"})
    st.plotly_chart(fig_month, use_container_width=True)

# --- Wash Sale Ledger ---
st.subheader("Wash Sale Ledger")
wash_df = ytd_df[ytd_df['Wash Sale'] == True].sort_values(by='Closed Date', ascending=False)
if not wash_df.empty:
    st.dataframe(wash_df[['Closed Date', 'Ticker', 'Quantity', 'Disallowed Loss', 'Account']], use_container_width=True)
else:
    st.write("No wash sales detected for this period.")

# --- Ticker Summary ---
st.subheader("Ticker-Level P&L Summary")
ticker_summary = ytd_df.groupby('Ticker').agg({
    'Proceeds': 'sum',
    'Cost Basis': 'sum',
    'Gain Loss $': 'sum',
    'Wash Sale': 'sum',
    'Disallowed Loss': 'sum'
}).sort_values(by='Gain Loss $', ascending=False)

st.table(ticker_summary.style.format({
    'Proceeds': '${:,.2f}',
    'Cost Basis': '${:,.2f}',
    'Gain Loss $': '${:,.2f}',
    'Disallowed Loss': '${:,.2f}'
}))
