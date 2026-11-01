"""Paiement de l'offre Pro par PayDunya (mobile money et carte, zone UEMOA).

Parcours : l'app demande une facture (create_invoice) et ouvre la page de
paiement PayDunya ; une fois le paiement fait, PayDunya renvoie le client
sur /trade/v1/billing/return et notifie /trade/v1/billing/ipn. Dans les deux cas l'etat est
relu aupres de PayDunya (confirm_invoice) : on ne prolonge jamais l'offre
sur la seule foi de ce que le client ou la notification affirment.

Doc : https://developers.paydunya.com/doc/FR/http_json
"""

import hashlib
import hmac

import httpx

from api.config import settings


class PaymentError(RuntimeError):
    """PayDunya a refuse la demande ou est injoignable. Message destine a
    l'utilisateur."""


def _base_url():

    return (
        "https://app.paydunya.com/api/v1"
        if settings.PAYDUNYA_MODE == "live"
        else "https://app.paydunya.com/sandbox-api/v1"
    )


def configured():

    return all((
        settings.PAYDUNYA_MASTER_KEY,
        settings.PAYDUNYA_PRIVATE_KEY,
        settings.PAYDUNYA_TOKEN
    ))


def _headers():

    return {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": settings.PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": settings.PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": settings.PAYDUNYA_TOKEN
    }


def _request(method, path, client=None, **kwargs):

    if not configured():
        raise PaymentError("Le paiement n'est pas encore configuré sur le serveur.")

    client = client or httpx.Client(timeout=20)

    try:
        response = client.request(
            method,
            f"{_base_url()}{path}",
            headers=_headers(),
            **kwargs
        )
        data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise PaymentError("PayDunya est injoignable, réessaie plus tard.") from error

    if str(data.get("response_code")) != "00":
        raise PaymentError(
            f"PayDunya a refusé la demande : {data.get('response_text', 'erreur inconnue')}"
        )

    return data


def create_invoice(user, client=None):
    """Cree une facture d'un mois Pro. Retourne (token, adresse de la page
    de paiement)."""

    data = _request(
        "POST",
        "/checkout-invoice/create",
        client=client,
        json={
            "invoice": {
                "total_amount": settings.PRO_PRICE_XOF,
                "description": (
                    f"Offre Pro {settings.PAYDUNYA_STORE_NAME}, "
                    f"{settings.PRO_DAYS} jours"
                ),
                "customer": {"email": user.email}
            },
            "store": {"name": settings.PAYDUNYA_STORE_NAME},
            "custom_data": {"user_id": user.id},
            "actions": {
                "return_url": f"{settings.PUBLIC_API_URL}{settings.API_PREFIX}/billing/return",
                "cancel_url": f"{settings.PUBLIC_API_URL}{settings.API_PREFIX}/billing/return",
                "callback_url": f"{settings.PUBLIC_API_URL}{settings.API_PREFIX}/billing/ipn"
            }
        }
    )

    return data["token"], data["response_text"]


def confirm_invoice(token, client=None):
    """Etat d'une facture selon PayDunya : {"status", "amount", "user_id"}.
    status : pending, completed, cancelled ou failed."""

    data = _request("GET", f"/checkout-invoice/confirm/{token}", client=client)

    return {
        "status": data.get("status"),
        "amount": int(float((data.get("invoice") or {}).get("total_amount") or 0)),
        "user_id": (data.get("custom_data") or {}).get("user_id")
    }


def valid_ipn_hash(received):
    """La notification vient de PayDunya : son champ hash vaut le SHA-512
    de la cle principale."""

    expected = hashlib.sha512(settings.PAYDUNYA_MASTER_KEY.encode("utf-8")).hexdigest()

    return bool(received) and hmac.compare_digest(expected, str(received).lower())
