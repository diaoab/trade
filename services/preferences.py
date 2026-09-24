"""Persistance sur disque des réglages choisis dans la page Paramètres.

st.session_state ne survit qu'à l'intérieur d'une session : un rechargement
de page (F5) ou un redémarrage du serveur en ouvre une nouvelle, vide. Pour
que la palette, les indicateurs et les poids "enregistrés" restent en place
après coup, on les recopie ici à chaque clic sur Enregistrer, et on les
relit au démarrage de l'app pour préremplir session_state.
"""

import json
import logging

from config import PREFERENCES_PATH


logger = logging.getLogger(__name__)


def load_preferences():
    """Renvoie les réglages enregistrés, ou {} si aucun (premier lancement,
    fichier absent ou illisible)."""

    if not PREFERENCES_PATH.exists():
        return {}

    try:

        with open(PREFERENCES_PATH, encoding="utf-8") as handle:
            return json.load(handle)

    except (json.JSONDecodeError, OSError):

        logger.warning(
            "Préférences illisibles (%s), reglages par defaut utilises.",
            PREFERENCES_PATH
        )

        return {}


def save_preferences(preferences):
    """Ecrase le fichier de réglages avec `preferences`."""

    with open(PREFERENCES_PATH, "w", encoding="utf-8") as handle:

        json.dump(
            preferences,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True
        )
