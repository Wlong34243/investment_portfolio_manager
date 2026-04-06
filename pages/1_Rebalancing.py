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
    # 1. Prepare targets
    t_df = t.copy()
    if 'Asset Class' in t_df.columns:
        t_df = t_df.rename(columns={'Asset Class': 'Category'})
    tgt_col = next((c for c in t_df.columns if 'Target' in c), None)
    if not tgt_col:
        return pd.DataFrame(), {}
    t_df['Target %'] = pd.to_numeric(t_df[tgt_col], errors='coerce').fillna(0.0)
    target_cats = t_df['Category'].tolist()

    # 2. Clean holdings — only the columns we need
    h_df = h[['Ticker', 'Asset Class', 'Market Value', 'Is Cash']].copy()
    h_df['Market Value'] = pd.to_numeric(h_df['Market Value'], errors='coerce').fillna(0.0)
    total_mv = h_df['Market Value'].sum()
    if total_mv <= 0:
        return pd.DataFrame(), {}

    # 3. Identify cash rows robustly
    ic = h_df['Is Cash']
    if ic.dtype == object:
        # String representation: "TRUE", "FALSE", "Yes", "1", etc.
        cash_flag = ic.astype(str).str.strip().str.upper().isin(['TRUE', 'YES', '1', 'T'])
    else:
        # Bool or numeric dtype — cast directly
        cash_flag = ic.fillna(False).astype(bool)

    cash_ticker = h_df['Ticker'].astype(str).str.strip().str.upper().isin(['QACDS', 'CASH_MANUAL', 'CASH'])
    cash_ac     = h_df['Asset Class'].astype(str).str.strip().str.lower() == 'cash'
    is_cash     = cash_flag | cash_ticker | cash_ac

    # 4. Map each unique non-cash Asset Class to the best target category
    def find_cat(ac):
        s = str(ac).strip()
        if not s or s.lower() in ('nan', 'n/a', 'other', ''):
            return 'Unallocated'
        if s in target_cats:
            return s
        sl = s.lower()
        for tc in target_cats:
            if tc.lower() == sl:
                return tc
        for tc in target_cats:
            if sl in tc.lower() or tc.lower() in sl:
                return tc
        return 'Unallocated'

    non_cash_df = h_df.loc[~is_cash].copy()
    non_cash_df['_ac'] = non_cash_df['Asset Class'].astype(str).str.strip()
    unique_acs  = non_cash_df['_ac'].unique()
    ac_map      = {ac: find_cat(ac) for ac in unique_acs}  # e.g. {"Technology": "Information Technology"}

    # 5. Accumulate market value per target category (plain Python loop — no apply/map magic)
    cat_mv: dict = {}
    for ac, grp in non_cash_df.groupby('_ac'):
        cat = ac_map.get(ac, 'Unallocated')
        cat_mv[cat] = cat_mv.get(cat, 0.0) + float(grp['Market Value'].sum())

    cash_mv = float(h_df.loc[is_cash, 'Market Value'].sum())
    if cash_mv > 0:
        cash_cat = 'Cash' if 'Cash' in target_cats else 'Unallocated'
        cat_mv[cash_cat] = cat_mv.get(cash_cat, 0.0) + cash_mv

    debug = {
        'cash_rows': int(is_cash.sum()),
        'ac_map': ac_map,
        'cat_mv': {c: round(v, 2) for c, v in cat_mv.items()},
    }

    # 6. Build actual % DataFrame
    actual = pd.DataFrame(
        [{'Category': c, 'Actual %': round(v / total_mv * 100, 2)} for c, v in cat_mv.items()]
    )

    # 7. Left-join against targets so every target category always appears
    result = pd.merge(t_df[['Category', 'Target %']], actual, on='Category', how='left')
    result['Actual %'] = result['Actual %'].fillna(0.0)

    # Append any categories that appear in actual but aren't in targets (e.g. Unallocated)
    extra = actual[~actual['Category'].isin(target_cats)].copy()
    if not extra.empty:
        extra['Target %'] = 0.0
        result = pd.concat([result, extra[['Category', 'Target %', 'Actual %']]], ignore_index=True)

    result['Drift %'] = result['Actual %'] - result['Target %']
    result['Breach']  = result['Drift %'].abs() > 5.0
    return result, debug

drift_df, drift_debug = _compute_drift(holdings_df, targets_df)

# --- Diagnostic (shown AFTER drift is computed so all values are visible) ---
with st.expander("🔍 Data Diagnostic", expanded=False):
    st.write(f"**Holdings rows:** {len(holdings_df)} | **Total MV:** ${holdings_df['Market Value'].sum():,.0f}")
    st.write(f"**Is Cash dtype:** {holdings_df['Is Cash'].dtype} | **Market Value dtype:** {holdings_df['Market Value'].dtype}")
    st.write(f"**Is Cash sample (first 5):** {holdings_df['Is Cash'].head().tolist()}")
    st.write("**Asset Class → Market Value (from sheet):**")
    st.write(holdings_df.groupby('Asset Class')['Market Value'].sum().sort_values(ascending=False).to_dict())
    st.write("**Target categories:**", targets_df['Asset Class'].tolist())
    if drift_debug:
        st.write(f"**Cash rows identified:** {drift_debug['cash_rows']}")
        st.write("**Asset Class → Target mapping:**", drift_debug['ac_map'])
        st.write("**Market Value by target category (before % calc):**", drift_debug['cat_mv'])
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
