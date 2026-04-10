# Phase 5-S: Schwab API Integration — Build Prompts

> **Purpose:** Replace manual CSV uploads with automated Schwab API pulls (positions, balances, transactions, quotes). CSV upload remains as a fallback path.
>
> **Architecture:** Two Schwab apps (Accounts and Trading + Market Data), each with its own OAuth token stored in GCS. A Cloud Function runs every 25 minutes 24/7 to keep both refresh tokens alive. The Streamlit app reads tokens from GCS and uses two scoped clients — Market Data client physically cannot reach account endpoints.
>
> **Safety rails (non-negotiable, enforced in every prompt):**
> 1. NO order/trading endpoints imported anywhere — grep-able at code review
> 2. `DRY_RUN` still gates all Sheet writes
> 3. API output flows through the same `normalize_positions()` as CSV input
> 4. Token files never logged, never printed, never committed
>
> **Pre-flight (already done):**
> - ✅ Both Schwab apps approved, keys in `secrets.toml`
> - ✅ GCS bucket `gs://portfolio-manager-tokens` created in `re-property-manager-487122` / `us-central1`
> - ✅ Service account `propertymanager@re-property-manager-487122.iam.gserviceaccount.com` granted `objectAdmin` on the bucket

---

## Pre-flight: Confirm `secrets.toml` and `config.py`

### `.streamlit/secrets.toml` additions

```toml
# Schwab — Accounts and Trading app (positions, balances, transactions)
schwab_accounts_app_key    = "..."
schwab_accounts_app_secret = "..."

# Schwab — Market Data app (quotes, price history, fundamentals)
schwab_market_app_key    = "..."
schwab_market_app_secret = "..."

# Shared
schwab_token_bucket  = "portfolio-manager-tokens"
schwab_account_hash  = ""    # filled in after running scripts/schwab_initial_auth.py
schwab_callback_url  = "https://127.0.0.1"
```

### `config.py` additions (paste under the existing API Keys block)

```python
# ---------------------------------------------------------------------------
# Schwab API (Phase 5-S)
# ---------------------------------------------------------------------------
SCHWAB_ACCOUNTS_APP_KEY    = _secret("schwab_accounts_app_key", "")
SCHWAB_ACCOUNTS_APP_SECRET = _secret("schwab_accounts_app_secret", "")
SCHWAB_MARKET_APP_KEY      = _secret("schwab_market_app_key", "")
SCHWAB_MARKET_APP_SECRET   = _secret("schwab_market_app_secret", "")

SCHWAB_TOKEN_BUCKET   = _secret("schwab_token_bucket", "portfolio-manager-tokens")
SCHWAB_ACCOUNT_HASH   = _secret("schwab_account_hash", "")
SCHWAB_CALLBACK_URL   = _secret("schwab_callback_url", "https://127.0.0.1")

# Token blob names in GCS (one per app — Market Data client cannot read accounts blob)
SCHWAB_TOKEN_BLOB_ACCOUNTS = "token_accounts.json"
SCHWAB_TOKEN_BLOB_MARKET   = "token_market.json"
SCHWAB_ALERT_BLOB          = "schwab_alert.json"

# GCP context (already used elsewhere — duplicated here for the Cloud Function)
GCP_PROJECT_ID = "re-property-manager-487122"
GCP_REGION     = "us-central1"

# Client cache TTL (Cloud Function does the actual refresh — this just caches the client object in Streamlit)
SCHWAB_CLIENT_CACHE_TTL = 1500   # 25 min
```

### `requirements.txt` additions

```
schwab-py>=1.5
httpx>=0.27
google-cloud-storage>=2.18
```

### `.gitignore` additions

```
token_accounts.json
token_market.json
*.token.json
.schwab/
```

---

## P5-S-A: Token Store + Initial Auth Script

**🤖 Claude Code Prompt:**

