import streamlit as st
import pandas as pd
from utils.sheet_readers import get_holdings_current, get_realized_gl
from utils.column_guard import ensure_display_columns
from utils.agents.tax_intelligence_agent import scan_harvest_opportunities, build_tlh_report
import os
import sys

st.title("✂️ Tax Optimization Hub")

# --- Load Data ---
try:
    holdings_df = get_holdings_current()
    holdings_df = ensure_display_columns(holdings_df)
except Exception as e:
    st.error("Could not connect to Google Sheets. Check your connection and service account permissions.")
    st.stop()

realized_gl_df = get_realized_gl()

if holdings_df.empty:
    st.warning("Please upload your investment portfolio on the main page.")
    st.stop()

# --- Proactive Tax-Loss Harvesting ---
st.subheader("📉 Proactive Tax-Loss Harvesting (TLH)")
st.info("Identify positions with significant unrealized losses to offset future gains.")

opps = scan_harvest_opportunities(holdings_df)

if not opps.empty:
    st.write(f"Found {len(opps)} positions with unrealized losses > $500.")
    st.table(opps[['Ticker', 'Description', 'Market Value', 'Unrealized G/L', 'tax_asset_value']].style.format({
        'Market Value': '${:,.2f}',
        'Unrealized G/L': '${:,.2f}',
        'tax_asset_value': '${:,.2f}'
    }))
    
    if st.button("🔍 Scan for TLH Substitutes", width='stretch'):
        with st.spinner("AI is finding correlated proxy securities..."):
            report = build_tlh_report(holdings_df, realized_gl_df)
            if report:
                for proposal in report:
                    with st.expander(f"TLH Strategy for {proposal['ticker']} (Loss: ${abs(proposal['unrealized_loss']):,.0f})", expanded=True):
                        st.write(f"**Rationale:** {proposal['harvest_rationale']}")
                        st.success(f"**Est. Tax Savings:** ${proposal['estimated_tax_savings']:,.2f}")
                        
                        st.write("**Suggested Proxy Options (Rule of Three):**")
                        cols = st.columns(len(proposal['proxy_options']))
                        for i, proxy in enumerate(proposal['proxy_options']):
                            with cols[i]:
                                st.markdown(f"🎯 **{proxy['ticker']}**")
                                st.write(proxy['description'])
                                st.caption(proxy['correlation_rationale'])
                        
                        st.warning(f"**Risks:** {', '.join(proposal['risks'])}")
            else:
                st.info("No uncleared TLH opportunities found (or wash-sale window is active).")
else:
    st.success("No significant unrealized losses found. Portfolio is performing well from a tax perspective.")

# --- Realized Gains Summary ---
st.divider()
st.subheader("📝 Year-to-Date Realized Summary")
if not realized_gl_df.empty:
    # Ensure date conversion
    realized_gl_df['Closed Date'] = pd.to_datetime(realized_gl_df['Closed Date'])
    
    # Filter for current year (2026)
    current_year = 2026
    ytd_df = realized_gl_df[realized_gl_df['Closed Date'].dt.year == current_year].copy()
    prior_df = realized_gl_df[realized_gl_df['Closed Date'].dt.year < current_year].copy()
    
    ytd_gain = ytd_df['Gain Loss $'].sum()
    st.metric(f"Net Realized G/L ({current_year})", f"${ytd_gain:,.2f}", delta_color="inverse" if ytd_gain < 0 else "normal")
    
    # --- Disposition Effect Analysis ---
    winners = ytd_df[ytd_df['Gain Loss $'] > 0]
    losers = ytd_df[ytd_df['Gain Loss $'] < 0]
    
    if not winners.empty and not losers.empty:
        avg_winner_days = winners['Holding Days'].mean()
        avg_loser_days = losers['Holding Days'].mean()
        
        if avg_winner_days < avg_loser_days:
            st.warning(f"⚡ **Disposition Effect Detected:** Avg holding period for winners "
                       f"({avg_winner_days:.0f} days) is shorter than losers "
                       f"({avg_loser_days:.0f} days). Consider letting winners run longer.")

    # --- Wash Sale Activity Section ---
    # Look for 'Wash Sale' column (case insensitive match via Column Guard if needed, 
    # but here we use the exact SCHEMA header 'Wash Sale')
    wash_col = 'Wash Sale' if 'Wash Sale' in realized_gl_df.columns else 'wash_sale'
    if wash_col in realized_gl_df.columns:
        # Handle string "TRUE", boolean True, or "YES"
        wash_mask = realized_gl_df[wash_col].astype(str).str.upper().isin(['TRUE', 'YES', '1'])
        wash_df = realized_gl_df[wash_mask].copy()
        
        if not wash_df.empty:
            st.subheader("🚿 Wash Sale Activity (YTD)")
            total_disallowed = wash_df['Disallowed Loss'].sum()
            st.metric("Total Disallowed Losses", f"${abs(total_disallowed):,.2f}")
            st.caption("These losses are not gone — they're added to your replacement shares' cost basis.")
            
            # Group by Ticker
            wash_summary = wash_df.groupby('Ticker').agg({
                'Disallowed Loss': 'sum',
                'Quantity': 'sum',
                'Gain Loss $': 'sum'
            }).sort_values('Disallowed Loss')
            
            st.table(wash_summary.style.format({
                'Disallowed Loss': '${:,.2f}',
                'Gain Loss $': '${:,.2f}',
                'Quantity': '{:,.2f}'
            }))

    if not ytd_df.empty:
        with st.expander(f"View {current_year} Realized Lots"):
            st.table(ytd_df.sort_values(by='Closed Date', ascending=False).head(20))
    else:
        st.info(f"No realized gains/losses recorded for {current_year} yet.")

    if not prior_df.empty:
        with st.expander("View Historical Realized (2025 & Prior)"):
            st.write(f"Total Historical Realized: `${prior_df['Gain Loss $'].sum():,.2f}`")
            st.table(prior_df.sort_values(by='Closed Date', ascending=False).head(10))
else:
    st.info("No realized gain/loss data found. Upload a Realized G/L CSV on the main page.")
