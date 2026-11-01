"""Reglages de l'API, lus dans l'environnement (et dans .env s'il existe).

Les valeurs par defaut suffisent en developpement local. En production
(ENV=production), les secrets et la base doivent etre definis : l'API
refuse de demarrer sinon (cf. _validate_production).
"""

import logging
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

from api.config.constants import BASE_DIR, DATA_DIR


load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


ENV = os.environ.get("ENV", "development")

IS_PROD = ENV == "production"

# Prefixe versionne de toutes les routes metier (hors /health).
API_PREFIX = "/trade/v1"

# Documentation interactive (/docs) : ouverte en developpement, fermee par
# defaut en production.
ENABLE_DOCS = os.environ.get("ENABLE_DOCS", "false" if IS_PROD else "true") == "true"

# Calcul des indicateurs de tous les titres au demarrage, pour que le
# premier GET /market reponde vite.
WARM_CACHE = os.environ.get("WARM_CACHE", "true") == "true"

# =========================================================
# LOGS
# =========================================================

LOG_DIR = os.environ.get("LOG_DIR", str(BASE_DIR / "logs"))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO" if IS_PROD else "DEBUG")

# =========================================================
# BASE DE DONNEES
# =========================================================


def _database_url():
    """DATABASE_URL si fourni ; sinon construit depuis DB_HOST, DB_NAME...
    (comme docker-compose) ; sinon SQLite local."""

    url = os.environ.get("DATABASE_URL")

    if not url and os.environ.get("DB_HOST"):
        url = "postgresql+psycopg://{user}:{password}@{host}:{port}/{name}".format(
            user=quote_plus(os.environ.get("DB_USER", "")),
            password=quote_plus(os.environ.get("DB_PASSWORD", "")),
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            name=os.environ.get("DB_NAME", "")
        )

    if not url:
        return f"sqlite:///{DATA_DIR / 'saas.db'}"

    # Les hebergeurs fournissent postgres:// ; SQLAlchemy attend le nom du
    # pilote installe (psycopg 3).
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]

    return url


DATABASE_URL = _database_url()

# =========================================================
# JETONS
# =========================================================

DEV_SECRET = "dev-secret-a-remplacer-en-production"
DEV_REFRESH_SECRET = "dev-refresh-secret-a-remplacer-en-production"

JWT_SECRET = os.environ.get("JWT_SECRET", DEV_SECRET)

JWT_REFRESH_SECRET = os.environ.get("JWT_REFRESH_SECRET", DEV_REFRESH_SECRET)

# Jeton d'acces court ; le jeton de rafraichissement (stocke hache en base,
# renouvele a chaque usage) garde la session ouverte sur le telephone.
ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "60"))

REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS", "30"))

# Sessions ouvertes en meme temps par compte (appareils) : au-dela, la plus
# ancienne est fermee.
MAX_REFRESH_TOKENS = int(os.environ.get("MAX_REFRESH_TOKENS", "5"))

# =========================================================
# CORS ET REDIRECTIONS
# =========================================================

# Origines autorisees a appeler l'API depuis un navigateur (app Expo en
# version web). "*" accepte en developpement seulement.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

# Adresse publique de l'API : PayDunya y renvoie le client apres paiement
# (return_url) et y notifie le resultat (callback_url / IPN).
PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", "http://localhost:8000")

# Debuts d'adresse vers lesquels l'API accepte de renvoyer l'utilisateur
# apres paiement : schema de l'app mobile, Expo Go, version web. Evite de
# faire de /billing/return une redirection ouverte.
APP_REDIRECT_PREFIXES = os.environ.get(
    "APP_REDIRECT_PREFIXES",
    "finadvisor://,exp://,http://localhost:8081"
).split(",")

# =========================================================
# ASSISTANT
# =========================================================

# Questions a l'assistant par jour et par utilisateur, selon l'offre : c'est
# le seul poste dont le cout croit avec l'usage (appels a l'API Claude).
ASSISTANT_DAILY_LIMITS = {
    "free": int(os.environ.get("ASSISTANT_LIMIT_FREE", "3")),
    "pro": int(os.environ.get("ASSISTANT_LIMIT_PRO", "50"))
}

# =========================================================
# PAYDUNYA
# =========================================================
# Cles du tableau de bord PayDunya (Integrez notre API > application).
# PAYDUNYA_MODE=test utilise le bac a sable : aucun argent reel ne circule.

PAYDUNYA_MODE = os.environ.get("PAYDUNYA_MODE", "test")

PAYDUNYA_MASTER_KEY = os.environ.get("PAYDUNYA_MASTER_KEY", "")
PAYDUNYA_PRIVATE_KEY = os.environ.get("PAYDUNYA_PRIVATE_KEY", "")
PAYDUNYA_TOKEN = os.environ.get("PAYDUNYA_TOKEN", "")

PAYDUNYA_STORE_NAME = os.environ.get("PAYDUNYA_STORE_NAME", "Financial AI Advisor")

# Prix et duree d'un mois Pro. PayDunya ne gere pas l'abonnement recurrent :
# chaque paiement prolonge l'offre Pro de PRO_DAYS jours.
PRO_PRICE_XOF = int(os.environ.get("PRO_PRICE_XOF", "5000"))
PRO_DAYS = int(os.environ.get("PRO_DAYS", "30"))

# =========================================================
# ADMINISTRATION
# =========================================================

# Cle des appels d'administration (import de cours, rafraichissement) :
# en-tete X-Admin-Key. Vide = administration desactivee.
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")


def _validate_production():
    """Refuse de demarrer en production avec une configuration dangereuse,
    plutot que de le decouvrir apres coup."""

    problems = []

    if JWT_SECRET == DEV_SECRET or JWT_REFRESH_SECRET == DEV_REFRESH_SECRET:
        problems.append("JWT_SECRET et JWT_REFRESH_SECRET doivent etre definis")

    if JWT_SECRET == JWT_REFRESH_SECRET:
        problems.append("JWT_SECRET et JWT_REFRESH_SECRET doivent etre differents")

    if "*" in CORS_ORIGINS:
        problems.append("CORS_ORIGINS=* est interdit en production")

    if DATABASE_URL.startswith("sqlite"):
        problems.append("une base PostgreSQL est requise (DATABASE_URL ou DB_HOST)")

    if problems:
        raise RuntimeError(
            "Configuration de production invalide : " + " ; ".join(problems)
        )


if IS_PROD:
    _validate_production()
elif JWT_SECRET == DEV_SECRET:
    logger.warning(
        "JWT_SECRET non defini : secret de developpement utilise. "
        "A definir imperativement en production."
    )
