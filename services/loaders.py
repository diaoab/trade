"""Chargements mis en cache, partages entre les pages de l'app Streamlit.

Regroupes ici (plutot que dans app.py) pour que toutes les pages puissent
les importer sans dependre du script d'entree.
"""

import streamlit as st

from config import DEFAULT_WEIGHTS
from services.analysis import (
    analyse_session,
    latest_sessions,
    next_dividend_cutoff,
    session_changes
)
from services.backtest import replay_signals
from services.predictor import load_model_metadata
from services.indicators import calculate_indicators
from services.market_data import get_structures, load_structure


@st.cache_data(show_spinner=False)
def load_prepared(symbol, adjust_dividends=True):
    """Charge un titre et calcule ses indicateurs.

    Mis en cache : sans cela, chaque interaction relancerait la lecture du
    classeur Excel et tout le calcul. Les dividendes eux-memes ne font pas
    partie de la cle de cache : la page Parametres vide ce cache quand elle
    les modifie.
    """

    df, report = load_structure(
        symbol,
        with_report=True,
        adjust_dividends=adjust_dividends
    )

    return calculate_indicators(df), report


@st.cache_data(show_spinner="Rejeu des signaux sur l'historique…")
def load_signal_backtest(symbols):
    """Rejeu des signaux techniques sur les structures du catalogue (cf.
    services.backtest.replay_signals) : une ligne par seance.

    Mis en cache : le rejeu appelle le moteur plusieurs fois par seance. Les
    tableaux de synthese (par horizon, frais deduits) se recalculent a la
    volee a partir de ce resultat.
    """

    histories = {}

    for symbol in symbols:

        try:

            histories[symbol] = load_structure(symbol)

        except (FileNotFoundError, ValueError):

            continue

    return replay_signals(histories)


def market_overview():
    """Etat de chaque structure du catalogue a sa derniere seance, pour les
    pages Marche, Portefeuille et Dividendes.

    Une entree par structure : cours reellement cote et variation, date de
    la seance, decision du moteur (None si l'historique est trop court ou
    qu'aucun indicateur n'est selectionne), changements depuis la seance
    precedente, prochain detachement de dividende. Le signal est exactement
    celui de la page Analyse : memes indicateurs, memes poids, meme modele.

    Non mis en cache : il depend des reglages de la session. Les lectures
    couteuses (load_prepared) le sont deja.
    """

    selected_parameters = st.session_state.get("selected_parameters", [])

    weights = st.session_state.get("weights", DEFAULT_WEIGHTS)

    adjust_dividends = st.session_state.get("adjust_dividends", True)

    model_metadata = load_model_metadata()

    overview = []

    for symbol, structure in get_structures().items():

        try:

            prepared, _ = load_prepared(symbol, adjust_dividends)

        except (FileNotFoundError, ValueError):

            continue

        if prepared.empty:
            continue

        # Cours reellement cote : Close_Raw existe des que l'historique a
        # ete ajuste d'un dividende.
        quoted = prepared.get("Close_Raw", prepared["Close"])

        close = float(quoted.iloc[-1])

        previous_close = float(quoted.iloc[-2]) if len(quoted) > 1 else None

        date = (
            prepared["Date"].iloc[-1]
            if "Date" in prepared.columns
            else None
        )

        entry = {
            "symbol": symbol,
            "name": structure["name"],
            "dividends": structure["dividends"],
            "close": close,
            "pct": (
                (close / previous_close - 1) * 100
                if previous_close
                else None
            ),
            "date": date,
            "result": None,
            "changes": [],
            "dividend": next_dividend_cutoff(structure["dividends"], date)
        }

        sessions = latest_sessions(prepared, count=2)

        if sessions and selected_parameters:

            results = [
                analyse_session(
                    session,
                    selected_parameters,
                    weights,
                    model_metadata
                )[0]
                for session in sessions
            ]

            entry["result"] = results[-1]

            if len(sessions) == 2:

                entry["changes"] = session_changes(
                    sessions[0],
                    sessions[1],
                    results[0],
                    results[1]
                )

        overview.append(entry)

    return overview
