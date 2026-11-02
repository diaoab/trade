from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, utcnow


class PasswordResetCode(Base):
    """Code a 6 chiffres envoye par e-mail pour "mot de passe oublie".

    Seul un HMAC du code est stocke. Un code par compte (une nouvelle
    demande remplace la precedente), valable quelques minutes et pour un
    nombre limite d'essais.
    """

    __tablename__ = "password_reset_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    code_hash: Mapped[str] = mapped_column(String(64))

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow
    )
