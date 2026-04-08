'''
SAFETY: This Cloud Function ONLY refreshes OAuth tokens.
It does NOT and MUST NOT place orders or modify account state.

The only Schwab API call made is get_account_numbers() — a read-only
call used to trigger schwab-py's automatic token refresh mechanism.

PROHIBITED imports: any module containing "order", "trade", "place"
Code review checkpoint: grep main.py for those terms — only this
docstring should match.
'''

import os
import json
import logging
import tempfile
import time
from datetime import datetime, timezone
import functions_framework
import schwab.auth
from google.cloud import storage
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText

# Configure logging
logging.basicConfig(level=logging.INFO)

# Constants from environment
TOKEN_BUCKET = os.environ.get("TOKEN_BUCKET", "portfolio-manager-tokens")
ALERT_BLOB = "schwab_alert.json"
FAILURE_COUNT_BLOB = "refresh_failure_count.json"
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO")

@functions_framework.http
def refresh_token(request) -> tuple[str, int]:
    '''
    Cloud Function triggered by Cloud Scheduler every 25 minutes, 24/7.
    Refreshes both Schwab access tokens (accounts app + market data app)
    to keep their refresh tokens alive within the 7-day window.
    '''
    results = []
    apps_to_refresh = [
        ("accounts", "SCHWAB_ACCOUNTS_APP_KEY", "SCHWAB_ACCOUNTS_APP_SECRET", "token_accounts.json"),
        ("market",   "SCHWAB_MARKET_APP_KEY",   "SCHWAB_MARKET_APP_SECRET",   "token_market.json"),
    ]
    
    for app_label, app_key_env, app_secret_env, blob_name in apps_to_refresh:
        app_key = os.environ.get(app_key_env)
        app_secret = os.environ.get(app_secret_env)
        
        if not app_key or not app_secret:
            msg = f"Missing env vars for {app_label}: {app_key_env} or {app_secret_env}"
            logging.error(msg)
            results.append({"status": "error", "app": app_label, "reason": "config_missing"})
            continue
            
        result = _refresh_one(app_label, app_key, app_secret, blob_name)
        results.append(result)

    if all(r["status"] == "ok" for r in results):
        _clear_alert()
        _reset_failure_counter()
        return (json.dumps({"status": "ok", "results": results}), 200)
    else:
        # Track consecutive failures for Gmail escalation
        fail_count = _increment_failure_counter()
        if fail_count >= 2:
            _send_gmail_alert(results, fail_count)
        return (json.dumps({"status": "error", "results": results}), 500)

