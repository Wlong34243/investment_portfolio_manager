import streamlit as st
import pandas as pd
import plotly.express as px
from utils.sheet_readers import get_holdings_current, get_realized_gl, get_target_allocation, get_ai_suggested_allocation
from utils.column_guard import ensure_display_columns
from utils.agents.tax_intelligence_agent import calculate_drift, generate_rebalance_proposals, check_wash_sale_risk
import os
import sys

st.title("⚖️ Tax-Aware Rebalancing")
st.info("💡 **Analysis only.** This page suggests actions but does not execute trades or modify your spreadsheet.")

if st.button("🔄 Refresh Holdings Data"):
    st.cache_data.clear()
    if "holdings_df" in st.session_state:
        del st.session_state["holdings_df"]
    st.rerun()

# --- Load Data ---
targets_df = get_target_allocation()
ai_suggested_df = get_ai_suggested_allocation()
realized_gl_df = get_realized_gl()

# --- AI Strategy Comparison ---
if not ai_suggested_df.empty:
    st.header("🤖 AI Strategy Comparison")
    source = ai_suggested_df['Source'].iloc[0]
    dt = ai_suggested_df['Date'].iloc[0]
    st.caption(f"Latest Strategy: {source} — {dt}")
    
    if 'Executive Summary' in ai_suggested_df.columns:
        st.info(ai_suggested_df['Executive Summary'].iloc[0])

    # --- Merge and Delta Calculation ---
    # Renaming to prevent collisions on merge
    t_copy = targets_df.copy().rename(columns={'Target %': 'Current Target %'})
    a_copy = ai_suggested_df.copy().rename(columns={'Target %': 'AI Target %'})
    
    # Outer join on Asset Class
    comparison_df = pd.merge(
        t_copy, 
        a_copy, 
        on='Asset Class', 
        how='outer'
    )
    
    # Fill NaN with 0.0
    comparison_df['Current Target %'] = comparison_df['Current Target %'].fillna(0.0)
    comparison_df['AI Target %'] = comparison_df['AI Target %'].fillna(0.0)
    
    # Calculate Delta %
    comparison_df['Delta %'] = comparison_df['AI Target %'] - comparison_df['Current Target %']
    
    # Display table
    display_cols = ['Asset Class', 'Current Target %', 'AI Target %', 'Delta %']
    if 'Notes_x' in comparison_df.columns:
        comparison_df = comparison_df.rename(columns={'Notes_x': 'Notes'})
        display_cols.append('Notes')
    elif 'Notes' in comparison_df.columns:
        display_cols.append('Notes')

    st.dataframe(
        comparison_df[display_cols],
        column_config={
            'Current Target %': st.column_config.NumberColumn(format="%.1f%%"),
            'AI Target %': st.column_config.NumberColumn(format="%.1f%%"),
            'Delta %': st.column_config.NumberColumn(format="%+.1f%%"),
        },
        use_container_width=True,
        hide_index=True
    )

# --- Load Holdings (direct read — bypasses all st.cache_data) ---
try:
    from utils.sheet_readers import get_gspread_client, read_gsheet_robust
    import config as _cfg
    _client = get_gspread_client()
    _ss = _client.open_by_key(_cfg.PORTFOLIO_SHEET_ID)
    _ws = _ss.worksheet(_cfg.TAB_HOLDINGS_CURRENT)
    holdings_df = ensure_display_columns(read_gsheet_robust(_ws))
except Exception as e:
    st.error(f"Could not load holdings data from sheet: {e}")
    st.stop()

if holdings_df.empty:
    st.warning("No holdings data available. Please upload a positions CSV on the main page.")
    st.stop()

if targets_df.empty:
    st.error("Target_Allocation tab not found or empty in Google Sheets.")
    st.stop()

