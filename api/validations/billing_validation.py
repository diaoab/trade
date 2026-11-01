"""Corps de requete de l'abonnement (paiement PayDunya)."""

from pydantic import BaseModel, Field


class CheckoutIn(BaseModel):
    redirect_url: str = Field(default="", max_length=500)


class ConfirmIn(BaseModel):
    token: str = Field(max_length=100)
