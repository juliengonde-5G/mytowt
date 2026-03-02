#!/bin/bash
# ═══════════════════════════════════════════════════════
# my_TOWT — VPS OVH Deployment Script
# Usage: ./scripts/deploy.sh [first-run|update|ssl]
# ═══════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[TOWT]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# ─── Check prerequisites ─────────────────────────────
check_prereqs() {
    log "Checking prerequisites..."
    for cmd in docker git; do
        if ! command -v $cmd &> /dev/null; then
            err "$cmd is not installed"
            exit 1
        fi
    done

    # Check docker compose (v2)
    if docker compose version &> /dev/null; then
        COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE="docker-compose"
    else
        err "docker compose is not available"
        exit 1
    fi

    if [ ! -f .env ]; then
        err ".env file not found. Copy .env.example to .env and configure it."
        exit 1
    fi

    log "All prerequisites OK"
}

# ─── First run: install everything from scratch ──────
first_run() {
    log "=== FIRST RUN DEPLOYMENT ==="
    check_prereqs

    # Load env
    source .env

    if [ -z "${DOMAIN:-}" ]; then
        err "DOMAIN is not set in .env"
        exit 1
    fi

    log "Domain: $DOMAIN"

    # Step 1: Use initial nginx config (HTTP only)
    log "Setting up initial Nginx config (HTTP only)..."
    cp nginx/conf.d/towt-initial.conf nginx/conf.d/default.conf
    # Replace domain placeholder
    sed -i "s/\${DOMAIN}/$DOMAIN/g" nginx/conf.d/default.conf

    # Step 2: Build and start
    log "Building and starting containers..."
    $COMPOSE -f docker-compose.prod.yml up -d --build

    log "Waiting for services to be ready..."
    sleep 10

    # Step 3: Obtain SSL certificate
    log "Obtaining SSL certificate from Let's Encrypt..."
    $COMPOSE -f docker-compose.prod.yml run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "${CERTBOT_EMAIL:-admin@$DOMAIN}" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"

    # Step 4: Switch to full SSL config
    log "Switching to SSL Nginx config..."
    cp nginx/conf.d/towt.conf nginx/conf.d/default.conf
    sed -i "s/\${DOMAIN}/$DOMAIN/g" nginx/conf.d/default.conf

    # Step 5: Reload nginx
    docker exec towt-nginx nginx -s reload

    log "=== DEPLOYMENT COMPLETE ==="
    log "Application available at: https://$DOMAIN"
}

# ─── Update: pull latest code and redeploy ───────────
update() {
    log "=== UPDATING APPLICATION ==="
    check_prereqs

    # Pull latest code
    log "Pulling latest code..."
    git pull origin main

    # Rebuild and restart app only
    log "Rebuilding application..."
    $COMPOSE -f docker-compose.prod.yml build app

    log "Restarting application..."
    $COMPOSE -f docker-compose.prod.yml up -d app

    log "Waiting for health check..."
    sleep 5

    if docker exec towt-app curl -sf http://localhost:8000/login > /dev/null 2>&1; then
        log "Application is healthy"
    else
        warn "Health check failed — check logs with: docker logs towt-app"
    fi

    log "=== UPDATE COMPLETE ==="
}

# ─── SSL: renew certificates ─────────────────────────
ssl_renew() {
    log "=== RENEWING SSL CERTIFICATE ==="
    $COMPOSE -f docker-compose.prod.yml run --rm certbot renew
    docker exec towt-nginx nginx -s reload
    log "=== SSL RENEWAL COMPLETE ==="
}

# ─── Status ──────────────────────────────────────────
status() {
    log "=== SERVICE STATUS ==="
    $COMPOSE -f docker-compose.prod.yml ps
    echo ""
    log "=== RECENT APP LOGS ==="
    docker logs --tail 20 towt-app 2>&1
}

# ─── Main ────────────────────────────────────────────
case "${1:-help}" in
    first-run)  first_run ;;
    update)     update ;;
    ssl)        ssl_renew ;;
    status)     status ;;
    logs)       docker logs -f towt-app ;;
    *)
        echo "Usage: $0 {first-run|update|ssl|status|logs}"
        echo ""
        echo "  first-run  — Full deployment (build, start, SSL)"
        echo "  update     — Pull code, rebuild, restart app"
        echo "  ssl        — Renew SSL certificates"
        echo "  status     — Show service status and logs"
        echo "  logs       — Follow application logs"
        ;;
esac
