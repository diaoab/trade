"""Redefinit le mot de passe d'un compte :
    python -m api.scripts.reset_password <email> <nouveau_mot_de_passe>

Le hash en base est irreversible : on ne retrouve pas un mot de passe perdu,
on en pose un nouveau. Toutes les sessions ouvertes du compte sont fermees.
S'appuie sur le .env du projet : cible la meme base que l'API.
"""

import sys

from sqlalchemy import select

from api.config.db import SessionLocal
from api.models import User
from api.services import token_service
from api.services.auth_service import MIN_PASSWORD_LENGTH, normalise_email


def main(argv):

    if len(argv) != 2:
        raise SystemExit("Usage : python -m api.scripts.reset_password <email> <nouveau_mot_de_passe>")

    email = normalise_email(argv[0])
    password = argv[1]

    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Mot de passe trop court ({MIN_PASSWORD_LENGTH} caracteres minimum).")

    with SessionLocal() as db:

        user = db.scalar(select(User).where(User.email == email))

        if user is None:
            raise SystemExit(f"Aucun compte avec l'e-mail « {email} ».")

        user.password_hash = token_service.hash_password(password)
        db.commit()

        token_service.revoke_all(db, user.id)

    print(f"Mot de passe de {email} redefini ; sessions ouvertes fermees.")


if __name__ == "__main__":
    main(sys.argv[1:])
