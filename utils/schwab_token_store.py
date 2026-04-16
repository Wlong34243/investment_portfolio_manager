"""
utils/schwab_token_store.py — Token persistence for Schwab OAuth.
Stores in GCS with local fallback.
"""

import os
import json
import logging
from datetime import datetime
from google.cloud import storage
from google.oauth2 import service_account

import config

def _get_storage_client():
    """
    Authenticated GCS client using project-standard resolution.
    """
    # 1. Environment variable (GitHub Actions / .env)
    env_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            info = json.loads(env_json)
            creds = service_account.Credentials.from_service_account_info(info)
            return storage.Client(credentials=creds, project=config.GCP_PROJECT_ID)
        except Exception as e:
            logging.warning(f"Failed to load GCS credentials from GCP_SERVICE_ACCOUNT_JSON: {e}")

    # 3. local service_account.json

    return None

def load_token(blob_name: str) -> dict | None:
    """Downloads {blob_name} from gs://{SCHWAB_TOKEN_BUCKET}."""
    client = _get_storage_client()
    if not client:
        # Fallback to local if client init failed (e.g. no creds)
        return load_token_local(blob_name)
    
    try:
        bucket = client.bucket(config.SCHWAB_TOKEN_BUCKET)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return None
        
        token_str = blob.download_as_text()
        return json.loads(token_str)
    except Exception as e:
        logging.warning(f"GCS load_token warning ({blob_name}): {e}")
        return None

def save_token(token_data: dict, blob_name: str) -> bool:
    """Uploads token_data as JSON to gs://{SCHWAB_TOKEN_BUCKET}/{blob_name}."""
    client = _get_storage_client()
    if not client:
        return save_token_local(token_data, blob_name)
    
    try:
        bucket = client.bucket(config.SCHWAB_TOKEN_BUCKET)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            data=json.dumps(token_data),
            content_type='application/json'
        )
        # NEVER log the token contents
        logging.info(f"Successfully saved {blob_name} to GCS.")
        return True
    except Exception as e:
        logging.warning(f"GCS save_token failure ({blob_name}): {e}")
        return False

def load_token_local(path: str) -> dict | None:
    """For local dev: reads from filesystem."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return None

def save_token_local(token_data: dict, path: str) -> bool:
    """For local dev: writes to filesystem."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(token_data, f)
        return True
    except Exception:
        return False

def write_alert(message: str, severity: str = "warning") -> bool:
    """Writes alert message to GCS for Streamlit banner."""
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "severity": severity,
        "message": message,
        "resolved": False
    }
    return save_token(payload, config.SCHWAB_ALERT_BLOB)

def read_alert() -> dict | None:
    """Reads the active alert blob."""
    return load_token(config.SCHWAB_ALERT_BLOB)

def clear_alert() -> bool:
    """Deletes the alert blob from GCS."""
    client = _get_storage_client()
    if not client:
        return False
    try:
        bucket = client.bucket(config.SCHWAB_TOKEN_BUCKET)
        blob = bucket.blob(config.SCHWAB_ALERT_BLOB)
        if blob.exists():
            blob.delete()
        return True
    except Exception:
        return False
