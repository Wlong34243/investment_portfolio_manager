import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
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
    ingest_realized_gl, ingest_transactions
)
from utils.sheet_readers import get_holdings_current

# --- Page Config ---
st.set_page_config(layout="wide", page_title="Investment Portfolio Manager", page_icon="📈")

# --- Password Gate ---
def check_password():
    """Returns True if the user had the correct password."""
    if "app_password" not in st.secrets:
        return True # Local dev mode

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True

if not check_password():
    st.stop()

# --- Load Data ---
if "holdings_df" not in st.session_state:
    st.session_state["holdings_df"] = get_holdings_current()

# --- Sidebar ---
with st.sidebar:
    st.header("Settings & Upload")
    
    if config.DRY_RUN:
        st.warning("⚠️ DRY_RUN = True (No Sheet Writes)")
    
    uploaded_file = st.file_uploader("Upload Schwab Positions CSV", type=["csv"])
    gl_file = st.file_uploader("Upload Realized G/L CSV", type=["csv"], help="Schwab: Accounts > History > Realized Gain/Loss > Export")
    tx_file = st.file_uploader("Upload Transaction History CSV", type=["csv"], help="Schwab: Accounts > History > Transactions > Export")
    
    cash_amount = st.number_input("Cash Amount ($)", value=10000.0, step=500.0)
    
    if st.button("Process CSVs", use_container_width=True):
        processing_errors = []
        
        # 1. Positions
        if uploaded_file is not None:
            with st.status("Processing Positions...") as status:
                try:
                    df_raw = parse_schwab_csv(uploaded_file.read())
                    df_cash = inject_cash_manual(df_raw, cash_amount)
                    df_enriched = enrich_positions(df_cash)
                    today_str = str(date.today())
                    df_norm = normalize_positions(df_enriched, today_str)
                    write_to_sheets(df_norm, cash_amount, dry_run=config.DRY_RUN)
                    st.session_state["holdings_df"] = df_norm
                    status.update(label="Positions Complete", state="complete")
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
            for err in processing_errors:
                st.error(err)
        else:
            st.success("All data processed successfully.")
            time.sleep(1)
            st.rerun()

    # Show info
    if not st.session_state["holdings_df"].empty:
        df = st.session_state["holdings_df"]
        last_import = df['Import Date'].iloc[0] if 'Import Date' in df.columns else "N/A"
        st.divider()
        st.info(f"Last Import: {last_import}\n\nPositions: {len(df)}")

# --- Main Tabs ---
tabs = st.tabs(["📊 Holdings", "💰 Income", "⚠️ Risk"])

