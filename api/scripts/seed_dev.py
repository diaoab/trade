"""Cree un compte de demonstration dans la base locale, pour essayer l'app
sans s'inscrire : python -m api.scripts.seed_dev
(apres python -m alembic upgrade head)

Developpement uniquement : refuse de tourner avec ENV=production.
"""

from sqlalchemy import select

from api.config.db import SessionLocal
from api.config.settings import IS_PROD
from api.models import User
from api.services.token_service import hash_password


DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-local-1234"


def main():

    if IS_PROD:
        raise SystemExit("seed_dev ne doit jamais tourner en production.")

    with SessionLocal() as db:

        if db.scalar(select(User).where(User.email == DEMO_EMAIL)) is None:
            db.add(User(
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                preferences={}
            ))
            db.commit()

    print(f"Compte de demonstration : {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
