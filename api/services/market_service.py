"""Analyses calculees pour l'API, sans Streamlit.

Meme enchainement que ui/loaders.py de trade_admin (lecture du classeur, indicateurs,
moteur de decision), mais les reglages viennent du compte de l'utilisateur
et non de st.session_state. Le cache est invalide quand le classeur ou le
registre des structures change sur disque.
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from api.config.constants import (
    DEFAULT_ADJUST_DIVIDENDS,
    DEFAULT_ROUND_TRIP_FEE,
    DEFAULT_WEIGHTS,
    INDICATOR_DEFAULTS,
    INDICATOR_OPTIONS
)
from api.services.engine import market_data
from api.services.engine.analysis import (
    analyse_session,
    latest_sessions,
    next_dividend_cutoff,
    session_changes
)
from api.services.engine.indicators import calculate_indicators
from api.services.engine.narration import build_narration
from api.services.engine.predictor import load_model_metadata


# Seances renvoyees pour le graphique : environ un an de bourse.
CHART_SESSIONS = 250

# Seances du mini-graphique de la liste des titres : environ trois mois.
SPARK_SESSIONS = 63

CHART_COLUMNS = [
    "Close",
    "MM20",
    "MM50",
    "Bollinger_Upper",
    "Bollinger_Lower",
    "RSI",
    "MACD",
    "MACD_Signal"
]


def user_settings(preferences):
    """Reglages d'analyse d'un compte, valeurs par defaut comprises."""

    preferences = preferences or {}

    selected = [
        name
        for name in preferences.get("selected_parameters", INDICATOR_DEFAULTS)
        if name in INDICATOR_OPTIONS
    ]

    return {
        "selected_parameters": selected,
        "adjust_dividends": bool(
            preferences.get("adjust_dividends", DEFAULT_ADJUST_DIVIDENDS)
        ),
        "round_trip_fee": float(
            preferences.get("round_trip_fee", DEFAULT_ROUND_TRIP_FEE)
        )
    }


def _mtime(path):

    try:
        return path.stat().st_mtime
    except OSError:
        return None


@lru_cache(maxsize=64)
def _prepared(symbol, adjust_dividends, file_mtime, registry_mtime):

    df = market_data.load_structure(symbol, adjust_dividends=adjust_dividends)

    return calculate_indicators(df)


def load_prepared(symbol, adjust_dividends=True):
    """Historique d'un titre avec ses indicateurs (FileNotFoundError si le
    titre n'existe pas)."""

    structures = market_data.get_structures()

    if symbol not in structures:
        raise FileNotFoundError(symbol)

    return _prepared(
        symbol,
        adjust_dividends,
        _mtime(structures[symbol]["path"]),
        _mtime(market_data.REGISTRY_PATH)
    )


def to_json(value):
    """Rend une valeur issue de pandas/numpy serialisable en JSON."""

    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]

    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.strftime("%Y-%m-%d")

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, (float, np.floating)):
        return None if np.isnan(value) else float(value)

    if value is pd.NaT:
        return None

    return value


def _quote(prepared):
    """Dernier cours reellement cote, variation, date de seance."""

    quoted = prepared.get("Close_Raw", prepared["Close"])

    close = float(quoted.iloc[-1])

    previous = float(quoted.iloc[-2]) if len(quoted) > 1 else None

    date = prepared["Date"].iloc[-1] if "Date" in prepared.columns else None

    return {
        "close": close,
        "pct": (close / previous - 1) * 100 if previous else None,
        "date": date
    }


