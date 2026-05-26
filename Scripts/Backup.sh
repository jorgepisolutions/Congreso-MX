#!/usr/bin/env bash
# Backup diario de MariaDB del proyecto CongresoMx.
#
# Hace mysqldump del schema completo de CongresoMx, comprime con gzip,
# guarda en BACKUPS_DIR con nombre YYYYMMDD-HHMM.sql.gz y purga archivos
# de mas de RETENTION_DAYS.
#
# Uso:
#   bash Scripts/Backup.sh
#
# Variables que lee del entorno (o usa defaults):
#   MARIADB_CONTAINER     - nombre del contenedor mariadb (default: CongresoMxMariadb)
#   MARIADB_DATABASE      - nombre de la DB (default: CongresoMx)
#   MARIADB_ROOT_PASSWORD - password root de mariadb (REQUERIDO)
#   BACKUPS_DIR           - donde guardar los .sql.gz (default: /var/backups/CongresoMx)
#   RETENTION_DAYS        - cuantos dias retener (default: 30)
#
# Cron sugerido (todos los dias a las 3am UTC):
#   0 3 * * * cd /usr/local/CongresoMX && bash Scripts/Backup.sh >> /var/log/CongresoMx-backup.log 2>&1
#
# Upload a almacenamiento remoto (Backblaze B2, Cloudflare R2, S3) queda
# como placeholder: descomenta la seccion rclone y configura tu remote.

set -euo pipefail

MARIADB_CONTAINER="${MARIADB_CONTAINER:-CongresoMxMariadb}"
MARIADB_DATABASE="${MARIADB_DATABASE:-CongresoMx}"
BACKUPS_DIR="${BACKUPS_DIR:-/var/backups/CongresoMx}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

if [[ -z "${MARIADB_ROOT_PASSWORD:-}" ]]; then
    echo "ERROR: MARIADB_ROOT_PASSWORD no esta seteado en el entorno" >&2
    exit 1
fi

TIMESTAMP="$(date -u +'%Y%m%d-%H%M')"
OUTPUT="${BACKUPS_DIR}/${MARIADB_DATABASE}-${TIMESTAMP}.sql.gz"

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Backup iniciado: ${OUTPUT}"
mkdir -p "${BACKUPS_DIR}"

# Hacemos el dump dentro del contenedor para no necesitar mariadb-client en el host.
# --single-transaction para snapshot consistente sin lockear tablas (InnoDB).
# --routines + --events para incluir stored procedures y eventos.
docker exec "${MARIADB_CONTAINER}" mariadb-dump \
    -uroot "-p${MARIADB_ROOT_PASSWORD}" \
    --single-transaction \
    --routines --events \
    --default-character-set=utf8mb4 \
    "${MARIADB_DATABASE}" \
    | gzip --best > "${OUTPUT}"

SIZE_BYTES="$(stat -c %s "${OUTPUT}" 2>/dev/null || stat -f %z "${OUTPUT}")"
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Backup OK (${SIZE_BYTES} bytes)"

# Upload remoto (descomenta y configura tu remote rclone):
# RCLONE_REMOTE="${RCLONE_REMOTE:-b2:CongresoMxBackups}"
# rclone copy "${OUTPUT}" "${RCLONE_REMOTE}/" --quiet
# echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Upload a ${RCLONE_REMOTE} OK"

# Purga local: deja solo los ultimos RETENTION_DAYS dias.
DELETED_COUNT="$(find "${BACKUPS_DIR}" -name "${MARIADB_DATABASE}-*.sql.gz" -type f -mtime "+${RETENTION_DAYS}" -delete -print | wc -l | tr -d ' ')"
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Purga local: ${DELETED_COUNT} archivos removidos (mas de ${RETENTION_DAYS} dias)"

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Backup completado"
