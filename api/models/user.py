from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, aware, utcnow


class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    password_hash: Mapped[str] = mapped_column(String(255))

    # Offre attribuee a la main ("free" ou "pro"), par exemple pour un
    # compte offert. L'offre payee passe par pro_until (cf. effective_plan).
    plan: Mapped[str] = mapped_column(String(20), default="free")

    # Fin de la periode Pro payee via PayDunya, ou None.
    pro_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    preferences: Mapped[dict] = mapped_column(JSON, default=dict)

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
    def effective_plan(self):
        """Offre en vigueur : "pro" tant que la periode payee court."""

        if self.plan == "pro":
            return "pro"

        if self.pro_until is not None and aware(self.pro_until) > utcnow():
            return "pro"

        return "free"
