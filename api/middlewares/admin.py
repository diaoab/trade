"""Acces aux routes d'administration, de deux facons :

- jeton d'un compte au role "admin" (back-office trade_admin) ;
- cle partagee dans l'en-tete X-Admin-Key (taches planifiees, scripts
  d'import en curl).
"""

import hmac

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from api.config import settings
from api.config.db import get_db
from api.errors.app_error import ForbiddenError
from api.middlewares.auth import bearer, current_user


def _valid_key(x_admin_key):

    return bool(settings.ADMIN_API_KEY) and hmac.compare_digest(
        x_admin_key,
        settings.ADMIN_API_KEY
    )


def require_admin(
    x_admin_key: str = Header(default=""),
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db)
):
    """Dependance FastAPI : le compte admin du jeton, None pour un appel par
    cle, 403 sinon (401 si le jeton est invalide ou expire, pour que le
    back-office le rafraichisse)."""

    if x_admin_key and _valid_key(x_admin_key):
        return None

    if credentials is not None:

        user = current_user(credentials, db)

        if user.is_admin:
            return user

    raise ForbiddenError("Accès réservé à l'administration.")


def require_admin_user(admin=Depends(require_admin)):
    """Pour les actions sur les comptes : un compte admin identifie, pas la
    cle partagee (on sait ainsi qui a fait quoi)."""

    if admin is None:
        raise ForbiddenError("Action réservée à un compte administrateur.")

    return admin