```
Read CLAUDE.md and config.py first to understand the project conventions.

Build two modules and one script:

============================================================
1. utils/schwab_token_store.py
============================================================

Token persistence layer for Schwab OAuth tokens. Stores in Google Cloud
Storage using the existing service account already used for Google Sheets.
Falls back to local file for development.

Functions:

  load_token(blob_name: str) -> dict | None
    - Downloads {blob_name} from gs://{SCHWAB_TOKEN_BUCKET}
    - Returns parsed JSON dict, or None if blob does not exist
    - Uses google-cloud-storage with credentials from
      st.secrets["gcp_service_account"] (same pattern as the existing
      Google Sheets client — see how gspread is initialized in pipeline.py
      and copy that auth pattern)
    - On any GCS error: log warning, return None (never raise)
    - NEVER log the token contents — only log the blob name and success/fail

  save_token(token_data: dict, blob_name: str) -> bool
    - Uploads token_data as JSON to gs://{SCHWAB_TOKEN_BUCKET}/{blob_name}
    - Sets content_type='application/json'
    - Returns True on success, False on failure
    - Last-write-wins is fine (single consumer per blob)
    - NEVER log the token contents

  load_token_local(path: str) -> dict | None
    - For local dev only: reads from filesystem
    - Returns None if file missing

  save_token_local(token_data: dict, path: str) -> bool
    - For local dev only: writes to filesystem
    - Creates parent dirs if needed

  write_alert(message: str, severity: str = "warning") -> bool
    - Writes {SCHWAB_ALERT_BLOB} to GCS with payload:
      {
        "timestamp": "<ISO8601 UTC>",
        "severity": "warning" | "critical",
        "message": message,
        "resolved": false
      }
    - Used by the Cloud Function and by client code on token failures
    - The Streamlit app reads this blob to show a banner

  read_alert() -> dict | None
    - Reads {SCHWAB_ALERT_BLOB} if present, returns parsed JSON
    - Used by app.py to show the banner

  clear_alert() -> bool
    - Deletes {SCHWAB_ALERT_BLOB} from GCS
    - Called when a successful token refresh happens after a failure

Module-level constants come from config.py — do not hardcode bucket names.

============================================================
2. utils/schwab_client.py
============================================================

READ-ONLY Schwab API client. Two scoped factory functions, one for the
Accounts app and one for the Market Data app. Each loads its own token
from GCS via schwab_token_store.

SAFETY PREAMBLE — paste at the top of the module as a docstring AND as
a comment block above the imports:

  '''
  SAFETY: This module provides READ-ONLY access to Schwab account and
  market data. It NEVER imports or calls order placement endpoints.

  PROHIBITED methods (do not import, do not call, do not even reference):
    - place_order
    - replace_order
    - cancel_order
    - get_orders_for_account
    - get_orders_for_all_linked_accounts

  Code review checkpoint: grep this file for "order" — only matches
  allowed are this docstring and comments. Any other match is a bug.
  '''

Functions:

  get_accounts_client() -> schwab.client.Client | None
    - Loads token from SCHWAB_TOKEN_BLOB_ACCOUNTS via load_token()
    - If token missing → write_alert("Accounts token missing — run initial auth", "critical")
      and return None
    - Builds a schwab-py client using SCHWAB_ACCOUNTS_APP_KEY,
      SCHWAB_ACCOUNTS_APP_SECRET, SCHWAB_CALLBACK_URL
    - Uses schwab.auth.client_from_access_functions() so we can supply
      our own load/save callbacks pointed at GCS (not the local file
      that schwab-py defaults to)
    - The save callback writes the refreshed token back to
      SCHWAB_TOKEN_BLOB_ACCOUNTS via save_token()
    - Wrap in @st.cache_resource(ttl=SCHWAB_CLIENT_CACHE_TTL) so we
      reuse the client object within a session

  get_market_client() -> schwab.client.Client | None
    - Same pattern as get_accounts_client() but uses
      SCHWAB_MARKET_APP_KEY / SCHWAB_MARKET_APP_SECRET and
      SCHWAB_TOKEN_BLOB_MARKET
    - Wrap in @st.cache_resource(ttl=SCHWAB_CLIENT_CACHE_TTL)

  fetch_positions(client) -> pd.DataFrame
    - Calls client.get_account(SCHWAB_ACCOUNT_HASH, fields=client.Account.Fields.POSITIONS)
    - Parses the JSON response into a DataFrame matching POSITION_COLUMNS
      from config.py exactly (use POSITION_COL_MAP for the rename)
    - Skips cash sweep tickers in CASH_TICKERS (these come from manual entry)
    - NUCLEAR TYPE ENFORCEMENT — required, not optional:
      Immediately after parsing the JSON response and BEFORE passing to
      normalize_positions, coerce every numeric column with:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
      Apply to: Quantity, Price, Market Value, Cost Basis, Unit Cost,
      Unrealized G/L, Unrealized G/L %, Est Annual Income, Dividend Yield,
      Daily Change %, Weight.
      Rationale: schwab-py occasionally returns numeric fields as strings
      depending on the endpoint, and Google Sheets is downstream — typing
      must be enforced at the source, not the sink. This matches the
      project's existing pattern for CSV ingestion in pipeline.py.
    - Adds 'Import Date' = today's date (UTC)
    - Computes 'Fingerprint' = "{import_date}|{ticker}|{quantity}|{market_value}"
    - Returns empty DataFrame on any error (never raises) and writes an alert

  fetch_transactions(client, start_date, end_date) -> pd.DataFrame
    - Calls client.get_transactions(SCHWAB_ACCOUNT_HASH, start_date=start_date, end_date=end_date)
    - Filters to types: TRADE, DIVIDEND_OR_INTEREST, RECEIVE_AND_DELIVER
    - Maps to the Transactions tab schema (look up the existing schema in
      pipeline.py or PORTFOLIO_SHEET_SCHEMA.md and match it exactly)
    - Builds fingerprint = "{trade_date}|{ticker}|{action}|{quantity}|{price}"
    - Returns empty DataFrame on error

  fetch_balances(client) -> dict
    - Calls client.get_account(SCHWAB_ACCOUNT_HASH)
    - Returns dict: {total_value, cash_value, buying_power, day_trading_buying_power}
    - Returns empty dict on error

  fetch_quotes(client, tickers: list[str]) -> pd.DataFrame
    - Uses the MARKET DATA client (not accounts)
    - Calls client.get_quotes(tickers)
    - Returns DataFrame: ticker, last_price, bid, ask, volume, change_pct, timestamp
    - Returns empty DataFrame on error
    - This will eventually replace yfinance for live pricing

  is_api_available() -> dict
    - Returns {"accounts": bool, "market": bool}
    - Used by app.py to decide whether to show the API source indicator
      or fall through to CSV upload

============================================================
3. scripts/schwab_initial_auth.py
============================================================

One-time browser OAuth setup. Run locally on Bill's machine, NOT on
Streamlit Cloud. Performs the initial auth for BOTH apps (accounts and
market data) and uploads both tokens to GCS.

Usage:
  python scripts/schwab_initial_auth.py

Flow:
  1. Print clear banner: "Schwab Initial Auth — One-Time Setup"
  2. Verify required secrets are present (both app keys, both secrets,
     bucket name, callback URL). If any missing, print which one and exit.
  3. Run schwab-py browser auth for the ACCOUNTS app:
     - Use schwab.auth.client_from_login_flow() pointed at a temp file
     - Browser opens to Schwab login → Bill logs in + 2FA → authorizes
     - Read the temp token file, upload to GCS as SCHWAB_TOKEN_BLOB_ACCOUNTS
     - Delete the temp file
  4. Call client.get_account_numbers() to retrieve account hashes
  5. Print all account hashes returned and prompt:
     "Copy the account hash for your PRIMARY INVESTMENT ACCOUNT (the
     ~$480K account, NOT the ~$12.5K reserve account ...8895) and paste
     it into secrets.toml as schwab_account_hash"
  6. Run schwab-py browser auth for the MARKET DATA app (same flow,
     separate temp file, separate GCS blob)
  7. Verify both tokens are readable from GCS
  8. Print success summary:
     "✅ Both tokens stored in GCS.
      Next: deploy the Cloud Function keep-alive (see P5-S-B).
      You should not need to run this script again unless a token dies."

Error handling:
  - Missing secrets → print which one and exit cleanly
  - Browser auth timeout → print recovery instructions
  - GCS upload failure → print the GCS error and exit
  - get_account_numbers failure → print error but don't fail (the token
    is already saved; user can re-fetch the hash later)

NEVER log token contents. Only log "uploaded {blob_name} to GCS".

============================================================
4. scripts/schwab_manual_reauth.py
============================================================

Emergency recovery script. Use only if a token has died (offline > 7 days,
password changed, etc.). Same flow as initial_auth.py but:
  - Explicitly deletes existing tokens from GCS before re-auth
  - After auth, calls fetch_positions() to verify connectivity
  - Prints position count as confirmation
  - Calls clear_alert() to clear any standing alert banner
```

