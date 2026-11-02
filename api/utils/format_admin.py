def format_admin_user(user, positions=0):
    """Compte tel que vu par le back-office : jamais le hash du mot de
    passe, ni les reglages personnels."""

    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "plan": user.plan,
        "effective_plan": user.effective_plan,
        "pro_until": user.pro_until,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "positions": positions
    }
