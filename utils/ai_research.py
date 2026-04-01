import json
import anthropic
import os
import sys

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import config
except ImportError:
    pass

def analyze_ticker(ticker: str, transcripts: list[dict], news: list[dict]) -> dict:
    """
    Orchestrate Claude 3.5 Sonnet analysis.
    Returns: {"bull_cases": [str], "bear_risks": [str], "sentiment_score": float, "summary": str}
    """
    if not config.ANTHROPIC_API_KEY:
        return {"error": "Anthropic API key not set."}
        
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    
    # Prepare context
    transcript_text = "\n\n".join([f"Date: {t['date']}\nContent: {t['content'][:5000]}..." for t in transcripts])
    news_text = "\n\n".join([f"Title: {n['title']}\nSummary: {n['text']}" for n in news])
    
    prompt = f"""
    You are a senior equity research analyst. Analyze the following data for {ticker}.
    
    TRANSCRIPTS:
    {transcript_text}
    
    RECENT NEWS:
    {news_text}
    
    Provide your analysis in EXACT JSON format with these keys:
    - "bull_cases": A list of exactly 3 bullet points.
    - "bear_risks": A list of exactly 2 bullet points.
    - "sentiment_score": A float from -1.0 (very bearish) to 1.0 (very bullish).
    - "summary": A 2-sentence executive summary.
    
    Output ONLY valid JSON. No conversational filler.
    """
    
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            temperature=0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Extract content
        text = response.content[0].text
        # Strip potential markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        
        data = json.loads(text.strip())
        return data
        
    except Exception as e:
        print(f"AI Research Error for {ticker}: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    # Stub test
    if config.ANTHROPIC_API_KEY:
        res = analyze_ticker("AAPL", [], [])
        print(json.dumps(res, indent=2))
    else:
        print("ANTHROPIC_API_KEY not set.")
