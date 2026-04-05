import streamlit as st

st.set_page_config(layout="wide", page_title="Investment Manager", page_icon="📈")

from utils.auth import require_auth
require_auth()

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import traceback
from datetime import date, datetime
import config
from utils.csv_parser import parse_schwab_csv, inject_cash_manual
from utils.enrichment import enrich_positions
from utils.risk import (
    build_price_histories, calculate_beta, calculate_portfolio_beta,
    run_stress_tests, capm_projection, concentration_alerts, calculate_correlation_matrix
)
from pipeline import (
    normalize_positions, write_to_sheets, write_risk_snapshot, 
    ingest_realized_gl, ingest_transactions, calculate_income_metrics
)
from utils.sheet_readers import get_holdings_current
from utils.validators import (
    validate_percentage_range, validate_no_negative_market_values, 
    validate_duplicate_tickers, validate_total_sanity
)
from utils.column_guard import ensure_display_columns

# --- Main Dashboard Logic ---
def main_dashboard():
    # --- Load Data ---
    if "holdings_df" not in st.session_state:
        try:
            st.session_state["holdings_df"] = get_holdings_current()
        except Exception as e:
            st.error("Could not connect to Google Sheets.")
            st.stop()

    # --- Sidebar ---
    with st.sidebar:
        st.header("Portfolio Management")
        
        # 1. Import Data Expander
        df = st.session_state["holdings_df"]
        is_empty = df.empty
        with st.expander("📥 Import Data", expanded=is_empty):
            uploaded_file = st.file_uploader("Upload Schwab Positions CSV", type=["csv"])
            gl_file = st.file_uploader("Upload Realized G/L CSV", type=["csv"])
            tx_file = st.file_uploader("Upload Transaction History CSV", type=["csv"])
            
            cash_amount = st.number_input("Manual Cash Injection ($)", value=0.0, step=500.0)
            
            if st.button("Process CSVs", width='stretch'):
                with st.status("Ingesting data...") as status:
                    if uploaded_file:
                        df_raw = parse_schwab_csv(uploaded_file.read())
                        df_cash = inject_cash_manual(df_raw, cash_amount)
                        df_enriched = enrich_positions(df_cash)
                        df_norm = normalize_positions(df_enriched, str(date.today()))
                        write_to_sheets(df_norm, cash_amount, dry_run=config.DRY_RUN)
                        st.session_state["holdings_df"] = ensure_display_columns(df_norm)
                    
                    if gl_file:
                        ingest_realized_gl(gl_file, dry_run=config.DRY_RUN)
                    
                    if tx_file:
                        ingest_transactions(tx_file, dry_run=config.DRY_RUN)
                        
                    status.update(label="Sync Complete", state="complete")
                    time.sleep(1)
                    st.rerun()

        # 2. Portfolio Status Section
        st.divider()
        st.subheader("Portfolio Status")
        
        if not df.empty:
            if 'Import Date' in df.columns:
                try:
                    last_import = pd.to_datetime(df['Import Date'].iloc[0])
                    days_old = (pd.Timestamp.now() - last_import).days
                    if days_old < 1: st.success("🟢 Fresh — imported today")
                    elif days_old <= 7: st.warning(f"🟡 {days_old} days old")
                    else: st.error(f"🔴 {days_old} days old — re-import")
                except: st.caption("Freshness: Unknown")
            
            st.metric("Positions", len(df))
        else:
            st.info("No data loaded. Import a CSV above.")

        if config.DRY_RUN:
            st.error("🔴 DRY RUN MODE — No writes to Sheets")

        st.divider()
        if st.button("🧹 Clear System Cache", width='stretch'):
            st.cache_data.clear()
            st.session_state.clear()
            st.toast("Cache cleared.")
            time.sleep(1)
            st.rerun()

    # --- Main Tabs ---
    tabs = st.tabs(["📊 Holdings", "💰 Income", "⚠️ Risk", "🔔 Signals"])

    with tabs[0]:
        if st.session_state["holdings_df"].empty:
            st.info("Upload a CSV to begin.")
        else:
            df = st.session_state["holdings_df"]
            total_val = df['Market Value'].sum()
            total_cost = df['Cost Basis'].sum()
            unrealized_gl = total_val - total_cost
            unrealized_gl_pct = (unrealized_gl / total_cost * 100) if total_cost > 0 else 0.0
            
            cash_val = df[df['Is Cash'] == True]['Market Value'].sum()
            invested_val = total_val - cash_val
            
            dc_col = 'Daily Change %' if 'Daily Change %' in df.columns else 'daily_change_pct'
            daily_change = (df['Weight'] * df[dc_col]).sum() / 100 if dc_col in df.columns else 0.0

            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Portfolio Value", f"${total_val:,.0f}", f"{daily_change:+.2f}%" if daily_change != 0 else None)
            with c2: st.metric("Unrealized G/L", f"${unrealized_gl:,.0f}", f"{unrealized_gl_pct:+.2f}%")
            with c3: st.metric("Cash Position", f"${cash_val:,.0f}", f"Invested: ${invested_val:,.0f}", delta_color="off")

            st.divider()
            non_cash_df = df[df['Is Cash'] == False]
            fig_tree = px.treemap(non_cash_df, path=['Asset Class', 'Ticker'], values='Market Value', title='Portfolio Allocation', color_discrete_sequence=['#1F4E79', '#2E86AB', '#A8DADC'])
            st.plotly_chart(fig_tree, use_container_width=True)

            st.subheader("Current Holdings")
            search = st.text_input("🔍 Search Ticker or Description")
            display_df = df if not search else df[df['Ticker'].str.contains(search, case=False) | df['Description'].str.contains(search, case=False)]
            
            cols = ['Ticker', 'Description', 'Market Value', 'Weight', 'Cost Basis', 'Unrealized G/L', 'Unrealized G/L %', 'Dividend Yield']
            st.dataframe(
                display_df[cols],
                column_config={
                    "Market Value": st.column_config.NumberColumn(format="$%,.2f"),
                    "Weight": st.column_config.ProgressColumn(format="%.2f%%", min_value=0, max_value=15),
                    "Unrealized G/L %": st.column_config.NumberColumn(format="%.2f%%"),
                },
                hide_index=True,
                use_container_width=True
            )

    with tabs[1]:
        if not st.session_state["holdings_df"].empty:
            df = st.session_state["holdings_df"]
            metrics = calculate_income_metrics(df)
            k1, k2, k3 = st.columns(3)
            k1.metric("Projected Annual Income", f"${metrics['projected_annual_income']:,.2f}")
            k2.metric("Blended Yield %", f"{metrics['blended_yield_pct']:.2f}%")
            k3.metric("Cash Contribution", f"${metrics['cash_contribution']:,.2f}")
            
            top_gen = df.nlargest(10, 'Est Annual Income')
            fig_income = px.bar(top_gen, x='Est Annual Income', y='Ticker', orientation='h', title='Top 10 Generators')
            st.plotly_chart(fig_income, use_container_width=True)

    with tabs[2]:
        if not st.session_state["holdings_df"].empty:
            df = st.session_state["holdings_df"]
            if st.button("Calculate Risk Analytics", width='stretch'):
                with st.spinner("Calculating..."):
                    hist = build_price_histories(df)
                    if not hist.empty and 'SPY' in hist.columns:
                        spy_returns = hist['SPY'].pct_change().dropna()
                        df['Beta'] = df['Ticker'].apply(lambda x: calculate_beta(x, hist, spy_returns))
                        p_beta = calculate_portfolio_beta(df)
                        st.metric("Portfolio Beta", f"{p_beta:.4f}")
                    else: st.error("Market data unavailable.")

    with tabs[3]:
        if not st.session_state["holdings_df"].empty:
            df = st.session_state["holdings_df"]
            from utils.agents.price_narrator import detect_significant_moves, batch_analyze_daily_moves
            movers = detect_significant_moves(df)
            if movers:
                with st.expander(f"🚀 Daily Movers ({len(movers)} active)", expanded=True):
                    if st.button("🎙️ Explain Movements with AI"):
                        with st.spinner("Checking news..."):
                            for n in batch_analyze_daily_moves(df):
                                st.info(f"**{n['ticker']} ({n['change_pct']:+.2f}%)**: {n['explanation']}")

# --- Define Pages ---
pg = st.navigation([
    st.Page(main_dashboard, title="Main Dashboard", icon="📈"),
    st.Page("pages/1_Rebalancing.py", title="Rebalancing", icon="⚖️"),
    st.Page("pages/2_Research.py", title="Research Hub", icon="🔬"),
    st.Page("pages/3_Performance.py", title="Performance", icon="📊"),
    st.Page("pages/4_Tax.py", title="Tax Intelligence", icon="💸"),
    st.Page("pages/5_Net_Worth.py", title="Unified Net Worth", icon="🏦"),
    st.Page("pages/6_Advisor.py", title="AI Advisor", icon="💬"),
])

pg.run()
