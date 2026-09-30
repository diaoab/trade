import pandas as pd
import streamlit as st

from config import DEFAULT_WEIGHTS
from services.analysis import analyse_session
from services.loaders import load_prepared, load_watchlist
from services.market_data import cutoff_date, get_structures
from services.predictor import load_model_metadata


# Memes colonnes que la page Analyse : sans elles, pas de signal.
CORE_INDICATORS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "MACD_Signal"
]

DECISION_COLORS = {
    "ACHETER": "green",
    "CONSERVER": "orange",
    "VENDRE": "red"
}


st.title("Marché")

st.caption(
    "Dernier cours, variation et signal de chaque structure du catalogue, "
    "sur sa dernière séance. Le signal est celui de la page Analyse, avec "
    "les indicateurs choisis dans Paramètres."
)


structures = get_structures()

watchlist = load_watchlist(tuple(structures.keys()))

selected_parameters = st.session_state.get("selected_parameters", [])

weights = st.session_state.get("weights", DEFAULT_WEIGHTS)

adjust_dividends = st.session_state.get("adjust_dividends", True)

model_metadata = load_model_metadata()


def latest_signal(symbol):
    """Decision du moteur sur la derniere seance du titre, ou None s'il n'a
    pas assez d'historique ou qu'aucun indicateur n'est selectionne."""

    if not selected_parameters:
        return None, None

    try:

        prepared, _ = load_prepared(symbol, adjust_dividends)

    except (FileNotFoundError, ValueError):

        return None, None

    usable = prepared.dropna(subset=CORE_INDICATORS)

    if usable.empty:
        return None, None

    session = usable.iloc[-1]

    result, _, _ = analyse_session(
        session,
        selected_parameters,
        weights,
        model_metadata
    )

    return result, session.get("Date")


def next_cutoff(symbol, session_date):
    """Prochaine date butoir de dividende apres la derniere seance."""

    if session_date is None:
        return None

    for dividend in structures[symbol]["dividends"]:

        if pd.Timestamp(dividend["ex_date"]) > session_date:

            cutoff = cutoff_date(dividend["ex_date"])

            return {
                "cutoff": cutoff,
                "amount": dividend["amount"],
                "days_left": (cutoff - session_date.normalize()).days
            }

    return None


for row in watchlist:

    row["result"], session_date = latest_signal(row["symbol"])

    row["dividend"] = next_cutoff(row["symbol"], session_date)


gainers = sum(1 for row in watchlist if (row["pct"] or 0) > 0)
losers = sum(1 for row in watchlist if (row["pct"] or 0) < 0)

buy_signals = sum(
    1
    for row in watchlist
    if row["result"] and row["result"]["decision"] == "ACHETER"
)

with st.container(horizontal=True):

    st.metric("Structures suivies", len(watchlist), border=True)
    st.metric("En hausse", gainers, border=True)
    st.metric("En baisse", losers, border=True)
    st.metric("Signaux d'achat", buy_signals, border=True)


market_filter = st.pills(
    "Filtre marché",
    ["Toutes", "Hausse", "Baisse", "Signal d'achat", "Dividende à venir"],
    default="Toutes",
    key="market_filter",
    label_visibility="collapsed"
)

filtered = watchlist

if market_filter == "Hausse":
    filtered = [row for row in watchlist if (row["pct"] or 0) > 0]
elif market_filter == "Baisse":
    filtered = [row for row in watchlist if (row["pct"] or 0) < 0]
elif market_filter == "Signal d'achat":
    filtered = [
        row
        for row in watchlist
        if row["result"] and row["result"]["decision"] == "ACHETER"
    ]
elif market_filter == "Dividende à venir":
    filtered = [row for row in watchlist if row["dividend"]]


if not filtered:

    st.caption("Aucune structure à afficher pour ce filtre.")


for row in filtered:

    pct = row["pct"]
    pct_text = f"{pct:+.2f} %" if pct is not None else "—"
    pct_color = "green" if (pct or 0) >= 0 else "red"

    result = row["result"]

    with st.container(border=True):

        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center"
        ):

            st.write(f"**{structures[row['symbol']]['name']}**")

            st.write(
                f"{row['close']:.2f}  :{pct_color}[{pct_text}]"
            )

            if result is not None:

                st.write(
                    f":{DECISION_COLORS[result['decision']]}"
                    f"[**{result['decision']}**] · {result['score']:.0f}/100"
                )

            else:

                st.write("—")

            analyser_clicked = st.button(
                "Analyser",
                icon=":material/arrow_forward:",
                key=f"watch_{row['symbol']}",
                type="primary"
                if row["symbol"] == st.session_state.get("selected_symbol")
                else "secondary"
            )

            if analyser_clicked:

                # Le widget "selected_symbol" est deja instancie par
                # app.py a chaque rerun : on ne peut pas ecrire dedans
                # d'ici. app.py applique "pending_symbol" juste avant de
                # le creer, au prochain rerun declenche par switch_page.
                st.session_state["pending_symbol"] = row["symbol"]

                st.switch_page("app_pages/analyse.py")

        notes = []

        if row["dividend"] is not None:

            dividend = row["dividend"]

            notes.append(
                f":material/event: Date butoir dividende "
                f"{dividend['cutoff']:%d/%m/%Y} "
                f"({dividend['amount']:g} FCFA par action, dans "
                f"{dividend['days_left']} j)"
            )

        if result is not None and result["liquidity_warnings"]:

            notes.append(":material/water_drop: Liquidité faible")

        if notes:

            st.caption(" · ".join(notes))
