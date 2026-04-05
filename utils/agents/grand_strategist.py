import pandas as pd
import logging
import streamlit as st
import config
from pydantic import BaseModel
from typing import List
from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE
from utils.sheet_readers import get_gspread_client

# RE Dashboard Sheet ID from Prompt
RE_DASHBOARD_ID = "1DXuY1iBo2GqZCCSZ7OrUa4iaunb5s8Kf1Rms8Z237rQ"

class FundingSource(BaseModel):
    source: str
    amount: float
    tax_impact: str
    notes: str

class GrandStrategy(BaseModel):
    analysis: str
    recommendation: str
    funding_sources: List[FundingSource]
    total_available: float
    shortfall: float

def _parse_currency(val: str) -> float:
    if not val:
        return 0.0
    clean_val = val.replace('$', '').replace(',', '').strip()
    if clean_val.startswith('(') and clean_val.endswith(')'):
        clean_val = '-' + clean_val[1:-1]
    try:
        return float(clean_val)
    except ValueError:
        return 0.0

@st.cache_data(ttl=3600)
def read_re_portfolio_summary() -> dict:
    """
    Read specific cells from RE Dashboard Sheet.
    """
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(RE_DASHBOARD_ID)
        
        ws_dash = spreadsheet.worksheet('Dashboard')
        ws_debt = spreadsheet.worksheet('Debt_Schedule')
        ws_assump = spreadsheet.worksheet('Assumptions')
        
        raw_cap_rate = ws_assump.acell('E16').value or "0.065"
        clean_cap = str(raw_cap_rate).replace('%', '').strip()
        try:
            val = float(clean_cap)
            cap_rate = val / 100 if val > 0.2 else val 
        except ValueError:
            cap_rate = 0.065

        re_data = {
            "noi": _parse_currency(ws_dash.acell('B23').value),
            "debt": _parse_currency(ws_debt.acell('D6').value),
            "debt_service": _parse_currency(ws_debt.acell('B20').value) * 12,
            "cap_rate": cap_rate,
            "reserve": 50000.0, 
            "property_value": 1500000.0 
        }
        return re_data
    except Exception as e:
        logging.error(f"Error reading RE Dashboard: {e}")
        return None

def calculate_net_worth(holdings_df: pd.DataFrame, re_data: dict) -> dict:
    """
    Liquid | RE Equity | Debt | Reserve.
    """
    try:
        liquid_assets = float(holdings_df['Market Value'].sum())
    except (ValueError, TypeError):
        liquid_assets = 0.0
    
    if not re_data:
        return {
            "liquid": liquid_assets,
            "total": liquid_assets
        }
        
    noi = float(re_data.get('noi', 0.0) or 0.0)
    prop_val = float(re_data.get('property_value', 0.0) or 0.0)
    debt = float(re_data.get('debt', 0.0) or 0.0)
    reserve = float(re_data.get('reserve', 0.0) or 0.0)
    cap_rate = float(re_data.get('cap_rate', 0.065) or 0.065)

    re_valuation = noi / cap_rate if noi > 0 else prop_val
    
    if re_valuation > 50000000:
        logging.warning(f"Astronomical RE valuation detected (${re_valuation:,.0f}). Falling back to manual property value.")
        re_valuation = prop_val

    re_equity = re_valuation - debt
    total_nw = liquid_assets + re_equity + reserve
    
    return {
        "liquid": liquid_assets,
        "re_equity": re_equity,
        "debt": debt,
        "reserve": reserve,
        "total": total_nw,
        "re_valuation": re_valuation
    }

def build_unified_context(holdings_df: pd.DataFrame, re_data: dict) -> str:
    """
    Summary under 1000 tokens.
    """
    liquid = holdings_df['Market Value'].sum()
    top_pos = holdings_df.nlargest(3, 'Weight')['Ticker'].tolist()
    
    context = f"Liquid Portfolio Value: ${liquid:,.0f}. Top positions: {', '.join(top_pos)}.\n"
    if re_data:
        context += f"Real Estate: Valuation approx ${re_data.get('property_value', 0):,.0f}, Debt: ${re_data.get('debt', 0):,.0f}, NOI: ${re_data.get('noi', 0):,.0f}, Reserves: ${re_data.get('reserve', 0):,.0f}."
        
    return context

def answer_cross_portfolio_question(question: str, context: str, holdings_df: pd.DataFrame) -> dict:
    """
    Gemini JSON: analysis, recommendation, funding_sources, shortfall.
    """
    prompt = f"""
    Portfolio Context:
    {context}
    
    Investor Question: {question}
    
    Provide a cross-portfolio recommendation. Consider using liquid assets or real estate reserves.
    Identify tax impacts if selling stock.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a grand strategist for a high-net-worth investor. Optimize across liquid and real estate assets."
    
    try:
        res = ask_gemini(prompt, system_instruction=system_instruction, response_schema=GrandStrategy)
        if res:
            return res.model_dump()
        return {"error": "AI failed to generate grand strategy"}
    except Exception as e:
        logging.error(f"Grand strategist error: {e}")
        return {"error": str(e)}
