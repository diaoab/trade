"""Compte, reglages et quota de l'assistant."""

from datetime import datetime, timezone

from sqlalchemy import select

from api.config.constants import INDICATOR_OPTIONS

from api.config.settings import ASSISTANT_DAILY_LIMITS
from api.errors.app_error import ValidationError
from api.models import AssistantUsage, Payment, RefreshToken
from api.services import market_service


def usage_row(db, user):

    today = datetime.now(timezone.utc).date()

    return db.scalar(
        select(AssistantUsage).where(
            AssistantUsage.user_id == user.id,
            AssistantUsage.day == today
        )
    )


def assistant_quota(db, user):

    row = usage_row(db, user)

    return {
        "used": row.count if row else 0,
        "limit": ASSISTANT_DAILY_LIMITS.get(user.effective_plan, 0)
    }


def delete_account(db, user):
    """Suppression du compte et de toutes ses donnees (exigee par l'App
    Store et le Play Store pour toute app qui permet d'en creer un)."""

    for table in (AssistantUsage, Payment, RefreshToken):
        db.query(table).filter(table.user_id == user.id).delete()

    db.delete(user)
    db.commit()


def get_preferences(user):

    return {
        **market_service.user_settings(user.preferences),
        "indicator_options": INDICATOR_OPTIONS
    }


def update_preferences(db, user, updates):

    if "selected_parameters" in updates:

        unknown = set(updates["selected_parameters"]) - set(INDICATOR_OPTIONS)

        if unknown:
            raise ValidationError("Indicateurs inconnus : " + ", ".join(sorted(unknown)))

    # Nouveau dict : SQLAlchemy ne voit pas une modification en place d'une
    # colonne JSON.
    user.preferences = {**(user.preferences or {}), **updates}

    db.commit()

    return get_preferences(user)
