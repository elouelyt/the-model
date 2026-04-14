#!/usr/bin/env bash
# push_secrets.sh
#
# Run this ONCE on the machine that has your local .env and service account JSON.
# Pushes all project secrets to GCP Secret Manager so any machine can pull them.
#
# Usage:
#   chmod +x scripts/push_secrets.sh
#   ./scripts/push_secrets.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - GCP project set (gcloud config set project YOUR_PROJECT_ID)
#   - Secret Manager API enabled (gcloud services enable secretmanager.googleapis.com)

set -euo pipefail

ENV_FILE=".env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Tennis AI Platform — Push Secrets to GCP Secret Manager ==="
echo ""

# --- Load .env ---
if [[ ! -f "$PROJECT_ROOT/$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found at $PROJECT_ROOT/$ENV_FILE"
  echo "       Make sure you run this script from the machine that has the .env file."
  exit 1
fi

source "$PROJECT_ROOT/$ENV_FILE"

# --- Helper: create or update a secret ---
push_secret() {
  local name="$1"
  local value="$2"

  if [[ -z "$value" ]]; then
    echo "  SKIP   $name (empty value)"
    return
  fi

  if gcloud secrets describe "$name" &>/dev/null; then
    echo "  UPDATE $name"
    echo -n "$value" | gcloud secrets versions add "$name" --data-file=-
  else
    echo "  CREATE $name"
    echo -n "$value" | gcloud secrets create "$name" --data-file=- --replication-policy="automatic"
  fi
}

# --- Push API keys ---
echo "--- Pushing API keys ---"
push_secret "THE_ODDS_API_KEY"  "${THE_ODDS_API_KEY:-}"
push_secret "GEMINI_API_KEY"    "${GEMINI_API_KEY:-}"

# --- Push service account JSON (file content, not path) ---
echo ""
echo "--- Pushing service account JSON ---"
if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -f "$GOOGLE_APPLICATION_CREDENTIALS" ]]; then
  if gcloud secrets describe "GCP_SERVICE_ACCOUNT_JSON" &>/dev/null; then
    echo "  UPDATE GCP_SERVICE_ACCOUNT_JSON"
    gcloud secrets versions add "GCP_SERVICE_ACCOUNT_JSON" --data-file="$GOOGLE_APPLICATION_CREDENTIALS"
  else
    echo "  CREATE GCP_SERVICE_ACCOUNT_JSON"
    gcloud secrets create "GCP_SERVICE_ACCOUNT_JSON" \
      --data-file="$GOOGLE_APPLICATION_CREDENTIALS" \
      --replication-policy="automatic"
  fi
else
  echo "  SKIP   GCP_SERVICE_ACCOUNT_JSON (GOOGLE_APPLICATION_CREDENTIALS not set or file not found)"
fi

echo ""
echo "=== Done! All secrets pushed to GCP Secret Manager. ==="
echo "    On a new machine, run: ./scripts/setup_env.sh"
