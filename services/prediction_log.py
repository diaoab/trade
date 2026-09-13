"""Journal des analyses demandees depuis l'application.

Chaque fois que l'utilisateur clique sur "Analyser", la decision et les
scores du moment sont ajoutes ici, avant que le resultat reel ne soit connu.
C'est la seule base qui permette, plus tard, de mesurer une performance en
conditions reelles jamais vue par l'entrainement -- contrairement meme au
test walk-forward (training.walk_forward), qui reste un backtest sur des
donnees deja passees au moment ou on l'execute.
"""

from datetime import datetime, timezone

import pandas as pd

from config import PREDICTION_LOG_PATH


LOG_COLUMNS = [
    "logged_at",
    "symbol",
    "structure_name",
    "session_date",
    "close",
    "decision",
    "score",
    "confidence",
    "technical_score",
    "ml_score",
    "probability_up",
    "risk_score",
    "weight_technique",
    "weight_ml",
    "weight_risque"
]


def log_prediction(
    symbol,
    structure_name,
    session_date,
    close,
    result,
    ml_result,
    weights
):
    """Ajoute une ligne au journal (cree le fichier avec son en-tete s'il
    n'existe pas encore). N'ecrase jamais les lignes precedentes."""

    row = {

        "logged_at": datetime.now(timezone.utc).isoformat(),

        "symbol": symbol,

        "structure_name": structure_name,

        "session_date": (
            session_date.isoformat()
            if hasattr(session_date, "isoformat")
            else session_date
        ),

        "close": float(close),

        "decision": result["decision"],

        "score": result["score"],

        "confidence": result["confidence"],

        "technical_score": result["technical_score"],

        "ml_score": result["ml_score"],

        "probability_up": ml_result["probability_up"],

        "risk_score": result["risk_score"],

        "weight_technique": weights["Technique"],

        "weight_ml": weights["Machine Learning"],

        "weight_risque": weights["Risque"]

    }

    frame = pd.DataFrame([row], columns=LOG_COLUMNS)

    frame.to_csv(
        PREDICTION_LOG_PATH,
        mode="a",
        header=not PREDICTION_LOG_PATH.exists(),
        index=False
    )


def load_prediction_log():
    """Relit le journal, ou un DataFrame vide (memes colonnes) s'il n'existe
    pas encore -- aucune analyse n'a ete lancee."""

    if not PREDICTION_LOG_PATH.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)

    return pd.read_csv(PREDICTION_LOG_PATH, parse_dates=["session_date"])
