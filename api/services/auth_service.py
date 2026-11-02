"""Inscription, connexion, sessions et mot de passe oublie."""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from sqlalchemy import delete, select

from api.config import settings
from api.errors.app_error import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
    ValidationError
)
from api.middlewares.auth import DISABLED_MESSAGE
from api.models import PasswordResetCode, User
from api.models.base import aware, utcnow
from api.services import token_service


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8

# Un compte admin ouvre le back-office : mot de passe plus robuste.
ADMIN_PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*\d)")

INVALID_CODE = "Code invalide ou expiré."

# Hash calcule pour un e-mail inconnu : la connexion prend alors le meme
# temps que pour un compte existant, et ne revele pas qu'il n'existe pas.
_DUMMY_HASH = token_service.hash_password("compte-inexistant")


def normalise_email(email):
    return email.strip().lower()


def check_password(password, admin=False):

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères."
        )

    if admin and not ADMIN_PASSWORD_PATTERN.match(password):
        raise ValidationError(
            "Le mot de passe d'un administrateur doit contenir au moins une majuscule et un chiffre."
        )


def check_new_account(db, email, password, admin=False):
    """E-mail normalise d'un nouveau compte (inscription ou creation depuis
    le back-office), apres controle de l'e-mail et du mot de passe."""

    email = normalise_email(email)

    if not EMAIL_PATTERN.match(email):
        raise ValidationError("Adresse e-mail invalide.")

    check_password(password, admin)

    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("Un compte existe déjà avec cette adresse.")

    return email


def register(db, email, password):

    email = check_new_account(db, email, password)

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

    # Apres le mot de passe : un tiers n'apprend pas qu'un compte est
    # desactive.
    if not user.is_active:
        raise ForbiddenError(DISABLED_MESSAGE)

    # Enregistre avec la session, par le commit de open_session.
    user.last_login_at = utcnow()

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

    check_password(new_password, admin=user.is_admin)

    user.password_hash = token_service.hash_password(new_password)
    user.must_change_password = False

    db.commit()

    token_service.revoke_all(db, user.id)

    return token_service.open_session(db, user)


# =========================================================
# MOT DE PASSE OUBLIE
# =========================================================

def _hash_code(user_id, code):
    """HMAC du code, lie au compte : une fuite de la base ne permet pas de
    retrouver les codes en essayant le million de combinaisons."""

    return hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        f"{user_id}:{code}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def request_reset(db, email):
    """Cree un code pour ce compte et rend l'e-mail a envoyer, ou None si
    le compte n'existe pas (ou est desactive). La reponse au client est la
    meme dans les deux cas : elle ne revele pas quels e-mails ont un
    compte."""

    user = db.scalar(select(User).where(User.email == normalise_email(email)))

    if user is None or not user.is_active:
        return None

    code = f"{secrets.randbelow(1_000_000):06d}"

    db.execute(
        delete(PasswordResetCode).where(PasswordResetCode.user_id == user.id),
        execution_options=token_service.NO_SYNC
    )

    db.add(PasswordResetCode(
        user_id=user.id,
        code_hash=_hash_code(user.id, code),
        expires_at=utcnow() + timedelta(minutes=settings.RESET_CODE_MINUTES),
        attempts=0
    ))

    db.commit()

    return {
        "to": user.email,
        "subject": "Ton code de réinitialisation",
        "body": (
            "Bonjour,\n\n"
            f"Voici ton code pour choisir un nouveau mot de passe : {code}\n\n"
            f"Il est valable {settings.RESET_CODE_MINUTES} minutes. "
            "Si tu n'as rien demandé, ignore cet e-mail : ton mot de passe ne change pas.\n\n"
            f"— {settings.MAIL_FROM_NAME}"
        )
    }


def _check_code(db, email, code):
    """Compte du code s'il est valide ; sinon BadRequestError, et un essai
    de plus compte contre ce code."""

    user = db.scalar(select(User).where(User.email == normalise_email(email)))

    stored = None if user is None else db.scalar(
        select(PasswordResetCode).where(PasswordResetCode.user_id == user.id)
    )

    if stored is None or not user.is_active:
        raise BadRequestError(INVALID_CODE)

    if aware(stored.expires_at) < utcnow() or stored.attempts >= settings.RESET_CODE_MAX_ATTEMPTS:
        db.delete(stored)
        db.commit()
        raise BadRequestError(INVALID_CODE)

    if not hmac.compare_digest(stored.code_hash, _hash_code(user.id, code.strip())):
        stored.attempts += 1
        db.commit()
        raise BadRequestError(INVALID_CODE)

    return user


def verify_reset_code(db, email, code):
    """Controle le code sans l'utiliser (etape "code" de l'ecran)."""

    _check_code(db, email, code)


def reset_password(db, email, code, new_password):
    """Nouveau mot de passe avec le code recu ; toutes les sessions sont
    fermees, il faut se reconnecter."""

    user = _check_code(db, email, code)

    check_password(new_password, admin=user.is_admin)

    user.password_hash = token_service.hash_password(new_password)
    user.must_change_password = False

    db.execute(
        delete(PasswordResetCode).where(PasswordResetCode.user_id == user.id),
        execution_options=token_service.NO_SYNC
    )

    db.commit()

    token_service.revoke_all(db, user.id)
