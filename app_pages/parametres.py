import pandas as pd
import streamlit as st

from config import INDICATOR_OPTIONS
from services.loaders import (
    load_prepared,
    load_signal_backtest,
    load_watchlist
)
from services.market_data import (
    clean_dividends,
    cutoff_date,
    get_structures,
    set_dividends
)
from services.preferences import save_preferences
from services.trading_calendar import (
    computed_holidays,
    load_extra_holidays,
    save_extra_holidays
)
from services.themes import THEMES, theme_swatch_html


st.title("Paramètres")

st.caption(
    "Apparence, indicateurs techniques et dividendes — "
    "utilisés par la page Analyse. Rien ne prend effet tant que tu n'as "
    "pas cliqué sur « Enregistrer »."
)


# Brouillon distinct des valeurs appliquees (session_state["theme_name"],
# ["selected_parameters"], lues par app.py et par la page
# Analyse) : les widgets ci-dessous editent ce brouillon, et seul le clic
# sur "Enregistrer" le recopie dans les valeurs appliquees (idem pour
# "adjust_dividends" et le tableau des dividendes). Initialise a
# partir de la derniere valeur appliquee, pour reprendre le fil d'une
# session a l'autre plutot que de repartir des reglages par defaut.
st.session_state.setdefault(
    "theme_name_draft",
    st.session_state["theme_name"]
)

st.session_state.setdefault(
    "selected_parameters_draft",
    st.session_state["selected_parameters"]
)

st.session_state.setdefault(
    "adjust_dividends_draft",
    st.session_state["adjust_dividends"]
)


# =========================================================
# APPARENCE
# =========================================================

st.subheader(":material/palette: Apparence")

theme_name_draft = st.selectbox(
    "Palette de couleurs",
    options=list(THEMES.keys()),
    key="theme_name_draft",
    help="Change uniquement les couleurs : fond, accents, boutons, cartes."
)

draft_theme = THEMES[theme_name_draft]

st.html(theme_swatch_html(draft_theme))
st.caption(draft_theme["description"])


st.divider()


# =========================================================
# INDICATEURS
# =========================================================

st.subheader(":material/show_chart: Indicateurs")

st.caption(
    "Affichés sur le graphique de la page Analyse et pris en compte dans "
    "le score technique."
)

selected_parameters_draft = st.pills(
    "Indicateurs",
    INDICATOR_OPTIONS,
    selection_mode="multi",
    key="selected_parameters_draft",
    label_visibility="collapsed"
) or []


st.divider()


# =========================================================
# DIVIDENDES
# =========================================================

st.subheader(":material/payments: Dividendes")

selected_symbol = st.session_state["selected_symbol"]

structure = get_structures()[selected_symbol]

saved_dividends = structure["dividends"]

st.caption(
    f"Détachements de **{structure['name']}** (structure choisie dans la "
    "barre latérale). La date ex-dividende est le premier jour où le titre "
    "cote sans son dividende ; la date butoir pour l'acheter avec droit au "
    "dividende est la séance qui précède."
)

# Jours feries saisis a la main : brouillon initialise ici parce que les
# dates butoir affichees plus bas en dependent, edite dans le volet "Jours
# fériés BRVM" en bas de section.
saved_holidays = load_extra_holidays()

st.session_state.setdefault("holidays_draft", saved_holidays)

holidays_draft = st.session_state["holidays_draft"]


# Brouillon par structure : "Ajouter" et "Retirer" ne modifient que cette
# liste, recopiee dans data/structures.json par "Enregistrer".
dividends_draft_key = f"dividends_draft_{selected_symbol}"

st.session_state.setdefault(dividends_draft_key, saved_dividends)

dividends_draft = st.session_state[dividends_draft_key]

if not dividends_draft:

    st.caption("Aucun dividende enregistré pour cette structure.")

for dividend in dividends_draft:

    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
        border=True
    ):

        st.markdown(
            f"**Ex-dividende {pd.Timestamp(dividend['ex_date']):%d/%m/%Y}** "
            f"· {dividend['amount']:g} FCFA par action · date butoir "
            "d'achat "
            f"{cutoff_date(dividend['ex_date'], holidays_draft):%d/%m/%Y}"
        )

        if st.button(
            "Retirer",
            icon=":material/delete:",
            key=f"remove_dividend_{selected_symbol}_{dividend['ex_date']}"
        ):

            st.session_state[dividends_draft_key] = [
                other
                for other in dividends_draft
                if other != dividend
            ]

            st.rerun()

def add_dividend():
    """Ajoute la saisie au brouillon et vide les deux champs. En callback :
    c'est le seul moment ou l'on peut encore reecrire la valeur de widgets
    deja affiches."""

    st.session_state[dividends_draft_key] = clean_dividends(
        st.session_state[dividends_draft_key]
        + [{
            "ex_date": st.session_state["new_dividend_ex_date"],
            "amount": st.session_state["new_dividend_amount"]
        }]
    )

    st.session_state["new_dividend_ex_date"] = None
    st.session_state["new_dividend_amount"] = None


