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
    calculate_correlation_matrix, run_stress_tests, capm_projection,
    concentration_alerts
)
from pipeline import (
    normalize_positions, write_to_sheets, ingest_realized_gl, 
    ingest_transactions, calculate_income_metrics
)
from utils.sheet_readers import get_holdings_current, get_daily_snapshots, get_risk_metrics
from utils.validators import (
    validate_percentage_range, validate_no_negative_market_values, 
    validate_duplicate_tickers, validate_total_sanity
)
from utils.column_guard import ensure_display_columns

# Import New Agents
from utils.agents.earnings_sentinel import scan_upcoming_earnings, generate_earnings_alerts
from utils.agents.macro_monitor import get_macro_snapshot, detect_macro_triggers, generate_macro_strategy
from utils.agents.concentration_hedger import check_on_page_load as check_concentration, scan_concentration_risks, generate_hedge_suggestions
from utils.agents.cash_sweeper import get_cash_sweep_alert, analyze_cash_position, generate_cash_deployment_suggestion
from utils.agents.correlation_optimizer import detect_correlation_spikes, calculate_diversification_benefit, generate_optimization_suggestions

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
        gl_file = st.file_uploader("Realized G/L", type=["csv"])
        tx_file = st.file_uploader("Transactions", type=["csv"])
        
        cash_inject = st.number_input("Manual Cash ($)", value=0.0, step=500.0)
        
        if st.button("Process Data", width='stretch'):
            if pos_file:
                with st.spinner("Ingesting Positions..."):
                    df_raw = parse_schwab_csv(pos_file.read())
                    df_cash = inject_cash_manual(df_raw, cash_inject)
                    df_enriched = enrich_positions(df_cash)
                    df_norm = normalize_positions(df_enriched, str(date.today()))
                    write_to_sheets(df_norm, cash_inject, dry_run=config.DRY_RUN)
                    st.session_state["holdings_df"] = ensure_display_columns(df_norm)
                    st.toast("Positions Updated", icon="✅")
            
            if gl_file:
                with st.spinner("Ingesting Gains..."):
                    res = ingest_realized_gl(gl_file, dry_run=config.DRY_RUN)
                    if res.get("new", 0) > 0:
                        st.toast(f"Gains: {res['new']} new rows", icon="💸")
                    else:
                        st.toast("Gains: No new rows", icon="ℹ️")

            if tx_file:
                with st.spinner("Ingesting Transactions..."):
                    res = ingest_transactions(tx_file, dry_run=config.DRY_RUN)
                    if res.get("new", 0) > 0:
                        st.toast(f"Transactions: {res['new']} new rows", icon="📑")
                    else:
                        st.toast("Transactions: No new rows", icon="ℹ️")

            if pos_file or gl_file or tx_file:
                time.sleep(1)
                st.rerun()

    st.divider()
    with st.expander("🧠 Category Enrichment"):
        st.caption("Saves ticker categories to `data/ticker_mapping.json` — applied on next CSV import.")
        if st.button("⬇️ Sync from Sheet", width='stretch', disabled=df.empty,
                     help="Reads Asset Class / Asset Strategy already in your Holdings sheet. Fast, no AI call."):
            with st.spinner("Syncing categories from sheet..."):
                try:
                    from utils.agents.portfolio_enricher import sync_from_holdings
                    ok, msg = sync_from_holdings(df)
                    if ok:
                        st.toast(msg, icon="✅")
                    else:
                        st.error(msg)
                except Exception as e:
                    st.error(f"Sync error: {e}")
        if st.button("🤖 Re-enrich via Gemini AI", width='stretch', disabled=df.empty,
                     help="Calls Gemini to re-categorize all tickers. Use if you want AI to overwrite current categories."):
            with st.spinner("Asking Gemini to categorize your holdings..."):
                try:
                    from utils.agents.portfolio_enricher import enrich_holdings_from_df
                    ok, msg = enrich_holdings_from_df(df)
                    if ok:
                        st.toast(msg, icon="✅")
                    else:
                        st.error(f"{msg} (Try 'Sync from Sheet' instead.)")
                except Exception as e:
                    st.error(f"Enrichment error: {e}")
        if df.empty:
            st.caption("Import a CSV first to enable enrichment.")

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

