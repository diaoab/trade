"""Administration des donnees : historiques, cours du jour, modele."""

import io
import logging
import os
import subprocess
import sys
import time

from core.constants import MODEL_DIR

from core.engine import market_data
from core.engine.predictor import load_model_metadata

from api.errors.app_error import BadGatewayError, ServiceUnavailableError, ValidationError
from api.services import market_service, quotes_feed


logger = logging.getLogger(__name__)

# Verrou de l'entrainement : la crontab du soir et /admin/retrain peuvent
# le lancer en meme temps, et deux entrainements paralleles saturent la
# memoire du conteneur. Fichier plutot que verrou en memoire : les deux
# passent par des processus differents.
TRAINING_LOCK = MODEL_DIR / ".training.lock"

# Au-dela, un verrou est celui d'un entrainement interrompu (conteneur
# redemarre) et peut etre repris.
STALE_LOCK_SECONDS = 2 * 3600


def list_structures():
    """Titres disponibles, avec l'etendue de leur historique : un titre dont
    la derniere seance date se voit tout de suite."""

    rows = []

    for symbol, entry in market_data.get_structures().items():

        row = {"symbol": symbol, "name": entry["name"], "dividends": len(entry["dividends"])}

        try:
            df = market_data.load_structure(symbol, adjust_dividends=False)
            dates = df["Date"] if "Date" in df else df.index
            row.update(rows=len(df), first_date=dates.min(), last_date=dates.max(), error=None)
        except Exception as error:
            row.update(rows=0, first_date=None, last_date=None, error=str(error))

        rows.append(row)

    return market_service.to_json(rows)


def model_status():
    """Fiche du dernier entrainement, et si un entrainement tourne."""

    return {
        "metadata": market_service.to_json(load_model_metadata()),
        "training": TRAINING_LOCK.exists()
    }


def upload_structure(name, content):
    """Importe ou complete l'historique d'un titre a partir d'un classeur
    .xlsx."""

    try:
        symbol, report = market_data.save_uploaded_structure(
            io.BytesIO(content),
            market_data.match_structure_name(name)
        )
    except ValueError as error:
        raise ValidationError(str(error))

    return market_service.to_json({"symbol": symbol, "rows_added": report["rows_added"]})


def refresh_quotes():
    """Recupere les cours du jour depuis le flux (QUOTES_FEED_URL)."""

    try:
        return quotes_feed.refresh()
    except RuntimeError as error:
        raise ServiceUnavailableError(str(error))
    except Exception as error:
        raise BadGatewayError(f"Flux de cours illisible : {error}")


def _acquire_training_lock():

    try:
        if time.time() - TRAINING_LOCK.stat().st_mtime > STALE_LOCK_SECONDS:
            TRAINING_LOCK.unlink()
    except FileNotFoundError:
        pass

    try:
        os.close(os.open(TRAINING_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False

    return True


def retrain():
    """Reentraine le modele (quelques minutes), dans un processus a part
    pour ne pas bloquer l'API. Ne fait rien si un entrainement tourne deja."""

    if not _acquire_training_lock():
        logger.warning("Entrainement deja en cours : demande ignoree")
        return 0

    try:
        result = subprocess.run([sys.executable, "-m", "core.training.train"], check=False)
    finally:
        TRAINING_LOCK.unlink(missing_ok=True)

    if result.returncode != 0:
        logger.error("Entrainement du modele en echec (code %s)", result.returncode)

    return result.returncode
