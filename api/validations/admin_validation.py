"""Corps de requete du back-office."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class UserUpdateIn(BaseModel):
    # Offre attribuee a la main ; l'offre payee (pro_until) n'est pas touchee.
    plan: Optional[Literal["free", "pro"]] = None
    role: Optional[Literal["user", "admin"]] = None
    # null efface la valeur ; un champ absent n'est pas touche.
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)


class AdminCreateIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)


class UserCreateIn(AdminCreateIn):
    """Compte cree depuis le back-office (utilisateur de l'app ou admin)."""

    role: Literal["user", "admin"] = "user"
    plan: Literal["free", "pro"] = "free"
    # Mot de passe provisoire : a changer a la premiere connexion.
    must_change_password: bool = True
