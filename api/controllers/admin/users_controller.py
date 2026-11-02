from fastapi import Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.middlewares.admin import require_admin_user
from api.models import User
from api.models.base import utcnow
from api.services.admin import users_service
from api.utils.response import created, ok
from api.validations.admin_validation import AdminCreateIn, UserUpdateIn


def list_users(
    page: int = 1,
    limit: int = 20,
    search: str = "",
    plan: str = "",
    role: str = "",
    status: str = "",
    db: Session = Depends(get_db)
):

    return ok(
        users_service.list_users(db, page, limit, search, plan, role, status),
        "Comptes récupérés"
    )


def export_users(
    search: str = "",
    plan: str = "",
    role: str = "",
    status: str = "",
    db: Session = Depends(get_db)
):

    filename = f"comptes-{utcnow():%Y%m%d-%H%M}.csv"

    return Response(
        users_service.export_csv(db, search, plan, role, status),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def create_admin(
    body: AdminCreateIn,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):

    user = users_service.create_admin(
        db, body.email, body.password, body.first_name, body.last_name, body.phone
    )

    return created(user, "Administrateur créé")


def get_user(user_id: int, db: Session = Depends(get_db)):

    return ok(users_service.get_user(db, user_id), "Compte récupéré")


def update_user(
    user_id: int,
    body: UserUpdateIn,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):

    user = users_service.update_user(db, admin, user_id, body.model_dump(exclude_unset=True))

    return ok(user, "Compte mis à jour")


def activate_user(
    user_id: int,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):

    return ok(users_service.set_active(db, admin, user_id, True), "Compte activé")


def deactivate_user(
    user_id: int,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):

    return ok(users_service.set_active(db, admin, user_id, False), "Compte désactivé")


def delete_user(
    user_id: int,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):

    return ok(users_service.delete_user(db, admin, user_id), "Compte supprimé")


def revoke_sessions(
    user_id: int,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):

    return ok(users_service.revoke_sessions(db, user_id), "Sessions fermées")
