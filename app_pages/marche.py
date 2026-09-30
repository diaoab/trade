import streamlit as st

from services.analysis import CUTOFF_ALERT_DAYS
from services.loaders import market_overview


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


overview = market_overview()


# =========================================================
# QUOI DE NEUF
# =========================================================

news = []

for row in overview:

    for change in row["changes"]:
        news.append(f"**{row['name']}** : {change}.")

    dividend = row["dividend"]

    if dividend is not None and 0 <= dividend["days_left"] <= CUTOFF_ALERT_DAYS:

        news.append(
            f"**{row['name']}** : date butoir de dividende le "
            f"{dividend['cutoff']:%d/%m/%Y} "
            + (
                f"(dans {dividend['days_left']} j)"
                if dividend["days_left"] > 0
                else "(c'est la dernière séance connue)"
            )
            + f", {dividend['amount']:g} FCFA par action."
        )

with st.container(border=True):

    st.markdown("**:material/notifications: Quoi de neuf**")

    if news:

        for line in news:
            st.markdown(f"- {line}")

    else:

        st.caption(
            "Rien de notable depuis la séance précédente : aucun signal n'a "
            "basculé, aucun RSI n'est entré en zone extrême, aucune date "
            "butoir de dividende dans les "
            f"{CUTOFF_ALERT_DAYS} jours."
        )


# =========================================================
# VUE D'ENSEMBLE
# =========================================================

gainers = sum(1 for row in overview if (row["pct"] or 0) > 0)
losers = sum(1 for row in overview if (row["pct"] or 0) < 0)

buy_signals = sum(
    1
    for row in overview
    if row["result"] and row["result"]["decision"] == "ACHETER"
)

with st.container(horizontal=True):

    st.metric("Structures suivies", len(overview), border=True)
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

filtered = overview

if market_filter == "Hausse":
    filtered = [row for row in overview if (row["pct"] or 0) > 0]
elif market_filter == "Baisse":
    filtered = [row for row in overview if (row["pct"] or 0) < 0]
elif market_filter == "Signal d'achat":
    filtered = [
        row
        for row in overview
        if row["result"] and row["result"]["decision"] == "ACHETER"
    ]
elif market_filter == "Dividende à venir":
    filtered = [row for row in overview if row["dividend"]]


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

            st.write(f"**{row['name']}**")

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
