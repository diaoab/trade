from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base


class Position(Base):
    """Ligne du portefeuille d'un utilisateur."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    symbol: Mapped[str] = mapped_column(String(50))

    quantity: Mapped[float] = mapped_column(Float)

    buy_price: Mapped[float] = mapped_column(Float)

    buy_date: Mapped[date] = mapped_column(Date)

    user: Mapped["User"] = relationship(back_populates="positions")
