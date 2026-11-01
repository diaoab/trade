"""Point d'entree de l'API du service en ligne.

Lancer en local :
    python -m alembic upgrade head
    python -m uvicorn api.main:app --reload
Documentation interactive : http://127.0.0.1:8000/docs
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.config import settings
from api.config.db import get_db
from api.config.security import CORS_CONFIG
from api.middlewares.error_handler import register_error_handlers
from api.middlewares.rate_limit import GlobalRateLimitMiddleware
from api.middlewares.request_logger import RequestLoggerMiddleware
from api.routes import api_router
from api.services import market_service
from api.utils.logger import configure_logging
from api.utils.response import fail


configure_logging()

logger = logging.getLogger("api.startup")


def warm_market_cache():
    """Calcule les indicateurs de tous les titres (reglages par defaut) :
    sans cela, le premier GET /market apres un demarrage prend plusieurs
    secondes."""

    try:
        market_service.market_overview(None)
    except Exception:
        logger.exception("Prechauffage du cache du marche en echec")


@asynccontextmanager
async def lifespan(app):

    if settings.WARM_CACHE:
        # En arriere-plan : l'API repond (et /health passe) sans attendre.
        threading.Thread(target=warm_market_cache, daemon=True).start()

    yield


app = FastAPI(
    lifespan=lifespan,
    title="Financial AI Advisor",
    description=(
        "Analyse technique et modèle expérimental sur les titres de la "
        "BRVM. Outil d'aide à l'analyse, pas un conseil en investissement."
    ),
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None
)

# ── Middlewares (le dernier ajoute s'execute en premier) ───────────────────
app.add_middleware(GlobalRateLimitMiddleware)
app.add_middleware(CORSMiddleware, **CORS_CONFIG)
app.add_middleware(RequestLoggerMiddleware)

register_error_handlers(app)


# ── Health check (hors versioning : sonde Docker / Nginx) ──────────────────
@app.get("/health", include_in_schema=False)
def health(db: Session = Depends(get_db)):

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return fail("Base de données injoignable", 503)

    return {"status": "ok", "db": "connected"}


# ── Routes metier ──────────────────────────────────────────────────────────
app.include_router(api_router, prefix=settings.API_PREFIX)
