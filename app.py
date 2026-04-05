import streamlit as st

st.set_page_config(layout="wide", page_title="Investment Manager", page_icon="📈")

from utils.auth import require_auth
require_auth()

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import traceback
from datetime import date
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

# --- Page Setup & Navigation (2026 Style) ---
def _main_dashboard_impl():
    # --- Load Data ---
    if "holdings_df" not in st.session_state:
        try:
            st.session_state["holdings_df"] = get_holdings_current()
        except Exception as e:
            st.error("Could not connect to Google Sheets. Check your connection and service account permissions.")
            st.stop()

    # --- Sidebar ---
    with st.sidebar:
        st.header("Control Panel")
        
        # 1. Import Data Expander
        is_empty = st.session_state.get("holdings_df", pd.DataFrame()).empty
        with st.expander("📥 Import Data", expanded=is_empty):
            uploaded_file = st.file_uploader("Upload Schwab Positions CSV", type=["csv"])
            gl_file = st.file_uploader("Upload Realized G/L CSV", type=["csv"], help="Schwab: Accounts > History > Realized Gain/Loss > Export")
            tx_file = st.file_uploader("Upload Transaction History CSV", type=["csv"], help="Schwab: Accounts > History > Transactions > Export")
            
            cash_amount = st.number_input("Cash Amount ($)", value=0.0, step=500.0)
            
            if st.button("Process CSVs", width='stretch'):
                processing_errors = []
                data_warnings = []
                
                # 1. Positions
                if uploaded_file is not None:
                    with st.status("Processing Positions...") as status:
                        try:
                            old_df = st.session_state.get("holdings_df", pd.DataFrame())
                            
                            df_raw = parse_schwab_csv(uploaded_file.read())
                            df_cash = inject_cash_manual(df_raw, cash_amount)
                            df_enriched = enrich_positions(df_cash)
                            
                            # --- Validation Step ---
                            pct_issues = validate_percentage_range(df_enriched, 'daily_change_pct')
                            if not pct_issues.empty:
                                data_warnings.append(f"⚠️ {len(pct_issues)} positions have suspicious daily changes (>100% or <-50%). Outliers capped.")
                                df_enriched['daily_change_pct'] = df_enriched['daily_change_pct'].clip(-50, 100)
                            
                            mv_issues = validate_no_negative_market_values(df_enriched)
                            if not mv_issues.empty:
                                data_warnings.append(f"⚠️ {len(mv_issues)} non-cash positions have zero or negative market value.")
                            
                            dup_issues = validate_duplicate_tickers(df_enriched)
                            if not dup_issues.empty:
                                data_warnings.append(f"⚠️ {len(dup_issues)} duplicate tickers detected.")
                                
                            total_warnings = validate_total_sanity(df_enriched, expected_range=(400000, 600000))
                            data_warnings.extend(total_warnings)
                            st.session_state["data_warnings"] = data_warnings

                            today_str = str(date.today())
                            df_norm = normalize_positions(df_enriched, today_str)
                            write_to_sheets(df_norm, cash_amount, dry_run=config.DRY_RUN)
                            
                            # Reconciliation Logic
                            if not old_df.empty:
                                old_tickers = set(old_df['Ticker'].unique())
                                new_tickers = set(df_norm['ticker'].unique())
                                added = new_tickers - old_tickers
                                removed = old_tickers - new_tickers
                                if added or removed:
                                    with st.expander("📋 Position Changes Since Last Import", expanded=True):
                                        if added: st.success(f"**New:** {', '.join(sorted(added))}")
                                        if removed: st.warning(f"**Removed:** {', '.join(sorted(removed))}")
                            
                            st.session_state["holdings_df"] = df_display
                            status.update(label="Positions Complete", state="complete")

                            # Audit Trail
                            if "import_history" not in st.session_state:
                                st.session_state["import_history"] = []
                            st.session_state["import_history"].append({
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "file": uploaded_file.name,
                                "type": "Positions",
                                "rows": len(df_norm),
                                "status": "Success"
                            })

                            if hasattr(get_holdings_current, "clear"):
                                get_holdings_current.clear()
                        except Exception as e:
                            processing_errors.append(f"Positions Error: {e}")
                            status.update(label="Positions Failed", state="error")
                
                # 2. Realized G/L
                if gl_file is not None:
                    with st.status("Processing Realized G/L...") as status:
                        try:
                            gl_result = ingest_realized_gl(gl_file, dry_run=config.DRY_RUN)
                            st.sidebar.success(f"G/L: {gl_result['new']} new lots.")
                            status.update(label="G/L Complete", state="complete")
                        except Exception as e:
                            processing_errors.append(f"G/L Error: {e}")
                            status.update(label="G/L Failed", state="error")

                # 3. Transactions
                if tx_file is not None:
                    with st.status("Processing Transactions...") as status:
                        try:
                            tx_result = ingest_transactions(tx_file, dry_run=config.DRY_RUN)
                            st.sidebar.success(f"TX: {tx_result['new']} new entries.")
                            status.update(label="Transactions Complete", state="complete")
                        except Exception as e:
                            processing_errors.append(f"Transactions Error: {e}")
                            status.update(label="Transactions Failed", state="error")

                if processing_errors:
                    for err in processing_errors: st.error(err)
                else:
                    st.toast("All data processed successfully.", icon="✅")
                    time.sleep(1)
                    st.rerun()

        # 2. Portfolio Status Section
        st.divider()
        st.subheader("Portfolio Status")
        if not st.session_state["holdings_df"].empty:
            df_status = st.session_state["holdings_df"]
            if 'Import Date' in df_status.columns:
                try:
                    last_import = pd.to_datetime(df_status['Import Date'].iloc[0])
                    days_old = (pd.Timestamp.now() - last_import).days
                    if days_old < 1: st.success(f"🟢 Fresh — imported today")
                    elif days_old <= 7: st.warning(f"🟡 {days_old} days old")
                    else: st.error(f"🔴 {days_old} days old — re-import")
                except: st.caption(f"Last Import: {df_status['Import Date'].iloc[0]}")
            st.metric("Positions", len(df_status))
            
            # Import History Audit Trail
            if st.session_state.get("import_history"):
                with st.expander("🕒 Import History"):
                    for entry in reversed(st.session_state["import_history"][-5:]):
                        st.write(f"**{entry['timestamp']}**")
                        st.caption(f"{entry['type']}: {entry['file']} ({entry['rows']} rows)")
        else:
            st.info("No data loaded. Import a Schwab CSV.")

        if config.DRY_RUN:
            st.error("🔴 DRY RUN MODE — No writes to Sheets")

        if st.session_state.get("data_warnings"):
            with st.sidebar.expander("📊 Data Quality Report", expanded=True):
                for warning in st.session_state["data_warnings"]: st.warning(warning)
                if st.button("Clear Report"):
                    st.session_state["data_warnings"] = []
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

            with st.expander("📊 Detailed Allocation (Pie Charts)"):
                pc1, pc2 = st.columns(2)
                with pc1: st.plotly_chart(px.pie(non_cash_df, values='Market Value', names='Asset Class', title='By Asset Class'), use_container_width=True)
                with pc2: st.plotly_chart(px.pie(non_cash_df, values='Market Value', names='Asset Strategy', title='By Strategy'), use_container_width=True)

            st.divider()
            st.subheader("Current Holdings")
            search = st.text_input("🔍 Search Ticker or Description", placeholder="e.g. AAPL")
            display_df = df if not search else df[df['Ticker'].str.contains(search, case=False) | df['Description'].str.contains(search, case=False)]
            cols = ['Ticker', 'Description', 'Market Value', 'Weight', 'Cost Basis', 'Unrealized G/L', 'Unrealized G/L %', 'Dividend Yield']
            st.dataframe(display_df[cols], column_config={"Market Value": st.column_config.NumberColumn(format="$%,.2f"), "Cost Basis": st.column_config.NumberColumn(format="$%,.2f"), "Weight": st.column_config.ProgressColumn(format="%.2f%%", min_value=0, max_value=15), "Unrealized G/L": st.column_config.NumberColumn(format="$%,.2f"), "Unrealized G/L %": st.column_config.NumberColumn(format="%.2f%%"), "Dividend Yield": st.column_config.NumberColumn(format="%.2f%%")}, hide_index=True, use_container_width=True)

    with tabs[1]:
        if not st.session_state["holdings_df"].empty:
            df = st.session_state["holdings_df"]
            metrics = calculate_income_metrics(df)
            k1, k2, k3 = st.columns(3)
            k1.metric("Projected Annual Income", f"${metrics['projected_annual_income']:,.2f}")
            k2.metric("Blended Yield %", f"{metrics['blended_yield_pct']:.2f}%")
            k3.metric("Cash Contribution", f"${metrics['cash_contribution']:,.2f}")
            top_gen = df.nlargest(10, 'Est Annual Income')
            st.plotly_chart(px.bar(top_gen, x='Est Annual Income', y='Ticker', orientation='h', title='Top 10 Generators', color_discrete_sequence=['#F39C12']), use_container_width=True)

    with tabs[2]:
        if not st.session_state["holdings_df"].empty:
            df = st.session_state["holdings_df"]
            if st.button("Calculate Risk Analytics", width='stretch'):
                with st.spinner("Analyzing risk..."):
                    hist = build_price_histories(df)
                    if not hist.empty and 'SPY' in hist.columns:
                        spy_returns = hist['SPY'].pct_change().dropna()
                        df['Beta'] = df['Ticker'].apply(lambda x: calculate_beta(x, hist, spy_returns))
                        p_beta = calculate_portfolio_beta(df)
                        st.metric("Portfolio Beta", f"{p_beta:.4f}")
                        st.plotly_chart(px.imshow(calculate_correlation_matrix(df, hist), color_continuous_scale='RdBu_r', zmin=-1, zmax=1, title="Correlation Matrix"), use_container_width=True)
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
                            for n in batch_analyze_daily_moves(df): st.info(f"**{n['ticker']} ({n['change_pct']:+.2f}%)**: {n['explanation']}")
            
            from utils.agents.macro_monitor import get_macro_snapshot, detect_macro_triggers, generate_macro_strategy
            with st.expander("🌍 Macro Event Monitor", expanded=True):
                macro = get_macro_snapshot()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("CPI", f"{macro['cpi']:.1f}", macro['cpi_trend'])
                m2.metric("Fed Rate", f"{macro['fed_rate']:.2f}%")
                m3.metric("10Y Treasury", f"{macro['treasury_10y']:.2f}%")
                m4.metric("VIX", f"{macro['vix']:.1f}", macro['vix_signal'], delta_color="inverse")
                if st.button("🗺️ Generate Macro Strategy"):
                    strat = generate_macro_strategy(detect_macro_triggers(macro, df), macro, df)
                    if "error" not in strat:
                        st.toast("Macro strategy generated", icon="✅")
                        st.success(f"**Outlook:** {strat['macro_outlook']}")
                        for rot in strat.get('sector_rotations', []): st.write(f"🔄 **Rotate:** {rot['from_sector']} → {rot['to_sector']} ({rot['rationale']})")

            from utils.agents.earnings_sentinel import scan_upcoming_earnings, generate_earnings_alerts
            upcoming = scan_upcoming_earnings(df)
            if not upcoming.empty:
                with st.expander(f"📅 Upcoming Earnings ({len(upcoming)})", expanded=True):
                    st.table(upcoming)
                    if st.button("🔔 Generate AI Insights"):
                        for alert in generate_earnings_alerts(upcoming, df): st.info(f"{alert['badge']} **{alert['ticker']} ({alert['date']})**: {alert['alert']}")

def main_dashboard():
    try:
        _main_dashboard_impl()
    except Exception as e:
        st.error("Dashboard failed to load.")
        with st.expander("Details"): st.code(traceback.format_exc())
        if st.button("🔄 Retry"):
            st.cache_data.clear()
            st.rerun()

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