def market_overview(preferences):
    """Derniere seance de chaque titre, avec le signal du moteur (cf.
    ui.loaders.market_overview, version Streamlit)."""

    settings = user_settings(preferences)

    model_metadata = load_model_metadata()

    overview = []

    for symbol, structure in market_data.get_structures().items():

        try:
            prepared = load_prepared(symbol, settings["adjust_dividends"])
        except (FileNotFoundError, ValueError):
            continue

        if prepared.empty:
            continue

        quote = _quote(prepared)

        entry = {
            "symbol": symbol,
            "name": structure["name"],
            **quote,
            "decision": None,
            "score": None,
            "confidence": None,
            "changes": [],
            "dividend": next_dividend_cutoff(
                structure["dividends"],
                quote["date"]
            ),
            "spark": list(
                prepared.get("Close_Raw", prepared["Close"]).tail(SPARK_SESSIONS)
            )
        }

        sessions = latest_sessions(prepared, count=2)

        if sessions and settings["selected_parameters"]:

            results = [
                analyse_session(
                    session,
                    settings["selected_parameters"],
                    DEFAULT_WEIGHTS,
                    model_metadata
                )[0]
                for session in sessions
            ]

            entry.update({
                "decision": results[-1]["decision"],
                "score": results[-1]["score"],
                "confidence": results[-1]["confidence"]
            })

            if len(sessions) == 2:
                entry["changes"] = session_changes(
                    sessions[0],
                    sessions[1],
                    results[0],
                    results[1]
                )

        overview.append(entry)

    return to_json(overview)


def analyse_raw(symbol, preferences):
    """Analyse de la derniere seance, objets pandas compris (non
    serialisee) : sert a l'ecran Analyse et au contexte de l'assistant."""

    settings = user_settings(preferences)

    structure = market_data.get_structures()[symbol]

    prepared = load_prepared(symbol, settings["adjust_dividends"])

    sessions = latest_sessions(prepared, count=1)

    if not sessions:
        raise ValueError(
            "Historique trop court pour calculer les indicateurs."
        )

    if not settings["selected_parameters"]:
        raise ValueError(
            "Aucun indicateur sélectionné dans les réglages."
        )

    session = sessions[-1]

    model_metadata = load_model_metadata()

    result, ml_result, weights = analyse_session(
        session,
        settings["selected_parameters"],
        DEFAULT_WEIGHTS,
        model_metadata
    )

    quote = _quote(prepared)

    session_date = session.get("Date")

    dividend = next_dividend_cutoff(structure["dividends"], session_date)

    return {
        "settings": settings,
        "structure": structure,
        "prepared": prepared,
        "quote": quote,
        "session_date": session_date,
        "result": result,
        "ml_result": ml_result,
        "weights": weights,
        "model_metadata": model_metadata,
        "dividend": dividend
    }


def analyse_structure(symbol, preferences):
    """Analyse complete de la derniere seance d'un titre, pour l'ecran
    Analyse : signal, detail des scores, raisons, graphique, resume lu."""

    raw = analyse_raw(symbol, preferences)

    structure = raw["structure"]
    result = raw["result"]
    ml_result = raw["ml_result"]
    weights = raw["weights"]
    model_metadata = raw["model_metadata"]
    session_date = raw["session_date"]
    dividend = raw["dividend"]
    quote = raw["quote"]

    chart = raw["prepared"].tail(CHART_SESSIONS)

    return to_json({
        "symbol": symbol,
        "name": structure["name"],
        **quote,
        "session_date": session_date,
        "result": {
            key: value
            for key, value in result.items()
            if key != "indicative"
        },
        "ml": {
            "probability_up": (
                ml_result["probability_up"] if ml_result else None
            ),
            # Faux quand le modele ne bat pas la reference naive : son
            # poids est alors nul et sa probabilite seulement indicative.
            "counted": weights["Machine Learning"] > 0 and ml_result is not None,
            "horizon_days": (
                model_metadata.get("target_horizon_days")
                if model_metadata
                else None
            )
        },
        "dividend": dividend,
        "narration": build_narration(
            structure["name"],
            session_date,
            result,
            dividend
        ),
        "chart": {
            "dates": (
                list(chart["Date"]) if "Date" in chart.columns else []
            ),
            **{
                column: list(chart[column])
                for column in CHART_COLUMNS
                if column in chart.columns
            }
        },
        "indicators": raw["settings"]["selected_parameters"]
    })
