#!/usr/bin/env bash
set -euo pipefail

# Configure these before running against your GCP project
PROJECT_ID="${PROJECT_ID:-your-gcp-project-id}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-novamart-ai-archetypes}"
AUTHOR_PASSCODE="${AUTHOR_PASSCODE:-change-me-before-public-deploy}"

echo "Deploying ${SERVICE_NAME} to Google Cloud Run (${PROJECT_ID} / ${REGION})..."

gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars "AUTHOR_PASSCODE=${AUTHOR_PASSCODE},DAILY_LIVE_BUDGET_USD=2.00"

# Recommended for production live runs: bind your keys from GCP Secret Manager instead of plain env vars:
# gcloud run services update "${SERVICE_NAME}" \
#   --project "${PROJECT_ID}" \
#   --region "${REGION}" \
#   --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest"