with st.container(horizontal=True, vertical_alignment="bottom"):

    new_ex_date = st.date_input(
        "Date ex-dividende",
        value=None,
        format="DD/MM/YYYY",
        key="new_dividend_ex_date"
    )

    new_amount = st.number_input(
        "Dividende net par action (FCFA)",
        min_value=0.0,
        value=None,
        key="new_dividend_amount"
    )

    st.button(
        "Ajouter",
        icon=":material/add:",
        disabled=new_ex_date is None or not new_amount,
        on_click=add_dividend
    )

st.caption(
    "La date butoir est la dernière séance avant le détachement : elle "
    "saute les week-ends et les jours fériés de la BRVM."
)


def add_holiday():

    if st.session_state["new_holiday"] is not None:

        st.session_state["holidays_draft"] = sorted(
            set(st.session_state["holidays_draft"])
            | {st.session_state["new_holiday"]}
        )

    st.session_state["new_holiday"] = None


with st.expander("Jours fériés BRVM", icon=":material/event_busy:"):

    this_year = pd.Timestamp.today().year

    st.caption(
        "Déjà pris en compte chaque année, sans rien saisir : "
        + ", ".join(
            f"{name} ({day:%d/%m})"
            for day, name in sorted(computed_holidays(this_year).items())
        )
        + f" — dates {this_year}."
    )

    st.caption(
        "Les fêtes musulmanes (lendemain de la Nuit du Destin, Ramadan, "
        "Tabaski, Maouloud) sont fixées chaque année par décret : ajoute "
        "ici leurs dates, ainsi que toute autre fermeture exceptionnelle."
    )

    for holiday in holidays_draft:

        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center"
        ):

            st.write(f"{holiday:%d/%m/%Y}")

            if st.button(
                "Retirer",
                icon=":material/delete:",
                key=f"remove_holiday_{holiday}"
            ):

                st.session_state["holidays_draft"] = [
                    other
                    for other in holidays_draft
                    if other != holiday
                ]

                st.rerun()

    with st.container(horizontal=True, vertical_alignment="bottom"):

        new_holiday = st.date_input(
            "Jour de fermeture",
            value=None,
            format="DD/MM/YYYY",
            key="new_holiday"
        )

        st.button(
            "Ajouter",
            icon=":material/add:",
            key="add_holiday",
            disabled=new_holiday is None,
            on_click=add_holiday
        )

adjust_dividends_draft = st.toggle(
    "Ajuster l'historique des dividendes détachés",
    key="adjust_dividends_draft",
    help="Le jour du détachement, le cours baisse mécaniquement du montant "
    "du dividende. Sans ajustement, MACD, Bollinger et RSI lisent cette "
    "marche comme un signal de vente. S'applique à toutes les structures."
)


st.divider()


# =========================================================
# ENREGISTRER
# =========================================================

has_unsaved_changes = (
    theme_name_draft != st.session_state["theme_name"]
    or selected_parameters_draft != st.session_state["selected_parameters"]
    or adjust_dividends_draft != st.session_state["adjust_dividends"]
    or dividends_draft != saved_dividends
    or holidays_draft != saved_holidays
)

if has_unsaved_changes:

    st.caption(
        ":material/edit: Modifications non enregistrées.",
    )

if st.button(
    "Enregistrer",
    icon=":material/save:",
    type="primary",
    disabled=not has_unsaved_changes
):

    st.session_state["theme_name"] = theme_name_draft
    st.session_state["selected_parameters"] = selected_parameters_draft
    st.session_state["adjust_dividends"] = adjust_dividends_draft

    if holidays_draft != saved_holidays:

        save_extra_holidays(holidays_draft)

    if dividends_draft != saved_dividends:

        set_dividends(selected_symbol, dividends_draft)

        # Les historiques en cache ont ete ajustes avec les anciens
        # dividendes.
        load_prepared.clear()
        load_watchlist.clear()
        load_signal_backtest.clear()

    # Sur disque, pas seulement en session_state : sans ca, un simple
    # rechargement de page (F5) ouvre une nouvelle session et revient aux
    # reglages par defaut malgre ce clic.
    save_preferences({
        "theme_name": theme_name_draft,
        "selected_parameters": selected_parameters_draft,
        "adjust_dividends": adjust_dividends_draft
    })

    # Rerun immediat : sans lui, la legende "Modifications non
    # enregistrees" plus haut resterait affichee jusqu'a la prochaine
    # interaction, puisqu'elle a deja ete dessinee avant ce clic dans ce
    # meme run. st.toast (contrairement a st.success) survit a ce rerun.
    st.toast(
        "Paramètres enregistrés et pris en compte dans l'analyse.",
        icon=":material/check_circle:"
    )

    st.rerun()