def _refresh_one(app_label, app_key, app_secret, blob_name) -> dict:
    '''
    Refresh a single Schwab app's token.
    '''
    storage_client = storage.Client()
    bucket = storage_client.bucket(TOKEN_BUCKET)
    blob = bucket.blob(blob_name)
    
    # a. Load token from GCS
    if not blob.exists():
        _write_alert(f"{app_label} token missing — run initial auth", "critical")
        return {"status": "error", "app": app_label, "reason": "missing"}
    
    token_str = blob.download_as_text()
    token_data = json.loads(token_str)
    
    # b. Check token age (to avoid hammering Schwab)
    # schwab-py token format usually has 'expires_at' or we can check blob metadata
    # We'll use the blob's updated time as a proxy for the last successful refresh
    updated_at = blob.updated
    if updated_at:
        age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
        if age_seconds < 1200: # 20 minutes
            logging.info(f"Skipping {app_label} refresh — last updated {age_seconds:.0f}s ago")
            return {"status": "ok", "app": app_label, "skipped": True, "age_seconds": age_seconds}

    # c. Build client with local temp file for auto-refresh
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tf:
        tf.write(token_str)
        temp_path = tf.name

    try:
        def token_loader():
            with open(temp_path, 'r') as f:
                return json.load(f)
        
        def token_saver(new_token):
            with open(temp_path, 'w') as f:
                json.dump(new_token, f)

        # d. Make lightweight API call to trigger auto-refresh
        # Note: we use a dummy callback URL as we only need the refresh flow
        client = schwab.auth.client_from_access_functions(
            app_key, app_secret, "https://127.0.0.1",
            token_loader, token_saver
        )
        
        # Trigger refresh
        r = client.get_account_numbers()
        
        if r.status_code == 401 or "invalid_client" in r.text:
            _write_alert(f"{app_label} refresh token expired — run manual reauth", "critical")
            return {"status": "error", "app": app_label, "reason": "expired"}
        
        r.raise_for_status()
        
        # e. Read updated token and save to GCS
        with open(temp_path, 'r') as f:
            refreshed_token = json.load(f)
            
        blob.upload_from_string(
            data=json.dumps(refreshed_token),
            content_type='application/json'
        )
        
        logging.info(f"Successfully refreshed {app_label} token.")
        return {"status": "ok", "app": app_label, "age_seconds": 0} # 0 because just updated
        
    except Exception as e:
        msg = str(e)
        if "401" in msg or "invalid_client" in msg:
            _write_alert(f"{app_label} refresh token expired — run manual reauth", "critical")
            return {"status": "error", "app": app_label, "reason": "expired"}
        
        logging.error(f"Error refreshing {app_label}: {e}")
        _write_alert(f"{app_label} refresh failed: {e}", "warning")
        return {"status": "error", "app": app_label, "reason": msg}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def _write_alert(message, severity):
    storage_client = storage.Client()
    bucket = storage_client.bucket(TOKEN_BUCKET)
    blob = bucket.blob(ALERT_BLOB)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "severity": severity,
        "message": message,
        "resolved": False
    }
    blob.upload_from_string(json.dumps(payload), content_type='application/json')

def _clear_alert():
    storage_client = storage.Client()
    bucket = storage_client.bucket(TOKEN_BUCKET)
    blob = bucket.blob(ALERT_BLOB)
    if blob.exists():
        blob.delete()

def _increment_failure_counter() -> int:
    storage_client = storage.Client()
    bucket = storage_client.bucket(TOKEN_BUCKET)
    blob = bucket.blob(FAILURE_COUNT_BLOB)
    
    count = 0
    if blob.exists():
        try:
            data = json.loads(blob.download_as_text())
            count = data.get("count", 0)
        except:
            pass
            
    count += 1
    blob.upload_from_string(json.dumps({"count": count}), content_type='application/json')
    return count

def _reset_failure_counter():
    storage_client = storage.Client()
    bucket = storage_client.bucket(TOKEN_BUCKET)
    blob = bucket.blob(FAILURE_COUNT_BLOB)
    if blob.exists():
        blob.upload_from_string(json.dumps({"count": 0}), content_type='application/json')

def _send_gmail_alert(results, fail_count):
    if not ALERT_EMAIL_TO:
        logging.warning("No ALERT_EMAIL_TO set, skipping Gmail alert.")
        return

    try:
        # The service account needs 'https://www.googleapis.com/auth/gmail.send'
        # and domain-wide delegation or a specifically authorized mailbox.
        # For simplicity, we assume the environment is authorized.
        service = build('gmail', 'v1')
        
        summary = "\n".join([f"- {r.get('app')}: {r.get('reason', 'ok')}" for r in results])
        
        body = f"""
Schwab token refresh is failing ({fail_count} consecutive failures).

Details:
{summary}

Recovery:
If 'expired': run python scripts/schwab_manual_reauth.py
If 'missing': run python scripts/schwab_initial_auth.py
"""
        message = MIMEText(body)
        message['to'] = ALERT_EMAIL_TO
        message['subject'] = f"[Portfolio Manager] Schwab token refresh failing ({fail_count}x)"
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        logging.info(f"Sent Gmail alert to {ALERT_EMAIL_TO}")
    except Exception as e:
        logging.error(f"Failed to send Gmail alert: {e}")
