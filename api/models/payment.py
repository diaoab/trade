from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, utcnow


class Payment(Base):
    """Facture PayDunya. `applied` garantit qu'un meme paiement ne
    prolonge l'offre qu'une fois, meme si la notification (IPN) et le
    retour du client arrivent tous les deux."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    token: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    amount: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(20), default="pending")

    applied: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ou renvoyer l'utilisateur apres paiement (app mobile ou web).
    redirect_url: Mapped[str] = mapped_column(String(500), default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow
    )
