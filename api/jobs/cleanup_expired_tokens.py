"""Supprime les jetons de rafraichissement expires.

Planifiee chaque nuit par la crontab du serveur (cf. deploy/crontab) :
    docker compose -f docker-compose.prod.yml exec -T backend \
        python -m api.jobs.cleanup_expired_tokens
"""

import logging

from api.config.db import SessionLocal
from api.services import token_service
from api.utils.logger import configure_logging


logger = logging.getLogger("api.jobs.cleanup_expired_tokens")


def main():

    configure_logging()

    with SessionLocal() as db:
        deleted = token_service.purge_expired(db)

    logger.info("Jetons de rafraichissement supprimes : %s", deleted)


if __name__ == "__main__":
    main()
