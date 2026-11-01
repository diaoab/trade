"""Acces aux routes d'administration : cle partagee dans l'en-tete
X-Admin-Key (taches planifiees, scripts d'import)."""

import hmac

from fastapi import Header

from api.config import settings
from api.errors.app_error import ForbiddenError


def require_admin(x_admin_key: str = Header(default="")):

    if not settings.ADMIN_API_KEY or not hmac.compare_digest(
        x_admin_key,
        settings.ADMIN_API_KEY
    ):
        raise ForbiddenError("Accès réservé à l'administration.")
