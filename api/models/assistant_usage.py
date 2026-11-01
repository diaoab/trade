from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class AssistantUsage(Base):
    """Nombre de questions posees a l'assistant, par utilisateur et par
    jour (UTC)."""

    __tablename__ = "assistant_usage"

    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    day: Mapped[date] = mapped_column(Date)

    count: Mapped[int] = mapped_column(Integer, default=0)
