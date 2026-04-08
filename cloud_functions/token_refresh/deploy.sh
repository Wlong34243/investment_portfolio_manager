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
