"""Corps de requete de l'authentification, valides par FastAPI avant le
controller (une erreur part en 422 au format { success, message, details })."""

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=1000)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class ForgotPasswordIn(BaseModel):
    email: str = Field(max_length=255)


class VerifyResetCodeIn(BaseModel):
    email: str = Field(max_length=255)
    code: str = Field(max_length=10)


class ResetPasswordIn(BaseModel):
    email: str = Field(max_length=255)
    code: str = Field(max_length=10)
    new_password: str = Field(max_length=128)
