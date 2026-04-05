import os
import json
import logging
import time
import re
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Type, TypeVar, Any

try:
    import config
except ImportError:
    config = None

# Module-level client cache
_GEMINI_CLIENT = None

T = TypeVar('T', bound=BaseModel)

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

def ask_gemini(prompt: str, system_instruction: str = None, json_mode: bool = False, max_tokens: int = 2000, response_schema: Type[T] = None) -> str | T:
    client = get_gemini_client()
    if not client:
        return "" if not response_schema else None
        
    model_name = getattr(config, 'GEMINI_MODEL', 'gemini-2.0-flash')
    
    full_system_instruction = SAFETY_PREAMBLE
    if system_instruction:
        full_system_instruction += f"\n\n{system_instruction}"
        
    if json_mode and not response_schema:
        full_system_instruction += "\n\nRespond ONLY with a valid JSON object."

    generation_config = types.GenerateContentConfig(
        system_instruction=full_system_instruction,
        max_output_tokens=max_tokens,
        temperature=0.1,
    )
    
    if response_schema:
        generation_config.response_mime_type = "application/json"
        generation_config.response_schema = response_schema
    elif json_mode:
        generation_config.response_mime_type = "application/json"

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=generation_config
        )
        
        if response_schema:
            return response.parsed
        return response.text
    except Exception as e:
        logging.error(f"Gemini API error ({model_name}): {e}")
        if "429" in str(e):
            logging.info("Rate limited. Waiting 30s...")
            time.sleep(30)
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=generation_config
                )
                if response_schema: return response.parsed
                return response.text
            except Exception:
                pass
        return "" if not response_schema else None

def ask_gemini_json(prompt: str, system_instruction: str = None, max_tokens: int = 2000) -> dict:
    """Legacy wrapper for raw JSON extraction."""
    response_text = ask_gemini(prompt, system_instruction, json_mode=True, max_tokens=max_tokens)
    if not response_text: return {"error": "Empty response"}
    
    # Surgical extract
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match: cleaned = match.group(1).strip()
    
    try:
        return json.loads(cleaned)
    except:
        return {"error": "JSON Parse Failure", "raw": response_text[:200]}
