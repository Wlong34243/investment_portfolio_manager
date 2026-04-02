import json
import logging
import os
import sys

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.gemini_client import ask_gemini_json

def analyze_ticker(ticker: str, transcript: str, news: list[dict]) -> dict:
    """
    Orchestrate Gemini 2.5 Pro analysis.
    Returns: {"bull_cases": [str], "bear_risks": [str], "sentiment_score": float, "summary": str}
    """
    
    # Prepare context
    news_text = "\n\n".join([f"Headline: {n['headline']}\nSummary: {n['summary']}" for n in news[:5]])
    
    prompt = f"""
    Analyze the following data for {ticker}.
    
    EARNINGS TRANSCRIPT SNIPPET:
    {transcript[:10000]}
    
    RECENT NEWS:
    {news_text}
    
    Provide your analysis in EXACT JSON format with these keys:
    - "bull_cases": A list of exactly 3 bullet points.
    - "bear_risks": A list of exactly 2 bullet points.
    - "sentiment_score": A float from -1.0 (very bearish) to 1.0 (very bullish).
    - "summary": A 2-sentence executive summary.
    """
    
    system_instruction = "You are a senior equity research analyst. Be objective, concise, and focus on fundamental catalysts."
    
    try:
        data = ask_gemini_json(prompt, system_instruction=system_instruction)
        return data
    except Exception as e:
        logging.error(f"AI Research Error for {ticker}: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    # Stub test
    res = analyze_ticker("AAPL", "Earnings were good.", [{"headline": "Apple does well", "summary": "Sales are up."}])
    print(json.dumps(res, indent=2))