with tabs[0]:
    if st.session_state["holdings_df"].empty:
        st.info("Upload a CSV to begin.")
    else:
        df = st.session_state["holdings_df"]
        
        # KPI row
        total_val = df['Market Value'].sum()
        total_cost = df['Cost Basis'].sum()
        unrealized_gl = total_val - total_cost
        unrealized_gl_pct = (unrealized_gl / total_cost * 100) if total_cost > 0 else 0.0
        
        cash_val = df[df['Is Cash'] == True]['Market Value'].sum()
        invested_val = total_val - cash_val
        pos_count = len(df)
        
        kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
        kpi1.metric("Total Value", f"${total_val:,.0f}")
        kpi2.metric("Total Cost", f"${total_cost:,.0f}")
        kpi3.metric("Unrealized G/L", f"${unrealized_gl:,.0f}", f"{unrealized_gl_pct:+.2f}%")
        kpi4.metric("Cash", f"${cash_val:,.0f}")
        kpi5.metric("Invested", f"${invested_val:,.0f}")
        kpi6.metric("Positions", pos_count)
        
        # Charts
        c1, c2 = st.columns(2)
        
        with c1:
            # Allocation by Asset Class
            non_cash_df = df[df['Is Cash'] == False]
            fig_class = px.pie(
                non_cash_df, 
                values='Market Value', 
                names='Asset Class', 
                title='Allocation by Asset Class (Invested Only)',
                color_discrete_sequence=['#1F4E79', '#2E86AB', '#A8DADC', '#457B9D']
            )
            st.plotly_chart(fig_class, use_container_width=True)
            
        with c2:
            # Allocation by Asset Strategy
            fig_strat = px.pie(
                non_cash_df, 
                values='Market Value', 
                names='Asset Strategy', 
                title='Allocation by Asset Strategy (Invested Only)',
                color_discrete_sequence=['#1F4E79', '#2E86AB', '#A8DADC', '#457B9D']
            )
            st.plotly_chart(fig_strat, use_container_width=True)
            
        # Top 10 positions bar chart
        top_10 = df.nlargest(10, 'Market Value')
        fig_top = px.bar(
            top_10, 
            x='Market Value', 
            y='Ticker', 
            orientation='h', 
            title='Top 10 Positions by Market Value',
            color_discrete_sequence=['#2E86AB']
        )
        fig_top.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_top, use_container_width=True)
        
        # Holdings table
        st.subheader("Current Holdings")
        
        # Search filter
        search = st.text_input("Search Ticker or Description")
        if search:
            display_df = df[
                df['Ticker'].str.contains(search, case=False) | 
                df['Description'].str.contains(search, case=False)
            ]
        else:
            display_df = df
            
        # Format columns for display
        cols = ['Ticker', 'Description', 'Market Value', 'Weight', 'Cost Basis', 'Unrealized G/L', 'Unrealized G/L %', 'Dividend Yield']
        
        # Styling function for concentration
        def highlight_concentration(row):
            if row['Weight'] > config.SINGLE_POSITION_WARN_PCT:
                return ['background-color: #FFF9C4'] * len(row)
            return [''] * len(row)
            
        # Pagination
        items_per_page = 20
        total_pages = (len(display_df) // items_per_page) + (1 if len(display_df) % items_per_page > 0 else 0)
        page = st.number_input("Page", min_value=1, max_value=max(1, total_pages), value=1, key="holdings_page")
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        page_df = display_df.iloc[start_idx:end_idx][cols]
        
        st.table(page_df.style.apply(highlight_concentration, axis=1).format({
            'Market Value': '${:,.2f}',
            'Weight': '{:.2f}%',
            'Cost Basis': '${:,.2f}',
            'Unrealized G/L': '${:,.2f}',
            'Unrealized G/L %': '{:.2f}%',
            'Dividend Yield': '{:.2f}%'
        }))

with tabs[1]:
    if st.session_state["holdings_df"].empty:
        st.info("Upload a CSV to begin.")
    else:
        df = st.session_state["holdings_df"]
        
        # Calculate metrics
        from pipeline import calculate_income_metrics
        income_metrics = calculate_income_metrics(df)
        
        # KPI row
        k1, k2, k3 = st.columns(3)
        k1.metric("Projected Annual Income", f"${income_metrics['projected_annual_income']:,.2f}")
        k2.metric("Blended Yield %", f"{income_metrics['blended_yield_pct']:.2f}%")
        k3.metric("Cash Contribution", f"${income_metrics['cash_contribution']:,.2f}")
        
        # Monthly estimate
        st.write(f"**Estimated Monthly Income:** `${income_metrics['projected_annual_income']/12:,.2f}`")
        
        # Top Generators Bar Chart
        top_gen = df.nlargest(10, 'Est Annual Income')
        fig_income = px.bar(
            top_gen,
            x='Est Annual Income',
            y='Ticker',
            orientation='h',
            title='Top 10 Income Generators',
            color_discrete_sequence=['#F39C12'] # Gold/Amber
        )
        fig_income.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_income, use_container_width=True)
        
        # Callout boxes
        if 'ET' in df['Ticker'].values:
            st.info("💡 **Energy Transfer LP (ET):** High yield but generates K-1. Consult tax advisor.")
        if 'JPIE' in df['Ticker'].values:
            st.info("💡 **JPMorgan Income ETF (JPIE):** Primary income vehicle. Monthly distributions.")
            
        # Income Table
        st.subheader("Income Details")
        income_df = df[df['Dividend Yield'] > 0].sort_values(by='Est Annual Income', ascending=False)
        st.table(income_df[['Ticker', 'Description', 'Market Value', 'Dividend Yield', 'Est Annual Income']].style.format({
            'Market Value': '${:,.2f}',
            'Dividend Yield': '{:.2f}%',
            'Est Annual Income': '${:,.2f}'
        }))

