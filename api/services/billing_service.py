"""Abonnement Pro paye par PayDunya."""

from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import select

from api.config import settings
from api.errors.app_error import (
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError
)
from api.models import Payment, User
from api.models.base import aware, utcnow
from api.services import paydunya


def offer():

    return {
        "price": settings.PRO_PRICE_XOF,
        "currency": "XOF",
        "days": settings.PRO_DAYS,
        "assistant_limit": settings.ASSISTANT_DAILY_LIMITS["pro"],
        "available": paydunya.configured()
    }


def sync_payment(db, token):
    """Relit une facture chez PayDunya et, si elle est payee, prolonge
    l'offre Pro du compte (une seule fois). Retourne le Payment ou None."""

    payment = db.scalar(select(Payment).where(Payment.token == token))

    if payment is None:
        return None

    info = paydunya.confirm_invoice(token)

    payment.status = info["status"] or payment.status

    if (
        info["status"] == "completed"
        and not payment.applied
        and str(info["user_id"]) == str(payment.user_id)
        and info["amount"] >= payment.amount
    ):

        user = db.get(User, payment.user_id)

        now = utcnow()

        start = max(now, aware(user.pro_until)) if user.pro_until else now

        user.pro_until = start + timedelta(days=settings.PRO_DAYS)

        payment.applied = True

    db.commit()

    return payment


def checkout(db, user, redirect_url):
    """Cree une facture PayDunya d'un mois Pro ; renvoie l'adresse de la
    page de paiement a ouvrir."""

    if redirect_url and not any(
        redirect_url.startswith(prefix)
        for prefix in settings.APP_REDIRECT_PREFIXES
    ):
        raise ValidationError("Adresse de retour non autorisée.")

    try:
        token, checkout_url = paydunya.create_invoice(user)
    except paydunya.PaymentError as error:
        raise ServiceUnavailableError(str(error))

    db.add(Payment(
        user_id=user.id,
        token=token,
        amount=settings.PRO_PRICE_XOF,
        redirect_url=redirect_url
    ))

    db.commit()

    return {"checkout_url": checkout_url, "token": token}


def confirm(db, user, token):
    """Verifie une facture du compte (au retour de la page de paiement, si
    la notification de PayDunya n'est pas encore arrivee)."""

    payment = db.scalar(select(Payment).where(Payment.token == token))

    if payment is None or payment.user_id != user.id:
        raise NotFoundError("Paiement introuvable.")

    try:
        payment = sync_payment(db, token)
    except paydunya.PaymentError as error:
        raise ServiceUnavailableError(str(error))

    db.refresh(user)

    return payment


def return_target(db, token):
    """Ou renvoyer le client revenu de PayDunya : (adresse de l'app ou
    None, etat du paiement)."""

    payment = None

    if token:
        try:
            payment = sync_payment(db, token)
        except paydunya.PaymentError:
            payment = db.scalar(select(Payment).where(Payment.token == token))

    status = payment.status if payment else "unknown"

    if payment is None or not payment.redirect_url:
        return None, status

    separator = "&" if "?" in payment.redirect_url else "?"

    return (
        payment.redirect_url + separator + urlencode({"billing": status, "token": token}),
        status
    )


def handle_ipn(db, form):
    """Notification de PayDunya (formulaire, champs sous data[...])."""

    def field(name):
        values = form.get(name)
        return values[0] if values else None

    if not paydunya.valid_ipn_hash(field("data[hash]")):
        raise ForbiddenError("Signature invalide.")

    token = field("data[invoice][token]")

    if token:
        try:
            sync_payment(db, token)
        except paydunya.PaymentError as error:
            # PayDunya renverra la notification ; l'erreur est journalisee.
            raise ServiceUnavailableError(str(error))
