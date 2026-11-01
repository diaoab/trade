"""Corps de requete du portefeuille."""

from datetime import date

from pydantic import BaseModel, Field


class PositionIn(BaseModel):
    symbol: str = Field(max_length=50)
    quantity: float = Field(gt=0)
    buy_price: float = Field(gt=0)
    buy_date: date
