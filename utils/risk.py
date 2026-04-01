import pandas as pd
import numpy as np
import yfinance as yf
import scipy.stats
import os
import sys

# Add project root to path so config is importable
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import config
except ImportError:
    pass

def calculate_beta(ticker, price_history, spy_returns) -> float:
    """
    - Covariance method ONLY (not regression):
        ticker_returns = price_history[ticker].pct_change().dropna()
        common_idx = ticker_returns.index.intersection(spy_returns.index)
        if len(common_idx) < config.MIN_BETA_DATA_POINTS: return 1.0
        beta = ticker_returns[common_idx].cov(spy_returns[common_idx]) / spy_returns[common_idx].var()
    - CASH_TICKERS always return 0.0
    - Outlier protection: Clamp beta to range [-0.5, 3.5]
    """
    if ticker in config.CASH_TICKERS:
        return 0.0
    
    if ticker not in price_history.columns:
        print(f"Warning: {ticker} not in price history. Using beta=1.0")
        return 1.0
        
    ticker_series = price_history[ticker]
    ticker_returns = ticker_series.pct_change().dropna()
    
    common_idx = ticker_returns.index.intersection(spy_returns.index)
    
    if len(common_idx) < config.MIN_BETA_DATA_POINTS:
        print(f"Warning: {ticker} has only {len(common_idx)} data points. Using beta=1.0")
        return 1.0
        
    try:
        # Covariance method
        beta = ticker_returns[common_idx].cov(spy_returns[common_idx]) / spy_returns[common_idx].var()
        
        # Clamp
        return float(np.clip(beta, -0.5, 3.5))
    except Exception as e:
        print(f"Error calculating beta for {ticker}: {e}")
        return 1.0

def calculate_portfolio_beta(df) -> float:
    """
    - invested_only = df[~df["ticker"].isin(config.CASH_TICKERS)]
    - weighted_beta = sum(row.weight * row.beta for row in invested_only)
    - divide by sum of weights for invested positions only
    - Return rounded to 4 decimal places
    """
    ticker_col = 'ticker' if 'ticker' in df.columns else 'Ticker'
    weight_col = 'weight' if 'weight' in df.columns else 'Weight'
    beta_col = 'beta' if 'beta' in df.columns else 'Beta'
    
    invested_only = df[~df[ticker_col].isin(config.CASH_TICKERS)].copy()
    
    if invested_only.empty:
        return 0.0
        
    # Ensure weight and beta are numeric
    invested_only[weight_col] = pd.to_numeric(invested_only[weight_col], errors='coerce').fillna(0.0)
    invested_only[beta_col] = pd.to_numeric(invested_only[beta_col], errors='coerce').fillna(1.0)
    
    total_invested_weight = invested_only[weight_col].sum()
    if total_invested_weight == 0:
        return 0.0
        
    weighted_beta = (invested_only[weight_col] * invested_only[beta_col]).sum()
    portfolio_beta = weighted_beta / total_invested_weight
    
    return round(float(portfolio_beta), 4)

