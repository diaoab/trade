"""Backtest des signaux techniques du moteur de decision.

Rejoue, seance par seance sur tout l'historique, ce que chaque indicateur
aurait dit ce jour-la, et le confronte a la variation du cours sur les
seances suivantes. Sert a verifier sur des faits que les conventions de
services.decision_engine (cours au-dessus de la MM20 = favorable, RSI sous
30 = favorable...) ont bien ete suivies de hausses ou de baisses sur les
titres du catalogue.

La composante ML n'est pas rejouee ici : le modele a ete entraine sur ces
memes seances, le rejouer dessus mesurerait sa memoire et non sa capacite a
prevoir. Son evaluation honnete reste training.train (jeu de test) et
training.walk_forward.
"""

import pandas as pd

from services.decision_engine import (
    DECISION_BUY_THRESHOLD,
    DECISION_HOLD_THRESHOLD,
    TECHNICAL_SCORE_NEUTRAL,
    analyze
)
from services.indicators import calculate_indicators
from services.targets import FUTURE_HORIZON_DAYS, compute_future_return


# Indicateurs qui deplacent le score technique. "Volatilité" n'en fait pas
# partie : elle alimente le score de risque, pas un signal de sens.
SIGNAL_INDICATORS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "Bollinger",
    "Momentum"
]

REQUIRED_COLUMNS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "MACD_Signal",
    "Bollinger_Upper",
    "Bollinger_Lower",
    "Return_5D",
    "Future_Return"
]

NEUTRAL_ML_RESULT = {"probability_up": 0.5}

TECHNICAL_ONLY = {"Technique": 100, "Machine Learning": 0, "Risque": 0}

SIGNAL_LABELS = {
    1: "favorable",
    0: "neutre",
    -1: "défavorable"
}


def _technical_score(row, indicators):

    return analyze(
        row,
        NEUTRAL_ML_RESULT,
        indicators,
        TECHNICAL_ONLY
    )["technical_score"]


def replay_signals(histories):
    """Rejoue le moteur sur chaque seance de chaque titre.

    histories : {symbole: DataFrame d'historique normalise}. Retourne une
    ligne par seance exploitable, avec le signal de chaque indicateur
    (+1 favorable, 0 neutre, -1 defavorable), le score technique tous
    indicateurs confondus et la variation du cours sur les
    FUTURE_HORIZON_DAYS seances suivantes.

    Le signal d'un indicateur est lu en appelant le moteur avec ce seul
    indicateur : ce backtest ne peut donc pas diverger des regles reellement
    appliquees dans l'application.
    """

    rows = []

    for symbol, history in histories.items():

        prepared = calculate_indicators(history)

        prepared["Future_Return"] = compute_future_return(prepared["Close"])

        prepared = prepared.dropna(subset=REQUIRED_COLUMNS)

        for _, session in prepared.iterrows():

            row = {
                "Symbol": symbol,
                "Date": session.get("Date"),
                "Future_Return": session["Future_Return"],
                "Technical_Score": _technical_score(
                    session,
                    SIGNAL_INDICATORS
                )
            }

            for indicator in SIGNAL_INDICATORS:

                deviation = (
                    _technical_score(session, [indicator])
                    - TECHNICAL_SCORE_NEUTRAL
                )

                row[indicator] = (deviation > 0) - (deviation < 0)

            rows.append(row)

    return pd.DataFrame(
        rows,
        columns=["Symbol", "Date", "Future_Return", "Technical_Score"]
        + SIGNAL_INDICATORS
    )


def _stats(future_returns):

    return {
        "Séances": len(future_returns),
        "Hausse ensuite (%)": (future_returns > 0).mean() * 100,
        "Baisse ensuite (%)": (future_returns < 0).mean() * 100,
        "Variation moyenne (%)": future_returns.mean() * 100
    }


def summarize_signals(replayed):
    """Ce qui a suivi chaque signal, indicateur par indicateur.

    La premiere ligne ("Toutes les séances") est la reference : un signal
    n'apporte quelque chose que s'il s'en ecarte nettement.
    """

    rows = [{
        "Indicateur": "Toutes les séances",
        "Signal": "—",
        **_stats(replayed["Future_Return"])
    }]

    for indicator in SIGNAL_INDICATORS:

        for value, label in SIGNAL_LABELS.items():

            matching = replayed.loc[
                replayed[indicator] == value,
                "Future_Return"
            ]

            if matching.empty:
                continue

            rows.append({
                "Indicateur": indicator,
                "Signal": label,
                **_stats(matching)
            })

    return pd.DataFrame(rows)


def summarize_scores(replayed):
    """Ce qui a suivi le score technique, selon les seuils de decision du
    moteur appliques au seul score technique."""

    zones = [
        (
            f"Score ≥ {DECISION_BUY_THRESHOLD} (zone ACHETER)",
            replayed["Technical_Score"] >= DECISION_BUY_THRESHOLD
        ),
        (
            f"Score {DECISION_HOLD_THRESHOLD} à {DECISION_BUY_THRESHOLD} "
            "(zone CONSERVER)",
            (replayed["Technical_Score"] >= DECISION_HOLD_THRESHOLD)
            & (replayed["Technical_Score"] < DECISION_BUY_THRESHOLD)
        ),
        (
            f"Score < {DECISION_HOLD_THRESHOLD} (zone VENDRE)",
            replayed["Technical_Score"] < DECISION_HOLD_THRESHOLD
        )
    ]

    return pd.DataFrame([
        {"Zone": label, **_stats(replayed.loc[mask, "Future_Return"])}
        for label, mask in zones
        if mask.any()
    ])


HORIZON_SESSIONS = FUTURE_HORIZON_DAYS