# --- Main Dashboard Page Function ---
def main_dashboard():
    df = ensure_display_columns(st.session_state.get(
        "holdings_df", pd.DataFrame(columns=config.POSITION_COLUMNS)
    ))

    st.title("💼 Investment Portfolio")
    tabs = st.tabs(["📊 Holdings", "💰 Income", "🛡️ Risk", "🔔 Signals"])

    with tabs[0]:
        if df.empty:
            st.info("No data loaded. Use the sidebar to import a Schwab CSV.")
        else:
            total_val = df['Market Value'].sum()
            cash_mask = (
                df['Ticker'].isin(['CASH_MANUAL', 'QACDS', 'CASH & CASH INVESTMENTS'])
                | (df['Asset Class'].astype(str).str.lower() == 'cash')
            )
            cash_val = df[cash_mask]['Market Value'].sum()

            k1, k2, k3 = st.columns(3)
            k1.metric("Total Portfolio", f"${total_val:,.0f}")
            k2.metric("Cash Balance",    f"${cash_val:,.0f}")
            k3.metric("Invested",        f"${total_val - cash_val:,.0f}")

            st.divider()

            invested_df = df[~cash_mask].copy()
            if not invested_df.empty:
                invested_df['Market Value'] = invested_df['Market Value'].clip(lower=0.01)
                fig = px.treemap(
                    invested_df, path=['Asset Class', 'Ticker'], values='Market Value',
                    title="Asset Allocation",
                    color_discrete_sequence=px.colors.qualitative.Prism
                )
                st.plotly_chart(fig, width='stretch')

            st.subheader("Current Positions")
            st.dataframe(df, width='stretch', hide_index=True)

    with tabs[1]:
        if not df.empty:
            metrics = calculate_income_metrics(df)
            i1, i2 = st.columns(2)
            i1.metric("Annual Projected Income", f"${metrics['projected_annual_income']:,.2f}")
            i2.metric("Blended Yield",           f"{metrics['blended_yield_pct']:.2f}%")
            
            # --- Cash Sweeper ---
            st.divider()
            st.subheader("💵 Yield Optimization (Cash Sweep)")
            cash_alert = get_cash_sweep_alert(df)
            if cash_alert:
                st.info(cash_alert)
                if st.button("🤖 Generate Cash Deployment Plan"):
                    with st.spinner("Analyzing yield alternatives..."):
                        analysis = analyze_cash_position(df)
                        suggestion = generate_cash_deployment_suggestion(analysis, df)
                        if "error" not in suggestion:
                            st.write(f"**Recommendation:** {suggestion['recommendation']}")
                            st.write(f"**Action:** {suggestion['proposed_action']}")
                            st.success(f"**Yield Improvement:** {suggestion['yield_improvement']}")
                            st.caption(f"Note: {suggestion['risk_note']}")
                        else:
                            st.error(suggestion['error'])
            else:
                st.success("Cash levels are optimized for yield.")

    with tabs[2]:
        if not df.empty:
            st.subheader("🛡️ Portfolio Risk Analytics")
            
            # Load existing risk results from session state OR try to fetch from Sheet
            if "risk_results" not in st.session_state:
                try:
                    risk_df = get_risk_metrics()
                    if not risk_df.empty:
                        # Extract latest metrics from Sheet
                        latest = risk_df.iloc[0]
                        st.session_state["risk_results"] = {
                            "p_beta": float(latest.get('Portfolio Beta', 1.0)),
                            "capm": {
                                "expected_pct": float(latest.get('Estimated Annual Return', 9.0)),
                                "volatility_pct": float(latest.get('Annual Volatility', 15.0)),
                            },
                            "stress": run_stress_tests(df['Market Value'].sum(), float(latest.get('Portfolio Beta', 1.0))),
                            "corr_matrix": pd.DataFrame() # Matrix isn't stored in sheet usually
                        }
                except:
                    pass

            # Action button
            if st.button("📊 Run Deep Risk Scan", help="Calculates Beta, Correlation, and Stress Tests using live market data."):
                with st.spinner("Downloading price history and calculating correlations..."):
                    hist = build_price_histories(df)
                    if not hist.empty and 'SPY' in hist.columns:
                        spy_returns = hist['SPY'].pct_change().dropna()
                        
                        # Calculate beta for all positions
                        df['Beta'] = df['Ticker'].apply(lambda x: calculate_beta(x, hist, spy_returns))
                        p_beta = calculate_portfolio_beta(df)
                        corr_matrix = calculate_correlation_matrix(df, hist)
                        
                        total_val = df['Market Value'].sum()
                        stress_results = run_stress_tests(total_val, p_beta)
                        capm_results = capm_projection(total_val, p_beta)
                        
                        # Save to session state
                        res = {
                            "p_beta": p_beta,
                            "capm": capm_results,
                            "stress": stress_results,
                            "corr_matrix": corr_matrix
                        }
                        st.session_state["risk_results"] = res
                        
                        # PERSIST TO SHEET (Hidden Step)
                        try:
                            from pipeline import write_risk_metrics
                            write_risk_metrics(res, df)
                        except:
                            pass
                            
                        st.rerun()
                    else:
                        st.error("Could not fetch enough price history for risk analysis.")

            if "risk_results" in st.session_state:
                res = st.session_state["risk_results"]
                
                r1, r2, r3 = st.columns(3)
                r1.metric("Portfolio Beta", f"{res['p_beta']:.2f}", 
                         help="Beta > 1.0 means more volatile than S&P 500")
                r2.metric("Expected Annual Return", f"{res['capm']['expected_pct']:.1f}%",
                         help="Based on CAPM (Risk-free rate + Beta * Equity Risk Premium)")
                r3.metric("Annual Volatility", f"{res['capm']['volatility_pct']:.1f}%")
                
                col_left, col_right = st.columns(2)
                with col_left:
                    st.write("### Stress Test Scenarios")
                    stress_df = pd.DataFrame(res['stress'])
                    # Add Total New Value column for clarity
                    st.table(stress_df[['scenario', 'impact_pct', 'impact', 'new_value']].style.format({
                        'impact_pct': '{:+.2f}%',
                        'impact': '${:,.0f}',
                        'new_value': '${:,.0f}'
                    }))
                
                with col_right:
                    st.write("### Correlation Heatmap (Top 20)")
                    if not res['corr_matrix'].empty:
                        fig_corr = px.imshow(
                            res['corr_matrix'],
                            color_continuous_scale='RdBu_r',
                            zmin=-1, zmax=1
                        )
                        st.plotly_chart(fig_corr, use_container_width=True)
                    else:
                        st.info("Heatmap not loaded from cache.")
                        if st.button("🔥 Generate Correlation Heatmap"):
                            with st.spinner("Downloading histories..."):
                                hist = build_price_histories(df)
                                res['corr_matrix'] = calculate_correlation_matrix(df, hist)
                                st.session_state["risk_results"] = res
                                st.rerun()

                # --- Concentration Hedger ---
                st.divider()
                st.subheader("🎯 Concentration & Hedging")
                risks = scan_concentration_risks(df)
                if risks:
                    for r in risks:
                        with st.expander(f"⚠️ {r['risk_type']}: {r['ticker']} ({r['weight']:.1f}%)"):
                            st.write(f"**Severity:** {r['severity']}")
                            st.write(f"**Price Trend (50MA):** {r['price_vs_ma']}")
                            if st.button(f"🤖 Suggest Hedge for {r['ticker']}", key=f"hedge_{r['ticker']}"):
                                with st.spinner("Consulting hedging strategist..."):
                                    suggestions = generate_hedge_suggestions([r], df)
                                    for s in suggestions:
                                        for sugg in s['suggestions']:
                                            st.info(f"**{sugg['strategy']}**: {sugg['description']}")
                else:
                    st.success("No significant concentration risks detected.")

    with tabs[3]:
        if not df.empty:
            # --- Macro Monitor ---
            st.subheader("🌐 Macro Environment")
            with st.spinner("Fetching macro data..."):
                macro_data = get_macro_snapshot()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("10Y Treasury", f"{macro_data['treasury_10y']:.2f}%")
                m2.metric("Fed Funds Rate", f"{macro_data['fed_rate']:.2f}%")
                m3.metric("VIX Index", f"{macro_data['vix']:.1f}", macro_data['vix_signal'])
                m4.metric("CPI Trend", f"{macro_data['cpi']:.1f}", macro_data['cpi_trend'])
                
                triggers = detect_macro_triggers(macro_data, df)
                if triggers:
                    for t in triggers:
                        st.warning(f"**{t['trigger']}**: {t['description']}")
                    if st.button("🤖 Generate Macro Strategy"):
                        with st.spinner("Analyzing macro implications..."):
                            strat = generate_macro_strategy(triggers, macro_data, df)
                            st.info(strat['macro_outlook'])
                            st.write(f"**Risk Level:** {strat['risk_level']}")
                            with st.expander("Sector Rotations"):
                                for rot in strat['sector_rotations']:
                                    st.write(f"**{rot['from_sector']} ➡️ {rot['to_sector']}**: {rot['rationale']}")
            
            st.divider()
            
            # --- Earnings Sentinel ---
            st.subheader("📅 Upcoming Earnings")
            with st.spinner("Scanning calendar..."):
                upcoming = scan_upcoming_earnings(df)
                if not upcoming.empty:
                    st.dataframe(upcoming[['ticker', 'date', 'eps_estimated', 'revenue_estimated']], hide_index=True)
                    if st.button("🤖 Generate Earnings Alerts"):
                        with st.spinner("Analyzing earnings impact..."):
                            alerts = generate_earnings_alerts(upcoming, df)
                            for a in alerts:
                                st.info(f"**{a['badge']} {a['ticker']} ({a['date']})**: {a['alert']}")
                else:
                    st.success("No major earnings reported in your holdings for the next 14 days.")
            
            st.divider()
            
            from utils.agents.price_narrator import detect_significant_moves, batch_analyze_daily_moves        
            movers = detect_significant_moves(df)
            if movers:
                st.subheader(f"🚀 Daily Movers ({len(movers)} active)")
                if st.button("🎙️ Explain Movements with AI"):
                    with st.spinner("Checking news..."):
                        analyses = batch_analyze_daily_moves(df)
                        for n in analyses:
                            st.info(f"**{n['Ticker']} ({n['Change %']:+.2f}%)**: {n['Explanation']}")
            else:
                st.success("No significant price movers detected today. Signals clear.")
        else:
            st.info("Agent signals appearing in next sync...")

# --- Page Navigation ---
pg = st.navigation([
    st.Page(main_dashboard,              title="Main Dashboard",    icon="📈"),
    st.Page("pages/1_Rebalancing.py",    title="Rebalancing",       icon="⚖️"),
    st.Page("pages/2_Research.py",       title="Research Hub",      icon="🔬"),
    st.Page("pages/3_Performance.py",    title="Performance",       icon="📊"),
    st.Page("pages/4_Tax.py",            title="Tax Intelligence",  icon="💸"),
    st.Page("pages/5_Net_Worth.py",      title="Unified Net Worth", icon="🏦"),
    st.Page("pages/6_Advisor.py",        title="AI Advisor",        icon="💬"),
    st.Page("pages/7_Journal.py",        title="Decision Journal",  icon="📝"),
])
pg.run()
