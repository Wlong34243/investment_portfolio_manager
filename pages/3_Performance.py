import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, timedelta
import os
import sys
import config
from utils.sheet_readers import get_gspread_client, get_daily_snapshots

# --- Password Gate ---
def check_password():
    if "app_password" not in st.secrets: return True
    if st.session_state.get("password_correct"): return True
    st.error("Please login on the main page first.")
    st.stop()

if not check_password():
    st.stop()

# --- Data Loading ---
snapshots_df = get_daily_snapshots()
if not snapshots_df.empty:
    snapshots_df['Date'] = pd.to_datetime(snapshots_df['Date'])
    snapshots_df = snapshots_df.sort_values(by='Date')

# --- Page Header ---
st.title("📈 Portfolio Performance")

if snapshots_df.empty:
    st.info("No snapshots found. Upload a CSV on the main page to begin tracking performance.")
    st.stop()

first_date = snapshots_df['Date'].min().date()
last_date = snapshots_df['Date'].max().date()
st.subheader(f"Tracking period: {first_date} to {last_date}")

# --- KPI Cards ---
latest = snapshots_df.iloc[-1]
total_val = float(latest['Total Value'])
total_cost = float(latest['Total Cost'])
unrealized_gl = total_val - total_cost
unrealized_pct = (unrealized_gl / total_cost * 100) if total_cost > 0 else 0.0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Value", f"${total_val:,.2f}")
k2.metric("Total Cost", f"${total_cost:,.2f}")
k3.metric("Total Unrealized G/L", f"${unrealized_gl:,.2f}")
k4.metric("Total G/L %", f"{unrealized_pct:.2f}%")

# --- Period Returns ---
st.subheader("Period Returns")

def calculate_returns(df):
    if len(df) < 2: return {}
    
    current_val = float(df.iloc[-1]['Total Value'])
    
    # MTD (Month to Date)
    first_of_month = df[df['Date'] >= datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)]
    mtd = ((current_val / float(first_of_month.iloc[0]['Total Value'])) - 1) * 100 if not first_of_month.empty else 0.0
    
    # QTD (Quarter to Date)
    current_q_start = datetime.now().replace(month=((datetime.now().month-1)//3)*3+1, day=1, hour=0, minute=0, second=0, microsecond=0)
    first_of_quarter = df[df['Date'] >= current_q_start]
    qtd = ((current_val / float(first_of_quarter.iloc[0]['Total Value'])) - 1) * 100 if not first_of_quarter.empty else 0.0
    
    # YTD (Year to Date)
    first_of_year = df[df['Date'] >= datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)]
    ytd = ((current_val / float(first_of_year.iloc[0]['Total Value'])) - 1) * 100 if not first_of_year.empty else 0.0
    
    # Since Inception
    inception = ((current_val / float(df.iloc[0]['Total Value'])) - 1) * 100
    
    return {"MTD": mtd, "QTD": qtd, "YTD": ytd, "Inception": inception}

returns = calculate_returns(snapshots_df)
if returns:
    ret_df = pd.DataFrame([returns]).T.reset_index()
    ret_df.columns = ["Period", "Return %"]
    st.table(ret_df.style.format({"Return %": "{:+.2f}%"}))

# --- Portfolio vs Benchmark ---
st.subheader("Portfolio vs Benchmarks (Normalized to 100)")

@st.cache_data(ttl=300)
def get_benchmark_data(tickers, start_date):
    try:
        data = yf.download(tickers, start=start_date, auto_adjust=True, progress=False)['Close']
        return data
    except Exception:
        return pd.DataFrame()

bench_data = get_benchmark_data(config.BENCHMARK_TICKERS, first_date)

if not bench_data.empty:
    # Prepare portfolio series
    port_series = snapshots_df.set_index('Date')['Total Value']
    port_normalized = (port_series / port_series.iloc[0]) * 100
    
    # Prepare benchmarks
    combined = pd.DataFrame({"Portfolio": port_normalized})
    for ticker in config.BENCHMARK_TICKERS:
        if ticker in bench_data.columns:
            b_series = bench_data[ticker].reindex(port_series.index, method='ffill')
            b_normalized = (b_series / b_series.iloc[0]) * 100
            combined[ticker] = b_normalized
            
    fig_bench = px.line(
        combined, 
        labels={"value": "Normalized Value (100 = Start)", "Date": "Date"},
        color_discrete_map={"Portfolio": "#1F4E79", "SPY": "#F39C12", "VTI": "#2E86AB", "QQQM": "#8E44AD"}
    )
    st.plotly_chart(fig_bench, width='stretch')

# --- Portfolio Value Over Time ---
st.subheader("Total Value History")
fig_area = px.area(
    snapshots_df, 
    x='Date', 
    y='Total Value',
    title="Portfolio Market Value",
    color_discrete_sequence=['#2E86AB']
)
st.plotly_chart(fig_area, width='stretch')

# --- Contribution Modeling ---
st.divider()
st.subheader("Future Contribution Modeling")

col_m1, col_m2 = st.columns(2)
with col_m1:
    monthly_contrib = st.slider("Monthly Contribution ($)", 0, 10000, 2000, step=500)
    years_to_project = st.slider("Years to Project", 1, 10, 5)

with col_m2:
    # Use expected return from risk results if available, else fallback
    expected_return_pct = 9.0 # Fallback
    if "risk_results" in st.session_state:
        expected_return_pct = st.session_state["risk_results"]["capm"]["expected_pct"]
    
    st.write(f"**Assumed Annual Return:** `{expected_return_pct:.2f}%` (from Risk tab)")

# Projection logic
projection_data = []
current_proj_val_no_contrib = total_val
current_proj_val_with_contrib = total_val
r = expected_return_pct / 100

for year in range(1, years_to_project + 1):
    # Scenario 1: No contributions
    current_proj_val_no_contrib = current_proj_val_no_contrib * (1 + r)
    
    # Scenario 2: With contributions
    # Simple approx: (val * (1+r)) + (monthly * 12)
    current_proj_val_with_contrib = (current_proj_val_with_contrib * (1 + r)) + (monthly_contrib * 12)
    
    projection_data.append({
        "Year": year,
        "No Contributions": current_proj_val_no_contrib,
        "With Contributions": current_proj_val_with_contrib
    })

proj_df = pd.DataFrame(projection_data)
fig_proj = px.bar(
    proj_df, 
    x='Year', 
    y=['No Contributions', 'With Contributions'],
    barmode='group',
    title=f"{years_to_project}-Year Growth Projection",
    labels={"value": "Projected Value ($)", "variable": "Scenario"},
    color_discrete_map={"No Contributions": "#BDC3C7", "With Contributions": "#2ECC71"}
)
st.plotly_chart(fig_proj, width='stretch')
