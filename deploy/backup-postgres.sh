#!/usr/bin/env bash
# ============================================================
#  Trade API — Sauvegarde PostgreSQL et donnees de marche
#  Usage : bash deploy/backup-postgres.sh   (planifie par deploy/crontab)
#
#   • pg_dump via le conteneur postgres, compresse en .gz
#   • archive du volume de donnees (historiques, modele, resultats)
#   • copie vers Google Drive si rclone est configure (remote "gdrive")
#   • garde KEEP_DAYS jours de sauvegardes locales
# ============================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/trade-api}"
BACKUP_DIR="${APP_DIR}/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
KEEP_DAYS=7
COMPOSE="docker compose -f ${APP_DIR}/docker-compose.prod.yml"

# Variables DB_* depuis .env
if [ -f "${APP_DIR}/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1090
    source <(grep -E '^DB_(NAME|USER)=' "${APP_DIR}/.env")
    set +o allexport
fi

DB_NAME="${DB_NAME:-tradeapp}"
DB_USER="${DB_USER:-tradeuser}"

mkdir -p "${BACKUP_DIR}"

echo "[backup] $(date '+%Y-%m-%d %H:%M:%S') — Debut"

DB_FILE="${BACKUP_DIR}/tradeapp_${TIMESTAMP}.sql.gz"
${COMPOSE} exec -T postgres pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${DB_FILE}"
echo "[backup] Base : ${DB_FILE} ($(du -sh "${DB_FILE}" | cut -f1))"

DATA_FILE="${BACKUP_DIR}/tradedata_${TIMESTAMP}.tar.gz"
${COMPOSE} exec -T backend tar -czf - -C /var/data . > "${DATA_FILE}"
echo "[backup] Donnees : ${DATA_FILE} ($(du -sh "${DATA_FILE}" | cut -f1))"

if command -v rclone > /dev/null && rclone listremotes | grep -q "^gdrive:"; then
    echo "[backup] Upload vers Google Drive..."
    rclone copy "${DB_FILE}" gdrive:trade-api-backups
    rclone copy "${DATA_FILE}" gdrive:trade-api-backups
else
    echo "[backup] rclone (remote gdrive) absent — upload ignore"
fi

find "${BACKUP_DIR}" -name "trade*_*.gz" -mtime "+${KEEP_DAYS}" -delete
echo "[backup] Sauvegardes locales conservees : $(find "${BACKUP_DIR}" -name 'trade*_*.gz' | wc -l)"

echo "[backup] $(date '+%Y-%m-%d %H:%M:%S') — Termine"
