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
from pathlib import Path
import google.auth
import google.auth.exceptions
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Type, TypeVar, Any, Union

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
    Two-path credential resolver.

    Path 1 — ADC / Vertex AI (CLI, local dev):
      genai.Client(vertexai=True, ...) lets the SDK discover ADC automatically.
      No explicit credentials object needed; gcloud auth application-default
      login is sufficient. Model strings must use Vertex AI naming convention
      (e.g. "gemini-3.1-pro-preview-customtools", NOT "gemini-3.1-pro-preview-customtools-latest").

    Path 2 — API key / AI Studio (Streamlit Cloud):
      Falls back to GEMINI_API_KEY from env var or Streamlit secrets when ADC
      is not present (Streamlit Cloud has no gcloud installation).

    Setup once for local CLI:
      gcloud auth application-default login
      gcloud auth application-default set-quota-project re-property-manager-487122
    """
    project_id = getattr(config, 'GCP_PROJECT_ID', 're-property-manager-487122')
    location = getattr(config, 'GCP_LOCATION', 'us-central1')

    # Path 1: ADC — SDK discovers credentials automatically (no explicit object needed)
    try:
        google.auth.default()  # raises DefaultCredentialsError if ADC absent
        return genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
        )
    except google.auth.exceptions.DefaultCredentialsError:
        pass
    except Exception:
        pass

    # Path 2: API key from environment
    api_key = os.environ.get('GEMINI_API_KEY')

    if api_key:
        return genai.Client(api_key=api_key)

    logging.warning(
        "No Gemini credentials found. Run:\n"
        "  gcloud auth application-default login\n"
        "  gcloud auth application-default set-quota-project re-property-manager-487122\n"
        "Or set GEMINI_API_KEY environment variable."
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
        
    model_name = getattr(config, 'GEMINI_MODEL', 'gemini-3.1-pro-preview-customtools')
    
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
        print(f"DEBUG: Gemini Response Finish Reason: {response.candidates[0].finish_reason if response.candidates else 'Unknown'}")
        print(f"DEBUG: Gemini Raw Response: {response.text[:200]}...")
        
        if response_schema:
            # response.parsed is populated by AI Studio but not always by
            # Vertex AI backend. Fall back to manual JSON parse when None.
            if response.parsed is not None:
                return response.parsed
            try:
                return response_schema.model_validate_json(response.text)
            except Exception as pe:
                print(f"DEBUG: Pydantic Parsing Failed: {pe}")
                return None
        return response.text
    except Exception as e:
        print(f"DEBUG: Gemini API error: {e}")
        logging.error(f"Gemini API error ({model_name}): {e}")
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            # Vertex AI TPM/RPM quota — exponential backoff with two retries
            for wait_sec in (60, 120):
                logging.info("429/RESOURCE_EXHAUSTED — waiting %ds before retry...", wait_sec)
                time.sleep(wait_sec)
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=generation_config,
                    )
                    print(f"DEBUG: Gemini Response Finish Reason: {response.candidates[0].finish_reason if response.candidates else 'Unknown'}")
                    if response_schema:
                        if response.parsed is not None:
                            return response.parsed
                        try:
                            return response_schema.model_validate_json(response.text)
                        except Exception:
                            return None
                    return response.text
                except Exception as retry_e:
                    if "429" not in str(retry_e) and "RESOURCE_EXHAUSTED" not in str(retry_e):
                        break  # non-quota error; stop retrying
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


def ask_gemini_bundled(
    prompt: str,
    bundle_path: Union[Path, str],
    response_schema: Type[T],
    system_instruction: str = None,
    max_tokens: int = 4000,
) -> T | None:
    """
    Bundle-aware Gemini call. Loads an immutable context bundle, verifies
    its hash, injects the hash into the Pydantic response metadata, and
    returns the parsed model instance.

    The response_schema MUST include a `bundle_hash: str` field. This is
    enforced at call time — if the schema lacks the field, raise ValueError
    before the LLM is invoked.

    This function is the ONLY sanctioned path for CLI agents. The legacy
    ask_gemini() remains for the Streamlit app during the transition.
    """
    from core.bundle import load_bundle

    # 1. Enforce schema contract before touching the LLM
    if "bundle_hash" not in response_schema.model_fields:
        raise ValueError(
            f"{response_schema.__name__} must include a 'bundle_hash: str' field "
            "to be used with ask_gemini_bundled()"
        )

    # 2. Load and verify bundle (raises ValueError on hash mismatch)
    bundle = load_bundle(Path(bundle_path))

    # 3. Build structured preamble that locks the model to this snapshot
    bundle_preamble = (
        f"CONTEXT BUNDLE (immutable snapshot):\n"
        f"  bundle_hash: {bundle['bundle_hash']}\n"
        f"  timestamp_utc: {bundle['timestamp_utc']}\n"
        f"  total_value: {bundle['total_value']}\n"
        f"  position_count: {bundle['position_count']}\n"
        f"  positions: {json.dumps(bundle['positions'], default=str)}\n\n"
        f"You MUST include bundle_hash='{bundle['bundle_hash']}' in your "
        f"response. This is how the output is traced to its input snapshot.\n\n"
        f"USER PROMPT:\n{prompt}"
    )

    # 4. Call existing ask_gemini() — SAFETY_PREAMBLE is auto-prepended there
    result = ask_gemini(
        bundle_preamble,
        system_instruction=system_instruction,
        response_schema=response_schema,
        max_tokens=max_tokens,
    )

    if result is None:
        return None

    # 5. Verify the returned hash matches; overwrite if the LLM hallucinated
    if result.bundle_hash != bundle["bundle_hash"]:
        logging.warning(
            f"ask_gemini_bundled: LLM returned bundle_hash={result.bundle_hash!r} "
            f"but expected {bundle['bundle_hash']!r}. Overwriting with correct hash."
        )
        result.bundle_hash = bundle["bundle_hash"]

    return result


def ask_gemini_composite(
    prompt: str,
    composite_bundle_path: Union[Path, str],
    response_schema: Type[T],
    ticker: str | None = None,
    system_instruction: str | None = None,
    max_tokens: int = 4000,
    include_vault_context: bool = True,
) -> T | None:
    """
    Composite-bundle-aware Gemini call.

    Loads the composite bundle, verifies hashes on both sub-bundles,
    and builds a structured context prompt that includes:
      - Full market bundle positions (from market sub-bundle)
      - Relevant thesis content (from vault sub-bundle)
        If ticker is provided: include only that position's thesis.
        If ticker is None: include all available theses.
      - theses_missing list so the agent can note coverage gaps.

    The response_schema MUST include a `bundle_hash: str` field.
    bundle_hash will be populated with composite_hash, not the
    individual sub-bundle hashes.

    SAFETY_PREAMBLE is still auto-prepended by the underlying ask_gemini()
    call — do NOT add it here.
    """
    from core.composite_bundle import load_composite_bundle
    from core.bundle import load_bundle
    from core.vault_bundle import load_vault_bundle

    # 1. Enforce schema contract
    if "bundle_hash" not in response_schema.model_fields:
        raise ValueError(
            f"{response_schema.__name__} must include a 'bundle_hash: str' field "
            "to be used with ask_gemini_composite()"
        )

    # 2. Load and verify composite bundle
    composite = load_composite_bundle(Path(composite_bundle_path))
    
    # 3. Load sub-bundles (load_ functions verify their own hashes)
    market = load_bundle(Path(composite["market_bundle_path"]))
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))

    # 4. Filter vault documents (only theses for V2)
    thesis_docs = []
    if ticker:
        ticker_upper = ticker.upper()
        # Find matching thesis
        for doc in vault["documents"]:
            if doc["doc_type"] == "thesis" and doc["ticker"] == ticker_upper:
                thesis_docs.append(doc)
                break
    else:
        # Include all theses
        thesis_docs = [doc for doc in vault["documents"] if doc["doc_type"] == "thesis"]

    # 5. Build composite preamble
    # include_vault_context=False skips the full thesis doc dump to keep input tokens small.
    # Use False for agents that pre-compute all needed context in their user_prompt (thesis, bagger).
    if include_vault_context:
        vault_section = (
            f"VAULT STATE:\n"
            f"  theses_present: {composite['theses_present']}\n"
            f"  theses_missing: {composite['theses_missing']}\n"
            f"  thesis_context: {json.dumps(thesis_docs, default=str)}\n\n"
        )
    else:
        vault_section = (
            f"VAULT STATE (summary only — full context pre-processed in user prompt):\n"
            f"  theses_present: {composite.get('theses_present', [])}\n"
            f"  theses_missing: {composite.get('theses_missing', [])}\n\n"
        )

    bundle_preamble = (
        f"COMPOSITE CONTEXT BUNDLE (immutable snapshot):\n"
        f"  composite_hash: {composite['composite_hash']}\n"
        f"  market_bundle_hash: {composite['market_bundle_hash']}\n"
        f"  vault_bundle_hash: {composite['vault_bundle_hash']}\n"
        f"  timestamp_utc: {composite['timestamp_utc']}\n\n"
        f"MARKET STATE:\n"
        f"  total_value: {market['total_value']}\n"
        f"  position_count: {market['position_count']}\n"
        f"  positions: {json.dumps(market['positions'], default=str)}\n\n"
        f"{vault_section}"
        f"You MUST include bundle_hash='{composite['composite_hash']}' "
        f"in your response.\n\n"
        f"USER PROMPT:\n{prompt}"
    )

    # 6. Call LLM
    result = ask_gemini(
        bundle_preamble,
        system_instruction=system_instruction,
        response_schema=response_schema,
        max_tokens=max_tokens,
    )

    if result is None:
        return None

    # 7. Verify/Overwrite hash
    if result.bundle_hash != composite["composite_hash"]:
        logging.warning(
            f"ask_gemini_composite: LLM returned bundle_hash={result.bundle_hash!r} "
            f"but expected {composite['composite_hash']!r}. Overwriting."
        )
        result.bundle_hash = composite["composite_hash"]

    return result
