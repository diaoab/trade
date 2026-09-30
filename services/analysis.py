"""Analyse complete d'une seance : modele ML + moteur de decision.

Partage entre la page Analyse et la page Marche, pour qu'un meme titre
recoive exactement la meme decision des deux cotes.
"""

import pandas as pd

from services.decision_engine import analyze
from services.indicators import RSI_OVERBOUGHT, RSI_OVERSOLD
from services.market_data import cutoff_date
from services.predictor import ModelUnavailable, predict_row


def analyse_session(row, selected_parameters, weights, model_metadata):
    """Retourne (resultat du moteur, resultat ML ou None, poids appliques).

    - Modele absent ou illisible : l'analyse se fait sans lui (ml_result
      vaut None), le moteur sait conclure sur la seule base technique.
    - Modele qui ne bat pas la reference naive : il n'a pas montre qu'il
      prevoyait quoi que ce soit. Le laisser peser dans le score reviendrait
      a y melanger du bruit ; son poids est mis a zero et sa probabilite
      reste disponible a titre indicatif.
    """

    try:

        ml_result = predict_row(row)

    except ModelUnavailable:

        ml_result = None

    if model_metadata is not None and not model_metadata["beats_baseline"]:

        weights = {**weights, "Machine Learning": 0}

    result = analyze(
        row,
        ml_result,
        selected_parameters,
        weights
    )

    return result, ml_result, weights


# Colonnes sans lesquelles ni le graphique ni le moteur de decision ne
# peuvent fonctionner.
CORE_INDICATORS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "MACD_Signal"
]

# Une date butoir de dividende est signalee quand elle tombe dans ce delai.
CUTOFF_ALERT_DAYS = 7


def latest_sessions(prepared, count=1):
    """Dernieres seances exploitables d'un historique prepare (indicateurs
    calcules), de la plus ancienne a la plus recente."""

    usable = prepared.dropna(subset=CORE_INDICATORS)

    return [
        usable.iloc[position]
        for position in range(max(0, len(usable) - count), len(usable))
    ]


def next_dividend_cutoff(dividends, session_date):
    """Prochain detachement apres `session_date` :
    {"cutoff", "ex_date", "amount", "days_left"}, ou None."""

    if session_date is None or pd.isna(session_date):
        return None

    for dividend in dividends:

        ex_date = pd.Timestamp(dividend["ex_date"])

        if ex_date > session_date:

            cutoff = cutoff_date(ex_date)

            return {
                "cutoff": cutoff,
                "ex_date": ex_date,
                "amount": dividend["amount"],
                "days_left": (cutoff - session_date.normalize()).days
            }

    return None


def _rsi_zone(rsi):

    if rsi > RSI_OVERBOUGHT:
        return "surachat"

    if rsi < RSI_OVERSOLD:
        return "survente"

    return None


def session_changes(previous, current, previous_result, current_result):
    """Ce qui a change entre deux seances consecutives d'un titre, en
    phrases courtes : decision qui bascule, RSI qui entre en zone extreme,
    titre qui devient peu liquide. Liste vide si rien de notable."""

    changes = []

    if previous_result["decision"] != current_result["decision"]:

        changes.append(
            f"le signal passe de {previous_result['decision']} à "
            f"{current_result['decision']}"
        )

    zone = _rsi_zone(current["RSI"])

    if zone is not None and zone != _rsi_zone(previous["RSI"]):

        changes.append(f"le RSI entre en zone de {zone}")

    if (
        current_result["liquidity_warnings"]
        and not previous_result["liquidity_warnings"]
    ):

        changes.append("le titre devient peu liquide")

    return changes


# Periodes de comparaison a l'indice, en jours calendaires.
COMPARISON_PERIODS = {
    "1 mois": 30,
    "3 mois": 91,
    "1 an": 365
}


def _performance(history, end_date, days):
    """Variation du cours entre la derniere seance au plus tard `days` jours
    avant `end_date` et la derniere seance au plus tard a `end_date`. None
    si l'historique ne couvre pas la periode."""

    until_end = history[history["Date"] <= end_date]

    until_start = history[
        history["Date"] <= end_date - pd.Timedelta(days=days)
    ]

    if until_end.empty or until_start.empty:
        return None

    return float(
        until_end["Close"].iloc[-1]
        / until_start["Close"].iloc[-1]
        - 1
    )


def relative_performance(history, benchmark, end_date):
    """Compare un titre a l'indice de reference sur chaque periode de
    COMPARISON_PERIODS : [{"period", "stock", "benchmark", "gap"}], les
    periodes que l'un des deux historiques ne couvre pas etant ecartees.

    gap > 0 : le titre a fait mieux que l'indice.
    """

    rows = []

    for period, days in COMPARISON_PERIODS.items():

        stock = _performance(history, end_date, days)

        reference = _performance(benchmark, end_date, days)

        if stock is None or reference is None:
            continue

        rows.append({
            "period": period,
            "stock": stock,
            "benchmark": reference,
            "gap": stock - reference
        })

    return rows