---

## P5-S-B: Cloud Function Token Keep-Alive

**🤖 Claude Code Prompt:**

```
Build the Cloud Function that keeps both Schwab refresh tokens alive.

============================================================
Directory: cloud_functions/token_refresh/
============================================================

Files to create:
  cloud_functions/token_refresh/main.py
  cloud_functions/token_refresh/requirements.txt
  cloud_functions/token_refresh/deploy.sh

============================================================
1. cloud_functions/token_refresh/main.py
============================================================

SAFETY PREAMBLE — paste at the top of main.py:

  '''
  SAFETY: This Cloud Function ONLY refreshes OAuth tokens.
  It does NOT and MUST NOT place orders or modify account state.

  The only Schwab API call made is get_account_numbers() — a read-only
  call used to trigger schwab-py's automatic token refresh mechanism.

  PROHIBITED imports: any module containing "order", "trade", "place"
  Code review checkpoint: grep main.py for those terms — only this
  docstring should match.
  '''

Entry point:

  def refresh_token(request) -> tuple[str, int]:
      '''
      Cloud Function triggered by Cloud Scheduler every 25 minutes, 24/7.
      Refreshes both Schwab access tokens (accounts app + market data app)
      to keep their refresh tokens alive within the 7-day window.
      '''
      results = []
      for app_label, app_key_env, app_secret_env, blob_name in [
          ("accounts", "SCHWAB_ACCOUNTS_APP_KEY", "SCHWAB_ACCOUNTS_APP_SECRET", "token_accounts.json"),
          ("market",   "SCHWAB_MARKET_APP_KEY",   "SCHWAB_MARKET_APP_SECRET",   "token_market.json"),
      ]:
          result = _refresh_one(app_label, app_key_env, app_secret_env, blob_name)
          results.append(result)

      if all(r["status"] == "ok" for r in results):
          _clear_alert()  # success after a failure clears the banner
          return (json.dumps({"status": "ok", "results": results}), 200)
      else:
          # Track consecutive failures for Gmail escalation
          fail_count = _increment_failure_counter()
          if fail_count >= 2:
              _send_gmail_alert(results, fail_count)
          return (json.dumps({"status": "error", "results": results}), 500)

  def _refresh_one(app_label, app_key_env, app_secret_env, blob_name) -> dict:
      '''
      Refresh a single Schwab app's token.
      '''
      Flow:
        a. Load token from GCS bucket (env var TOKEN_BUCKET)
        b. If token age < 20 minutes, return early {"status": "ok", "skipped": True}
           to avoid hammering Schwab on overlapping scheduler runs
        c. Build a schwab-py client using client_from_access_functions()
           with load/save callbacks that operate on a local temp file
           (Cloud Function tmpfs)
        d. Make a lightweight API call: client.get_account_numbers()
           This triggers schwab-py's auto-refresh
        e. Read the updated token back from the temp file
        f. Save refreshed token to GCS via the same blob name
        g. Log success with token age (NEVER log token contents)
        h. Return {"status": "ok", "app": app_label, "age_seconds": ...}

      Error handling:
        - Token blob not found in GCS:
          → _write_alert(f"{app_label} token missing — run initial auth", "critical")
          → return {"status": "error", "app": app_label, "reason": "missing"}
        - Schwab returns invalid_client (refresh token expired):
          → _write_alert(f"{app_label} refresh token expired — run manual reauth", "critical")
          → return {"status": "error", "app": app_label, "reason": "expired"}
        - Network timeout / 5xx from Schwab:
          → log warning, return {"status": "error", "app": app_label, "reason": "transient"}
          → (Scheduler will retry on next 25-min cycle)
        - Any other exception:
          → _write_alert(f"{app_label} refresh failed: {e}", "warning")
          → return {"status": "error", "app": app_label, "reason": str(e)}

============================================================
Helper functions in main.py
============================================================

  _write_alert(message, severity):
      Writes alert.json to GCS bucket. Same schema as
      utils/schwab_token_store.write_alert() in the main app.
      Payload: {timestamp, severity, message, resolved: false}

  _clear_alert():
      Deletes alert.json from GCS if present.

  _increment_failure_counter() -> int:
      Reads gs://{bucket}/refresh_failure_count.json (or creates it),
      increments count, writes back, returns new count.
      Resets to 0 on successful refresh (handled in main flow).

  _reset_failure_counter():
      Sets failure count back to 0.

  _send_gmail_alert(results, fail_count):
      '''
      Fires a Gmail alert ONLY after 2+ consecutive failures (~50 min)
      to avoid spamming on transient hiccups.
      '''
      - Uses google-api-python-client + the same GCP service account
      - Subject: "[Portfolio Manager] Schwab token refresh failing ({fail_count}x)"
      - Body: human-readable summary of which apps failed and why,
        with the recovery command:
          "If 'expired': run python scripts/schwab_manual_reauth.py
           If 'missing': run python scripts/schwab_initial_auth.py"
      - Recipient comes from env var ALERT_EMAIL_TO
      - On Gmail send failure, log but do not crash (alert.json still
        works as a fallback)

============================================================
2. cloud_functions/token_refresh/requirements.txt
============================================================

  schwab-py>=1.5
  httpx>=0.27
  google-cloud-storage>=2.18
  google-api-python-client>=2.140
  google-auth>=2.34
  functions-framework>=3.8

============================================================
3. cloud_functions/token_refresh/deploy.sh
============================================================

  #!/bin/bash
  # Deploy the Schwab token refresh Cloud Function.
  # Run from repo root: bash cloud_functions/token_refresh/deploy.sh
  set -euo pipefail

  PROJECT="re-property-manager-487122"
  REGION="us-central1"
  FUNCTION_NAME="schwab-token-refresh"
  SERVICE_ACCOUNT="propertymanager@re-property-manager-487122.iam.gserviceaccount.com"

  echo "Deploying $FUNCTION_NAME to $PROJECT/$REGION..."

  gcloud functions deploy $FUNCTION_NAME \
    --gen2 \
    --runtime python311 \
    --trigger-http \
    --entry-point refresh_token \
    --memory 256MB \
    --timeout 60s \
    --project $PROJECT \
    --region $REGION \
    --source cloud_functions/token_refresh/ \
    --service-account $SERVICE_ACCOUNT \
    --no-allow-unauthenticated \
    --set-env-vars "TOKEN_BUCKET=portfolio-manager-tokens"

  echo ""
  echo "⚠️  Set the Schwab credentials and alert email as env vars (not committed):"
  echo ""
  echo "  gcloud functions deploy $FUNCTION_NAME \\"
  echo "    --gen2 --region $REGION --project $PROJECT \\"
  echo "    --update-env-vars SCHWAB_ACCOUNTS_APP_KEY=xxx,SCHWAB_ACCOUNTS_APP_SECRET=xxx,SCHWAB_MARKET_APP_KEY=xxx,SCHWAB_MARKET_APP_SECRET=xxx,ALERT_EMAIL_TO=bill@example.com"
  echo ""
  echo "Then create the Cloud Scheduler job (24/7, every 25 min):"
  echo ""
  echo "  FUNCTION_URL=\$(gcloud functions describe $FUNCTION_NAME --gen2 --region $REGION --project $PROJECT --format='value(serviceConfig.uri)')"
  echo ""
  echo "  gcloud scheduler jobs create http schwab-token-keepalive \\"
  echo "    --schedule='*/25 * * * *' \\"
  echo "    --time-zone='America/New_York' \\"
  echo "    --uri=\"\$FUNCTION_URL\" \\"
  echo "    --http-method=POST \\"
  echo "    --oidc-service-account-email=$SERVICE_ACCOUNT \\"
  echo "    --project $PROJECT \\"
  echo "    --location $REGION"

DO NOT bake the Schwab keys into deploy.sh — they go in via the
--update-env-vars step printed at the end so they never hit git.

============================================================
Authentication note (do not pass JSON keys to the Cloud Function)
============================================================

The Cloud Function inherits IAM permissions via Application Default
Credentials (ADC) because deploy.sh attaches the service account with
--service-account=propertymanager@re-property-manager-487122.iam.gserviceaccount.com.

This means:
  - google-cloud-storage automatically authenticates as that service
    account when the function runs in GCP — no key file needed
  - google-api-python-client (for Gmail) does the same
  - DO NOT load a JSON service account key file from disk
  - DO NOT pass credentials= to any client constructor unless ADC fails
  - DO NOT mount or upload any service account key as part of the
    Cloud Function source

If you find yourself writing `service_account.Credentials.from_service_account_file(...)`
or `from_service_account_info(...)` inside the Cloud Function, stop —
that's the wrong pattern for in-GCP execution. Use the no-argument
client constructor: `storage.Client()` and let ADC handle it.
```

