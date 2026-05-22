#!/bin/bash
# Database backup script — run via cron daily
set -euo pipefail

BACKUP_DIR="/backups/escrow_bot"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

source .env

echo "[$TIMESTAMP] Starting backup..."
docker compose exec -T postgres pg_dump \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-password \
    | gzip > "$BACKUP_DIR/db_${TIMESTAMP}.sql.gz"

# Keep 30 days of backups
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +30 -delete

echo "[$TIMESTAMP] Backup complete: $BACKUP_DIR/db_${TIMESTAMP}.sql.gz"
