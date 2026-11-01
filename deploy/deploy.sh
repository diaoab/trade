#!/usr/bin/env bash
# ============================================================
#  Trade API — Mise a jour sur le VPS
#  Usage : bash deploy/deploy.sh   (depuis n'importe ou sur le VPS)
#  Le workflow GitHub .github/workflows/deploy.yml fait la meme chose a
#  chaque push sur main une fois les tests passes.
# ============================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/trade-api}"
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "[deploy] Repertoire : ${APP_DIR}"
cd "${APP_DIR}"

if [ ! -f ".env" ]; then
    echo "[deploy] ERREUR : fichier .env manquant dans ${APP_DIR}"
    echo "         Copier .env.example vers .env et remplir toutes les valeurs."
    exit 1
fi

mkdir -p backups

echo "[deploy] git pull..."
git pull --ff-only

# Les migrations Alembic tournent au demarrage du conteneur (cf. Dockerfile).
echo "[deploy] Build et rechargement des conteneurs..."
${COMPOSE} up -d --build --remove-orphans

echo "[deploy] Attente du health check..."
for _ in $(seq 1 30); do
    if curl -fs http://127.0.0.1:8000/health > /dev/null; then
        echo "[deploy] API en ligne."
        break
    fi
    sleep 2
done
curl -fs http://127.0.0.1:8000/health > /dev/null || {
    echo "[deploy] ERREUR : l'API ne repond pas. Logs :"
    ${COMPOSE} logs --tail=50 backend
    exit 1
}

${COMPOSE} ps

echo "[deploy] Nettoyage des images inutilisees..."
docker image prune -f

echo "[deploy] Deploiement termine — $(date '+%Y-%m-%d %H:%M:%S')"
