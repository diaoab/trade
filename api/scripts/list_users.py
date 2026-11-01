"""Liste les comptes en base : python -m api.scripts.list_users

N'affiche jamais le hash du mot de passe, seulement de quoi identifier les
comptes (e-mail, offre, fin de la periode Pro). S'appuie sur le .env du
projet : cible la meme base que l'API.
"""

from sqlalchemy import func, select

from api.config.db import SessionLocal
from api.models import Position, User


def main():

    with SessionLocal() as db:

        rows = db.execute(
            select(User, func.count(Position.id))
            .outerjoin(Position, Position.user_id == User.id)
            .group_by(User.id)
            .order_by(User.created_at)
        ).all()

    if not rows:
        print("Aucun compte en base.")
        return

    print(f"{len(rows)} compte(s) :\n")

    for user, positions in rows:
        print(f"  id          : {user.id}")
        print(f"  email       : {user.email}")
        print(f"  role        : {user.role}")
        print(f"  offre       : {user.effective_plan} (attribuee : {user.plan})")
        print(f"  pro jusqu'au: {user.pro_until.isoformat() if user.pro_until else '-'}")
        print(f"  positions   : {positions}")
        print(f"  cree le     : {user.created_at.isoformat() if user.created_at else '?'}")
        print("")


if __name__ == "__main__":
    main()