def build_price_histories(df) -> pd.DataFrame:
    """
    - Bulk download top 20 + SPY in single yf.download() call
    - Return DataFrame of adjusted close prices
    - Include "SPY" always.
    """
    ticker_col = 'ticker' if 'ticker' in df.columns else 'Ticker'
    mv_col = 'market_value' if 'market_value' in df.columns else 'Market Value'
    
    invested_df = df[~df[ticker_col].isin(config.CASH_TICKERS)]
    top_tickers = invested_df.nlargest(config.TOP_N_ENRICH, mv_col)[ticker_col].tolist()
    
    tickers_to_download = list(set(top_tickers + ["SPY"]))
    
    print(f"Downloading history for {len(tickers_to_download)} tickers...")
    try:
        data = yf.download(tickers_to_download, period="1y", auto_adjust=True, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            # If multiple tickers, columns are (Attribute, Ticker)
            if 'Close' in data.columns.levels[0]:
                return data['Close']
            elif 'Adj Close' in data.columns.levels[0]:
                return data['Adj Close']
        return data
    except Exception as e:
        print(f"Error downloading price histories: {e}")
        return pd.DataFrame()

def calculate_correlation_matrix(df, price_histories) -> pd.DataFrame:
    """
    - top20 = df[~df["ticker"].isin(config.CASH_TICKERS)].nlargest(20,"market_value")["ticker"].tolist()
    - Build returns_df = pd.DataFrame of pct_change() for each ticker in top20
    - return returns_df.corr()
    """
    ticker_col = 'ticker' if 'ticker' in df.columns else 'Ticker'
    mv_col = 'market_value' if 'market_value' in df.columns else 'Market Value'
    
    invested_df = df[~df[ticker_col].isin(config.CASH_TICKERS)]
    top20 = invested_df.nlargest(20, mv_col)[ticker_col].tolist()
    
    # Filter price_histories to top20
    available_tickers = [t for t in top20 if t in price_histories.columns]
    
    if not available_tickers:
        return pd.DataFrame()
        
    returns_df = price_histories[available_tickers].pct_change().dropna()
    return returns_df.corr()

def run_stress_tests(portfolio_value, portfolio_beta) -> list[dict]:
    """
    - For each (name, pct) in config.STRESS_SCENARIOS:
        impact = portfolio_value * portfolio_beta * pct
        new_value = portfolio_value + impact
    - Return: [{"scenario": name, "market_pct": pct, "impact": impact,
                "new_value": new_value, "impact_pct": impact/portfolio_value*100}]
    """
    results = []
    for name, pct in config.STRESS_SCENARIOS:
        impact = portfolio_value * portfolio_beta * pct
        new_value = portfolio_value + impact
        impact_pct = (impact / portfolio_value * 100) if portfolio_value > 0 else 0.0
        
        results.append({
            "scenario": name,
            "market_pct": pct * 100,
            "impact": float(impact),
            "new_value": float(new_value),
            "impact_pct": float(impact_pct)
        })
    return results

def capm_projection(portfolio_value, portfolio_beta) -> dict:
    """
    - expected_return = config.RISK_FREE_RATE + portfolio_beta * config.MARKET_PREMIUM
    - volatility = portfolio_beta * config.BASE_VOLATILITY
    - Use scipy.stats.norm:
        bad_return  = scipy.stats.norm.ppf(0.10, expected_return, volatility)
        good_return = scipy.stats.norm.ppf(0.90, expected_return, volatility)
    - Return dollar values
    """
    expected_return = config.RISK_FREE_RATE + portfolio_beta * config.MARKET_PREMIUM
    volatility = portfolio_beta * config.BASE_VOLATILITY
    
    # 10th percentile (bad) and 90th percentile (good)
    bad_return = scipy.stats.norm.ppf(0.10, expected_return, volatility)
    good_return = scipy.stats.norm.ppf(0.90, expected_return, volatility)
    
    return {
        "bad": float(portfolio_value * (1 + bad_return)),
        "expected": float(portfolio_value * (1 + expected_return)),
        "good": float(portfolio_value * (1 + good_return)),
        "expected_pct": float(expected_return * 100),
        "volatility_pct": float(volatility * 100)
    }

def concentration_alerts(df) -> list[str]:
    """
    - Flag position weight > config.SINGLE_POSITION_WARN_PCT
    - Flag sector weight > config.SECTOR_CONCENTRATION_WARN_PCT
    """
    ticker_col = 'ticker' if 'ticker' in df.columns else 'Ticker'
    weight_col = 'weight' if 'weight' in df.columns else 'Weight'
    sector_col = 'asset_class' if 'asset_class' in df.columns else 'Asset Class'
    
    alerts = []
    
    # Position concentration
    over_conc = df[df[weight_col] > config.SINGLE_POSITION_WARN_PCT]
    for _, row in over_conc.iterrows():
        alerts.append(f"Concentration: {row[ticker_col]} = {row[weight_col]:.2f}% of portfolio")
        
    # Sector concentration
    sector_weights = df.groupby(sector_col)[weight_col].sum()
    over_sector = sector_weights[sector_weights > config.SECTOR_CONCENTRATION_WARN_PCT]
    for sector, weight in over_sector.items():
        alerts.append(f"Sector Concentration: {sector} = {weight:.2f}% of portfolio")
        
    return alerts

if __name__ == "__main__":
    import pandas as pd
    from utils.csv_parser import parse_schwab_csv, inject_cash_manual
    from utils.enrichment import enrich_positions
    from pipeline import normalize_positions
    
    test_file = "All-Accounts-Positions-2026-03-30-103853.csv"
    if os.path.exists(test_file):
        df = parse_schwab_csv(open(test_file,'rb').read())
        df = inject_cash_manual(df, 10000)
        df = enrich_positions(df)
        df = normalize_positions(df, "2026-04-01")
        
        hist = build_price_histories(df)
        if not hist.empty and 'SPY' in hist.columns:
            spy_returns = hist['SPY'].pct_change().dropna()
            
            # Calculate betas
            df['Beta'] = df['Ticker'].apply(lambda x: calculate_beta(x, hist, spy_returns))
            
            p_beta = calculate_portfolio_beta(df)
            print(f"\nPortfolio Beta: {p_beta}")
            
            corr = calculate_correlation_matrix(df, hist)
            print(f"\nCorrelation Matrix (Top 5):\n{corr.iloc[:5,:5]}")
            
            total_val = df['Market Value'].sum()
            stress = run_stress_tests(total_val, p_beta)
            print(f"\nStress Test (Market -10%): {stress[2]}")
            
            capm = capm_projection(total_val, p_beta)
            print(f"\nCAPM Expected 1yr: ${capm['expected']:,.2f} ({capm['expected_pct']:.2f}%)")
            
            alerts = concentration_alerts(df)
            print(f"\nAlerts: {alerts}")
        else:
            print("Could not build price histories.")
    else:
        print(f"Test file {test_file} not found.")
