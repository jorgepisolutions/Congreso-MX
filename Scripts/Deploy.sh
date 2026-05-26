#!/usr/bin/env bash
# Deploy / actualizacion del stack CongresoMx en el servidor.
#
# Pasos:
#   1. git pull --ff-only desde origin/main
#   2. docker compose build (con archivos prod o server segun ambiente)
#   3. Aplica migraciones Alembic via un container temporal
#   4. docker compose up -d
#   5. Health check final
#
# Uso:
#   bash Scripts/Deploy.sh                    # usa Server override (default)
#   COMPOSE_OVERRIDE=Prod bash Scripts/Deploy.sh   # usa Prod override (con Caddy)
#
# Idempotente: si no hay cambios en git, igual rebuilea y aplica migraciones
# (que tambien son idempotentes).

set -euo pipefail

REPO_DIR="${REPO_DIR:-/usr/local/CongresoMX}"
COMPOSE_OVERRIDE="${COMPOSE_OVERRIDE:-Server}"  # Server | Prod
BRANCH="${BRANCH:-main}"

cd "${REPO_DIR}"

COMPOSE_FILES=(-f "Docker/DockerCompose.yml" -f "Docker/DockerCompose.${COMPOSE_OVERRIDE}.yml")

echo "[$(date -u +'%H:%M:%SZ')] === Deploy CongresoMx ($COMPOSE_OVERRIDE) ==="

# 1) Pull
echo "[$(date -u +'%H:%M:%SZ')] git fetch + ff-only pull desde origin/${BRANCH}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only

# 2) Build
echo "[$(date -u +'%H:%M:%SZ')] docker compose build (sin --no-cache; rebuilds rapidos si solo cambio Src/)"
docker compose "${COMPOSE_FILES[@]}" build AppApi AppScheduler

# 3) Migraciones via container temporal
echo "[$(date -u +'%H:%M:%SZ')] Aplicando migraciones Alembic"
docker compose "${COMPOSE_FILES[@]}" run --rm AppApi alembic upgrade head || {
    echo "ERROR: migraciones fallaron; revertir o investigar antes de up -d"
    exit 1
}

# 4) Up
echo "[$(date -u +'%H:%M:%SZ')] docker compose up -d --remove-orphans"
docker compose "${COMPOSE_FILES[@]}" up -d --remove-orphans

# 5) Health check
echo "[$(date -u +'%H:%M:%SZ')] Esperando AppApi healthy..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "[$(date -u +'%H:%M:%SZ')] AppApi healthy"
        break
    fi
    sleep 2
    if [[ "${i}" == "30" ]]; then
        echo "ERROR: AppApi no respondio en 60s; revisa docker logs CongresoMxAppApi"
        exit 1
    fi
done

# Estado final
docker compose "${COMPOSE_FILES[@]}" ps
echo "[$(date -u +'%H:%M:%SZ')] === Deploy completado ==="