# --- Drift Calculation (inlined to avoid stale module cache on Streamlit Cloud) ---
def _compute_drift(h, t):
    t_df = t.copy()
    if 'Asset Class' in t_df.columns:
        t_df = t_df.rename(columns={'Asset Class': 'Category'})
    target_pct_col = next((c for c in t_df.columns if 'Target' in c), None)
    if not target_pct_col:
        return pd.DataFrame()
    t_df['Target %'] = pd.to_numeric(t_df[target_pct_col], errors='coerce').fillna(0.0)
    target_cats = t_df['Category'].tolist()

    h_df = h.copy()
    h_df['Market Value'] = pd.to_numeric(h_df['Market Value'], errors='coerce').fillna(0.0)

    def _match(ac):
        if not ac or str(ac).lower() in ('other', 'n/a', '', 'nan'):
            return 'Unallocated'
        if ac in target_cats:
            return ac
        ac_l = str(ac).lower()
        for tc in target_cats:
            if tc.lower() == ac_l:
                return tc
        for tc in target_cats:
            if ac_l in tc.lower() or tc.lower() in ac_l:
                return tc
        return ac  # unmatched — surfaces in Unallocated

    # Build a lookup dict from unique Asset Class values — avoids apply() closure issues
    unique_ac = h_df['Asset Class'].astype(str).str.strip().unique()
    ac_to_cat = {ac: _match(ac) for ac in unique_ac}

    # Vectorized assignment: map Asset Class → Category, then override cash rows
    h_df['Category'] = h_df['Asset Class'].astype(str).str.strip().map(ac_to_cat)

    is_cash_bool = h_df['Is Cash'].astype(str).str.upper().isin(['TRUE', 'YES', '1', 'T'])
    cash_ticker_mask = h_df['Ticker'].astype(str).str.upper().isin(['QACDS', 'CASH_MANUAL', 'CASH'])
    h_df.loc[is_cash_bool | cash_ticker_mask, 'Category'] = 'Cash'

    total_mv = h_df['Market Value'].sum()
    if total_mv <= 0:
        return pd.DataFrame()

    actual = (
        h_df.groupby('Category')['Market Value']
        .sum()
        .apply(lambda x: round(x / total_mv * 100, 2))
        .reset_index()
    )
    actual.columns = ['Category', 'Actual %']

    known_cats = set(target_cats) | {'Cash'}
    unmatched_pct = actual[~actual['Category'].isin(known_cats)]['Actual %'].sum()
    result = pd.merge(t_df, actual, on='Category', how='left')
    result['Actual %'] = result['Actual %'].fillna(0.0)

    # Append Cash row if Cash is not already a target category
    cash_actual = actual[actual['Category'] == 'Cash']['Actual %'].sum()
    if cash_actual > 0.01 and 'Cash' not in target_cats:
        result = pd.concat([result, pd.DataFrame([{
            'Category': 'Cash', 'Target %': 0.0, 'Actual %': round(cash_actual, 2)
        }])], ignore_index=True)

    if unmatched_pct > 0.01:
        result = pd.concat([result, pd.DataFrame([{
            'Category': 'Unallocated', 'Target %': 0.0, 'Actual %': round(unmatched_pct, 2)
        }])], ignore_index=True)
    result['Drift %'] = result['Actual %'] - result['Target %']
    result['Breach'] = result['Drift %'].abs() > 5.0
    return result

drift_df = _compute_drift(holdings_df, targets_df)

# --- Diagnostic (shown AFTER drift is computed so all values are visible) ---
with st.expander("🔍 Data Diagnostic", expanded=False):
    st.write(f"**Holdings rows:** {len(holdings_df)} | **Total MV:** ${holdings_df['Market Value'].sum():,.0f}")
    st.write(f"**Is Cash dtype:** {holdings_df['Is Cash'].dtype} | **Market Value dtype:** {holdings_df['Market Value'].dtype}")
    st.write("**Asset Class → Market Value (from sheet):**")
    st.write(holdings_df.groupby('Asset Class')['Market Value'].sum().sort_values(ascending=False).to_dict())
    st.write("**Is Cash sample (first 5):**", holdings_df['Is Cash'].head().tolist())
    st.write("**Target categories:**", targets_df['Asset Class'].tolist())
    st.write("**Drift result:**")
    st.write(drift_df[['Category','Target %','Actual %','Drift %']].to_dict('records') if not drift_df.empty else "EMPTY — _compute_drift returned nothing")

# --- Drift Analysis ---
st.subheader("Allocation Drift")

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
    st.plotly_chart(fig_drift, width='stretch')
    
    # Table
    st.dataframe(
        drift_df,
        column_config={
            'Target %': st.column_config.NumberColumn(format="%.1f%%"),
            'Actual %': st.column_config.NumberColumn(format="%.1f%%"),
            'Drift %': st.column_config.NumberColumn(format="%+.1f%%"),
        },
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Drift data could not be calculated. Ensure Categories in Target_Allocation match your Holdings.")

# --- Rebalancing Proposals ---
st.divider()
st.subheader("AI Rebalancing Proposals")

if st.button("🧠 Generate Tax-Aware Proposals", width='stretch'):
    with st.spinner("AI is evaluating tax lots and drift..."):
        proposals = generate_rebalance_proposals(drift_df, holdings_df)
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
            st.plotly_chart(fig_term, width='stretch')
        except:
            st.write("Could not calculate holding periods from available data.")
    else:
        st.info("Acquisition dates not found in current holdings.")
