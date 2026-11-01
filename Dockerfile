# ============================================================
#  Trade API — image de production
#  Historiques, modele entraine et resultats vivent sur un volume
#  (DATA_DIR, MODEL_DIR, RESULT_DIR) : ils survivent aux redeploiements.
#  Voir docker-compose.prod.yml.
# ============================================================
FROM python:3.12-slim

# libgomp1 : OpenMP pour xgboost ; curl : HEALTHCHECK
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Manifeste en premier pour profiter du cache Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]>=3.2"

COPY alembic.ini ./
COPY core core
COPY api api

# Utilisateur non-root ; dossiers des volumes crees avec les bons droits
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /var/data/data /var/data/models /var/data/results /app/logs \
    && chown -R app:app /var/data /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f "http://localhost:${PORT}/health" || exit 1

# Migrations puis API. Un seul worker : les limites de debit sont en
# memoire (cf. api/middlewares/rate_limit.py). --proxy-headers : l'IP
# reelle du client vient de Nginx (X-Forwarded-For) ; le port n'est publie
# que sur 127.0.0.1, seul Nginx peut donc se presenter en proxy.
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
