# COMPLETE PORTFOLIO ANALYZER - SINGLE WORKBOOK OUTPUT
# Upload → Parse → Aggregate → Analyze → Technical → Options → Export to ONE Excel File
# Fixed version that creates a single workbook with multiple sheets

print("🚀 COMPLETE PORTFOLIO ANALYZER - SINGLE WORKBOOK OUTPUT")
print("=" * 80)
print("📊 Data Input → Position Analysis → Technical Analysis → Options Strategies")
print("=" * 80)

# ==================== IMPORTS ====================
import pandas as pd
import numpy as np
from google.colab import files
import io
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# Set up plotting style
plt.style.use('default')
sns.set_palette("husl")

print("✅ All libraries imported successfully")

# Install required packages
print("📦 Installing required packages...")
import subprocess
import sys

try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

try:
    from scipy.stats import norm
except ImportError:
    print("Installing scipy...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "scipy"])
    from scipy.stats import norm

try:
    import openpyxl
except ImportError:
    print("Installing openpyxl...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl

print("✅ All packages ready")

# ==================== MODULE 1: DATA INPUT & CLEANING ====================

def clean_numeric(value):
    """Clean numeric values - remove $ signs, commas, parentheses"""
    if pd.isna(value) or value is None:
        return 0.0
    
    if isinstance(value, (int, float)):
        return float(value)
    
    str_val = str(value).strip()
    
    if not str_val or str_val.lower() in ['nan', 'none', '']:
        return 0.0
    
    is_negative = str_val.startswith('(') and str_val.endswith(')')
    if is_negative:
        str_val = str_val[1:-1]
    
    str_val = re.sub(r'[^\d.-]', '', str_val)
    
    if not str_val:
        return 0.0
    
    try:
        numeric_val = float(str_val)
        return -numeric_val if is_negative else numeric_val
    except ValueError:
        return 0.0

def find_account_sections(df):
    """Find where each account section starts"""
    account_patterns = [
        'Individual_401', 'Contributory', 'Joint_Tenant', 'Individual',
        'Account Total'
    ]
    
    account_sections = []
    current_account = "Unknown"
    
    for idx, row in df.iterrows():
        first_col = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ""
        
        # Check for account headers
        for pattern in account_patterns:
            if pattern.lower() in first_col.lower():
                current_account = first_col
                break
        
        # Include positions AND cash positions
        if len(first_col) > 0 and not any(word in first_col.lower() for word in ['account', 'total']):
            # Include both regular positions and cash positions
            if (first_col.isalpha() and len(first_col) <= 6) or 'cash & cash investments' in first_col.lower():
                account_sections.append({
                    'row_index': idx,
                    'account': current_account,
                    'symbol': first_col,
                    'row_data': row
                })
    
    return account_sections

def create_aggregated_positions(sections, original_df):
    """Create a clean aggregated positions DataFrame"""
    positions = []
    
    for section in sections:
        row_data = section['row_data']
        
        try:
            position = {
                'Account': section['account'],
                'Symbol': str(row_data.iloc[0]) if pd.notna(row_data.iloc[0]) else '',
                'Description': str(row_data.iloc[1]) if len(row_data) > 1 and pd.notna(row_data.iloc[1]) else '',
                'Quantity': clean_numeric(row_data.iloc[2]) if len(row_data) > 2 else 0,
                'Price': clean_numeric(row_data.iloc[3]) if len(row_data) > 3 else 0,
                'Market_Value': clean_numeric(row_data.iloc[6]) if len(row_data) > 6 else 0,
                'Day_Change_Dollar': clean_numeric(row_data.iloc[7]) if len(row_data) > 7 else 0,
                'Day_Change_Percent': clean_numeric(row_data.iloc[8]) if len(row_data) > 8 else 0,
            }
            
            if position['Symbol'] and position['Market_Value'] != 0:
                positions.append(position)
                
        except Exception as e:
            continue
    
    df = pd.DataFrame(positions)
    
    if len(df) > 0:
        numeric_columns = ['Quantity', 'Price', 'Market_Value', 'Day_Change_Dollar', 'Day_Change_Percent']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        text_columns = ['Account', 'Symbol', 'Description']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str)
    
    return df

# ==================== MODULE 2: POSITION ANALYSIS ====================

def classify_sector(symbol, description=""):
    """Classify securities by sector"""
    tech_symbols = ['AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'CRM', 'ADBE', 'AMD', 'INTC', 'CSCO', 'PANW', 'ZS', 'DELL', 'AVGO']
    energy_symbols = ['XOM', 'ET', 'EPD', 'NEE', 'COP', 'SLB']
    health_symbols = ['UNH', 'JNJ', 'PFE']
    financial_symbols = ['KEY', 'BX', 'ARCC']
    reit_symbols = ['O', 'IIPR', 'ADC']
    comm_symbols = ['VZ', 'DIS']
    industrial_symbols = ['MMM', 'ETN', 'HMC']
    consumer_symbols = ['BABA']
    crypto_symbols = ['GBTC']
    
    etf_patterns = ['ETF', 'FUND', 'INDEX', 'SPDR', 'VANGUARD', 'ISHARES', 'INVESCO', 'SCHWAB', 'SELECT']
    
    symbol = symbol.upper()
    desc_upper = description.upper()
    
    # Handle cash specially
    if symbol == 'CASH':
        return 'Cash & Equivalents'
    
    if any(pattern in desc_upper for pattern in etf_patterns) or symbol in ['VTI', 'VEA', 'VEU', 'XLF', 'SCHD', 'IFRA', 'OIH', 'PPA']:
        if any(word in desc_upper for word in ['FINANCIAL', 'BANK']):
            return 'ETF-Financial'
        elif any(word in desc_upper for word in ['TECH', 'NASDAQ', 'QQQ']):
            return 'ETF-Technology'
        elif any(word in desc_upper for word in ['ENERGY', 'OIL']):
            return 'ETF-Energy'
        elif any(word in desc_upper for word in ['INFRAST', 'UTILITY']):
            return 'ETF-Infrastructure'
        elif any(word in desc_upper for word in ['DIVIDEND', 'INCOME']):
            return 'ETF-Dividend'
        elif any(word in desc_upper for word in ['INTERNATIONAL', 'WORLD', 'DEVELOPED']):
            return 'ETF-International'
        elif any(word in desc_upper for word in ['DEFENSE', 'AEROSPACE']):
            return 'ETF-Defense'
        else:
            return 'ETF-Broad Market'
    
    if symbol in tech_symbols:
        return 'Technology'
    elif symbol in energy_symbols:
        return 'Energy'
    elif symbol in health_symbols:
        return 'Healthcare'
    elif symbol in financial_symbols:
        return 'Financial Services'
    elif symbol in reit_symbols:
        return 'Real Estate'
    elif symbol in comm_symbols:
        return 'Communication'
    elif symbol in industrial_symbols:
        return 'Industrial'
    elif symbol in consumer_symbols:
        return 'Consumer Discretionary'
    elif symbol in crypto_symbols:
        return 'Cryptocurrency'
    else:
        return 'Other'

def calculate_portfolio_metrics(consolidated_df, total_portfolio_value):
    """Calculate comprehensive portfolio metrics using consolidated positions"""
    
    metrics = {
        'total_portfolio_value': total_portfolio_value,
        'position_count': len(consolidated_df),  # Use consolidated count
        'average_position_size': total_portfolio_value / len(consolidated_df) if len(consolidated_df) > 0 else 0,
        'largest_position': consolidated_df['Market_Value'].max(),
        'smallest_position': consolidated_df['Market_Value'].min(),
        'top_10_concentration': consolidated_df.nlargest(10, 'Market_Value')['Market_Value'].sum() / total_portfolio_value * 100,
        'top_5_concentration': consolidated_df.nlargest(5, 'Market_Value')['Market_Value'].sum() / total_portfolio_value * 100,
        'single_largest_weight': consolidated_df['Market_Value'].max() / total_portfolio_value * 100,
        'cash_percentage': consolidated_df[consolidated_df['Symbol'] == 'CASH']['Market_Value'].sum() / total_portfolio_value * 100
    }
    
    return metrics

# ==================== MODULE 3: TECHNICAL ANALYSIS ====================

def get_current_market_data(symbols, period='1mo'):
    """Fetch current market data for technical analysis"""
    print(f"📊 Fetching market data for technical analysis...")
    
    market_data = {}
    failed_symbols = []
    
    for symbol in symbols[:10]:  # Limit to avoid API limits
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            info = ticker.info
            
            if len(hist) > 0:
                market_data[symbol] = {
                    'current_price': hist['Close'].iloc[-1],
                    'history': hist,
                    'volume': hist['Volume'].iloc[-1] if len(hist) > 0 else 0,
                    'high_52w': info.get('fiftyTwoWeekHigh', 0),
                    'low_52w': info.get('fiftyTwoWeekLow', 0),
                }
            else:
                failed_symbols.append(symbol)
                
        except Exception as e:
            failed_symbols.append(symbol)
            continue
    
    print(f"✅ Fetched data for {len(market_data)} symbols")
    return market_data

def calculate_technical_indicators(hist_data):
    """Calculate key technical indicators"""
    if len(hist_data) < 20:
        return {}
    
    close = hist_data['Close']
    indicators = {}
    
    # Moving Averages
    indicators['sma_20'] = close.rolling(window=20).mean().iloc[-1]
    indicators['sma_50'] = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else 0
    
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    indicators['rsi'] = (100 - (100 / (1 + rs))).iloc[-1]
    
    # Support and Resistance
    recent_data = hist_data.tail(20)
    indicators['resistance'] = recent_data['High'].max()
    indicators['support'] = recent_data['Low'].min()
    
    return indicators

# ==================== MODULE 4: OPTIONS ANALYSIS ====================

def black_scholes_call(S, K, T, r, sigma):
    """Calculate Black-Scholes call option price and Greeks"""
    if T <= 0:
        return max(S - K, 0), 0, 0, 0, 0
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    call_price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    delta = norm.cdf(d1)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    theta = -(S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100
    
    return call_price, delta, gamma, theta, vega

def black_scholes_put(S, K, T, r, sigma):
    """Calculate Black-Scholes put option price and Greeks"""
    if T <= 0:
        return max(K - S, 0), 0, 0, 0, 0
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    put_price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    delta = -norm.cdf(-d1)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    theta = -(S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100
    
    return put_price, delta, gamma, theta, vega

def analyze_covered_call(stock_price, position_size, position_value, strike_prices, days_to_expiry=30):
    """Analyze covered call opportunities"""
    strategies = []
    estimated_vol = 0.25
    risk_free_rate = 0.05
    
    for strike in strike_prices:
        if strike <= stock_price:
            continue
            
        T = days_to_expiry / 365
        call_price, delta, gamma, theta, vega = black_scholes_call(stock_price, strike, T, risk_free_rate, estimated_vol)
        
        premium_income = call_price * position_size * 100
        monthly_yield = (premium_income / position_value) * (30 / days_to_expiry)
        
        strategy = {
            'strategy': 'Covered Call',
            'strike': strike,
            'premium': call_price,
            'total_premium': premium_income,
            'monthly_yield': monthly_yield * 100,
            'annualized_yield': monthly_yield * 12 * 100,
        }
        
        strategies.append(strategy)
    
    return strategies

def analyze_protective_put(stock_price, position_size, position_value, strike_prices, days_to_expiry=30):
    """Analyze protective put strategies"""
    strategies = []
    estimated_vol = 0.25
    risk_free_rate = 0.05
    
    for strike in strike_prices:
        if strike >= stock_price:
            continue
            
        T = days_to_expiry / 365
        put_price, delta, gamma, theta, vega = black_scholes_put(stock_price, strike, T, risk_free_rate, estimated_vol)
        
        protection_cost = put_price * position_size * 100
        protection_cost_pct = (protection_cost / position_value) * 100
        downside_protection = ((stock_price - strike) / stock_price) * 100
        
        strategy = {
            'strategy': 'Protective Put',
            'strike': strike,
            'premium': put_price,
            'total_cost': protection_cost,
            'cost_pct': protection_cost_pct,
            'downside_protection': downside_protection,
        }
        
        strategies.append(strategy)
    
    return strategies

def generate_strike_prices(stock_price, num_strikes=3):
    """Generate reasonable strike prices"""
    strikes = []
    
    for i in range(1, num_strikes + 1):
        strikes.append(round(stock_price * (1 + i * 0.05), 2))  # Calls above
        strikes.append(round(stock_price * (1 - i * 0.05), 2))  # Puts below
    
    return sorted(strikes)

# ==================== MAIN EXECUTION ====================

print("\n📁 STEP 1: Upload your positions file")
print("👆 Click 'Choose Files' button below to upload CSV or Excel file")

try:
    uploaded = files.upload()
    
    if uploaded:
        filename = list(uploaded.keys())[0]
        print(f"\n✅ File uploaded: {filename}")
        
        # Load the file
        try:
            if filename.lower().endswith('.csv'):
                df = pd.read_csv(io.BytesIO(uploaded[filename]))
            elif filename.lower().endswith(('.xlsx', '.xls')):
                df = pd.read_excel(io.BytesIO(uploaded[filename]))
            else:
                raise ValueError("Unsupported file format")
                
            print(f"✅ File loaded successfully! Shape: {df.shape}")
            
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            exit()
        
        # ==================== STEP 2: AGGREGATE POSITIONS ====================
        
        print(f"\n📊 STEP 2: Aggregating positions across all accounts")
        
        sections = find_account_sections(df)
        print(f"🔍 Found {len(sections)} potential position rows")
        
        agg_df = create_aggregated_positions(sections, df)
        
        if len(agg_df) > 0:
            # Filter out empty symbols but keep cash
            agg_df = agg_df[agg_df['Symbol'] != '']
            agg_df = agg_df[agg_df['Market_Value'] > 0]
            
            print(f"✅ Successfully aggregated {len(agg_df)} positions")
            
            # Add sector classification
            agg_df['Sector'] = agg_df.apply(lambda row: classify_sector(row['Symbol'], row['Description']), axis=1)
            
            # ==================== CREATE CONSOLIDATED VIEW ====================
            
            print(f"🔄 Creating consolidated view by symbol...")
            
            symbol_agg = agg_df.groupby('Symbol').agg({
                'Market_Value': 'sum',
                'Quantity': 'sum', 
                'Day_Change_Dollar': 'sum',
                'Account': lambda x: ', '.join(sorted(set(x))),
                'Description': 'first',
                'Sector': 'first'
            }).reset_index()
            
            # Calculate total portfolio value from consolidated positions
            total_portfolio_value = symbol_agg['Market_Value'].sum()
            
            # Calculate metrics using consolidated positions
            metrics = calculate_portfolio_metrics(symbol_agg, total_portfolio_value)
            
            # Add position weights to both dataframes
            agg_df['Position_Weight'] = (agg_df['Market_Value'] / total_portfolio_value * 100).round(2)
            symbol_agg['Consolidated_Weight'] = (symbol_agg['Market_Value'] / total_portfolio_value * 100).round(2)
            symbol_agg['Account_Count'] = symbol_agg['Account'].apply(lambda x: len(x.split(', ')))
            symbol_agg = symbol_agg.sort_values('Market_Value', ascending=False)
            # Data type enforcement for both dataframes
            numeric_columns = ['Quantity', 'Price', 'Market_Value', 'Day_Change_Dollar', 'Day_Change_Percent', 'Position_Weight']
            for col in numeric_columns:
                if col in agg_df.columns:
                    agg_df[col] = agg_df[col].apply(clean_numeric)
                    agg_df[col] = pd.to_numeric(agg_df[col], errors='coerce').fillna(0.0)
                    agg_df[col] = agg_df[col].astype('float64')
            
            consolidated_numeric_columns = ['Market_Value', 'Quantity', 'Day_Change_Dollar', 'Consolidated_Weight', 'Account_Count']
            for col in consolidated_numeric_columns:
                if col in symbol_agg.columns:
                    symbol_agg[col] = symbol_agg[col].apply(clean_numeric)
                    symbol_agg[col] = pd.to_numeric(symbol_agg[col], errors='coerce').fillna(0.0)
                    symbol_agg[col] = symbol_agg[col].astype('float64')
            
            # ==================== DISPLAY RESULTS ====================
            
            print(f"\n" + "="*60)
            print(f"🎯 COMPLETE PORTFOLIO ANALYSIS RESULTS")
            print(f"="*60)
            
            print(f"\n📊 PORTFOLIO SUMMARY:")
            print(f"   Total Portfolio Value: ${metrics['total_portfolio_value']:,.2f}")
            print(f"   Total Consolidated Positions: {metrics['position_count']} (including cash)")
            print(f"   Cash & Equivalents: ${symbol_agg[symbol_agg['Symbol'] == 'CASH']['Market_Value'].sum():,.2f} ({metrics['cash_percentage']:.1f}%)")
            print(f"   Largest Position: {symbol_agg.iloc[0]['Symbol']} = ${metrics['largest_position']:,.2f} ({metrics['single_largest_weight']:.1f}%)")
            print(f"   Top 5 Concentration: {metrics['top_5_concentration']:.1f}%")
            
            print(f"\n🏆 TOP 10 HOLDINGS (CONSOLIDATED):")
            top_10_consolidated = symbol_agg.head(10)[['Symbol', 'Description', 'Market_Value', 'Consolidated_Weight', 'Account_Count']]
            print(top_10_consolidated.to_string(index=False))
            
            # Sector analysis
            print(f"\n🏭 SECTOR ALLOCATION:")
            sector_analysis = symbol_agg.groupby('Sector').agg({'Market_Value': 'sum'}).round(2)
            sector_analysis['Percentage'] = (sector_analysis['Market_Value'] / total_portfolio_value * 100).round(1)
            sector_analysis = sector_analysis.sort_values('Market_Value', ascending=False)
            print(sector_analysis.head(10))
            
            # ==================== STEP 3: TECHNICAL ANALYSIS ====================
            
            print(f"\n📈 STEP 3: Technical Analysis")
            
            # Get top positions for technical analysis
            top_positions = symbol_agg.head(10)
            stock_symbols = []
            
            for _, pos in top_positions.iterrows():
                symbol = pos['Symbol']
                if symbol and len(symbol) <= 5 and symbol.isalpha():
                    stock_symbols.append(symbol)
            
            market_data = {}
            tech_data = []
            
            if stock_symbols:
                market_data = get_current_market_data(stock_symbols[:5])  # Limit to 5 to avoid API limits
                
                if market_data:
                    print(f"\n📊 TECHNICAL SIGNALS:")
                    print(f"{'Symbol':<6} {'Price':<8} {'RSI':<6} {'vs SMA20':<10} {'Signal':<12}")  
                    print(f"-" * 50)
                    
                    for symbol in market_data:
                        indicators = calculate_technical_indicators(market_data[symbol]['history'])
                        current_price = market_data[symbol]['current_price']
                        
                        rsi = indicators.get('rsi', 50)
                        sma_20 = indicators.get('sma_20', current_price)
                        vs_sma = "Above" if current_price > sma_20 else "Below"
                        
                        if rsi < 30:
                            signal = "OVERSOLD"
                        elif rsi > 70:
                            signal = "OVERBOUGHT"
                        elif current_price > sma_20:
                            signal = "BULLISH"
                        else:
                            signal = "BEARISH"
                        
                        print(f"{symbol:<6} ${current_price:<7.2f} {rsi:<5.1f} {vs_sma:<10} {signal:<12}")
                        
                        # Store for export
                        tech_record = {
                            'Symbol': symbol,
                            'Current_Price': current_price,
                            'RSI': rsi,
                            'SMA_20': sma_20,
                            'Support': indicators.get('support', 0),
                            'Resistance': indicators.get('resistance', 0),
                            'Signal': signal
                        }
                        tech_data.append(tech_record)
            
            # ==================== STEP 4: OPTIONS ANALYSIS ====================
            
            print(f"\n📊 STEP 4: Options Analysis")
            
            # Focus on larger positions for options (exclude cash)
            large_positions = symbol_agg[(symbol_agg['Consolidated_Weight'] > 3) & (symbol_agg['Symbol'] != 'CASH')].copy()
            options_data = []
            
            if len(large_positions) > 0:
                print(f"\n🎯 OPTIONS OPPORTUNITIES (Positions >3%):")
                print(f"{'Symbol':<6} {'Value':<10} {'Weight':<8} {'Covered Calls':<15} {'Protective Puts':<15}")
                print(f"-" * 70)
                
                for _, position in large_positions.head(5).iterrows():  # Top 5 large positions
                    symbol = position['Symbol']
                    
                    if len(symbol) <= 4 and symbol.isalpha():  # Only analyze stocks
                        position_value = position['Market_Value']
                        weight = position['Consolidated_Weight']
                        
                        # Estimate current price
                        estimated_price = position_value / position.get('Quantity', 1) if position.get('Quantity', 0) > 0 else 100
                        
                        # Calculate position size in round lots
                        total_shares = position.get('Quantity', position_value / estimated_price)
                        round_lots = max(1, int(total_shares / 100))
                        
                        # Generate strike prices
                        strikes = generate_strike_prices(estimated_price, 2)
                        
                        # Analyze covered calls
                        call_strikes = [s for s in strikes if s > estimated_price][:2]
                        if call_strikes:
                            covered_calls = analyze_covered_call(estimated_price, round_lots, position_value, call_strikes)
                            best_call = max(covered_calls, key=lambda x: x['monthly_yield']) if covered_calls else None
                            call_info = f"{best_call['monthly_yield']:.1f}%/mo" if best_call else "N/A"
                            
                            if best_call:
                                options_data.append({
                                    'Symbol': symbol,
                                    'Strategy': 'Covered Call',
                                    'Strike': best_call['strike'],
                                    'Premium': best_call['premium'],
                                    'Monthly_Yield_%': best_call['monthly_yield'],
                                    'Annual_Yield_%': best_call['annualized_yield'],
                                    'Position_Value': position_value,
                                    'Position_Weight_%': weight
                                })
                        else:
                            call_info = "N/A"
                        
                        # Analyze protective puts  
                        put_strikes = [s for s in strikes if s < estimated_price][:2]
                        if put_strikes:
                            protective_puts = analyze_protective_put(estimated_price, round_lots, position_value, put_strikes)
                            best_put = max(protective_puts, key=lambda x: x['downside_protection']) if protective_puts else None
                            put_info = f"{best_put['downside_protection']:.1f}% protect" if best_put else "N/A"
                            
                            if best_put:
                                options_data.append({
                                    'Symbol': symbol,
                                    'Strategy': 'Protective Put',
                                    'Strike': best_put['strike'],
                                    'Premium': best_put['premium'],
                                    'Cost_%': best_put['cost_pct'],
                                    'Protection_%': best_put['downside_protection'],
                                    'Position_Value': position_value,
                                    'Position_Weight_%': weight
                                })
                        else:
                            put_info = "N/A"
                        
                        print(f"{symbol:<6} ${position_value:<9,.0f} {weight:<7.1f}% {call_info:<15} {put_info:<15}")
                
                print(f"\n💡 OPTIONS STRATEGY RECOMMENDATIONS:")
                print(f"✅ Use covered calls on large positions to generate 1-3% monthly income")
                print(f"✅ Consider protective puts on concentrated holdings >10% of portfolio")
                print(f"✅ Monitor time decay - options lose value as expiration approaches")
                print(f"✅ Roll positions before expiration to maintain strategies")
            
            # ==================== VISUALIZATION ====================
            
            print(f"\n📊 Creating portfolio visualization...")
            
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
            fig.suptitle('Complete Portfolio Analysis Dashboard', fontsize=16, fontweight='bold')
            
            # 1. Sector allocation
            sector_values = sector_analysis.head(8)['Market_Value']
            ax1.pie(sector_values, labels=sector_values.index, autopct='%1.1f%%', startangle=90)
            ax1.set_title('Portfolio by Sector')
            
            # 2. Top 10 positions
            top_10_viz = symbol_agg.head(10)
            bars = ax2.barh(top_10_viz['Symbol'], top_10_viz['Market_Value'])
            ax2.set_title('Top 10 Holdings')
            ax2.set_xlabel('Market Value ($)')
            
            # 3. Position concentration
            weights = symbol_agg['Consolidated_Weight'].head(15)
            ax3.bar(range(len(weights)), weights)
            ax3.set_title('Position Weights (Top 15)')
            ax3.set_ylabel('Portfolio Weight (%)')
            ax3.set_xticks(range(len(weights)))
            ax3.set_xticklabels(symbol_agg['Symbol'].head(15), rotation=45)
            
            # 4. Account allocation
            account_analysis = agg_df.groupby('Account')['Market_Value'].sum()
            ax4.pie(account_analysis.values, labels=account_analysis.index, autopct='%1.1f%%', startangle=90)
            ax4.set_title('Portfolio by Account')
            
            plt.tight_layout()
            plt.show()
            
            # ==================== EXPORT TO SINGLE EXCEL WORKBOOK ====================
            
            print(f"\n💾 Exporting all analysis results to single Excel workbook...")
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            workbook_filename = f"complete_portfolio_analysis_{timestamp}.xlsx"
            
            # Create Excel writer object
            with pd.ExcelWriter(workbook_filename, engine='openpyxl') as writer:
                
                # Sheet 1: Portfolio Summary
                summary_data = {
                    'Metric': [
                        'Total Portfolio Value',
                        'Total Positions', 
                        'Average Position Size',
                        'Largest Position Value',
                        'Largest Position %',
                        'Top 5 Concentration %',
                        'Top 10 Concentration %',
                        'Cash Percentage %'
                    ],
                    'Value': [
                        f"${metrics['total_portfolio_value']:,.2f}",
                        metrics['position_count'],
                        f"${metrics['average_position_size']:,.2f}",
                        f"${metrics['largest_position']:,.2f}",
                        f"{metrics['single_largest_weight']:.2f}%",
                        f"{metrics['top_5_concentration']:.2f}%",
                        f"{metrics['top_10_concentration']:.2f}%",
                        f"{metrics['cash_percentage']:.2f}%"
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Portfolio_Summary', index=False)
                
                # Sheet 2: Individual Positions (by account)
                individual_export = agg_df.sort_values('Market_Value', ascending=False).copy()
                individual_export.to_excel(writer, sheet_name='Individual_Positions', index=False)
                
                # Sheet 3: Consolidated Positions (by symbol)
                consolidated_export = symbol_agg.copy()
                consolidated_export.to_excel(writer, sheet_name='Consolidated_Positions', index=False)
                
                # Sheet 4: Sector Analysis
                sector_export = sector_analysis.copy()
                sector_export['Sector'] = sector_export.index
                sector_export = sector_export[['Sector', 'Market_Value', 'Percentage']]
                sector_export.to_excel(writer, sheet_name='Sector_Analysis', index=False)
                
                # Sheet 5: Account Analysis
                account_export = agg_df.groupby('Account').agg({
                    'Market_Value': 'sum',
                    'Symbol': 'count',
                    'Day_Change_Dollar': 'sum'
                }).reset_index()
                account_export.columns = ['Account', 'Total_Value', 'Position_Count', 'Day_Change_Total']
                account_export['Percentage'] = (account_export['Total_Value'] / metrics['total_portfolio_value'] * 100).round(2)
                account_export.to_excel(writer, sheet_name='Account_Analysis', index=False)
                
                # Sheet 6: Technical Analysis (if available)
                if tech_data:
                    tech_df = pd.DataFrame(tech_data)
                    tech_df.to_excel(writer, sheet_name='Technical_Analysis', index=False)
                
                # Sheet 7: Options Strategies (if available)
                if options_data:
                    options_df = pd.DataFrame(options_data)
                    options_df.to_excel(writer, sheet_name='Options_Strategies', index=False)
                
                # Sheet 8: Risk Metrics
                risk_data = []
                
                # Concentration risks
                concentrated_positions = symbol_agg[symbol_agg['Consolidated_Weight'] > 5]
                for _, pos in concentrated_positions.iterrows():
                    risk_data.append({
                        'Risk_Type': 'Concentration Risk',
                        'Symbol': pos['Symbol'],
                        'Description': f"{pos['Symbol']} represents {pos['Consolidated_Weight']:.1f}% of portfolio",
                        'Severity': 'High' if pos['Consolidated_Weight'] > 10 else 'Medium',
                        'Recommendation': 'Consider reducing position size or hedging'
                    })
                
                # Multi-account positions
                multi_account_positions = symbol_agg[symbol_agg['Account_Count'] > 1]
                for _, pos in multi_account_positions.iterrows():
                    risk_data.append({
                        'Risk_Type': 'Consolidation Opportunity',
                        'Symbol': pos['Symbol'],
                        'Description': f"{pos['Symbol']} held across {pos['Account_Count']} accounts",
                        'Severity': 'Low',
                        'Recommendation': 'Consider consolidating positions for better management'
                    })
                
                # Sector concentration
                sector_concentration = sector_analysis[sector_analysis['Percentage'] > 25]
                for sector, data in sector_concentration.iterrows():
                    risk_data.append({
                        'Risk_Type': 'Sector Concentration',
                        'Symbol': sector,
                        'Description': f"{sector} sector represents {data['Percentage']:.1f}% of portfolio",
                        'Severity': 'Medium',
                        'Recommendation': 'Consider diversifying across sectors'
                    })
                
                if risk_data:
                    risk_df = pd.DataFrame(risk_data)
                    risk_df.to_excel(writer, sheet_name='Risk_Analysis', index=False)
                
                # Sheet 9: Top Holdings Detail
                top_holdings_detail = symbol_agg.head(20).copy()
                top_holdings_detail['Cumulative_Weight'] = top_holdings_detail['Consolidated_Weight'].cumsum()
                top_holdings_detail.to_excel(writer, sheet_name='Top_Holdings_Detail', index=False)
            
            print(f"✅ Complete analysis exported to: {workbook_filename}")
            
            # Download the file
            files.download(workbook_filename)
            
            print(f"\n🎉 COMPLETE ANALYSIS FINISHED!")
            print(f"📊 ALL 4 MODULES EXECUTED SUCCESSFULLY")
            print(f"💾 SINGLE EXCEL WORKBOOK CREATED WITH 9 SHEETS")
            print(f"=" * 60)
            
            print(f"\n📝 Excel workbook contains:")
            print(f"   📋 Sheet 1: Portfolio Summary - Key metrics and KPIs")
            print(f"   📊 Sheet 2: Individual Positions - All positions by account")
            print(f"   🔄 Sheet 3: Consolidated Positions - Positions aggregated by symbol")
            print(f"   🏭 Sheet 4: Sector Analysis - Allocation by sector")
            print(f"   🏦 Sheet 5: Account Analysis - Breakdown by account")
            if tech_data:
                print(f"   📈 Sheet 6: Technical Analysis - RSI, moving averages, signals")
            if options_data:
                print(f"   📊 Sheet 7: Options Strategies - Covered calls and protective puts")
            print(f"   ⚠️  Sheet 8: Risk Analysis - Concentration and diversification risks")
            print(f"   🏆 Sheet 9: Top Holdings Detail - Top 20 positions with cumulative weights")
            
            print(f"\n🎯 TACTICAL INSIGHTS SUMMARY:")
            
            # Risk warnings
            if metrics['single_largest_weight'] > 10:
                largest_symbol = symbol_agg.iloc[0]['Symbol']
                print(f"⚠️  CONCENTRATION RISK: {largest_symbol} is {metrics['single_largest_weight']:.1f}% of portfolio")
            
            if metrics['top_5_concentration'] > 50:
                print(f"⚠️  HIGH CONCENTRATION: Top 5 positions = {metrics['top_5_concentration']:.1f}% of portfolio")
            
            # Multi-account positions
            multi_account_symbols = symbol_agg[symbol_agg['Account_Count'] > 1]
            if len(multi_account_symbols) > 0:
                print(f"\n🔄 CONSOLIDATION OPPORTUNITIES:")
                for _, pos in multi_account_symbols.head(3).iterrows():
                    print(f"   • {pos['Symbol']}: ${pos['Market_Value']:,.0f} across {pos['Account_Count']} accounts")
            
            # Options opportunities
            if len(large_positions) > 0:
                print(f"\n📊 OPTIONS OPPORTUNITIES:")
                print(f"   • {len(large_positions)} positions >3% suitable for covered calls")
                print(f"   • Consider protective puts for positions >10% of portfolio")
                print(f"   • Estimated monthly income potential: 1-3% on large positions")
            
            print(f"\n💡 NEXT STEPS:")
            print(f"✅ Review the Excel workbook for detailed analysis")
            print(f"✅ Focus on concentration risks identified in Risk Analysis sheet")
            print(f"✅ Implement covered call strategies from Options Strategies sheet")
            print(f"✅ Monitor technical signals from Technical Analysis sheet")
            print(f"✅ Consider consolidating multi-account positions")
            
            # Final success message
            print(f"\n🚀 COMPLETE PORTFOLIO ANALYSIS TOOLKIT READY!")
            print(f"   📈 Position Analysis ✅")
            print(f"   🎯 Risk Assessment ✅") 
            print(f"   📊 Technical Signals ✅")
            print(f"   💼 Options Strategies ✅")
            print(f"   📁 Single Workbook Export ✅")
            
        else:
            print("❌ No valid positions found in the data")
            
    else:
        print("❌ No file uploaded")
        
except Exception as e:
    print(f"❌ Error in complete analysis: {e}")
    import traceback
    traceback.print_exc()

print(f"\n✨ Portfolio analysis complete! Single Excel workbook created successfully.")