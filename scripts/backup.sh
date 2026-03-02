#!/bin/bash
# ═══════════════════════════════════════════════════════
# my_TOWT — Database Backup Script
# Usage: ./scripts/backup.sh
# Add to crontab: 0 3 * * * /opt/mytowt/scripts/backup.sh
# ═══════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

cd "$PROJECT_DIR"

# Load env
if [ -f .env ]; then
    source .env
fi

DB_USER="${POSTGRES_USER:-towt_admin}"
DB_NAME="${POSTGRES_DB:-towt_planning}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# Dump database
docker exec towt-db pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

if [ -f "$BACKUP_FILE" ] && [ -s "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup created: $BACKUP_FILE ($SIZE)"
else
    echo "[$(date)] ERROR: Backup failed!" >&2
    exit 1
fi

# Clean old backups
DELETED=$(find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date)] Cleaned $DELETED old backups (>$RETENTION_DAYS days)"
fi

echo "[$(date)] Backup complete."