---

## P5-S-C: Wire Schwab API into `app.py` as Primary Source

**🤖 Claude Code Prompt:**

```
Read app.py to understand how the CSV upload sidebar currently works.
Read utils/schwab_client.py (built in P5-S-A).

============================================================
CRITICAL ARCHITECTURE CONSTRAINT — read this before writing any code
============================================================

The dashboard UI is encapsulated inside a `main_dashboard()` function
(or a dedicated sidebar rendering function — find it before you start).
This is intentional: it prevents global scope leakage where UI elements
bleed across sub-pages registered via st.navigation.

ALL new code from this prompt — sidebar widgets, the data source radio,
the Schwab fetch logic, the manual refresh button, the quote enrichment
block — MUST live INSIDE main_dashboard() (or whichever function owns
the dashboard page).

DO NOT add any st.sidebar.*, st.spinner, st.error, st.button, st.radio,
or st.success calls at the module-level global scope of app.py. If you
find yourself writing one outside a function body, stop and put it in
the right function.

The only module-level additions allowed are imports
(import utils.schwab_client as schwab_client, etc.).

============================================================

Modify app.py to add Schwab API as the primary data source, with CSV
upload as a fallback. Do NOT remove or break the CSV path — it stays
as the explicit fallback for the case where the API is unavailable.

============================================================
Sidebar — new Data Source section (place ABOVE the existing CSV uploader)
============================================================

Add a new sidebar section: "Data Source"

  api_status = schwab_client.is_api_available()
  alert = schwab_token_store.read_alert()

  if alert:
      st.sidebar.error(f"⚠️ Schwab API: {alert['message']}")
      st.sidebar.caption("Falling back to CSV upload below.")

  if api_status["accounts"]:
      st.sidebar.success("✅ Schwab API connected (Accounts)")
  else:
      st.sidebar.warning("⚪ Schwab API offline (Accounts)")

  if api_status["market"]:
      st.sidebar.success("✅ Schwab API connected (Market Data)")
  else:
      st.sidebar.warning("⚪ Schwab API offline (Market Data)")

  source_options = []
  if api_status["accounts"]:
      source_options.append("Schwab API (live)")
  source_options.append("CSV Upload (manual)")

  data_source = st.sidebar.radio(
      "Choose data source",
      source_options,
      index=0,
      help="Schwab API pulls live positions automatically. CSV upload is the manual fallback."
  )

============================================================
Main flow — branching on data source
============================================================

  if data_source == "Schwab API (live)":
      with st.spinner("Fetching positions from Schwab API..."):
          client = schwab_client.get_accounts_client()
          if client is None:
              st.error("Could not initialize Schwab client. Check the alert above or use CSV upload.")
              st.stop()

          raw_positions = schwab_client.fetch_positions(client)
          if raw_positions.empty:
              st.error("Schwab API returned no positions. Check the alert above or use CSV upload.")
              st.stop()

          positions_df = pipeline.normalize_positions(raw_positions, source="schwab_api")
          st.success(f"✅ Fetched {len(positions_df)} positions from Schwab API")

  else:  # CSV Upload (existing path — leave unchanged)
      uploaded_file = st.sidebar.file_uploader("Upload Schwab Positions CSV", type=["csv"])
      if uploaded_file is None:
          st.info("Upload a Schwab positions CSV to begin.")
          st.stop()
      raw_positions = csv_parser.parse_schwab_csv(uploaded_file)
      positions_df = pipeline.normalize_positions(raw_positions, source="csv")

============================================================
pipeline.normalize_positions — add the source parameter
============================================================

Modify pipeline.normalize_positions() to accept a `source` keyword
("schwab_api" or "csv") and pass it through to any logging or audit
trail. The actual normalization logic should be source-agnostic — both
inputs must produce the same output schema (POSITION_COLUMNS from
config.py).

If the function does not currently exist with that signature, refactor
it so the post-normalization DataFrame is identical regardless of
source. The downstream code (Sheet writer, dashboards, risk metrics)
must not need to know which source the data came from.

============================================================
REFACTOR DISCIPLINE — read before touching pipeline.py
============================================================

pipeline.py contains tightly coupled functions including (but not
limited to) sanitize_dataframe_for_sheets, write_to_sheets, fingerprint
generation, weight calculations, and Unrealized G/L math. Surgical
text-replacement during refactoring has previously caused omission
errors that silently delete neighboring functions or strip logic out
of the function being modified.

Hard requirements:

  1. Before editing, READ pipeline.py end-to-end and list every
     function defined in it. Confirm normalize_positions can be found
     and identify its exact start and end lines.

  2. When you modify normalize_positions, you MUST return the FULL,
     COMPLETE replacement for that function. Do not use partial diffs.
     Do not omit any existing logic — including but not limited to:
       - weight calculations (Weight column = market_value / total)
       - Unrealized G/L math (both $ and %)
       - Unit Cost derivation
       - Fingerprint generation
       - Cash ticker filtering
       - Any sanitization or type coercion already present
     Every line of existing logic must appear in the new version
     unless you are explicitly removing it for a documented reason.

  3. Do NOT touch any other function in pipeline.py. Specifically, do
     NOT modify, rewrite, or "clean up" sanitize_dataframe_for_sheets
     or write_to_sheets while you're in the file. Hands off.

  4. After editing, verify by re-reading pipeline.py and confirming:
       - Every function from the pre-edit list is still present
       - normalize_positions has the new `source` parameter
       - No other function's signature has changed

  5. If you cannot complete the refactor without touching other
     functions, STOP and report the conflict instead of guessing.

============================================================
Manual refresh button
============================================================

Add a button below the data source radio:

  if st.sidebar.button("🔄 Refresh from Schwab API"):
      st.cache_resource.clear()  # bust the schwab client cache
      st.cache_data.clear()      # bust any data caches
      st.rerun()

============================================================
Quote enrichment (optional, only if api_status["market"] is True)
============================================================

After positions are loaded, if the market data API is available,
enrich live prices using fetch_quotes() instead of yfinance:

  if api_status["market"] and data_source == "Schwab API (live)":
      market_client = schwab_client.get_market_client()
      if market_client:
          tickers = positions_df["Ticker"].tolist()
          quotes = schwab_client.fetch_quotes(market_client, tickers)
          # Merge quotes into positions_df, overwriting Price column
          # Leave yfinance enrichment in place as a fallback for any
          # tickers that fail to return a quote

DRY_RUN must still gate all Sheet writes — do not bypass it on the
API path. The flag's existing behavior is unchanged.
```

