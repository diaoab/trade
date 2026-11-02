from fastapi import BackgroundTasks, Depends
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.middlewares.auth import current_user
from api.models import User
from api.services import auth_service, mailer
from api.utils.format_user import format_user
from api.utils.response import created, ok
from api.validations.auth_validation import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    VerifyResetCodeIn
)


def register(body: RegisterIn, db: Session = Depends(get_db)):

    user, session = auth_service.register(db, body.email, body.password)

    return created({**session, "user": format_user(db, user)}, "Compte créé")


def login(body: LoginIn, db: Session = Depends(get_db)):

    user, session = auth_service.login(db, body.email, body.password)

    return ok({**session, "user": format_user(db, user)}, "Connexion réussie")


def refresh(body: RefreshIn, db: Session = Depends(get_db)):

    session = auth_service.refresh(db, body.refresh_token)

    return ok(
        {"token": session["token"], "refresh_token": session["refresh_token"]},
        "Jeton renouvelé"
    )


def logout(body: RefreshIn, db: Session = Depends(get_db)):
    """Pas d'authentification exigee : se deconnecter doit rester possible
    avec un jeton d'acces expire."""

    auth_service.logout(db, body.refresh_token)

    return ok(None, "Déconnexion réussie")


def change_password(
    body: ChangePasswordIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):

    session = auth_service.change_password(db, user, body.current_password, body.new_password)

    return ok(session, "Mot de passe modifié : les autres appareils sont déconnectés")


def forgot_password(
    body: ForgotPasswordIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Meme reponse que le compte existe ou non ; l'e-mail part apres la
    reponse, qui ne trahit donc pas non plus par sa duree."""

    email = auth_service.request_reset(db, body.email)

    if email is not None:
        background.add_task(mailer.send, **email)

    return ok(None, "Si un compte existe avec cette adresse, un code vient d'y être envoyé.")


def verify_reset_code(body: VerifyResetCodeIn, db: Session = Depends(get_db)):

    auth_service.verify_reset_code(db, body.email, body.code)

    return ok(None, "Code valide")


def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):

    auth_service.reset_password(db, body.email, body.code, body.new_password)

    return ok(None, "Mot de passe modifié : reconnecte-toi.")
