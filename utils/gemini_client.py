"""
utils/gemini_client.py — Centralized Gemini LLM interface (Pydantic support).

Auth: ADC preferred (gcloud auth application-default login). API key fallback
for Streamlit Cloud.

Credential resolution:
  1. Application Default Credentials (ADC) via gcloud — preferred for local CLI.
     Same credential used by Gemini CLI. Setup once:
       gcloud auth application-default login
       gcloud auth application-default set-quota-project re-property-manager-487122
  2. GEMINI_API_KEY env var or Streamlit secrets — used on Streamlit Cloud.
"""

import os
import json
import logging
import time
import re
import google.auth
import google.auth.exceptions
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


def _build_genai_client():
    """
    Build a google-genai client using Application Default Credentials (ADC).
    Works automatically when `gcloud auth application-default login` has been run.
    No API key or service account JSON required for local CLI use.

    Falls back to GEMINI_API_KEY env var / Streamlit secrets so the
    Streamlit Cloud deployment is not broken.

    NOTE: When using vertexai=True the model name must be a valid Vertex AI
    model string (e.g. "gemini-2.0-flash", "gemini-2.5-pro-preview-03-25").
    config.GEMINI_MODEL is passed through as-is — verify it matches the model
    name used by your Gemini CLI if you change it.
    """
    project_id = getattr(config, 'GCP_PROJECT_ID', 're-property-manager-487122')

    # Path 1: ADC — preferred for local CLI use
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return genai.Client(
            vertexai=True,
            project=project_id,
            location="us-central1",
            credentials=credentials,
        )
    except google.auth.exceptions.DefaultCredentialsError:
        pass
    except Exception:
        pass

    # Path 2: API key from environment or Streamlit secrets
    api_key = getattr(config, 'GEMINI_API_KEY', None) or os.environ.get('GEMINI_API_KEY')
    if api_key:
        return genai.Client(api_key=api_key)

    logging.warning(
        "No Gemini credentials found. Run:\n"
        "  gcloud auth application-default login\n"
        "  gcloud auth application-default set-quota-project re-property-manager-487122\n"
        "Or set GEMINI_API_KEY in your environment."
    )
    return None


def get_gemini_client():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT
    _GEMINI_CLIENT = _build_genai_client()
    return _GEMINI_CLIENT

def ask_gemini(prompt: str, system_instruction: str = None, json_mode: bool = False, max_tokens: int = 2000, response_schema: Type[T] = None) -> str | T:
    client = get_gemini_client()
    if not client:
        return "" if not response_schema else None
        
    model_name = getattr(config, 'GEMINI_MODEL', 'gemini-3.1-pro-preview')
    
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
        
        # DEBUG
        print(f"DEBUG: Gemini Raw Response: {response.text[:200]}...")
        
        if response_schema:
            try:
                return response.parsed
            except Exception as pe:
                print(f"DEBUG: Pydantic Parsing Failed: {pe}")
                return None
        return response.text
    except Exception as e:
        print(f"DEBUG: Gemini API error: {e}")
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
