"""Chargements mis en cache, partages entre les pages de l'app Streamlit.

Regroupes ici (plutot que dans app.py) pour que app_pages/analyse.py et
app_pages/marche.py puissent tous les deux les importer sans dependre du
script d'entree.
"""

import streamlit as st

from services.indicators import calculate_indicators
from services.market_data import load_structure


@st.cache_data(show_spinner=False)
def load_prepared(symbol):
    """Charge un titre et calcule ses indicateurs.

    Mis en cache : sans cela, chaque interaction relancerait la lecture du
    classeur Excel et tout le calcul.
    """

    df, report = load_structure(
        symbol,
        with_report=True
    )

    return calculate_indicators(df), report


@st.cache_data(show_spinner=False)
def load_watchlist(symbols):
    """Dernier cours et variation de chaque structure du catalogue.

    Version legere de load_prepared : pas de calcul d'indicateurs, juste la
    lecture normalisee (cf. load_structure), pour rester rapide meme avec
    beaucoup de structures.
    """

    rows = []

    for symbol in symbols:

        try:

            history = load_structure(symbol)

        except (FileNotFoundError, ValueError):

            continue

        if history.empty:
            continue

        last_close = history["Close"].iloc[-1]

        previous_close = (
            history["Close"].iloc[-2]
            if len(history) > 1
            else None
        )

        delta = (
            last_close - previous_close
            if previous_close is not None
            else None
        )

        pct = (
            delta / previous_close * 100
            if delta is not None and previous_close
            else None
        )

        rows.append({
            "symbol": symbol,
            "close": last_close,
            "delta": delta,
            "pct": pct
        })

    return rows
