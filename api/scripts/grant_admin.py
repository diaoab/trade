"""Donne (ou retire) l'acces au back-office a un compte existant :
    python -m api.scripts.grant_admin <email>
    python -m api.scripts.grant_admin <email> --revoke

Seul moyen de creer le premier administrateur : l'API ne permet pas de
s'attribuer ce role. S'appuie sur le .env du projet : cible la meme base
que l'API.
"""

import sys

from sqlalchemy import select

from api.config.db import SessionLocal
from api.models import User
from api.services.auth_service import normalise_email


def main(argv):

    if not argv or argv[0].startswith("-"):
        raise SystemExit("Usage : python -m api.scripts.grant_admin <email> [--revoke]")

    email = normalise_email(argv[0])
    role = "user" if "--revoke" in argv[1:] else "admin"

    with SessionLocal() as db:

        user = db.scalar(select(User).where(User.email == email))

        if user is None:
            raise SystemExit(
                f"Aucun compte avec l'e-mail « {email} » : le creer d'abord depuis l'app."
            )

        user.role = role
        db.commit()

    print(f"{email} : role = {role}")


if __name__ == "__main__":
    main(sys.argv[1:])
