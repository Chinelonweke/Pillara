#!/usr/bin/env bash
# deploy.sh
# Deploys a PREBUILT Pillara image on this server. Never builds on the server.
#
# Usage:   bash deploy.sh <staging|production> <image_tag>
# Example: bash deploy.sh production 9165c77f3a...
#
# Normally called by .github/workflows/deploy.yml over SSH, AFTER the workflow
# has checked out the exact commit being deployed (so compose files, nginx.conf
# and scripts match the image). You can also run it by hand to redeploy or to
# roll back to any tag that was previously built.
#
# What it does:
#   1. Pulls the prebuilt api/worker image from GHCR
#   2. Runs Alembic migrations
#   3. Starts/updates all services (infra is left alone if unchanged)
#   4. Health-checks the API
#   5. On failure, rolls back to the previously deployed tag
#
# NOTE ON ROLLBACK: only the app image is rolled back. Database migrations are
# NOT reversed. Write migrations that are backward-compatible (add columns,
# don't rename/drop in the same release) so the old image still works.

set -euo pipefail

# ─── ARGUMENTS ────────────────────────────────────────────────────────────────
DEPLOY_ENV="${1:?Usage: bash deploy.sh <staging|production> <image_tag>}"
IMAGE_TAG="${2:?Usage: bash deploy.sh <staging|production> <image_tag>}"

case "$DEPLOY_ENV" in
  staging|production) ;;
  *) echo "❌ First argument must be 'staging' or 'production', got '$DEPLOY_ENV'"; exit 1 ;;
esac

# ─── CONFIG ───────────────────────────────────────────────────────────────────
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # wherever the repo is cloned
ENV_FILE="$APP_DIR/.env.$DEPLOY_ENV"                     # .env.staging / .env.production
TAG_FILE="$APP_DIR/.deployed_tag.$DEPLOY_ENV"            # remembers the last good tag
MAX_HEALTH_RETRIES=30
HEALTH_RETRY_INTERVAL=5

cd "$APP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ Missing $ENV_FILE — create it from .env.$DEPLOY_ENV.example first."
  exit 1
fi

# API host port: 8000 by default. Only set API_PORT in the env file if two
# environments share one server (e.g. staging on 8001).
API_PORT="$(grep -E '^API_PORT=' "$ENV_FILE" | cut -d= -f2 || true)"
API_PORT="${API_PORT:-8000}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/health"

# -p gives each environment its own containers, network and volumes.
# --env-file supplies values for ${...} in the compose files (e.g. GRAFANA_PASSWORD).
COMPOSE=(docker compose
  -p "pillara-$DEPLOY_ENV"
  --env-file "$ENV_FILE"
  -f docker-compose.yml
  -f docker-compose.prod.yml)

# Compose reads these from the shell to fill ${DEPLOY_ENV} and ${IMAGE_TAG}.
export DEPLOY_ENV IMAGE_TAG

PREVIOUS_TAG="$(cat "$TAG_FILE" 2>/dev/null || true)"

echo "====================================="
echo "  Pillara deploy — $DEPLOY_ENV — $(date)"
echo "  New tag:      $IMAGE_TAG"
echo "  Previous tag: ${PREVIOUS_TAG:-none (first deploy)}"
echo "====================================="

# ─── HELPERS ──────────────────────────────────────────────────────────────────
wait_until_healthy() {
  local retries=0
  until curl -sf "$HEALTH_URL" > /dev/null 2>&1; do
    retries=$((retries + 1))
    if [ "$retries" -ge "$MAX_HEALTH_RETRIES" ]; then
      return 1
    fi
    echo "   Waiting for API... ($retries/$MAX_HEALTH_RETRIES)"
    sleep "$HEALTH_RETRY_INTERVAL"
  done
  return 0
}

# ─── STEP 1: Pull the prebuilt image ──────────────────────────────────────────
echo ""
echo "→ Pulling image $IMAGE_TAG..."
"${COMPOSE[@]}" pull api worker
echo "✅ Image pulled"

# ─── STEP 2: Run database migrations ──────────────────────────────────────────
echo ""
echo "→ Running Alembic migrations..."
"${COMPOSE[@]}" run --rm api alembic upgrade head
echo "✅ Migrations complete"

# ─── STEP 3: Start / update services ──────────────────────────────────────────
# Only services whose config or image changed are recreated (api, worker).
# Redis, ChromaDB, Prometheus and Grafana keep running untouched.
echo ""
echo "→ Starting services..."
"${COMPOSE[@]}" up -d --remove-orphans
echo "✅ Services started"

# ─── STEP 4: Health check (with real rollback) ────────────────────────────────
echo ""
echo "→ Checking API health at $HEALTH_URL..."
if ! wait_until_healthy; then
  echo ""
  echo "❌ API not healthy after $((MAX_HEALTH_RETRIES * HEALTH_RETRY_INTERVAL))s"
  echo "--- Last 50 lines of api logs ---"
  "${COMPOSE[@]}" logs api --tail=50 || true

  if [ -n "$PREVIOUS_TAG" ]; then
    echo ""
    echo "→ Rolling back to $PREVIOUS_TAG..."
    export IMAGE_TAG="$PREVIOUS_TAG"
    "${COMPOSE[@]}" pull api worker
    "${COMPOSE[@]}" up -d --no-deps api worker
    if wait_until_healthy; then
      echo "⚠️  Rolled back to $PREVIOUS_TAG — the service is up, but this deploy FAILED."
    else
      echo "🚨 Rollback ALSO unhealthy — manual intervention needed."
    fi
  else
    echo "🚨 No previous tag to roll back to (first deploy)."
  fi
  exit 1
fi

echo "$IMAGE_TAG" > "$TAG_FILE"
echo "✅ API is healthy — recorded $IMAGE_TAG as the current tag"

# ─── STEP 5: Clean up old images ──────────────────────────────────────────────
# Keeps a week of images locally; older tags can always be re-pulled from GHCR.
echo ""
echo "→ Cleaning up old Docker images..."
docker image prune -af --filter "until=168h" > /dev/null
echo "✅ Cleanup done"

echo ""
echo "====================================="
echo "  ✅ $DEPLOY_ENV deploy complete — $(date)"
echo "====================================="
"${COMPOSE[@]}" ps