---

## P5-S-D: Update Docs, Config, and Changelog

**🤖 Claude Code Prompt:**

```
Update the following files to document the Schwab API integration.

============================================================
1. CLAUDE.md — add a new section under "Critical Infrastructure"
============================================================

  ### Schwab API Integration (Phase 5-S)

  - Two Schwab apps: Accounts and Trading + Market Data
  - Each app has its own OAuth token, stored in
    gs://portfolio-manager-tokens/{token_accounts.json, token_market.json}
  - Token refresh handled by Cloud Function `schwab-token-refresh`
    on a 24/7 every-25-minute Cloud Scheduler trigger
  - Streamlit app uses two scoped clients:
      - utils/schwab_client.get_accounts_client()  → positions, balances, transactions
      - utils/schwab_client.get_market_client()    → quotes, price history
  - CSV upload remains as the explicit fallback path
  - PROHIBITED endpoints (never imported anywhere):
      place_order, replace_order, cancel_order,
      get_orders_for_account, get_orders_for_all_linked_accounts
  - Recovery procedures:
      - Token expired (offline > 7 days): python scripts/schwab_manual_reauth.py
      - Token missing (first setup or wiped): python scripts/schwab_initial_auth.py
  - Alert channels:
      - alert.json in GCS → banner in Streamlit app sidebar
      - Gmail (after 2+ consecutive Cloud Function failures, ~50 min)

  Repo additions:
    utils/schwab_client.py
    utils/schwab_token_store.py
    scripts/schwab_initial_auth.py
    scripts/schwab_manual_reauth.py
    cloud_functions/token_refresh/main.py
    cloud_functions/token_refresh/requirements.txt
    cloud_functions/token_refresh/deploy.sh

============================================================
2. CHANGELOG.md — add a new entry at the top
============================================================

  ## [TODAY'S DATE] — Phase 5-S: Schwab API Integration

  ### feat: Automated position, transaction, and quote pulls via Schwab API

  **What changed:**
  - utils/schwab_client.py — read-only Schwab API client (positions,
    balances, transactions, quotes); two scoped factory functions for
    the Accounts and Market Data apps
  - utils/schwab_token_store.py — GCS-backed OAuth token persistence
    plus alert read/write/clear helpers
  - cloud_functions/token_refresh/ — Cloud Function keep-alive that
    refreshes both tokens every 25 min, 24/7; Gmail escalation after
    2+ consecutive failures
  - scripts/schwab_initial_auth.py — one-time browser OAuth setup for
    both apps; uploads tokens to GCS and prints account hashes
  - scripts/schwab_manual_reauth.py — emergency token recovery
  - app.py sidebar — Schwab API as the primary data source with CSV
    upload as the explicit fallback; manual refresh button included

  **Architecture:**
  - Two Schwab apps, two GCS-stored tokens, one keep-alive Cloud Function
  - Market Data client physically cannot reach account endpoints (separate
    app key, separate token, separate client object)
  - DRY_RUN safety gate unchanged — still gates all Sheet writes
  - Graceful degradation to CSV on any Schwab API failure

  **Status:** [FILL IN AFTER TESTING]

============================================================
3. PORTFOLIO_SHEET_SCHEMA.md — add a "Source" annotation
============================================================

Add a one-liner to the Holdings_Current section noting that the
'Source' may be either 'schwab_api' or 'csv', and that the schema
is identical regardless of source.

============================================================
4. lessonsLearned.md — append
============================================================

  ## Phase 5-S Lessons

  - **Two Schwab apps, two tokens, one auth flow per app** — each Schwab
    app gets its own App Key/Secret and its own OAuth token. They share
    the same browser login but generate independent refresh tokens.
    Storing them in separate GCS blobs gives the Market Data client a
    physical inability to reach account endpoints.

  - **Refresh token 7-day expiry is the real constraint** — the access
    token lasts 30 minutes (auto-refreshed by schwab-py), but the
    refresh token dies in 7 days unless something keeps it warm. The
    Cloud Function exists solely to make sure that "something" is
    automated and reliable.

  - **Cloud Function on 24/7 schedule, not market hours** — saves nothing
    in dollars (free tier) and removes a class of weekend edge cases
    against the 7-day window.

  - **Two-failure threshold for Gmail alerts** — single transient
    failures get caught by the next 25-minute cycle without notification.
    Two consecutive failures (~50 min of trouble) means it's a real
    problem worth pinging about.

  - **Never log token contents** — only log blob names and success/fail.
    Token files are gitignored AND never written to stdout/stderr.
```

