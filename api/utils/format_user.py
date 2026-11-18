from api.config import settings
from api.services.account_service import assistant_quota


def plan_limits(user):
    """Limites de l'offre du compte : {"positions", "favorites"}, None = sans
    limite."""

    if user.effective_plan == "pro":
        return {key: None for key in settings.FREE_LIMITS}

    return dict(settings.FREE_LIMITS)


def format_user(db, user):
    """Compte tel que renvoye a l'app : jamais le hash du mot de passe."""

    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "role": user.role,
        "must_change_password": user.must_change_password,
        "plan": user.effective_plan,
        "pro_until": user.pro_until.isoformat() if user.pro_until else None,
        "assistant": assistant_quota(db, user),
        "limits": plan_limits(user)
    }
