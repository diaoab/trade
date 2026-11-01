"""Paiements PayDunya, vus depuis le back-office."""

from sqlalchemy import func, select

from api.models import Payment, User
from api.utils.paginate import page_info, paginate


def list_payments(db, page=1, limit=20, status=""):

    pages = paginate(page, limit)

    query = select(Payment, User.email).join(User, User.id == Payment.user_id)

    if status:
        query = query.where(Payment.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery()))

    rows = db.execute(
        query.order_by(Payment.created_at.desc(), Payment.id.desc())
        .offset(pages["offset"])
        .limit(pages["limit"])
    ).all()

    return {
        "items": [
            {
                "id": payment.id,
                "user_id": payment.user_id,
                "email": email,
                "amount": payment.amount,
                "status": payment.status,
                "applied": payment.applied,
                "created_at": payment.created_at
            }
            for payment, email in rows
        ],
        "pagination": page_info(total, pages["page"], pages["limit"])
    }
