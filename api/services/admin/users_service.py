"""Gestion des comptes depuis le back-office."""

from sqlalchemy import func, or_, select

from api.errors.app_error import NotFoundError, ValidationError
from api.models import AssistantUsage, Payment, Position, User
from api.models.base import utcnow
from api.services import token_service
from api.utils.format_admin import format_admin_user
from api.utils.paginate import page_info, paginate


def _pro_filter():
    return or_(User.plan == "pro", User.pro_until > utcnow())


def list_users(db, page=1, limit=20, search="", plan="", role=""):

    pages = paginate(page, limit)

    query = select(User)

    if search:
        query = query.where(User.email.ilike(f"%{search.strip().lower()}%"))

    if plan == "pro":
        query = query.where(_pro_filter())
    elif plan == "free":
        query = query.where(~_pro_filter())

    if role:
        query = query.where(User.role == role)

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


def update_user(db, admin, user_id, plan=None, role=None):

    user = _get(db, user_id)

    # Un admin ne se retire pas lui-meme le role : le back-office pourrait
    # se retrouver sans aucun administrateur.
    if role is not None and user.id == admin.id and role != "admin":
        raise ValidationError("Tu ne peux pas retirer ton propre rôle d'administrateur.")

    if plan is not None:
        user.plan = plan

    if role is not None:
        user.role = role

    db.commit()

    return format_admin_user(user, len(user.positions))


def revoke_sessions(db, user_id):
    """Deconnecte le compte de tous ses appareils (compte compromis)."""

    user = _get(db, user_id)

    token_service.revoke_all(db, user.id)

    return {"id": user.id}
