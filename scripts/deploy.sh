#!/bin/bash
# ═══════════════════════════════════════════════════════
# my_TOWT — VPS Deployment Script
# Usage: ./scripts/deploy.sh [first-run|update|seed|status|logs]
# ═══════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BRANCH="${DEPLOY_BRANCH:-main}"

cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[TOWT]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }

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
        warn ".env not found — creating from .env.example..."
        if [ -f .env.example ]; then
            cp .env.example .env
            # Generate a random SECRET_KEY
            SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
            sed -i "s/CHANGE_ME_generate_a_random_64_char_hex_string/$SECRET/" .env
            warn ">>> Edit .env to set POSTGRES_PASSWORD and other values <<<"
            err ".env created but needs configuration. Edit it and re-run."
            exit 1
        else
            err ".env.example not found"
            exit 1
        fi
    fi

    log "All prerequisites OK"
}

# ─── First run: full deployment from scratch ─────────
first_run() {
    log "══════════════════════════════════════════"
    log "   FIRST RUN DEPLOYMENT"
    log "══════════════════════════════════════════"
    check_prereqs
    source .env

    # Step 1: Build and start all services
    log "Building and starting containers..."
    $COMPOSE -f docker-compose.prod.yml up -d --build

    log "Waiting for database to be ready..."
    for i in {1..30}; do
        if docker exec towt-db pg_isready -U "${POSTGRES_USER:-towt_admin}" -h 127.0.0.1 &>/dev/null; then
            log "Database is ready"
            break
        fi
        sleep 1
    done

    log "Waiting for application to start..."
    for i in {1..30}; do
        if docker exec towt-app curl -sf http://localhost:8000/login &>/dev/null; then
            log "Application is healthy"
            break
        fi
        sleep 2
    done

    # Step 2: Seed admin user
    seed_admin

    log "══════════════════════════════════════════"
    log "   DEPLOYMENT COMPLETE"
    log "══════════════════════════════════════════"
    IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "your-server-ip")
    info "Application : http://$IP"
    info "Login       : admin / towt2025"
    info ""
    info "Next steps:"
    info "  1. Go to Admin > Paramètres > Ports"
    info "  2. Click 'Importer les ports (UN/LOCODE)'"
    info "  3. Create your vessels in Admin > Paramètres > Navires"
}

# ─── Update: pull latest code and redeploy ───────────
update() {
    log "══════════════════════════════════════════"
    log "   UPDATING APPLICATION"
    log "══════════════════════════════════════════"
    check_prereqs

    # Pull latest code
    log "Pulling latest code from branch: $BRANCH ..."
    git pull origin "$BRANCH"

    # Rebuild and restart app only
    log "Rebuilding application..."
    $COMPOSE -f docker-compose.prod.yml build app

    log "Restarting application..."
    $COMPOSE -f docker-compose.prod.yml up -d app

    log "Waiting for health check..."
    for i in {1..15}; do
        if docker exec towt-app curl -sf http://localhost:8000/login &>/dev/null; then
            log "Application is healthy"
            log "═══ UPDATE COMPLETE ═══"
            return
        fi
        sleep 2
    done

    warn "Health check failed — check logs:"
    docker logs --tail 30 towt-app 2>&1
}

# ─── Seed admin user ─────────────────────────────────
seed_admin() {
    log "Creating admin user (admin / towt2025)..."
    docker exec towt-app python3 -c "
import asyncio
from app.database import async_session
from app.models.user import User
from app.auth import hash_password
from sqlalchemy import select

async def seed():
    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == 'admin'))
        if result.scalar_one_or_none():
            print('[TOWT] Admin user already exists — skipping')
            return
        admin = User(
            username='admin',
            email='admin@towt.eu',
            hashed_password=hash_password('towt2025'),
            full_name='Administrateur',
            role='administrateur',
            language='fr',
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print(f'[TOWT] Admin user created (id={admin.id})')

asyncio.run(seed())
"
}

