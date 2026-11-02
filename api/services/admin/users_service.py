"""Gestion des comptes depuis le back-office."""

import csv
import io

from sqlalchemy import func, or_, select

from api.errors.app_error import NotFoundError, ValidationError
from api.models import AssistantUsage, Payment, Position, User
from api.models.base import utcnow
from api.services import account_service, auth_service, token_service
from api.utils.format_admin import format_admin_user
from api.utils.paginate import page_info, paginate


def _pro_filter():
    return or_(User.plan == "pro", User.pro_until > utcnow())


def _filtered(search="", plan="", role="", status=""):
    """Comptes repondant aux filtres de la liste (et de l'export)."""

    query = select(User)

    if search:

        pattern = f"%{search.strip()}%"

        query = query.where(or_(
            User.email.ilike(pattern),
            User.first_name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.phone.ilike(pattern)
        ))

    if plan == "pro":
        query = query.where(_pro_filter())
    elif plan == "free":
        query = query.where(~_pro_filter())

    if role:
        query = query.where(User.role == role)

    if status == "active":
        query = query.where(User.is_active.is_(True))
    elif status == "inactive":
        query = query.where(User.is_active.is_(False))

    return query


def list_users(db, page=1, limit=20, search="", plan="", role="", status=""):

    pages = paginate(page, limit)

    query = _filtered(search, plan, role, status)

    total = db.scalar(select(func.count()).select_from(query.subquery()))

    positions = (
        select(Position.user_id, func.count(Position.id).label("n"))
        .group_by(Position.user_id)
        .subquery()
    )

    rows = db.execute(
        query.add_columns(func.coalesce(positions.c.n, 0))
        .outerjoin(positions, positions.c.user_id == User.id)
        .order_by(User.created_at.desc(), User.id.desc())
        .offset(pages["offset"])
        .limit(pages["limit"])
    ).all()

    return {
        "items": [format_admin_user(user, count) for user, count in rows],
        "pagination": page_info(total, pages["page"], pages["limit"])
    }


def _get(db, user_id):

    user = db.get(User, user_id)

    if user is None:
        raise NotFoundError("Compte introuvable.")

    return user


def get_user(db, user_id):

    user = _get(db, user_id)

    payments = db.scalars(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())
    ).all()

    questions = db.scalar(
        select(func.coalesce(func.sum(AssistantUsage.count), 0))
        .where(AssistantUsage.user_id == user.id)
    )

    return {
        **format_admin_user(user, len(user.positions)),
        "positions_detail": [
            {
                "id": position.id,
                "symbol": position.symbol,
                "quantity": position.quantity,
                "buy_price": position.buy_price,
                "buy_date": position.buy_date
            }
            for position in user.positions
        ],
        "payments": [
            {
                "id": payment.id,
                "amount": payment.amount,
                "status": payment.status,
                "applied": payment.applied,
                "created_at": payment.created_at
            }
            for payment in payments
        ],
        "assistant_questions": questions
    }


def create_admin(db, email, password, first_name=None, last_name=None, phone=None):
    """Compte administrateur cree depuis le back-office, actif d'emblee. Le
    mot de passe choisi par l'admin createur est provisoire : le nouvel
    admin doit le changer a sa premiere connexion."""

    user = User(
        email=auth_service.check_new_account(db, email, password, admin=True),
        password_hash=token_service.hash_password(password),
        first_name=account_service.clean_text(first_name),
        last_name=account_service.clean_text(last_name),
        phone=account_service.clean_text(phone),
        role="admin",
        must_change_password=True,
        preferences={}
    )

    db.add(user)
    db.commit()

    return format_admin_user(user)


def update_user(db, admin, user_id, changes):
    """changes : champs envoyes par le back-office (les absents ne sont pas
    touches ; plan et role ne s'effacent pas)."""

    user = _get(db, user_id)

    role = changes.get("role")

    # Un admin ne se retire pas lui-meme le role : le back-office pourrait
    # se retrouver sans aucun administrateur.
    if role is not None and user.id == admin.id and role != "admin":
        raise ValidationError("Tu ne peux pas retirer ton propre rôle d'administrateur.")

    for field in ("plan", "role"):
        if changes.get(field) is not None:
            setattr(user, field, changes[field])

    account_service.update_profile(db, user, changes)

    return format_admin_user(user, len(user.positions))


def set_active(db, admin, user_id, active):
    """Active ou desactive un compte. Desactiver ferme aussi ses sessions :
    il est deconnecte de tous ses appareils."""

    user = _get(db, user_id)

    if not active and user.id == admin.id:
        raise ValidationError("Tu ne peux pas désactiver ton propre compte.")

    user.is_active = active

    db.commit()

    if not active:
        token_service.revoke_all(db, user.id)

    return format_admin_user(user, len(user.positions))


def delete_user(db, admin, user_id):
    """Supprime le compte et toutes ses donnees (positions, paiements,
    sessions), comme la suppression depuis l'app."""

    user = _get(db, user_id)

    if user.id == admin.id:
        raise ValidationError("Tu ne peux pas supprimer ton propre compte.")

    account_service.delete_account(db, user)

    return {"id": user_id}


EXPORT_HEADER = [
    "E-mail", "Prénom", "Nom", "Téléphone", "Rôle", "Offre", "Statut",
    "Inscription", "Dernière connexion"
]


def export_csv(db, search="", plan="", role="", status=""):
    """Comptes filtres comme la liste, au format CSV (sans pagination)."""

    users = db.scalars(
        _filtered(search, plan, role, status).order_by(User.created_at.desc(), User.id.desc())
    ).all()

    buffer = io.StringIO()

    writer = csv.writer(buffer)

    writer.writerow(EXPORT_HEADER)

    for user in users:
        writer.writerow([
            user.email,
            user.first_name or "",
            user.last_name or "",
            user.phone or "",
            user.role,
            user.effective_plan,
            "actif" if user.is_active else "désactivé",
            user.created_at.date().isoformat(),
            user.last_login_at.date().isoformat() if user.last_login_at else ""
        ])

    # BOM : Excel ouvre alors le fichier en UTF-8 (accents).
    return "\ufeff" + buffer.getvalue()


def revoke_sessions(db, user_id):
    """Deconnecte le compte de tous ses appareils (compte compromis)."""

    user = _get(db, user_id)

    token_service.revoke_all(db, user.id)

    return {"id": user.id}
