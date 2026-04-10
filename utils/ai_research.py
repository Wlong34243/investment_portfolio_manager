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

def analyze_ticker(ticker: str, transcript: str | None, news: list[dict]) -> dict:
    """
    Orchestrate Gemini analysis for a single ticker.
    Handles missing transcript/news gracefully — falls back to Gemini's
    training knowledge so the response is always substantive.
    Returns: {"bull_cases": [str], "bear_risks": [str], "sentiment_score": float, "summary": str}
    """
    transcript_text = transcript[:10000] if transcript else "No earnings transcript available."
    news_text = (
        "\n\n".join([f"Headline: {n['headline']}\nSummary: {n['summary']}" for n in news[:5]])
        if news else "No recent news available."
    )

    prompt = f"""You are a senior equity research analyst writing a brief but thorough research note on {ticker}.

EARNINGS TRANSCRIPT (most recent available):
{transcript_text}

RECENT NEWS HEADLINES:
{news_text}

INSTRUCTIONS:
- If transcript or news data is limited, draw on your training knowledge of {ticker}'s business model,
  competitive position, recent financial performance, and sector dynamics to produce a complete analysis.
- Do NOT truncate or abbreviate. Every field must be fully populated.
- Respond in valid JSON only — no markdown, no extra text outside the JSON object.

Required JSON keys:
- "summary": A 3–4 sentence executive summary covering business model, recent performance, and outlook.
- "bull_cases": A list of exactly 3 detailed bullet points (1–2 sentences each) describing the strongest upside catalysts.
- "bear_risks": A list of exactly 3 detailed bullet points (1–2 sentences each) describing the key downside risks.
- "sentiment_score": A float from -1.0 (very bearish) to 1.0 (very bullish) based on the overall picture.
"""

    system_instruction = (
        "You are a senior equity research analyst at a top-tier investment bank. "
        "Provide detailed, specific, actionable analysis. Never give vague or one-line answers. "
        "Always complete every field fully even when source data is sparse."
    )

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
