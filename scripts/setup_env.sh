#!/usr/bin/env bash
# setup_env.sh
#
# Run this on any NEW machine after cloning the repo.
# Pulls all project secrets from GCP Secret Manager and writes them to .env.
# Also recreates the service account JSON file.
#
# Usage:
#   chmod +x scripts/setup_env.sh
#   ./scripts/setup_env.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - GCP project set (gcloud config set project YOUR_PROJECT_ID)
#   - Secrets already pushed from source machine (scripts/push_secrets.sh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
SA_KEY_PATH="$PROJECT_ROOT/service-account-key.json"

echo "=== Tennis AI Platform — Setup Environment from GCP Secret Manager ==="
echo ""

# --- Helper: fetch a secret value ---
fetch_secret() {
  local name="$1"
  gcloud secrets versions access latest --secret="$name" 2>/dev/null || echo ""
}

# --- Warn if .env already exists ---
if [[ -f "$ENV_FILE" ]]; then
  echo "WARNING: .env already exists. It will be overwritten."
  read -r -p "Continue? (y/N): " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

echo "--- Fetching secrets from GCP Secret Manager ---"

THE_ODDS_API_KEY=$(fetch_secret "THE_ODDS_API_KEY")
GEMINI_API_KEY=$(fetch_secret "GEMINI_API_KEY")

# --- Write .env ---
cat > "$ENV_FILE" <<EOF
# The-Odds-API credentials
THE_ODDS_API_KEY=${THE_ODDS_API_KEY}

# GCP — service account key path (local only)
GOOGLE_APPLICATION_CREDENTIALS=${SA_KEY_PATH}

# Gemini (Google AI Studio — free tier)
GEMINI_API_KEY=${GEMINI_API_KEY}
EOF

echo "  WRITTEN .env"

# --- Fetch and write service account JSON ---
echo ""
echo "--- Fetching service account JSON ---"
SA_JSON=$(fetch_secret "GCP_SERVICE_ACCOUNT_JSON")

if [[ -n "$SA_JSON" ]]; then
  echo "$SA_JSON" > "$SA_KEY_PATH"
  chmod 600 "$SA_KEY_PATH"
  echo "  WRITTEN $SA_KEY_PATH (permissions: 600)"
else
  echo "  SKIP    GCP_SERVICE_ACCOUNT_JSON not found in Secret Manager."
  echo "          Run: gcloud auth application-default login  (alternative for local dev)"
fi

# --- Install Python dependencies ---
echo ""
echo "--- Installing Python dependencies ---"
if [[ ! -d "$PROJECT_ROOT/.venv" ]]; then
  python3 -m venv "$PROJECT_ROOT/.venv"
  echo "  CREATED .venv"
fi
"$PROJECT_ROOT/.venv/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" --quiet
echo "  INSTALLED requirements.txt"

echo ""
echo "=== Setup complete! ==="
echo "    Activate your environment: source .venv/bin/activate"
echo "    Test the pipeline:         python src/ingestion/extract_odds.py"
