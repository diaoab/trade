"""Corps de requete du compte (profil et reglages de l'utilisateur)."""

from typing import List, Optional

from pydantic import BaseModel, Field


class PreferencesIn(BaseModel):
    selected_parameters: Optional[List[str]] = None
    adjust_dividends: Optional[bool] = None
    round_trip_fee: Optional[float] = Field(default=None, ge=0, le=20)


class ProfileIn(BaseModel):
    # null efface la valeur ; un champ absent n'est pas touche.
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)
