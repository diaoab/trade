"""Journalisation de l'API.

Developpement : lignes lisibles dans la console. Production : JSON (une
ligne par evenement, facile a filtrer) dans la console et dans LOG_DIR
(app.log, error.log), avec rotation par taille.
"""

import json
import logging
import os
from logging.handlers import RotatingFileHandler

from api.config.settings import IS_PROD, LOG_DIR, LOG_LEVEL


logger = logging.getLogger("api")


class JsonFormatter(logging.Formatter):

    RESERVED = set(vars(logging.makeLogRecord({})))

    def format(self, record):

        entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage()
        }

        # Champs passes via extra={...}
        entry.update({
            key: value
            for key, value in vars(record).items()
            if key not in self.RESERVED and not key.startswith("_")
        })

        if record.exc_info:
            entry["stack"] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging():

    formatter = (
        JsonFormatter()
        if IS_PROD
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    handlers = [console]

    if IS_PROD:

        os.makedirs(LOG_DIR, exist_ok=True)

        app_file = RotatingFileHandler(
            os.path.join(LOG_DIR, "app.log"),
            maxBytes=20 * 1024 * 1024,
            backupCount=10
        )

        error_file = RotatingFileHandler(
            os.path.join(LOG_DIR, "error.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        error_file.setLevel(logging.ERROR)

        for handler in (app_file, error_file):
            handler.setFormatter(formatter)
            handlers.append(handler)

    root = logging.getLogger()

    root.handlers = handlers

    root.setLevel(LOG_LEVEL)

    # Uvicorn journalise deja chaque requete ; le middleware request_logger
    # le fait au format de l'API.
    logging.getLogger("uvicorn.access").disabled = True