---

## P5-S-E: Smoke Test + Gemini Peer Review

### Smoke test prompt (Claude Code)

```
Add to smoke_test.py a new section: "Schwab API Integration Smoke Tests"

Tests to add (each isolated, each can be skipped if API is unavailable):

  test_token_store_round_trip():
    - Write a dummy token dict to GCS
    - Read it back
    - Assert equality
    - Delete the dummy blob
    - PASS if all four steps succeed

  test_alert_round_trip():
    - write_alert("test message", "warning")
    - assert read_alert()["message"] == "test message"
    - clear_alert()
    - assert read_alert() is None

  test_accounts_client_initializes():
    - client = get_accounts_client()
    - skip if client is None (no token yet)
    - PASS if client object is created without error

  test_market_client_initializes():
    - same pattern with get_market_client()

  test_fetch_positions_returns_valid_schema():
    - skip if accounts client unavailable
    - df = fetch_positions(client)
    - assert all POSITION_COLUMNS are present in df.columns
    - assert df is not empty (or print warning if account is empty)

  test_no_order_imports():
    - Read utils/schwab_client.py as text
    - Assert that no line outside the safety preamble docstring contains
      "place_order", "cancel_order", "replace_order", or "get_orders"
    - This is the mechanical version of the code review checkpoint

  test_dry_run_still_active():
    - Read pipeline.py / config.py
    - Confirm DRY_RUN gate is still in place on sheet writes
```

