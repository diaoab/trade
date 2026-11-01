"""Mots de passe, jetons d'acces et jetons de rafraichissement.

Hachage PBKDF2 de la bibliotheque standard (pas de dependance de plus).
Jeton d'acces : JWT court, envoye dans l'en-tete Authorization. Jeton de
rafraichissement : JWT long signe d'un autre secret, dont seul le hash est
stocke en base (table refresh_tokens), renouvele a chaque usage.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt
from sqlalchemy import delete, select

from api.config import settings
from api.errors.app_error import UnauthorizedError
from api.models import RefreshToken
from api.models.base import aware, utcnow


PBKDF2_ITERATIONS = 600_000

ALGORITHM = "HS256"

# Suppressions et mises a jour en masse : la base fait foi, sans comparer
# en Python les objets deja charges (SQLite les rend sans fuseau).
NO_SYNC = {"synchronize_session": False}


# =========================================================
# MOTS DE PASSE
# =========================================================

def hash_password(password):

    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        PBKDF2_ITERATIONS
    ).hex()

    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password, stored):

    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        int(iterations)
    ).hex()

    return hmac.compare_digest(candidate, digest)


# =========================================================
# JETON D'ACCES
# =========================================================

def create_access_token(user_id):

    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def read_access_token(token):
    """Id du compte porteur du jeton ; UnauthorizedError sinon."""

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Session expirée : renouvelle le jeton.")
    except jwt.PyJWTError:
        raise UnauthorizedError("Jeton invalide.")

    if payload.get("type") != "access":
        raise UnauthorizedError("Jeton invalide.")

    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedError("Jeton invalide.")


# =========================================================
# JETON DE RAFRAICHISSEMENT
# =========================================================

def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_refresh_token(db, user_id):
    """Emet un jeton, stocke son hash, purge les jetons expires du compte et
    ferme les sessions les plus anciennes au-dela de MAX_REFRESH_TOKENS."""

    now = utcnow()

    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_DAYS)

    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            # Deux jetons emis dans la meme seconde restent distincts.
            "jti": secrets.token_hex(16),
            "exp": expires_at
        },
        settings.JWT_REFRESH_SECRET,
        algorithm=ALGORITHM
    )

    db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.expires_at < now
        ),
        execution_options=NO_SYNC
    )

    active = db.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .order_by(RefreshToken.created_at.desc(), RefreshToken.id.desc())
    ).all()

    for old in active[settings.MAX_REFRESH_TOKENS - 1:]:
        db.delete(old)

    db.add(RefreshToken(user_id=user_id, token_hash=_hash(token), expires_at=expires_at))

    return token


def open_session(db, user):
    """Jetons d'une nouvelle session (inscription, connexion)."""

    refresh_token = _create_refresh_token(db, user.id)

    db.commit()

    return {
        "token": create_access_token(user.id),
        "refresh_token": refresh_token
    }


def rotate(db, refresh_token):
    """Echange un jeton de rafraichissement contre une nouvelle paire.

    Un jeton deja revoque presente de nouveau signale une fuite (il a ete
    copie puis utilise par quelqu'un d'autre) : toutes les sessions du
    compte sont alors fermees.
    """

    invalid = UnauthorizedError("Session expirée : reconnecte-toi.")

    try:
        payload = jwt.decode(
            refresh_token,
            settings.JWT_REFRESH_SECRET,
            algorithms=[ALGORITHM]
        )
    except jwt.PyJWTError:
        raise invalid

    if payload.get("type") != "refresh":
        raise invalid

    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(refresh_token))
    )

    if stored is None or aware(stored.expires_at) < utcnow():
        raise invalid

    if stored.revoked:
        revoke_all(db, stored.user_id)
        raise invalid

    stored.revoked = True

    new_refresh = _create_refresh_token(db, stored.user_id)

    db.commit()

    return {
        "user_id": stored.user_id,
        "token": create_access_token(stored.user_id),
        "refresh_token": new_refresh
    }


def revoke(db, refresh_token):
    """Ferme la session de ce jeton (deconnexion). Sans effet si inconnu."""

    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(refresh_token))
    )

    if stored is not None:
        db.delete(stored)
        db.commit()


def revoke_all(db, user_id):
    """Ferme toutes les sessions du compte (fuite, changement de mot de
    passe)."""

    db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user_id),
        execution_options=NO_SYNC
    )

    db.commit()


def purge_expired(db):
    """Supprime les jetons expires (tache planifiee). Les jetons revoques
    par rotation restent jusqu'a leur expiration : c'est ce qui permet de
    reconnaitre un jeton vole presente une seconde fois."""

    result = db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < utcnow()),
        execution_options=NO_SYNC
    )

    db.commit()

    return result.rowcount
