import logging
from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE

def build_portfolio_summary(holdings_df, income_metrics=None, risk_data=None) -> str:
    """Summary under 800 tokens for context."""
    total_val = holdings_df['Market Value'].sum()
    pos_count = len(holdings_df)
    top_pos = holdings_df.nlargest(3, 'Market Value')['Ticker'].tolist()
    
    summary = f"Portfolio Value: ${total_val:,.0f}, Positions: {pos_count}. Top 3: {', '.join(top_pos)}.\n"
    if income_metrics:
        summary += f"Annual Income: ${income_metrics.get('projected_annual_income', 0):,.0f}, Yield: {income_metrics.get('blended_yield_pct', 0):.2f}%.\n"
    if risk_data:
        summary += f"Beta: {risk_data.get('p_beta', 0):.4f}.\n"
        
    return summary

def detect_intent(user_message: str) -> str:
    msg = user_message.lower()
    if any(k in msg for k in ["hedge", "concentration", "exposure"]): return "concentration"
    if any(k in msg for k in ["rebalance", "trim", "tax", "wash sale"]): return "rebalancing"
    if any(k in msg for k in ["cash", "sweep", "idle", "money market"]): return "cash_sweep"
    if any(k in msg for k in ["earnings", "report", "quarter"]): return "earnings"
    if any(k in msg for k in ["valuation", "p/e", "accumulate", "cheap"]): return "valuation"
    if any(k in msg for k in ["covered call", "options", "premium"]): return "options"
    if any(k in msg for k in ["correlation", "diversification", "beta"]): return "correlation"
    if any(k in msg for k in ["property", "real estate", "net worth"]): return "grand_strategy"
    if any(k in msg for k in ["screen", "find me", "thesis", "stocks like"]): return "thesis"
    if any(k in msg for k in ["fed", "rate cut", "cpi", "macro", "economy"]): return "macro"
    if any(k in msg for k in ["why did", "dropped", "jumped", "moved"]): return "price_move"
    if any(k in msg for k in ["harvest", "tax loss", "losses"]): return "tax_harvest"
    return "general"

def chat(user_message: str, history: list, portfolio_summary: str) -> str:
    """
    Main chat entry point.
    """
    intent = detect_intent(user_message)
    
    system_instruction = f"""
    {SAFETY_PREAMBLE}
    You are the AI Portfolio Advisor for an investment dashboard. You have access to 12 specialized agents.
    Portfolio Summary: {portfolio_summary}
    Detected Intent: {intent}
    
    If the intent is specific, provide high-level insights and refer the user to the dedicated page for deep analysis.
    
    ### STREAMLIT APP STRUCTURE (Navigation):
    1. Dashboard (Main Page): `app.py`
       - Tab 1: Holdings (KPIs, Movers, Macro, Earnings, Concentration Alerts)
       - Tab 2: Income (Cash Sweep, Options Potential, Yield Metrics)
       - Tab 3: Risk (Correlation, Beta, Stress Tests, CAPM)
    2. Rebalancing: `pages/1_Rebalancing.py`
    3. Research: `pages/2_Research.py` (Ticker analysis, transcripts, valuation plan)
    4. Performance: `pages/3_Performance.py` (Historical snapshots, benchmarks, projections)
    5. Tax: `pages/4_Tax.py` (Lot-level details, cost basis analysis)
    6. Net Worth: `pages/5_Net_Worth.py` (Investment + Real Estate + Cash)
    7. Advisor: `pages/6_Advisor.py` (This chat interface)
    
    ### NAVIGATION RULES:
    - For "Concentration" or "Exposure" questions, refer the user to the "Dashboard (Main Page) > Risk Tab" or the "Dashboard (Main Page) > Holdings Tab (for specific alerts)".
    - For "Rebalancing" or "Trimming" questions, refer to the "Rebalancing" page.
    - For "Dividends" or "Income" questions, refer to the "Dashboard (Main Page) > Income Tab".
    - For "Market Value History" or "Benchmarks", refer to the "Performance" page.
    - For "Deep Ticker Research", refer to the "Research" page.
    
    Be concise, professional, and act as a senior portfolio strategist co-pilot.
    """
    
    # Format history for Gemini (simple append for now)
    chat_context = "\n".join([f"{'User' if i%2==0 else 'AI'}: {m}" for i, m in enumerate(history)])
    full_prompt = f"{chat_context}\nUser: {user_message}\nAI:"
    
    try:
        response = ask_gemini(full_prompt, system_instruction=system_instruction)
        return response, intent
    except Exception as e:
        logging.error(f"Chat error: {e}")
        return "I encountered an error processing your request.", "error"
