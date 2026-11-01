def format_admin_user(user, positions=0):
    """Compte tel que vu par le back-office : jamais le hash du mot de
    passe, ni les reglages personnels."""

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "plan": user.plan,
        "effective_plan": user.effective_plan,
        "pro_until": user.pro_until,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "positions": positions
    }
