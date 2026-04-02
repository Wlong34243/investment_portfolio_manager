import os
import json
import logging
import time
from google import genai
from google.genai import types

try:
    import config
except ImportError:
    config = None  # Fallback for CLI testing

# Module-level client cache
_GEMINI_CLIENT = None

SAFETY_PREAMBLE = "You must NEVER recommend executing specific trades. You provide analysis and considerations only. All buy/sell decisions are the investor's."

def get_gemini_client():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT
    
    api_key = getattr(config, 'GEMINI_API_KEY', os.environ.get('GEMINI_API_KEY'))
    if not api_key:
        logging.warning("Gemini API key not found in config or environment.")
        return None
    
    _GEMINI_CLIENT = genai.Client(api_key=api_key)
    return _GEMINI_CLIENT

def ask_gemini(prompt: str, system_instruction: str = None, json_mode: bool = False, max_tokens: int = 2000) -> str:
    client = get_gemini_client()
    if not client:
        return ""
        
    model_name = getattr(config, 'GEMINI_MODEL', 'gemini-2.5-pro')
    
    # Prepend safety preamble to all system instructions
    full_system_instruction = SAFETY_PREAMBLE
    if system_instruction:
        full_system_instruction += f"\n\n{system_instruction}"
        
    if json_mode:
        full_system_instruction += "\n\nRespond ONLY with a JSON object. No preamble, no markdown fences, no explanation outside the JSON."

    generation_config = types.GenerateContentConfig(
        system_instruction=full_system_instruction,
        max_output_tokens=max_tokens,
        temperature=0.1,  # Low temp for deterministic financial reasoning
    )
    
    if json_mode:
        generation_config.response_mime_type = "application/json"

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=generation_config
        )
        return response.text
    except Exception as e:
        logging.error(f"Gemini API error: {e}")
        # Simple retry logic for rate limits
        if "429" in str(e):
            logging.info("Rate limited. Waiting 30s...")
            time.sleep(30)
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=generation_config
                )
                return response.text
            except Exception as retry_e:
                logging.error(f"Retry failed: {retry_e}")
        return ""

def ask_gemini_json(prompt: str, system_instruction: str = None, max_tokens: int = 2000) -> dict:
    response_text = ask_gemini(prompt, system_instruction, json_mode=True, max_tokens=max_tokens)
    if not response_text:
        return {"error": "Empty response from Gemini"}
        
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        # Fallback: try to strip markdown fences if the model ignored MIME type instructions
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
            
        try:
            return json.loads(cleaned_text.strip())
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON even after stripping fences.")
            return {"error": "Failed to parse response", "raw": response_text[:300]}
            
if __name__ == "__main__":
    # CLI Smoke Test
    print("Testing Gemini Client...")
    res = ask_gemini("Hello! Just reply 'Status Green' if you can read this.")
    print(f"Response: {res}")