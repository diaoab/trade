"""Chemins et constantes partagés par l'application et l'entraînement."""

import logging
from pathlib import Path


# Config unique du logging pour tout le projet : app Streamlit et
# entrainement partagent ce logger plutot que d'appeler print() eux-memes,
# pour que les messages restent visibles (et filtrables) meme quand l'app
# tourne en arriere-plan, hors de la console interactive.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
RESULT_DIR = BASE_DIR / "results"

REGISTRY_PATH = DATA_DIR / "structures.json"

MODEL_PATH = MODEL_DIR / "financial_model.pkl"
FEATURES_PATH = MODEL_DIR / "features.pkl"
MODEL_METADATA_PATH = MODEL_DIR / "metadata.json"
PROBA_REFERENCE_PATH = MODEL_DIR / "probability_reference.pkl"

# Journal des analyses demandees par l'utilisateur : chaque clic sur
# "Analyser" y ajoute une ligne, horodatee avant que le resultat futur ne
# soit connu. C'est la seule facon de mesurer plus tard une performance en
# conditions reelles, jamais influencee par l'entrainement -- contrairement
# meme au test walk-forward, qui reste un backtest sur donnees passees.
PREDICTION_LOG_PATH = RESULT_DIR / "prediction_log.csv"


# Colonnes minimales dont dépendent les indicateurs et le moteur de décision.
REQUIRED_COLUMNS = ["Close"]


# Constantes de l'UI Streamlit partagees entre le point d'entree (app.py,
# qui doit pre-remplir st.session_state avant que la page "Parametres" ne
# se soit forcement deja executee) et app_pages/parametres.py.
INDICATOR_OPTIONS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "Bollinger",
    "Momentum",
    "Volatilité"
]

INDICATOR_DEFAULTS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "Momentum",
    "Volatilité"
]

DEFAULT_WEIGHTS = {
    "Technique": 40,
    "Machine Learning": 40,
    "Risque": 20
}


for directory in (DATA_DIR, MODEL_DIR, RESULT_DIR):
    directory.mkdir(exist_ok=True)
