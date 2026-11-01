from fastapi import Depends
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.middlewares.admin import require_admin_user
from api.models import User
from api.services.admin import users_service
from api.utils.response import ok
from api.validations.admin_validation import UserUpdateIn


def list_users(
    page: int = 1,
    limit: int = 20,
    search: str = "",
    plan: str = "",
    role: str = "",
    db: Session = Depends(get_db)
):

    return ok(users_service.list_users(db, page, limit, search, plan, role), "Comptes récupérés")


def get_user(user_id: int, db: Session = Depends(get_db)):

    return ok(users_service.get_user(db, user_id), "Compte récupéré")


def update_user(
    user_id: int,
    body: UserUpdateIn,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):

    user = users_service.update_user(db, admin, user_id, body.plan, body.role)

    return ok(user, "Compte mis à jour")


def revoke_sessions(
    user_id: int,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):

    return ok(users_service.revoke_sessions(db, user_id), "Sessions fermées")
