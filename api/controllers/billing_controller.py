from html import escape
from urllib.parse import parse_qs

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.middlewares.auth import current_user
from api.models import User
from api.services import billing_service
from api.utils.format_user import format_user
from api.utils.response import ok
from api.validations.billing_validation import CheckoutIn, ConfirmIn


def offer():
    return ok(billing_service.offer())


def checkout(
    body: CheckoutIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    return ok(billing_service.checkout(db, user, body.redirect_url), "Facture créée")


def confirm(
    body: ConfirmIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):

    payment = billing_service.confirm(db, user, body.token)

    return ok({"status": payment.status, "user": format_user(db, user)})


def payment_return(token: str = "", db: Session = Depends(get_db)):
    """Page ou PayDunya renvoie le client : verifie la facture, puis le
    renvoie dans l'app. Reponse HTML ou redirection, pas du JSON."""

    target, status = billing_service.return_target(db, token)

    if target:
        return RedirectResponse(target)

    message = (
        "Paiement reçu, ton offre Pro est active."
        if status == "completed"
        else "Paiement non finalisé."
    )

    return HTMLResponse(
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<body style='font-family:system-ui;text-align:center;padding:48px'>"
        f"<h2>{escape(message)}</h2><p>Tu peux revenir dans l'application.</p></body>"
    )


async def ipn(request: Request, db: Session = Depends(get_db)):

    form = parse_qs((await request.body()).decode("utf-8"))

    billing_service.handle_ipn(db, form)

    return ok(None, "Notification traitée")
