"""Envoi d'e-mails par l'API de Resend (https://resend.com/docs/api-reference).

Appele en tache de fond apres la reponse : une erreur d'envoi est
journalisee, jamais renvoyee au client.
"""

import httpx

from api.config import settings
from api.utils.logger import logger


RESEND_URL = "https://api.resend.com/emails"

TIMEOUT_SECONDS = 15


def send(to, subject, body):

    if not settings.RESEND_API_KEY:

        logger.warning("Resend non configuré : e-mail « %s » non envoyé à %s", subject, to)

        # Sans cle en developpement : le code reste lisible.
        if not settings.IS_PROD:
            logger.info("Contenu de l'e-mail non envoyé :\n%s", body)

        return

    try:

        response = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>",
                "to": [to],
                "subject": subject,
                "text": body
            },
            timeout=TIMEOUT_SECONDS
        )

        response.raise_for_status()

    except httpx.HTTPStatusError as error:
        logger.error(
            "Resend a refusé l'e-mail « %s » à %s : %s %s",
            subject, to, error.response.status_code, error.response.text[:300]
        )

    except httpx.HTTPError:
        logger.exception("Échec de l'envoi de l'e-mail « %s » à %s", subject, to)
