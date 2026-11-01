"""Tache du soir de seance : cours du jour depuis le flux, puis (option
--retrain) reentrainement du modele.

Planifiee par la crontab du serveur (cf. deploy/crontab) :
    docker compose -f docker-compose.prod.yml exec -T backend \
        python -m api.jobs.refresh_market --retrain
"""

import argparse
import json
import logging
import sys

from api.services import admin_service, quotes_feed
from api.utils.logger import configure_logging


logger = logging.getLogger("api.jobs.refresh_market")


def main(argv=None):

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrain", action="store_true", help="reentrainer le modele ensuite")
    args = parser.parse_args(argv)

    configure_logging()

    try:
        report = quotes_feed.refresh()
    except Exception:
        logger.exception("Rafraichissement des cours en echec")
        return 1

    logger.info("Cours mis a jour : %s", json.dumps(report, default=str, ensure_ascii=False))

    if args.retrain:
        return admin_service.retrain()

    return 0


if __name__ == "__main__":
    sys.exit(main())
