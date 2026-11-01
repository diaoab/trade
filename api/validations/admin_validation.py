"""Corps de requete du back-office."""

from typing import Literal, Optional

from pydantic import BaseModel


class UserUpdateIn(BaseModel):
    # Offre attribuee a la main ; l'offre payee (pro_until) n'est pas touchee.
    plan: Optional[Literal["free", "pro"]] = None
    role: Optional[Literal["user", "admin"]] = None
