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
from services.market_data import load_structure
from services.targets import FUTURE_HORIZON_DAYS


# Horizon auquel une decision est jugee, en seances : celui de la cible du
# modele (cf. services.targets).
HORIZON_SESSIONS = FUTURE_HORIZON_DAYS

OUTCOME_PENDING = "en attente"
OUTCOME_RIGHT = "juste"
OUTCOME_WRONG = "fausse"
OUTCOME_UNJUDGED = "non jugée"
OUTCOME_UNKNOWN = "introuvable"


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


NUMERIC_LOG_COLUMNS = [
    "close",
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

        "probability_up": (
            ml_result["probability_up"]
            if ml_result is not None
            else None
        ),

        "risk_score": result["risk_score"],

        "weight_technique": weights["Technique"],

        "weight_ml": weights["Machine Learning"],

        "weight_risque": weights["Risque"]

    }

    frame = pd.DataFrame([row], columns=LOG_COLUMNS)

    # Creation exclusive de l'en-tete : tester "le fichier existe-t-il ?"
    # puis ecrire laissait deux analyses simultanees (deux onglets ouverts)
    # ecrire chacune leur en-tete.
    try:

        with open(PREDICTION_LOG_PATH, "x", encoding="utf-8") as handle:
            handle.write(",".join(LOG_COLUMNS) + "\n")

    except FileExistsError:
        pass

    frame.to_csv(
        PREDICTION_LOG_PATH,
        mode="a",
        header=False,
        index=False
    )


def load_prediction_log():
    """Relit le journal, ou un DataFrame vide (memes colonnes) s'il n'existe
    pas encore -- aucune analyse n'a ete lancee."""

    if not PREDICTION_LOG_PATH.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)

    log = pd.read_csv(PREDICTION_LOG_PATH, dtype=str)

    # Anciens journaux : un en-tete a pu etre ecrit deux fois (cf.
    # log_prediction), il se relit alors comme une ligne de donnees.
    log = log[log["logged_at"] != "logged_at"].reset_index(drop=True)

    log["session_date"] = pd.to_datetime(log["session_date"], errors="coerce")

    for column in NUMERIC_LOG_COLUMNS:
        log[column] = pd.to_numeric(log[column], errors="coerce")

    return log


def evaluate_predictions(log, load_history=load_structure):
    """Confronte chaque analyse du journal a ce que le cours a fait ensuite.

    Ajoute trois colonnes :
    - future_close : cloture HORIZON_SESSIONS seances apres la seance analysee
    - realized_return : variation entre les deux, sur les cours ajustes des
      dividendes (un detachement entre-temps n'est pas une baisse)
    - outcome : "juste" si ACHETER a ete suivi d'une hausse ou VENDRE d'une
      baisse, "fausse" dans le cas inverse, "non jugée" pour CONSERVER (ni
      hausse ni baisse ne lui donne tort) ou un cours inchange, "en attente"
      tant que l'historique ne va pas assez loin, "introuvable" si la
      structure ou la seance n'existe plus dans data/.

    load_history(symbol) doit renvoyer l'historique du titre ; injectable
    pour les tests.
    """

    evaluated = log.copy()

    future_closes = []
    realized_returns = []
    outcomes = []

    histories = {}

    for row in evaluated.itertuples():

        if row.symbol not in histories:

            try:
                histories[row.symbol] = load_history(row.symbol)
            except (FileNotFoundError, ValueError):
                histories[row.symbol] = None

        history = histories[row.symbol]

        future_close = None
        realized_return = None
        outcome = OUTCOME_UNKNOWN

        if (
            history is not None
            and "Date" in history.columns
            and not pd.isna(row.session_date)
        ):

            positions = history.index[history["Date"] == row.session_date]

            if len(positions) > 0:

                position = history.index.get_loc(positions[-1])

                if position + HORIZON_SESSIONS < len(history):

                    start_close = history["Close"].iloc[position]

                    future_close = history["Close"].iloc[
                        position + HORIZON_SESSIONS
                    ]

                    realized_return = future_close / start_close - 1

                    outcome = _judge(row.decision, realized_return)

                else:

                    outcome = OUTCOME_PENDING

        future_closes.append(future_close)
        realized_returns.append(realized_return)
        outcomes.append(outcome)

    evaluated["future_close"] = pd.array(future_closes, dtype="Float64")
    evaluated["realized_return"] = pd.array(realized_returns, dtype="Float64")
    evaluated["outcome"] = outcomes

    return evaluated


def _judge(decision, realized_return):

    if decision == "ACHETER" and realized_return > 0:
        return OUTCOME_RIGHT

    if decision == "VENDRE" and realized_return < 0:
        return OUTCOME_RIGHT

    if decision in ("ACHETER", "VENDRE") and realized_return != 0:
        return OUTCOME_WRONG

    return OUTCOME_UNJUDGED


def summarize_performance(evaluated):
    """Bilan par decision, sur les analyses dont l'issue est connue.

    Une meme seance analysee plusieurs fois ne compte qu'une fois (derniere
    analyse) : cliquer dix fois sur "Analyser" ne doit pas gonfler le bilan.
    Retourne {decision: {"count", "right", "hit_rate", "mean_return"}}.
    """

    known = evaluated.dropna(subset=["realized_return"])

    known = known.drop_duplicates(
        subset=["symbol", "session_date"],
        keep="last"
    )

    summary = {}

    for decision, group in known.groupby("decision"):

        judged = group[
            group["outcome"].isin([OUTCOME_RIGHT, OUTCOME_WRONG])
        ]

        summary[decision] = {

            "count": len(group),

            "right": int((judged["outcome"] == OUTCOME_RIGHT).sum()),

            "hit_rate": (
                float((judged["outcome"] == OUTCOME_RIGHT).mean())
                if len(judged) > 0
                else None
            ),

            "mean_return": float(group["realized_return"].mean())
        }

    return summary
