from datetime import datetime, timezone

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


# Noms explicites des index et contraintes : les migrations Alembic les
# retrouvent a l'identique sur SQLite et sur PostgreSQL.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    """SQLite rend les dates sans fuseau : on les relit en UTC."""

    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
