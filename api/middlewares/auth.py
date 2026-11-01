"""Authentification : l'utilisateur porteur du jeton d'acces."""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.errors.app_error import UnauthorizedError
from api.models import User
from api.services import token_service


bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db)
):
    """Dependance FastAPI : l'utilisateur du jeton d'acces, ou 401."""

    if credentials is None:
        raise UnauthorizedError("Jeton manquant : connecte-toi.")

    user_id = token_service.read_access_token(credentials.credentials)

    user = db.get(User, user_id)

    if user is None:
        raise UnauthorizedError()

    return user
