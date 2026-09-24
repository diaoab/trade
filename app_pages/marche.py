import streamlit as st

from services.loaders import load_watchlist
from services.market_data import get_structures


st.title("Marché")

st.caption(
    "Dernier cours et variation de chaque structure du catalogue."
)


structures = get_structures()

watchlist = load_watchlist(tuple(structures.keys()))


gainers = sum(1 for row in watchlist if (row["pct"] or 0) > 0)
losers = sum(1 for row in watchlist if (row["pct"] or 0) < 0)

with st.container(horizontal=True, wrap=False):

    st.metric("Structures suivies", len(watchlist), border=True)
    st.metric("En hausse", gainers, border=True)
    st.metric("En baisse", losers, border=True)


market_filter = st.pills(
    "Filtre marché",
    ["Toutes", "Hausse", "Baisse"],
    default="Toutes",
    key="market_filter",
    label_visibility="collapsed"
)

filtered = watchlist

if market_filter == "Hausse":
    filtered = [row for row in watchlist if (row["pct"] or 0) > 0]
elif market_filter == "Baisse":
    filtered = [row for row in watchlist if (row["pct"] or 0) < 0]


if not filtered:

    st.caption("Aucune structure à afficher pour ce filtre.")


for row in filtered:

    pct = row["pct"]
    pct_text = f"{pct:+.2f} %" if pct is not None else "—"
    pct_color = "green" if (pct or 0) >= 0 else "red"

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
