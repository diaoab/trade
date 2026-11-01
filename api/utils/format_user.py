from api.services.account_service import assistant_quota


def format_user(db, user):
    """Compte tel que renvoye a l'app : jamais le hash du mot de passe."""

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "plan": user.effective_plan,
        "pro_until": user.pro_until.isoformat() if user.pro_until else None,
        "assistant": assistant_quota(db, user)
    }
