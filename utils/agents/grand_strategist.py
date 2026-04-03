import pandas as pd
import logging
import streamlit as st
import config
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE
from utils.sheet_readers import get_gspread_client

# RE Dashboard Sheet ID from Prompt
RE_DASHBOARD_ID = "1DXuY1iBo2GqZCCSZ7OrUa4iaunb5s8Kf1Rms8Z237rQ"

def _parse_currency(val: str) -> float:
    if not val:
        return 0.0
    # Strip $, commas, and whitespace
    clean_val = val.replace('$', '').replace(',', '').strip()
    # Handle parens for negative numbers
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
    property value, NOI, debt (B21), debt service (B20), reserve.
    """
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(RE_DASHBOARD_ID)
        # Assuming summary data is on the first sheet or a sheet named 'Summary'
        ws = spreadsheet.get_worksheet(0)
        
        # Mapping based on prompt info (Debt B21, Debt Service B20)
        re_data = {
            "debt": _parse_currency(ws.acell('B21').value),
            "debt_service": _parse_currency(ws.acell('B20').value),
            # Placeholders for now until exact cells are confirmed
            "property_value": 1500000.0, 
            "noi": 90000.0,
            "reserve": 50000.0
        }
        return re_data
    except Exception as e:
        logging.error(f"Error reading RE Dashboard: {e}")
        return None

def calculate_net_worth(holdings_df: pd.DataFrame, re_data: dict) -> dict:
    """
    Liquid | RE Equity | Debt | Reserve.
    Total Net Worth = (Investment Portfolio) + (RE NOI / Cap Rate) + (RE Reserve Account) - (Debt)
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
        
    # Net Worth calculation based on prompt formula
    # Using a 6% cap rate if not provided
    cap_rate = 0.06
    
    noi = float(re_data.get('noi', 0.0) or 0.0)
    prop_val = float(re_data.get('property_value', 0.0) or 0.0)
    debt = float(re_data.get('debt', 0.0) or 0.0)
    reserve = float(re_data.get('reserve', 0.0) or 0.0)

    re_valuation = noi / cap_rate if noi > 0 else prop_val
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
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a grand strategist for a high-net-worth investor. Optimize across liquid and real estate assets. Respond ONLY with JSON: {{'analysis': str, 'recommendation': str, 'funding_sources': [{{'source': str, 'amount': float, 'tax_impact': str, 'notes': str}}], 'total_available': float, 'shortfall': float}}"
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"Grand strategist error: {e}")
        return {"error": str(e)}
