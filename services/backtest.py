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
from services.targets import compute_future_return


# Horizons de mesure, en seances : une semaine, un mois, un trimestre de
# bourse. Le plus court est celui de la cible du modele ML ; les plus longs
# sont ceux ou un signal a le temps de rapporter plus que les frais.
HORIZONS = (5, 20, 60)


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
    "Return_5D"
]

NEUTRAL_ML_RESULT = {"probability_up": 0.5}

TECHNICAL_ONLY = {"Technique": 100, "Machine Learning": 0, "Risque": 0}

SIGNAL_LABELS = {
    1: "favorable",
    0: "neutre",
    -1: "défavorable"
}


def _analyze(row, indicators):

    return analyze(
        row,
        NEUTRAL_ML_RESULT,
        indicators,
        TECHNICAL_ONLY
    )


def replay_signals(histories):
    """Rejoue le moteur sur chaque seance de chaque titre.

    histories : {symbole: DataFrame d'historique normalise}. Retourne une
    ligne par seance exploitable, avec le signal de chaque indicateur
    (+1 favorable, 0 neutre, -1 defavorable), le score technique tous
    indicateurs confondus et la variation du cours a chaque horizon de
    HORIZONS (colonnes Future_Return_5, _20, _60 ; vide quand l'historique
    ne va pas assez loin).

    Le signal d'un indicateur est lu en appelant le moteur avec ce seul
    indicateur : ce backtest ne peut donc pas diverger des regles reellement
    appliquees dans l'application.
    """

    rows = []

    for symbol, history in histories.items():

        prepared = calculate_indicators(history)

        for horizon in HORIZONS:

            prepared[f"Future_Return_{horizon}"] = compute_future_return(
                prepared["Close"],
                horizon
            )

        prepared = prepared.dropna(
            subset=REQUIRED_COLUMNS + [f"Future_Return_{HORIZONS[0]}"]
        )

        for _, session in prepared.iterrows():

            row = {
                "Symbol": symbol,
                "Date": session.get("Date"),
                "Technical_Score": _analyze(
                    session,
                    SIGNAL_INDICATORS
                )["technical_score"]
            }

            for horizon in HORIZONS:

                row[f"Future_Return_{horizon}"] = session[
                    f"Future_Return_{horizon}"
                ]

            for indicator in SIGNAL_INDICATORS:

                result = _analyze(session, [indicator])

                deviation = (
                    result["technical_score"]
                    - TECHNICAL_SCORE_NEUTRAL
                )

                # Un signal indicatif ne deplace pas le score : son sens
                # est lu dans le champ que le moteur lui reserve.
                row[indicator] = result["indicative"].get(
                    indicator,
                    (deviation > 0) - (deviation < 0)
                )

            rows.append(row)

    return pd.DataFrame(
        rows,
        columns=["Symbol", "Date", "Technical_Score"]
        + [f"Future_Return_{horizon}" for horizon in HORIZONS]
        + SIGNAL_INDICATORS
    )


def _stats(future_returns, fee):
    """fee : frais d'un aller-retour (achat puis revente), en pourcentage.

    "Net de frais" est ce qu'il serait reste, en moyenne, a qui aurait
    achete a chacune de ces seances et revendu a l'horizon.
    """

    future_returns = future_returns.dropna()

    mean = future_returns.mean() * 100

    return {
        "Séances": len(future_returns),
        "Hausse ensuite (%)": (future_returns > 0).mean() * 100,
        "Baisse ensuite (%)": (future_returns < 0).mean() * 100,
        "Variation moyenne (%)": mean,
        "Net de frais (%)": mean - fee
    }


def summarize_signals(replayed, horizon=HORIZONS[0], fee=0.0):
    """Ce qui a suivi chaque signal, indicateur par indicateur, `horizon`
    seances plus tard.

    La premiere ligne ("Toutes les séances") est la reference : un signal
    n'apporte quelque chose que s'il s'en ecarte nettement.
    """

    future_return = f"Future_Return_{horizon}"

    rows = [{
        "Indicateur": "Toutes les séances",
        "Signal": "—",
        **_stats(replayed[future_return], fee)
    }]

    for indicator in SIGNAL_INDICATORS:

        for value, label in SIGNAL_LABELS.items():

            matching = replayed.loc[
                replayed[indicator] == value,
                future_return
            ].dropna()

            if matching.empty:
                continue

            rows.append({
                "Indicateur": indicator,
                "Signal": label,
                **_stats(matching, fee)
            })

    return pd.DataFrame(rows)


def summarize_scores(replayed, horizon=HORIZONS[0], fee=0.0):
    """Ce qui a suivi le score technique, selon les seuils de decision du
    moteur appliques au seul score technique."""

    future_return = f"Future_Return_{horizon}"

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
        {"Zone": label, **_stats(replayed.loc[mask, future_return], fee)}
        for label, mask in zones
        if mask.any()
    ])
