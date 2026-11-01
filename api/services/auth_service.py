"""Inscription, connexion et sessions."""

import re

from sqlalchemy import select

from api.errors.app_error import ConflictError, UnauthorizedError, ValidationError
from api.models import User
from api.services import token_service


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8

# Hash calcule pour un e-mail inconnu : la connexion prend alors le meme
# temps que pour un compte existant, et ne revele pas qu'il n'existe pas.
_DUMMY_HASH = token_service.hash_password("compte-inexistant")


def normalise_email(email):
    return email.strip().lower()


def register(db, email, password):

    email = normalise_email(email)

    if not EMAIL_PATTERN.match(email):
        raise ValidationError("Adresse e-mail invalide.")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères."
        )

    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("Un compte existe déjà avec cette adresse.")

    user = User(
        email=email,
        password_hash=token_service.hash_password(password),
        preferences={}
    )

    db.add(user)
    db.commit()

    return user, token_service.open_session(db, user)


def login(db, email, password):

    user = db.scalar(select(User).where(User.email == normalise_email(email)))

    stored = user.password_hash if user is not None else _DUMMY_HASH

    if not token_service.verify_password(password, stored) or user is None:
        raise UnauthorizedError("E-mail ou mot de passe incorrect.")

    return user, token_service.open_session(db, user)


def refresh(db, refresh_token):
    return token_service.rotate(db, refresh_token)


def logout(db, refresh_token):
    token_service.revoke(db, refresh_token)


def change_password(db, user, current_password, new_password):
    """Change le mot de passe et ferme toutes les sessions ouvertes ; une
    nouvelle session est rendue pour l'appareil qui a fait la demande."""

    if not token_service.verify_password(current_password, user.password_hash):
        raise UnauthorizedError("Mot de passe actuel incorrect.")

    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères."
        )

    user.password_hash = token_service.hash_password(new_password)

    db.commit()

    token_service.revoke_all(db, user.id)

    return token_service.open_session(db, user)
