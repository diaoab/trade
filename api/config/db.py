"""Connexion a la base des comptes. Le schema est gere par les migrations
Alembic (api/migrations) : python -m alembic upgrade head."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.config.settings import DATABASE_URL


def make_engine(url=DATABASE_URL):

    connect_args = (
        {"check_same_thread": False}
        if url.startswith("sqlite")
        else {}
    )

    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = make_engine()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    """Dependance FastAPI : une session par requete."""

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
