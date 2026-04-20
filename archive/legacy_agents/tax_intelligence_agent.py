import pandas as pd
import logging
import streamlit as st
import config
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE
from utils.sheet_readers import get_gspread_client, get_target_allocation
from utils.fmp_client import get_company_profile

# --- Schemas ---
...
# --- Target Allocation & Drift (Rebalancing) ---

def calculate_drift(holdings_df: pd.DataFrame, targets_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Robust drift calculation:
    1. Standardizes category labels.
    2. Identifies cash via Asset Class + Ticker (ignores flaky Is Cash column).
    3. Fuzzy matches Asset Classes to Target Categories.
    4. Handles Unallocated positions.
    Returns: (drift_df, debug_dict)
    """
    if targets_df.empty or holdings_df.empty:
        return pd.DataFrame(), {}
    
    # 1. Prepare targets
    t_df = targets_df.copy()
    if 'Asset Class' in t_df.columns:
        t_df = t_df.rename(columns={'Asset Class': 'Category'})
    
    tgt_col = next((c for c in t_df.columns if 'Target' in c), None)
    if not tgt_col:
        return pd.DataFrame(), {}
    t_df['Target %'] = pd.to_numeric(t_df[tgt_col], errors='coerce').fillna(0.0)
    target_cats = t_df['Category'].tolist()

    # 2. Clean holdings
    h_df = holdings_df[['Ticker', 'Asset Class', 'Market Value']].copy()
    h_df['Market Value'] = pd.to_numeric(h_df['Market Value'], errors='coerce').fillna(0.0)
    h_df['_ac'] = h_df['Asset Class'].astype(str).str.strip()
    h_df['_tk'] = h_df['Ticker'].astype(str).str.strip().str.upper()

    total_mv = h_df['Market Value'].sum()
    if total_mv <= 0:
        return pd.DataFrame(), {}

    # 3. Identify cash rows by Asset Class or known cash tickers — ignores Is Cash column
    CASH_TICKERS = {'QACDS', 'CASH_MANUAL', 'CASH', 'CASH & CASH INVESTMENTS'}
    is_cash = (h_df['_ac'].str.lower() == 'cash') | h_df['_tk'].isin(CASH_TICKERS)

    # 4. Map each unique non-cash Asset Class to the best target category
    def find_cat(ac):
        if not ac or ac.lower() in ('nan', 'n/a', 'other', ''):
            return 'Unallocated'
        if ac in target_cats:
            return ac
        al = ac.lower()
        for tc in target_cats:
            if tc.lower() == al:
                return tc
        for tc in target_cats:
            if al in tc.lower() or tc.lower() in al:
                return tc
        return 'Unallocated'

    non_cash = h_df.loc[~is_cash]
    ac_map = {ac: find_cat(ac) for ac in non_cash['_ac'].unique()}

    # 5. Accumulate MV per target category
    cat_mv: dict = {}
    for ac, grp in non_cash.groupby('_ac'):
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

    # 6. Build actual % and merge with targets
    actual = pd.DataFrame(
        [{'Category': c, 'Actual %': round(v / total_mv * 100, 2)} for c, v in cat_mv.items()]
    )
    result = pd.merge(t_df[['Category', 'Target %']], actual, on='Category', how='left')
    result['Actual %'] = result['Actual %'].fillna(0.0)

    # Append rows in actual that aren't in targets (Unallocated, extra categories)
    extra = actual[~actual['Category'].isin(target_cats)].copy()
    if not extra.empty:
        extra['Target %'] = 0.0
        result = pd.concat([result, extra[['Category', 'Target %', 'Actual %']]], ignore_index=True)

    result['Drift %'] = result['Actual %'] - result['Target %']
    result['Breach']  = result['Drift %'].abs() > 5.0
    return result, debug

def generate_rebalance_proposals(drift_df: pd.DataFrame, holdings_df: pd.DataFrame) -> list[dict]:
    """AI-generated rebalancing suggestions using the Rule of Three."""
    proposals = []
    # Drift threshold for proposal generation
    overweight = drift_df[drift_df['Drift %'] > 2.0]
    
    for _, row in overweight.iterrows():
        cat = row['Category']
        # Use Asset Class fuzzy matching or Category column if it exists in holdings
        # For now, filter by exact Asset Class if Category isn't in holdings
        mask = holdings_df['Asset Class'] == cat
        tickers = holdings_df[mask]['Ticker'].tolist()
        
        if not tickers:
            continue
            
        prompt = f"""
        Category '{cat}' is overweight by {row['Drift %']:.2f}%.
        Target: {row['Target %']:.2f}%, Actual: {row['Actual %']:.2f}%.
        
        Suggest 3 rebalancing options for these tickers: {tickers}.
        Analyze tax impact qualitatively (LT vs ST). Do NOT attempt to calculate exact tax dollars.
        """
        
        system_instruction = "You are a tax-aware rebalancing advisor for a CPA. Focus on 'The Rule of Three' options."
        
        try:
            res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=RebalanceProposal)
            if res:
                proposals.append(res.model_dump())
        except Exception as e:
            logging.error(f"Rebalance proposal error for {cat}: {e}")
            
    return proposals

# --- Tax Loss Harvesting (TLH) ---

def scan_harvest_opportunities(holdings_df: pd.DataFrame, min_loss_dollars: float = 500.0) -> pd.DataFrame:
    """Filter for positions with significant unrealized losses."""
    df = holdings_df.copy()
    df['Unrealized G/L'] = pd.to_numeric(df['Unrealized G/L'], errors='coerce').fillna(0.0)
    losses = df[df['Unrealized G/L'] <= -min_loss_dollars].copy()
    losses['tax_asset_value'] = losses['Unrealized G/L'].abs() * 0.15
    return losses.sort_values(by='Unrealized G/L')

def check_wash_sale_risk(ticker: str, realized_gl_df: pd.DataFrame) -> dict:
    """Check for recent losses in this ticker (past 30 days). Returns status dict."""
    if realized_gl_df.empty:
        return {"at_risk": False}
        
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    try:
        realized_gl_df['Closed Date'] = pd.to_datetime(realized_gl_df['Closed Date'])
        recent_losses = realized_gl_df[
            (realized_gl_df['Ticker'] == ticker) & 
            (realized_gl_df['Closed Date'] > thirty_days_ago) & 
            (realized_gl_df['Gain Loss $'] < 0)
        ]
        
        if not recent_losses.empty:
            last_loss = recent_losses.iloc[0]
            return {
                "at_risk": True,
                "last_loss_date": last_loss['Closed Date'].strftime("%Y-%m-%d"),
                "loss_amount": last_loss['Gain Loss $'],
                "warning": f"Wash sale risk: Loss of ${abs(last_loss['Gain Loss $']):,.2f} on {last_loss['Closed Date'].strftime('%m/%d')}"
            }
    except Exception:
        pass
        
    return {"at_risk": False}

def build_tlh_report(holdings_df: pd.DataFrame, realized_gl_df: pd.DataFrame) -> list[dict]:
    """Scan, filter wash sales, and generate AI proposals for top losses."""
    opps = scan_harvest_opportunities(holdings_df)
    results = []
    
    # Filter wash sales (Helper function inside for boolean filtering)
    def _is_safe(ticker):
        risk = check_wash_sale_risk(ticker, realized_gl_df)
        return not risk['at_risk']

    cleared_opps = opps[opps['Ticker'].apply(_is_safe)]
    
    for _, row in cleared_opps.head(3).iterrows():
        ticker = row['Ticker']
        profile = get_company_profile(ticker)
        
        prompt = f"""
        Ticker: {ticker}
        Unrealized Loss: ${abs(row['Unrealized G/L']):,.2f}
        Estimated Tax Savings (15% rate): ${row['tax_asset_value']:,.2f}
        Company Profile: {profile.get('sector')}, {profile.get('industry')}
        
        Suggest 2 highly correlated but legally distinct proxy securities (ETFs or competitors) 
        to maintain market exposure for 31 days while avoiding the wash-sale rule.
        """
        
        system_instruction = "You are a tax-loss harvesting advisor for a CPA. Suggest proxy options to maintain exposure."
        
        try:
            res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=TLHProposal)
            if res:
                p_dict = res.model_dump()
                p_dict['unrealized_loss'] = abs(row['Unrealized G/L'])
                results.append(p_dict)
        except Exception as e:
            logging.error(f"TLH proposal error for {ticker}: {e}")
            
    return results
