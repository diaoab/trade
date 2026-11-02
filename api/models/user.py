from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, aware, utcnow


class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    password_hash: Mapped[str] = mapped_column(String(255))

    # Identite facultative : l'inscription ne demande que l'e-mail, le
    # back-office peut completer.
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Un compte desactive par le back-office ne se connecte plus et ses
    # jetons d'acces sont refuses ; ses donnees sont conservees.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    # Mot de passe provisoire (admin cree depuis le back-office) : a changer
    # avant d'acceder au back-office.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # Offre attribuee a la main ("free" ou "pro"), par exemple pour un
    # compte offert. L'offre payee passe par pro_until (cf. effective_plan).
    plan: Mapped[str] = mapped_column(String(20), default="free")

    # Fin de la periode Pro payee via PayDunya, ou None.
    pro_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    preferences: Mapped[dict] = mapped_column(JSON, default=dict)

    # "user" ou "admin" : un admin se connecte au back-office (trade_admin).
    # Attribue par python -m api.scripts.grant_admin, jamais par l'API
    # publique.
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")

    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow
    )

    positions: Mapped[List["Position"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Position.buy_date"
    )

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def effective_plan(self):
        """Offre en vigueur : "pro" tant que la periode payee court."""

        if self.plan == "pro":
            return "pro"

        if self.pro_until is not None and aware(self.pro_until) > utcnow():
            return "pro"

        return "free"
