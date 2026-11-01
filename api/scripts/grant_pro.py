"""Attribue (ou retire) l'offre Pro a la main, par exemple pour un compte
offert :
    python -m api.scripts.grant_pro <email>
    python -m api.scripts.grant_pro <email> --revoke

L'offre payee via PayDunya passe par pro_until et n'est pas touchee ici.
S'appuie sur le .env du projet : cible la meme base que l'API.
"""

import sys

from sqlalchemy import select

from api.config.db import SessionLocal
from api.models import User
from api.services.auth_service import normalise_email


def main(argv):

    if not argv or argv[0].startswith("-"):
        raise SystemExit("Usage : python -m api.scripts.grant_pro <email> [--revoke]")

    email = normalise_email(argv[0])
    plan = "free" if "--revoke" in argv[1:] else "pro"

    with SessionLocal() as db:

        user = db.scalar(select(User).where(User.email == email))

        if user is None:
            raise SystemExit(f"Aucun compte avec l'e-mail « {email} ».")

        user.plan = plan
        db.commit()

        print(f"{user.email} : offre attribuee = {user.plan}, en vigueur = {user.effective_plan}")


if __name__ == "__main__":
    main(sys.argv[1:])
