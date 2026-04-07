import streamlit as st
import pandas as pd
import plotly.express as px
from utils.sheet_readers import get_holdings_current, get_realized_gl, get_target_allocation, get_ai_suggested_allocation
from utils.column_guard import ensure_display_columns
from utils.agents.tax_intelligence_agent import calculate_drift, generate_rebalance_proposals, check_wash_sale_risk
import os
import sys
import json
import subprocess
from datetime import date
import config

st.set_page_config(layout="wide", page_title="Rebalancing", page_icon="⚖️")

st.title("⚖️ Tax-Aware Rebalancing Overhaul")
st.info("💡 **Comparative Matrix.** This page compares your current holdings against manual targets and AI podcast suggestions.")

if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

try:
    # 1. Data Loading
    df_holdings = get_holdings_current()
    df_targets = get_target_allocation()
    df_ai = get_ai_suggested_allocation()
    realized_gl_df = get_realized_gl()

    if df_holdings.empty or df_targets.empty:
        st.warning("Please ensure your Current Holdings and Target Allocations are populated in Google Sheets.")
        st.stop()

    # 2. Calculate Current Allocations
    # Ensure Market Value is numeric
    df_holdings['Market Value'] = pd.to_numeric(df_holdings['Market Value'], errors='coerce').fillna(0.0)
    total_portfolio_value = df_holdings['Market Value'].sum()

    # --- NORMALIZE CASH ---
    # Identify cash rows by Asset Class or known cash tickers
    cash_mask = (
        (df_holdings['Asset Class'].astype(str).str.lower() == 'cash') | 
        (df_holdings['Ticker'].astype(str).str.upper().isin(config.CASH_TICKERS))
    )
    # Force Asset Class to 'Cash' for these rows before grouping
    df_holdings.loc[cash_mask, 'Asset Class'] = 'Cash'

    # Group by Asset Class
    df_actuals = df_holdings.groupby('Asset Class')['Market Value'].sum().reset_index()
    df_actuals.columns = ['Asset Class', 'Actual Value']
    df_actuals['Actual %'] = (df_actuals['Actual Value'] / total_portfolio_value * 100).astype(float)

    # 3. The Grand Merge
    # Ensure Asset Class is string for matching
    df_actuals['Asset Class'] = df_actuals['Asset Class'].astype(str).str.strip()
    df_targets['Asset Class'] = df_targets['Asset Class'].astype(str).str.strip()
    df_ai['Asset Class'] = df_ai['Asset Class'].astype(str).str.strip()

    # Prefix AI columns to avoid clash
    df_ai_prep = df_ai.rename(columns={
        'Target %': 'AI Target %',
        'Notes': 'AI Notes',
        'Min %': 'AI Min %',
        'Max %': 'AI Max %'
    })

    # First merge: Actuals + Targets
    df_merged = pd.merge(df_actuals, df_targets, on='Asset Class', how='outer')

    # Second merge: + AI Suggestions
    df_final = pd.merge(df_merged, df_ai_prep[['Asset Class', 'AI Target %', 'AI Notes']], on='Asset Class', how='outer')

    # Fill NaNs in percentage columns
    pct_cols = ['Actual %', 'Target %', 'Min %', 'Max %', 'AI Target %']
    for col in pct_cols:
        if col in df_final.columns:
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0.0)

    # 4. Delta Calculations
    df_final['Drift %'] = df_final['Actual %'] - df_final['Target %']
    df_final['AI Delta %'] = df_final['AI Target %'] - df_final['Target %']

    # --- UI Rendering - The Chart ---
    st.subheader("Allocation Comparison")
    
    # Prepare data for long-form plotly
    chart_data = df_final.melt(
        id_vars=['Asset Class'], 
        value_vars=['Actual %', 'Target %', 'AI Target %'],
        var_name='Type', 
        value_name='Percentage'
    )
    # Ensure ONLY floats
    chart_data['Percentage'] = chart_data['Percentage'].astype(float)

    fig = px.bar(
        chart_data, 
        x='Asset Class', 
        y='Percentage', 
        color='Type', 
        barmode='group',
        color_discrete_map={
            'Actual %': '#2E86AB',   # Blue
            'Target %': '#BDC3C7',   # Grey
            'AI Target %': '#F1C40F'  # Yellow
        },
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- UI Rendering - The Matrix ---
    st.subheader("Comparative Matrix")
    
    # Select and order columns
    matrix_cols = [
        'Asset Class', 'Asset Strategy', 'Actual %', 'Target %', 
        'Drift %', 'AI Target %', 'AI Delta %', 'AI Notes'
    ]
    # Filter to columns that actually exist
    matrix_cols = [c for c in matrix_cols if c in df_final.columns]

    st.dataframe(
        df_final[matrix_cols],
        column_config={
            'Actual %': st.column_config.NumberColumn(format="%.1f%%"),
            'Target %': st.column_config.NumberColumn(format="%.1f%%"),
            'Drift %': st.column_config.NumberColumn(format="%+.1f%%"),
            'AI Target %': st.column_config.NumberColumn(format="%.1f%%"),
            'AI Delta %': st.column_config.NumberColumn(format="%+.1f%%"),
        },
        use_container_width=True,
        hide_index=True
    )

    # --- Strategy Imports (JSON & STAX) ---
    st.divider()
    imp_col1, imp_col2 = st.columns(2)

    with imp_col1:
        with st.expander("📥 Import Offline AI Strategy"):
            st.write("Upload a JSON strategy file generated by your AI (Claude/ChatGPT).")
            uploaded_file = st.file_uploader("Upload Strategy JSON", type=["json"])
            
            if uploaded_file is not None:
                try:
                    strategy_preview = json.load(uploaded_file)
                    st.json(strategy_preview, expanded=False)
                    
                    if st.button("🚀 Execute JSON Import", type="primary"):
                        with st.spinner("Writing to Google Sheets..."):
                            temp_path = os.path.join("tasks", "temp_strategy.json")
                            uploaded_file.seek(0)
                            with open(temp_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                                
                            try:
                                result = subprocess.run(
                                    [sys.executable, "tasks/weekly_podcast_sync.py", "--import-json", temp_path, "--live"],
                                    capture_output=True, text=True, check=True
                                )
                                os.remove(temp_path)
                                st.success("Strategy successfully written!")
                                st.code(result.stdout)
                                time.sleep(1)
                                st.rerun()
                            except subprocess.CalledProcessError as e:
                                st.error("The import script failed.")
                                st.code(e.stderr)
                                if os.path.exists(temp_path):
                                    os.remove(temp_path)
                except json.JSONDecodeError:
                    st.error("Invalid JSON file.")

    with imp_col2:
        with st.expander("📊 Ingest STAX Report"):
            st.write("Paste the Schwab STAX monthly summary text here.")
            stax_text = st.text_area("STAX Report Text", height=150, help="Paste PDF or website summary text.")
            stax_source = st.text_input("Source Label", value=f"Schwab STAX {date.today().strftime('%B %Y')}")
            
            if st.button("🤖 Analyze & Sync STAX", type="primary", disabled=len(stax_text) < 200):
                with st.spinner("Gemini is analyzing STAX flows..."):
                    # Use a temp file to pass text to the script
                    temp_stax = os.path.join("tasks", "temp_stax.txt")
                    with open(temp_stax, "w", encoding="utf-8") as f:
                        f.write(stax_text)
                        
                    try:
                        result = subprocess.run(
                            [sys.executable, "tasks/stax_sync.py", "--file", temp_stax, "--source", stax_source, "--live"],
                            capture_output=True, text=True, check=True
                        )
                        os.remove(temp_stax)
                        st.success("STAX Intelligence successfully synced!")
                        st.code(result.stdout)
                        time.sleep(1)
                        st.rerun()
                    except subprocess.CalledProcessError as e:
                        st.error("STAX Ingestion failed.")
                        st.code(e.stderr)
                        if os.path.exists(temp_stax):
                            os.remove(temp_stax)
            elif len(stax_text) > 0 and len(stax_text) < 200:
                st.caption("⚠️ Report text too short for analysis.")

    # --- Rebalancing Proposals ---
    st.divider()
    st.subheader("AI Rebalancing Proposals")

    if st.button("🧠 Generate Tax-Aware Proposals", width='stretch'):
        with st.spinner("AI is evaluating tax lots and drift..."):
            # Note: calculate_drift in agent returns a tuple, but here we already have df_final
            # We'll pass df_final (which has Drift %) to the proposal engine.
            # Standardize names for the agent
            agent_drift = df_final.rename(columns={'Asset Class': 'Category'})
            proposals = generate_rebalance_proposals(agent_drift, df_holdings)
            if proposals:
                for p in proposals:
                    st.write(f"### Category: {p['category']}")
                    opts = p['options']
                    cols = st.columns(max(1, min(len(opts), 3)))
                    for i, opt in enumerate(opts[:3]):
                        with cols[i]:
                            st.markdown(f"**{opt['label']}**")
                            st.write(opt['description'])
                            st.info(f"Tax: {opt['tax_impact']}\n\nLevel: {opt['estimated_tax_impact_level']}")
            else:
                st.success("Your portfolio is within tolerance. No urgent rebalancing needed.")

    # --- Wash Sale Monitor ---
    st.divider()
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🚿 Wash Sale Monitor")
        # Ensure weight exists for sorting
        df_h_calc = df_holdings.copy()
        df_h_calc['Weight'] = (df_h_calc['Market Value'] / total_portfolio_value * 100)
        tickers_to_check = df_h_calc.nlargest(10, 'Weight')['Ticker'].tolist()
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
        if 'Acquisition Date' in df_holdings.columns:
            try:
                df_h_calc['Acquisition Date'] = pd.to_datetime(df_h_calc['Acquisition Date'], errors='coerce')
                one_year_ago = pd.Timestamp.now() - pd.Timedelta(days=365)
                df_h_calc['Term'] = df_h_calc['Acquisition Date'].apply(lambda x: 'Long Term' if x < one_year_ago else 'Short Term')
                term_dist = df_h_calc.groupby('Term')['Market Value'].sum().reset_index()
                fig_term = px.pie(term_dist, values='Market Value', names='Term', color_discrete_sequence=['#27AE60', '#F1C40F'])
                st.plotly_chart(fig_term, use_container_width=True)
            except:
                st.write("Could not calculate holding periods from available data.")
        else:
            st.info("Acquisition dates not found in current holdings.")

except Exception as e:
    st.error(f"An error occurred during rebalancing calculation: {e}")
    st.exception(e)
