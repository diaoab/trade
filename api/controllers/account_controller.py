from fastapi import Depends
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.middlewares.auth import current_user
from api.models import User
from api.services import account_service
from api.utils.format_user import format_user
from api.utils.response import ok
from api.validations.account_validation import PreferencesIn, ProfileIn


def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ok(format_user(db, user), "Profil récupéré")


def update_profile(
    body: ProfileIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):

    account_service.update_profile(db, user, body.model_dump(exclude_unset=True))

    return ok(format_user(db, user), "Profil mis à jour")


def delete_account(user: User = Depends(current_user), db: Session = Depends(get_db)):

    account_service.delete_account(db, user)

    return ok(None, "Compte supprimé")


def get_preferences(user: User = Depends(current_user)):
    return ok(account_service.get_preferences(user), "Réglages récupérés")


def update_preferences(
    body: PreferencesIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):

    preferences = account_service.update_preferences(
        db,
        user,
        body.model_dump(exclude_none=True)
    )

    return ok(preferences, "Réglages enregistrés")