with tabs[2]:
    if st.session_state["holdings_df"].empty:
        st.info("Upload a CSV to begin.")
    else:
        df = st.session_state["holdings_df"]
        
        # Calculate Alerts
        alerts = concentration_alerts(df)
        for alert in alerts:
            st.warning(alert)
            
        if st.button("Calculate Risk Analytics", use_container_width=True):
            with st.spinner("Fetching 1yr price history and calculating risk..."):
                try:
                    # Cache price histories in session state
                    if "price_histories" not in st.session_state or time.time() - st.session_state.get("price_hist_ts", 0) > 300:
                        hist = build_price_histories(df)
                        st.session_state["price_histories"] = hist
                        st.session_state["price_hist_ts"] = time.time()
                    else:
                        hist = st.session_state["price_histories"]
                        
                    if not hist.empty and 'SPY' in hist.columns:
                        spy_returns = hist['SPY'].pct_change().dropna()
                        
                        # Calculate individual betas
                        df['Beta'] = df['Ticker'].apply(lambda x: calculate_beta(x, hist, spy_returns))
                        
                        # Portfolio Beta
                        p_beta = calculate_portfolio_beta(df)
                        
                        # Stress Tests
                        total_val = df['Market Value'].sum()
                        stress_results = run_stress_tests(total_val, p_beta)
                        
                        # CAPM
                        capm_res = capm_projection(total_val, p_beta)
                        
                        # Prepare Risk Metrics for Sheet
                        top_pos = df.nlargest(1, 'Weight')
                        
                        # Sector concentration
                        sector_weights = df.groupby('Asset Class')['Weight'].sum()
                        top_sector_name = sector_weights.idxmax()
                        top_sector_pct = sector_weights.max()
                        
                        risk_snapshot = {
                            "portfolio_beta": p_beta,
                            "top_pos_pct": float(top_pos['Weight'].iloc[0]),
                            "top_pos_ticker": str(top_pos['Ticker'].iloc[0]),
                            "top_sector_pct": float(top_sector_pct),
                            "top_sector_name": str(top_sector_name),
                            "var_95": 0.0,
                            "stress_impact": float(stress_results[2]['impact']) # -10% scenario
                        }
                        
                        # Write to sheets
                        if not config.DRY_RUN:
                            from utils.sheet_readers import get_gspread_client
                            client = get_gspread_client()
                            spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
                            ws_risk = spreadsheet.worksheet(config.TAB_RISK_METRICS)
                            write_risk_snapshot(ws_risk, risk_snapshot)
                        
                        # Store results in session state for display
                        st.session_state["risk_results"] = {
                            "p_beta": p_beta,
                            "stress": stress_results,
                            "capm": capm_res,
                            "corr": calculate_correlation_matrix(df, hist)
                        }
                        st.success("Risk analytics calculated successfully.")
                    else:
                        st.error("Could not fetch price history for SPY or other tickers.")
                except Exception as e:
                    st.error(f"Error calculating risk: {e}")
                    import traceback
                    st.write(traceback.format_exc())

        # Display Results
        if "risk_results" in st.session_state:
            res = st.session_state["risk_results"]
            
            # KPI Row
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Portfolio Beta", f"{res['p_beta']:.4f}")
            r2.metric("Expected 1yr Return", f"${res['capm']['expected']:,.0f}", f"{res['capm']['expected_pct']:.2f}%")
            r3.metric("Worst Case (10th)", f"${res['capm']['bad']:,.0f}")
            r4.metric("Best Case (90th)", f"${res['capm']['good']:,.0f}")
            
            # CAPM Chart
            st.subheader("CAPM 1yr Projection")
            fig_capm = go.Figure()
            fig_capm.add_trace(go.Bar(
                y=['Bad Case', 'Expected', 'Good Case'],
                x=[res['capm']['bad'], res['capm']['expected'], res['capm']['good']],
                orientation='h',
                marker_color=['#E74C3C', '#3498DB', '#2ECC71']
            ))
            st.plotly_chart(fig_capm, use_container_width=True)
            
            # Stress Test Table
            st.subheader("Market Stress Tests")
            stress_df = pd.DataFrame(res['stress'])
            st.table(stress_df.style.format({
                'market_pct': '{:+.2f}%',
                'impact': '${:,.2f}',
                'new_value': '${:,.2f}',
                'impact_pct': '{:+.2f}%'
            }))
            
            # Correlation Heatmap
            if not res['corr'].empty:
                st.subheader("Correlation Heatmap (Top 20)")
                fig_corr = px.imshow(
                    res['corr'],
                    color_continuous_scale='RdBu_r',
                    zmin=-1, zmax=1,
                    title="Price Correlation (1yr Daily Returns)"
                )
                st.plotly_chart(fig_corr, use_container_width=True)
