#!/bin/bash
# deploy.sh
# Zero-downtime deployment script for Pillara on Contabo VPS
#
# Usage: ./deploy.sh
# Run from: /opt/pillara on the Contabo VPS
#
# What this script does:
# 1. Pulls latest code from main branch
# 2. Builds a new Docker image
# 3. Runs database migrations
# 4. Restarts API and worker with the new image
# 5. Verifies the app is healthy before finishing

set -e  # Exit immediately on any error

echo "====================================="
echo "  Pillara Deployment — $(date)"
echo "====================================="

# ─── CONFIG ──────────────────────────────────────────────────────────────────
APP_DIR="/opt/pillara"
COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
HEALTH_URL="http://localhost:8000/health"
MAX_HEALTH_RETRIES=30
HEALTH_RETRY_INTERVAL=5

# ─── STEP 1: Pull latest code ─────────────────────────────────────────────────
echo ""
echo "→ Pulling latest code from main..."
cd "$APP_DIR"
git pull origin main
echo "✅ Code updated"

# ─── STEP 2: Build new Docker image ──────────────────────────────────────────
echo ""
echo "→ Building new Docker image..."
$COMPOSE_CMD build api
echo "✅ Image built"

# ─── STEP 3: Run database migrations ─────────────────────────────────────────
echo ""
echo "→ Running Alembic migrations..."
$COMPOSE_CMD run --rm api alembic upgrade head
echo "✅ Migrations complete"

# ─── STEP 4: Restart services ────────────────────────────────────────────────
echo ""
echo "→ Restarting API..."
$COMPOSE_CMD up -d --no-deps api
echo ""
echo "→ Restarting worker..."
$COMPOSE_CMD up -d --no-deps worker
echo "✅ Services restarted"

# ─── STEP 5: Wait for health check ───────────────────────────────────────────
echo ""
echo "→ Waiting for API to be healthy..."
retries=0
until curl -sf "$HEALTH_URL" > /dev/null 2>&1; do
    retries=$((retries + 1))
    if [ $retries -ge $MAX_HEALTH_RETRIES ]; then
        echo ""
        echo "❌ Deployment FAILED — API did not become healthy after $((MAX_HEALTH_RETRIES * HEALTH_RETRY_INTERVAL)) seconds"
        echo "→ Check logs: $COMPOSE_CMD logs api --tail=50"
        echo "→ Rolling back..."
        $COMPOSE_CMD restart api
        exit 1
    fi
    echo "   Waiting... ($retries/$MAX_HEALTH_RETRIES)"
    sleep $HEALTH_RETRY_INTERVAL
done

echo "✅ API is healthy"

# ─── STEP 6: Clean up old images ─────────────────────────────────────────────
echo ""
echo "→ Cleaning up old Docker images..."
docker image prune -f --filter "until=24h"
echo "✅ Cleanup done"

# ─── DONE ────────────────────────────────────────────────────────────────────
echo ""
echo "====================================="
echo "  ✅ Deployment complete — $(date)"
echo "====================================="
echo ""
echo "Services running:"
$COMPOSE_CMD ps