### Gemini CLI peer review prompt

```
Review the Schwab API integration files for safety, correctness, and
adherence to the project's architecture rules:

  utils/schwab_client.py
  utils/schwab_token_store.py
  cloud_functions/token_refresh/main.py
  scripts/schwab_initial_auth.py
  scripts/schwab_manual_reauth.py
  app.py (the modified sidebar and main flow only)

Check for:

  CRITICAL — fail the review if any of these are violated:
  - Any import or call to order/trading endpoints
    (place_order, replace_order, cancel_order, get_orders_*)
  - Any token contents printed, logged, or written to a non-token file
  - Any hardcoded GCP project ID, bucket name, or service account email
    that should come from config.py
  - Any bypass of the DRY_RUN gate
  - Any path that lets the Market Data client reach account endpoints
  - Schwab keys committed to deploy.sh or any other file in git

  WARNING:
  - Functions that raise to the caller instead of returning empty
    DataFrames / None / False (the project pattern is graceful degradation)
  - Missing @st.cache_resource on the client factory functions
  - fetch_positions() output that does not match POSITION_COLUMNS exactly
  - Missing fingerprint on positions or transactions (breaks dedup)
  - Cloud Function that does not handle "token age < 20 min" early-exit
    (will hammer Schwab on overlapping scheduler runs)

  INFO:
  - Opportunities to share code between schwab_client.py and the Cloud
    Function without coupling them
  - Places where yfinance could be replaced by Schwab quotes once the
    market data client is proven stable

For each finding, output: SEVERITY, FILE:LINE, ISSUE, SUGGESTED FIX.
```

