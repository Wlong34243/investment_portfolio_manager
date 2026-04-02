import logging
import pandas as pd

try:
    import pandas_ta as ta
except ImportError:
    ta = None

try:
    import yfinance as yf
except ImportError:
    yf = None

def calculate_technical_indicators(ticker: str, price_history: pd.DataFrame = None) -> dict:
    if not ta:
        logging.warning("pandas_ta is not installed.")
        return {"error": "pandas_ta not installed", "installed": False}
        
    if price_history is None:
        if not yf:
            return {"error": "yfinance not installed"}
        try:
            stock = yf.Ticker(ticker)
            price_history = stock.history(period="1y")
        except Exception as e:
            logging.warning(f"Failed to fetch yfinance data for {ticker}: {e}")
            return {}

    if price_history.empty or len(price_history) < 50:
        logging.warning(f"Not enough price history for {ticker} to calculate MAs.")
        return {}

    close = price_history['Close']
    
    try:
        rsi = ta.rsi(close, length=14)
        sma_50 = ta.sma(close, length=50)
        sma_200 = ta.sma(close, length=200)
        macd = ta.macd(close)
        
        latest_close = close.iloc[-1]
        latest_rsi = rsi.iloc[-1] if not rsi.empty else None
        latest_sma50 = sma_50.iloc[-1] if not sma_50.empty else None
        latest_sma200 = sma_200.iloc[-1] if not sma_200.empty else None
        
        macd_line = macd.iloc[-1, 0] if macd is not None and not macd.empty else None
        signal_line = macd.iloc[-1, 2] if macd is not None and not macd.empty else None
        
        rsi_signal = "Neutral"
        if latest_rsi:
            if latest_rsi > 70: rsi_signal = "Overbought"
            elif latest_rsi < 30: rsi_signal = "Oversold"
            
        ma_signal = "Neutral"
        if latest_sma50 and latest_sma200:
            if latest_sma50 > latest_sma200: ma_signal = "Golden Cross"
            elif latest_sma50 < latest_sma200: ma_signal = "Death Cross"
            
        price_vs_sma50 = "Above" if latest_sma50 and latest_close > latest_sma50 else "Below"
        price_vs_sma200 = "Above" if latest_sma200 and latest_close > latest_sma200 else "Below"
        
        macd_signal = "Neutral"
        if macd_line is not None and signal_line is not None:
            macd_signal = "Bullish" if macd_line > signal_line else "Bearish"

        return {
            "installed": True,
            "latest_price": latest_close,
            "rsi": latest_rsi,
            "sma_50": latest_sma50,
            "sma_200": latest_sma200,
            "macd": macd_line,
            "macd_signal_line": signal_line,
            "signals": {
                "rsi_signal": rsi_signal,
                "ma_signal": ma_signal,
                "price_vs_sma50": price_vs_sma50,
                "price_vs_sma200": price_vs_sma200,
                "macd_signal": macd_signal
            }
        }
    except Exception as e:
        logging.error(f"Error calculating technicals for {ticker}: {e}")
        return {}

def get_combined_signal_score(technicals: dict) -> dict:
    if not technicals or not technicals.get("signals"):
        return {"score": 0.0, "label": "Neutral", "components": {}}
        
    score = 0
    components = {}
    sigs = technicals["signals"]
    
    if sigs.get("rsi_signal") == "Oversold":
        score += 1; components["RSI"] = "+1 (Oversold/Buy)"
    elif sigs.get("rsi_signal") == "Overbought":
        score -= 1; components["RSI"] = "-1 (Overbought/Sell)"
        
    if sigs.get("ma_signal") == "Golden Cross":
        score += 1; components["MA_Cross"] = "+1 (Golden Cross)"
    elif sigs.get("ma_signal") == "Death Cross":
        score -= 1; components["MA_Cross"] = "-1 (Death Cross)"
        
    if sigs.get("price_vs_sma50") == "Above":
        score += 0.5; components["Price/SMA50"] = "+0.5 (Above)"
    elif sigs.get("price_vs_sma50") == "Below":
        score -= 0.5; components["Price/SMA50"] = "-0.5 (Below)"
        
    if sigs.get("macd_signal") == "Bullish":
        score += 1; components["MACD"] = "+1 (Bullish)"
    elif sigs.get("macd_signal") == "Bearish":
        score -= 1; components["MACD"] = "-1 (Bearish)"
        
    # Normalize approximately between -1.0 and 1.0
    normalized_score = max(min(score / 3.5, 1.0), -1.0)
    
    label = "Neutral"
    if normalized_score > 0.3: label = "Bullish"
    elif normalized_score < -0.3: label = "Bearish"
    
    return {
        "score": round(normalized_score, 2),
        "label": label,
        "components": components
    }
    
if __name__ == "__main__":
    print("Testing Technicals...")
    techs = calculate_technical_indicators("AMZN")
    print(get_combined_signal_score(techs))