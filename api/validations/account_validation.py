"""Corps de requete du compte (reglages de l'utilisateur)."""

from typing import List, Optional

from pydantic import BaseModel, Field


class PreferencesIn(BaseModel):
    selected_parameters: Optional[List[str]] = None
    adjust_dividends: Optional[bool] = None
    round_trip_fee: Optional[float] = Field(default=None, ge=0, le=20)
