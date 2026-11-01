from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, utcnow


class RefreshToken(Base):
    """Jeton de rafraichissement d'une session (un par appareil connecte).

    Seul le hash SHA-256 est stocke, jamais le jeton brut. Rotation a chaque
    usage : l'ancien jeton est marque `revoked` ; s'il est presente de
    nouveau, c'est qu'il a fuite, et toutes les sessions du compte sont
    fermees. Deconnexion et changement de mot de passe suppriment la ligne.
    """

    __tablename__ = "refresh_tokens"

    __table_args__ = (Index("ix_refresh_tokens_user_id_expires_at", "user_id", "expires_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow
    )
