"""Gestion centralisee des erreurs.

Format de reponse uniforme : { success: false, message, details? }.
Aucun detail interne (trace, requete SQL, chemin) ne part au client en
production : il est journalise cote serveur.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.config.settings import IS_PROD
from api.errors.app_error import AppError
from api.utils.response import fail


logger = logging.getLogger("api.errors")


def _context(request):

    return {
        "path": request.url.path,
        "method": request.method,
        "ip": request.client.host if request.client else None
    }


async def app_error_handler(request: Request, error: AppError):

    if error.status_code >= 500:
        logger.error(error.message, extra=_context(request))
    else:
        logger.info(f"{error.status_code} {error.message}", extra=_context(request))

    return fail(error.message, error.status_code, error.details, error.headers)


async def http_error_handler(request: Request, error: StarletteHTTPException):
    """Erreurs levees par FastAPI lui-meme (route inconnue, methode non
    permise, en-tete Bearer absent...)."""

    messages = {
        404: "Route introuvable",
        405: "Méthode non autorisée"
    }

    message = error.detail if isinstance(error.detail, str) else None

    if message in (None, "Not Found", "Method Not Allowed"):
        message = messages.get(error.status_code, "Requête invalide")

    return fail(message, error.status_code, headers=getattr(error, "headers", None))


async def validation_error_handler(request: Request, error: RequestValidationError):

    details = []

    for item in error.errors():

        location = ".".join(
            str(part) for part in item.get("loc", ()) if part not in ("body", "query", "path")
        )

        details.append(f"{location} : {item.get('msg')}" if location else item.get("msg"))

    return fail("Données invalides", 422, details)


async def integrity_error_handler(request: Request, error: IntegrityError):

    logger.warning("Contrainte d'intégrité violée", extra=_context(request))

    return fail("Cette ressource existe déjà", 409)


async def database_error_handler(request: Request, error: OperationalError):

    logger.error("Base de données indisponible", exc_info=error, extra=_context(request))

    return fail("Service temporairement indisponible", 503)


async def unhandled_error_handler(request: Request, error: Exception):

    logger.error(str(error), exc_info=error, extra=_context(request))

    message = "Erreur interne du serveur" if IS_PROD else (str(error) or "Erreur interne du serveur")

    return fail(message, 500)


def register_error_handlers(app: FastAPI):

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(OperationalError, database_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
