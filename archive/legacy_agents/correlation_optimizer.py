import pandas as pd
import numpy as np
import logging
from utils.gemini_client import ask_gemini_json, SAFETY_PREAMBLE

def detect_correlation_spikes(holdings_df: pd.DataFrame, price_histories: pd.DataFrame, threshold: float = 0.80) -> list[dict]:
    """
    Specifically check for high correlation between top positions.
    """
    if price_histories.empty:
        return []
        
    # Calculate correlation matrix for the price history
    # Only for tickers we actually have history for
    corr_matrix = price_histories.pct_change().corr()
    
    spikes = []
    tickers = corr_matrix.columns.tolist()
    
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            t1 = tickers[i]
            t2 = tickers[j]
            corr = corr_matrix.loc[t1, t2]
            
            if corr > threshold:
                spikes.append({
                    "pair": f"{t1} / {t2}",
                    "correlation": float(corr),
                    "severity": "High" if corr > 0.9 else "Medium"
                })
                
    return spikes

def calculate_diversification_benefit(holdings_df: pd.DataFrame, price_histories: pd.DataFrame) -> dict:
    """
    diversification_ratio, effective_positions.
    """
    if price_histories.empty:
        return {}
        
    # Simple estimate: 1 - (Weighted Avg Correlation)
    # This is a proxy for the 'benefit'
    returns = price_histories.pct_change().dropna()
    weights = holdings_df.set_index('Ticker')['Weight'].to_dict()
    
    # Filter tickers present in both
    common_tickers = [t for t in returns.columns if t in weights]
    if not common_tickers:
        return {"diversification_score": 0.0}
        
    # Re-normalize weights for the subset
    sub_weights = np.array([weights[t] for t in common_tickers])
    sub_weights = sub_weights / sub_weights.sum()
    
    corr_mat = returns[common_tickers].corr().values
    
    # Weighted average correlation
    # sum(w_i * w_j * rho_ij)
    avg_corr = 0.0
    for i in range(len(sub_weights)):
        for j in range(len(sub_weights)):
            if i != j:
                avg_corr += sub_weights[i] * sub_weights[j] * corr_mat[i, j]
                
    # Effective positions (Inverse of Herfindahl index but adjusted for correlation)
    # Simplified: N / (1 + (N-1)*rho)
    n = len(common_tickers)
    eff_n = n / (1 + (n - 1) * avg_corr) if n > 1 else 1
    
    return {
        "diversification_score": float(1.0 - avg_corr),
        "effective_positions": float(eff_n),
        "actual_positions": n
    }

def generate_optimization_suggestions(spikes: list[dict], holdings_df: pd.DataFrame) -> dict:
    """
    Gemini JSON: alerts, assessment, score.
    """
    prompt = f"""
    The following position pairs have high correlations (>0.80):
    {spikes}
    
    Portfolio has {len(holdings_df)} positions.
    
    Suggest how to improve diversification. Should any positions be swapped for less correlated proxies?
    Reference specific high-correlation pairs.
    """
    
    system_instruction = f"{SAFETY_PREAMBLE}\n\nYou are a diversification specialist. Your goal is to maximize the 'free lunch' of diversification by identifying and reducing redundant risks. Respond ONLY with JSON: {{'alerts': [{{'pair': str, 'correlation': float, 'suggestion': str, 'impact': str}}], 'overall_assessment': str, 'diversification_score': str}}"
    
    try:
        return ask_gemini_json(prompt, system_instruction=system_instruction)
    except Exception as e:
        logging.error(f"Diversification suggestion error: {e}")
        return {"error": str(e)}

def run_background_risk_scan(holdings_df: pd.DataFrame) -> list[str]:
    """Quick alerts, no LLM."""
    alerts = []
    # Check for sector concentration (already in agent 1, but can add specifics here)
    # E.g. Check for 'Bitcoin' or 'Crypto' related overlap
    crypto_related = ['CORZ', 'IREN', 'MARA', 'RIOT', 'BTC']
    portfolio_crypto = holdings_df[holdings_df['Ticker'].isin(crypto_related)]
    if not portfolio_crypto.empty and portfolio_crypto['Weight'].sum() > 10.0:
        alerts.append(f"⚠️ **Volatility Alert:** You have {portfolio_crypto['Weight'].sum():.1f}% exposure to highly correlated crypto-infrastructure stocks.")
        
    return alerts