---

## Execution order

| Step | What | Where | Time |
|---|---|---|---|
| 0 | Add config + secrets + requirements + gitignore changes | Hand edit | 5 min |
| 1 | Run prompt **P5-S-A** | Claude Code | ~10 min |
| 2 | Run `python scripts/schwab_initial_auth.py` locally | Your machine | ~5 min |
| 3 | Paste `schwab_account_hash` into `secrets.toml` | Hand edit | 1 min |
| 4 | Run prompt **P5-S-B** | Claude Code | ~10 min |
| 5 | Run `bash cloud_functions/token_refresh/deploy.sh` then the two follow-up commands it prints | Cloud Shell | ~5 min |
| 6 | Run prompt **P5-S-C** | Claude Code | ~10 min |
| 7 | Run prompt **P5-S-D** | Claude Code | ~5 min |
| 8 | Run prompt **P5-S-E** smoke test additions | Claude Code | ~5 min |
| 9 | Run `python smoke_test.py` and the Gemini peer review | Local + Gemini CLI | ~10 min |
| 10 | Open Streamlit app, click "Schwab API (live)" radio, verify positions load | Streamlit | ~5 min |

Total elapsed: ~70 minutes if nothing goes sideways.

---

## Recovery procedures

| Symptom | Cause | Fix |
|---|---|---|
| Banner: "accounts token missing" | First-time setup, or token wiped | `python scripts/schwab_initial_auth.py` |
| Banner: "refresh token expired" | Cloud Function offline > 7 days | `python scripts/schwab_manual_reauth.py` |
| Banner: "refresh failed: ..." (transient) | Schwab API hiccup | Wait 25 min — next scheduler run will retry |
| Gmail alert: "failing 2x" | Two consecutive failures | Check Cloud Function logs in GCP console |
| Account hash returns empty positions | Wrong hash in secrets (e.g., reserve account ...8895) | Re-run initial_auth, pick the primary investment account hash |
| `is_api_available()` always False | Service account missing GCS read on bucket | `gsutil iam ch serviceAccount:propertymanager@re-property-manager-487122.iam.gserviceaccount.com:objectAdmin gs://portfolio-manager-tokens` |

---

## FAQ

**Q: What happens if Streamlit Cloud restarts the app?**
A: Nothing breaks. The client factories re-read the token from GCS on first call and `@st.cache_resource` rebuilds the client object. The Cloud Function keeps the token fresh independently.

**Q: Can the Cloud Function accidentally place trades?**
A: No. It only calls `get_account_numbers()` to trigger schwab-py's auto-refresh. No trading modules are imported. The safety preamble at the top of `main.py` is enforced by the smoke test grep check.

**Q: Why two apps instead of one?**
A: Schwab issues separate App Keys for Accounts/Trading and Market Data. Storing them as separate clients with separate tokens means the Market Data client physically cannot reach account endpoints — a defense-in-depth layer on top of the "no order imports" rule.

**Q: How much does this cost?**
A: $0/month. Cloud Function free tier covers ~2 million invocations; you'll use ~57,000/month. Cloud Storage cost on a < 1 KB token file is rounding error. Cloud Scheduler gives 3 free jobs.

**Q: What if I want to add the reserve account ...8895 later?**
A: It's a separate Schwab account hash under the same login, so the same Accounts token works. Add a second `SCHWAB_RESERVE_ACCOUNT_HASH` to config and a parallel `fetch_positions(client, account_hash=...)` call. But the RE Property Manager already tracks that account, so probably not worth it.

**Q: Can I run the initial auth script from Cloud Shell instead of locally?**
A: No — it opens a browser for the OAuth callback. Has to run on a machine where you can complete the Schwab login + 2FA in a browser that can hit `https://127.0.0.1`.
