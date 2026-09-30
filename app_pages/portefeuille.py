import pandas as pd
import streamlit as st

from services.loaders import market_overview
from services.portfolio import load_positions, save_positions, value_position


DECISION_COLORS = {
    "ACHETER": "green",
    "CONSERVER": "orange",
    "VENDRE": "red"
}


st.title("Portefeuille")

st.caption(
    "Tes lignes, chiffrées à la dernière séance connue de chaque titre, "
    "avec le signal de l'application en face. Saisie manuelle : rien n'est "
    "relié à ton compte-titres."
)


overview = {row["symbol"]: row for row in market_overview()}

positions = load_positions()

fee = st.session_state.get("round_trip_fee", 0.0)


def _amount(value):
    """1234567.8 -> "1 234 568" (espace insecable comme separateur)."""

    return f"{value:,.0f}".replace(",", "\u202f")


# =========================================================
# LIGNES
# =========================================================

valued = []

for position in positions:

    row = overview.get(position["symbol"])

    # Structure retiree du catalogue depuis la saisie : la ligne reste
    # listee pour pouvoir etre supprimee, sans etre chiffree.
    if row is None or row["date"] is None:

        valued.append((position, None, None))

        continue

    valued.append((
        position,
        row,
        value_position(
            position,
            row["close"],
            row["date"],
            row["dividends"],
            fee
        )
    ))


priced = [value for _, _, value in valued if value is not None]

if priced:

    total_cost = sum(value["cost"] for value in priced)
    total_value = sum(value["value"] for value in priced)
    total_dividends = sum(value["dividends"] for value in priced)
    total_net = sum(value["net"] for value in priced)

    with st.container(horizontal=True):

        st.metric("Investi", f"{_amount(total_cost)} FCFA", border=True)

        st.metric(
            "Valeur actuelle",
            f"{_amount(total_value)} FCFA",
            delta=f"{(total_value / total_cost - 1) * 100:+.2f} %",
            border=True
        )

        st.metric(
            "Dividendes encaissés",
            f"{_amount(total_dividends)} FCFA",
            border=True
        )

        st.metric(
            "Résultat net de frais",
            f"{_amount(total_net)} FCFA",
            delta=f"{total_net / total_cost * 100:+.2f} %",
            border=True
        )

    st.caption(
        "Résultat net : plus-value latente + dividendes encaissés − frais "
        f"d'un aller-retour ({fee:g} %, réglable dans Paramètres). Les "
        "dividendes viennent de ceux saisis dans Paramètres."
    )

elif not positions:

    st.info(
        "Aucune ligne pour l'instant. Ajoute ta première position "
        "ci-dessous.",
        icon=":material/info:"
    )


for index, (position, row, value) in enumerate(valued):

    with st.container(border=True):

        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center"
        ):

            st.write(
                f"**{row['name'] if row else position['symbol']}** · "
                f"{position['quantity']:g} titres à "
                f"{position['buy_price']:g} · achetés le "
                f"{pd.Timestamp(position['buy_date']):%d/%m/%Y}"
            )

            if value is not None:

                color = "green" if value["net"] >= 0 else "red"

                st.write(
                    f"{row['close']:.2f} · :{color}["
                    f"{_amount(value['net'])} FCFA "
                    f"({value['net_pct']:+.2f} %)]"
                )

                result = row["result"]

                st.write(
                    f":{DECISION_COLORS[result['decision']]}"
                    f"[**{result['decision']}**] · {result['score']:.0f}/100"
                    if result is not None
                    else "—"
                )

            else:

                st.write("Structure absente du catalogue")

            if st.button(
                "Retirer",
                icon=":material/delete:",
                key=f"remove_position_{index}"
            ):

                save_positions(
                    positions[:index] + positions[index + 1:]
                )

                st.rerun()

        if value is not None:

            notes = [
                f"Plus-value latente {_amount(value['gain'])} FCFA "
                f"({value['gain_pct']:+.2f} %)",
                f"dividendes encaissés {_amount(value['dividends'])} FCFA",
                f"frais estimés {_amount(value['fees'])} FCFA"
            ]

            if row["dividend"] is not None:

                notes.append(
                    ":material/event: prochain dividende : détachement le "
                    f"{row['dividend']['ex_date']:%d/%m/%Y}"
                )

            st.caption(" · ".join(notes))


# =========================================================
# AJOUT
# =========================================================

st.subheader(":material/add_circle: Ajouter une ligne")

if not overview:

    st.caption("Importe d'abord au moins une structure.")

else:

    with st.form("add_position", clear_on_submit=True, border=False):

        with st.container(horizontal=True, vertical_alignment="bottom"):

            symbol = st.selectbox(
                "Structure",
                options=list(overview),
                format_func=lambda symbol: overview[symbol]["name"]
            )

            quantity = st.number_input(
                "Quantité",
                min_value=0.0,
                step=1.0,
                value=None
            )

            buy_price = st.number_input(
                "Prix d'achat unitaire (FCFA)",
                min_value=0.0,
                value=None
            )

            buy_date = st.date_input(
                "Date d'achat",
                value=None,
                format="DD/MM/YYYY"
            )

        submitted = st.form_submit_button(
            "Ajouter",
            icon=":material/add:",
            type="primary"
        )

    if submitted:

        if not quantity or not buy_price or buy_date is None:

            st.error("Renseigne la quantité, le prix et la date d'achat.")

        else:

            save_positions(
                positions
                + [{
                    "symbol": symbol,
                    "quantity": quantity,
                    "buy_price": buy_price,
                    "buy_date": buy_date
                }]
            )

            st.rerun()
