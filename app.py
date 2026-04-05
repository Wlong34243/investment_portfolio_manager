import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import traceback
from datetime import date, datetime
import config
from utils.auth import require_auth
from utils.csv_parser import parse_schwab_csv, inject_cash_manual
from utils.enrichment import enrich_positions
from utils.risk import (
    build_price_histories, calculate_beta, calculate_portfolio_beta,
    calculate_correlation_matrix
)
from pipeline import (
    normalize_positions, write_to_sheets, ingest_realized_gl, 
    ingest_transactions, calculate_income_metrics
)
from utils.sheet_readers import get_holdings_current
from utils.validators import (
    validate_percentage_range, validate_no_negative_market_values, 
    validate_duplicate_tickers, validate_total_sanity
)
from utils.column_guard import ensure_display_columns

# --- Initialization ---
st.set_page_config(layout="wide", page_title="Investment Manager", page_icon="📈")
require_auth()

if "holdings_df" not in st.session_state:
    try:
        raw_df = get_holdings_current()
        st.session_state["holdings_df"] = ensure_display_columns(raw_df)
    except:
        st.session_state["holdings_df"] = pd.DataFrame(columns=config.POSITION_COLUMNS)

# Force sanitization on every rerun
st.session_state["holdings_df"] = ensure_display_columns(st.session_state["holdings_df"])
df = st.session_state["holdings_df"]

# --- Sidebar ---
with st.sidebar:
    st.header("Maintenance")
    
    # Import Hub
    with st.expander("📥 Import Schwab CSVs", expanded=df.empty):
        pos_file = st.file_uploader("Positions", type=["csv"])
        cash_inject = st.number_input("Manual Cash ($)", value=0.0, step=500.0)
        
        if st.button("Process Data", width='stretch'):
            if pos_file:
                with st.spinner("Ingesting..."):
                    df_raw = parse_schwab_csv(pos_file.read())
                    df_cash = inject_cash_manual(df_raw, cash_inject)
                    df_enriched = enrich_positions(df_cash)
                    df_norm = normalize_positions(df_enriched, str(date.today()))
                    write_to_sheets(df_norm, cash_inject, dry_run=config.DRY_RUN)
                    st.session_state["holdings_df"] = ensure_display_columns(df_norm)
                    st.toast("Portfolio Updated", icon="✅")
                    time.sleep(1)
                    st.rerun()

    st.divider()
    if st.button("🔄 Clear System Cache", width='stretch'):
        st.cache_data.clear()
        st.session_state.clear()
        st.rerun()
    
    if not df.empty:
        st.subheader("Stats")
        st.metric("Total Positions", len(df))
        if 'Import Date' in df.columns:
            st.caption(f"Last Import: {df['Import Date'].iloc[0]}")

# --- Dashboard Layout ---
st.title("💼 Investment Portfolio")

tabs = st.tabs(["📊 Holdings", "💰 Income", "🔔 Signals"])

with tabs[0]:
    if df.empty:
        st.info("No data loaded. Use the sidebar to import a Schwab CSV.")
    else:
        # KPIs
        total_val = df['Market Value'].sum()
        cash_mask = df['Ticker'].isin(['CASH_MANUAL', 'QACDS', 'CASH & CASH INVESTMENTS']) | df['Is Cash'].astype(bool)
        cash_val = df[cash_mask]['Market Value'].sum()
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Portfolio", f"${total_val:,.0f}")
        k2.metric("Cash Balance", f"${cash_val:,.0f}")
        k3.metric("Invested", f"${total_val - cash_val:,.0f}")

        st.divider()
        
        # Treemap
        invested_df = df[~cash_mask].copy()
        if not invested_df.empty:
            if 'Ticker' in invested_df.columns:
                invested_df['Market Value'] = invested_df['Market Value'].clip(lower=0.01)
                fig = px.treemap(invested_df, path=['Asset Class', 'Ticker'], values='Market Value', 
                                 title="Asset Allocation", color_discrete_sequence=px.colors.qualitative.Prism)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("Cannot render Treemap: Ticker column missing.")
        
        # Table
        st.subheader("Current Positions")
        st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[1]:
    if not df.empty:
        metrics = calculate_income_metrics(df)
        i1, i2 = st.columns(2)
        i1.metric("Annual Projected Income", f"${metrics['projected_annual_income']:,.2f}")
        i2.metric("Blended Yield", f"{metrics['blended_yield_pct']:.2f}%")

with tabs[2]:
    st.info("Agent signals appearing in next sync...")

# --- Page Nav ---
pg = st.navigation([
    st.Page(lambda: None, title="Main Dashboard", icon="📈"), # Placeholder, handled by app.py main
    st.Page("pages/1_Rebalancing.py", title="Rebalancing", icon="⚖️"),
    st.Page("pages/2_Research.py", title="Research Hub", icon="🔬"),
    st.Page("pages/3_Performance.py", title="Performance", icon="📊"),
    st.Page("pages/4_Tax.py", title="Tax Intelligence", icon="💸"),
    st.Page("pages/5_Net_Worth.py", title="Unified Net Worth", icon="🏦"),
    st.Page("pages/6_Advisor.py", title="AI Advisor", icon="💬"),
])
pg.run()
