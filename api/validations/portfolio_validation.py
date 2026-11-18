"""Corps de requete du portefeuille."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class PositionIn(BaseModel):
    """Un achat se fait au cours actuel et a la date du jour : le prix et la
    date sont fixes par le serveur. buy_price et buy_date, envoyes par les
    anciennes versions de l'app, sont ignores."""

    symbol: str = Field(max_length=50)
    quantity: float = Field(gt=0)
    buy_price: Optional[float] = None
    buy_date: Optional[date] = None