# ─── Seed: create admin + import ports ────────────────
seed() {
    log "══════════════════════════════════════════"
    log "   SEEDING DATABASE"
    log "══════════════════════════════════════════"

    seed_admin

    log "Importing ports from UN/LOCODE..."
    docker exec towt-app python3 -c "
import asyncio
from app.database import async_session
from app.utils.port_loader import load_ports_from_unlocode

async def run():
    async with async_session() as session:
        stats = await load_ports_from_unlocode(session)
        await session.commit()
        print(f'[TOWT] Ports: {stats[\"inserted\"]} added, {stats[\"updated\"]} updated, {stats[\"skipped\"]} skipped')

asyncio.run(run())
"
    log "═══ SEEDING COMPLETE ═══"
}

# ─── SSL: obtain or renew certificates ───────────────
ssl_setup() {
    log "═══ SSL CERTIFICATE SETUP ═══"
    check_prereqs
    source .env

    if [ -z "${DOMAIN:-}" ]; then
        err "DOMAIN is not set in .env — SSL requires a domain name"
        exit 1
    fi

    log "Domain: $DOMAIN"

    # Check if certbot service exists
    if ! grep -q certbot docker-compose.prod.yml; then
        warn "No certbot service in docker-compose.prod.yml"
        warn "Add certbot service or use external SSL termination"
        exit 1
    fi

    $COMPOSE -f docker-compose.prod.yml run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "${CERTBOT_EMAIL:-admin@$DOMAIN}" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"

    # Switch to SSL config if available
    if [ -f nginx/conf.d/towt-ssl.conf ]; then
        cp nginx/conf.d/towt-ssl.conf nginx/conf.d/default.conf
        sed -i "s/\${DOMAIN}/$DOMAIN/g" nginx/conf.d/default.conf
        docker exec towt-nginx nginx -s reload
        log "SSL enabled — https://$DOMAIN"
    fi
}

ssl_renew() {
    log "═══ RENEWING SSL CERTIFICATE ═══"
    $COMPOSE -f docker-compose.prod.yml run --rm certbot renew
    docker exec towt-nginx nginx -s reload
    log "═══ SSL RENEWAL COMPLETE ═══"
}

# ─── Status ──────────────────────────────────────────
status() {
    check_prereqs
    log "═══ SERVICE STATUS ═══"
    $COMPOSE -f docker-compose.prod.yml ps
    echo ""
    log "═══ DATABASE ═══"
    docker exec towt-db psql -U "${POSTGRES_USER:-towt_admin}" -d "${POSTGRES_DB:-towt_planning}" \
        -c "SELECT 'Users: ' || count(*) FROM users UNION ALL SELECT 'Ports: ' || count(*) FROM ports UNION ALL SELECT 'Vessels: ' || count(*) FROM vessels;" 2>/dev/null || warn "Could not query database"
    echo ""
    log "═══ RECENT LOGS ═══"
    docker logs --tail 20 towt-app 2>&1
}

# ─── Restart ─────────────────────────────────────────
restart() {
    check_prereqs
    log "Restarting application..."
    $COMPOSE -f docker-compose.prod.yml restart app
    log "Done"
}

# ─── Main ────────────────────────────────────────────
case "${1:-help}" in
    first-run)  first_run ;;
    update)     update ;;
    seed)       seed ;;
    ssl)        ssl_setup ;;
    ssl-renew)  ssl_renew ;;
    status)     status ;;
    restart)    restart ;;
    logs)       docker logs -f towt-app ;;
    *)
        echo ""
        echo "  my_TOWT Deployment"
        echo "  Usage: $0 <command>"
        echo ""
        echo "  Commands:"
        echo "    first-run  — Full deployment (build, start, create admin)"
        echo "    update     — Pull code, rebuild, restart app"
        echo "    seed       — Create admin user + import ports"
        echo "    restart    — Restart application container"
        echo "    ssl        — Setup SSL certificate (requires DOMAIN in .env)"
        echo "    ssl-renew  — Renew SSL certificate"
        echo "    status     — Show services, DB stats, recent logs"
        echo "    logs       — Follow application logs"
        echo ""
        echo "  Environment:"
        echo "    DEPLOY_BRANCH=main  — Git branch to pull (default: main)"
        echo ""
        echo "  Examples:"
        echo "    ./scripts/deploy.sh first-run"
        echo "    ./scripts/deploy.sh update"
        echo "    DEPLOY_BRANCH=develop ./scripts/deploy.sh update"
        echo ""
        ;;
esac
