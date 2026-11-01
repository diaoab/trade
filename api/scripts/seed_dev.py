"""Cree des comptes de demonstration dans la base locale, pour essayer l'app
et le back-office sans s'inscrire : python -m api.scripts.seed_dev
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

# Compte du back-office (trade_admin).
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-local-1234"


def main():

    if IS_PROD:
        raise SystemExit("seed_dev ne doit jamais tourner en production.")

    with SessionLocal() as db:

        for email, password, role in (
            (DEMO_EMAIL, DEMO_PASSWORD, "user"),
            (ADMIN_EMAIL, ADMIN_PASSWORD, "admin")
        ):
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(User(
                    email=email,
                    password_hash=hash_password(password),
                    preferences={},
                    role=role
                ))

        db.commit()

    print(f"Compte de demonstration : {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"Compte du back-office   : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()
