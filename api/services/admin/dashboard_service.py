"""Indicateurs du tableau de bord du back-office."""

from collections import Counter
from datetime import timedelta

from sqlalchemy import func, or_, select

from api.models import AssistantUsage, Payment, Position, User
from api.models.base import aware, utcnow
from core.engine import market_data
from core.engine.predictor import load_model_metadata


SIGNUP_DAYS = 30


def _count(db, *where):
    return db.scalar(select(func.count(User.id)).where(*where))


def stats(db):

    now = utcnow()

    week = now - timedelta(days=7)

    month = now - timedelta(days=SIGNUP_DAYS)

    paid = Payment.status == "completed"

    signup_dates = db.scalars(select(User.created_at).where(User.created_at >= month)).all()

    per_day = Counter(aware(created).date() for created in signup_dates)

    today = now.date()

    model = load_model_metadata() or {}

    return {
        "users": {
            "total": _count(db),
            "pro": _count(db, or_(User.plan == "pro", User.pro_until > now)),
            "admins": _count(db, User.role == "admin"),
            "inactive": _count(db, User.is_active.is_(False)),
            "new_7d": _count(db, User.created_at >= week),
            "new_30d": len(signup_dates),
            "active_7d": _count(db, User.last_login_at >= week)
        },
        "signups": [
            {"day": day, "count": per_day.get(day, 0)}
            for day in (today - timedelta(days=offset) for offset in range(SIGNUP_DAYS - 1, -1, -1))
        ],
        "payments": {
            "completed": db.scalar(select(func.count(Payment.id)).where(paid)),
            "pending": db.scalar(select(func.count(Payment.id)).where(Payment.status == "pending")),
            "revenue_total": db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(paid)),
            "revenue_30d": db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0))
                .where(paid, Payment.created_at >= month)
            )
        },
        "assistant": {
            "today": db.scalar(
                select(func.coalesce(func.sum(AssistantUsage.count), 0))
                .where(AssistantUsage.day == today)
            ),
            "last_7d": db.scalar(
                select(func.coalesce(func.sum(AssistantUsage.count), 0))
                .where(AssistantUsage.day >= week.date())
            )
        },
        "positions": db.scalar(select(func.count(Position.id))),
        "structures": len(market_data.get_structures()),
        "model": {
            "name": model.get("model"),
            "trained_at": model.get("trained_at"),
            "roc_auc": (model.get("test_scores") or {}).get("roc_auc"),
            "beats_baseline": model.get("beats_baseline")
        }
    }
