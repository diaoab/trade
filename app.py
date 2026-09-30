import streamlit as st

from config import (
    DEFAULT_ADJUST_DIVIDENDS,
    DEFAULT_ROUND_TRIP_FEE,
    DEFAULT_WEIGHTS,
    INDICATOR_DEFAULTS
)
from services.loaders import (
    load_prepared,
    load_signal_backtest
)
from services.market_data import (
    get_structures,
    match_structure_name,
    save_uploaded_structure
)
from services.preferences import load_preferences
from services.themes import DEFAULT_THEME, THEMES, theme_css


# =========================================================
# CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Financial AI Advisor",
    page_icon=":material/monitoring:",
    layout="wide"
)


# Valeurs par defaut de l'etat partage : ce script s'execute avant CHAQUE
# page (cf. app_pages/), donc c'est le seul endroit garanti pour les poser
# avant que app_pages/parametres.py -- qui possede les vrais widgets -- ait
# eu l'occasion de tourner au moins une fois dans la session. On part des
# reglages enregistres sur disque (cf. services/preferences.py) : sans ca,
# un simple rechargement de page (nouvelle session_state) reviendrait aux
# reglages d'usine malgre un "Enregistrer" precedent.
preferences = load_preferences()

st.session_state.setdefault(
    "theme_name",
    preferences.get("theme_name")
    if preferences.get("theme_name") in THEMES
    else DEFAULT_THEME
)

st.session_state.setdefault(
    "selected_parameters",
    preferences.get("selected_parameters", INDICATOR_DEFAULTS)
)

# Ponderation fixe : le reglage a ete retire de la page Parametres. On
# ignore volontairement d'anciens poids restes dans preferences.json, qui
# continueraient sinon a s'appliquer sans plus pouvoir etre modifies.
st.session_state["weights"] = DEFAULT_WEIGHTS

st.session_state.setdefault(
    "adjust_dividends",
    bool(preferences.get("adjust_dividends", DEFAULT_ADJUST_DIVIDENDS))
)

# Structure servant d'indice de reference (BRVM Composite importe comme une
# structure), ou None.
st.session_state.setdefault(
    "benchmark_symbol",
    preferences.get("benchmark_symbol")
)

st.session_state.setdefault(
    "round_trip_fee",
    float(preferences.get("round_trip_fee", DEFAULT_ROUND_TRIP_FEE))
)


# =========================================================
# APPARENCE
# =========================================================

# Le theme statique (.streamlit/config.toml) fixe le socle -- fond sombre,
# rayons arrondis, typographie -- et ne peut pas changer sans redemarrer le
# serveur. Pour laisser chaque utilisateur choisir sa propre palette sans
# redemarrage, on recolore l'app par-dessus via du CSS injecte (cf.
# services/themes.py). Le selecteur lui-meme vit sur la page Parametres ;
# ce qui compte ici, c'est que l'injection tourne sur CHAQUE page.
active_theme = THEMES[st.session_state["theme_name"]]

st.html(theme_css(active_theme))


# =========================================================
# MARQUE + NAVIGATION
# =========================================================

# position="hidden" : le widget natif de st.navigation s'affiche toujours
# tout en haut de la sidebar, avant tout autre contenu -- impossible d'y
# mettre la marque au-dessus. On construit donc le menu nous-memes avec
# st.page_link (ci-dessous), dans l'ordre voulu : marque, puis menu, puis
# la structure a analyser.
pages = [
    st.Page(
        "app_pages/analyse.py",
        title="Analyse",
        icon=":material/dashboard:",
        default=True
    ),
    st.Page(
        "app_pages/marche.py",
        title="Marché",
        icon=":material/storefront:"
    ),
    st.Page(
        "app_pages/portefeuille.py",
        title="Portefeuille",
        icon=":material/account_balance_wallet:"
    ),
    st.Page(
        "app_pages/dividendes.py",
        title="Dividendes",
        icon=":material/payments:"
    ),
    st.Page(
        "app_pages/journal.py",
        title="Journal",
        icon=":material/history:"
    ),
    st.Page(
        "app_pages/parametres.py",
        title="Paramètres",
        icon=":material/tune:"
    )
]

page = st.navigation(pages, position="hidden")


with st.sidebar:

    st.markdown("### :material/monitoring: Financial AI Advisor")

    st.caption("Assistant expérimental d'analyse BRVM")

    for nav_page in pages:

        st.page_link(
            nav_page,
            label=nav_page.title,
            icon=nav_page.icon,
            disabled=nav_page.title == page.title
        )


# =========================================================
# STRUCTURE (globale : necessaire sur toutes les pages)
# =========================================================

st.sidebar.divider()

st.sidebar.header(":material/database: Structure")


with st.sidebar.expander("Ajouter des structures", icon=":material/upload_file:"):

    uploaded_files = st.file_uploader(
        "Historiques Excel (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=True,
        help="Un fichier par titre ; tu peux en déposer plusieurs d'un coup."
    )

    # Un seul fichier : le nom se choisit librement. Plusieurs : chacun
    # prend le nom de son fichier, pour ne pas avoir a les saisir un a un.
    structure_name = st.text_input(
        "Nom de la structure",
        disabled=len(uploaded_files) > 1,
        placeholder="Nom du fichier par défaut",
        help="Un nom déjà présent dans le catalogue (même écrit sans "
        "espace) complète l'historique de cette structure au lieu d'en "
        "créer une nouvelle."
    )

    if st.button("Importer", icon=":material/file_upload:", width="stretch"):

        if not uploaded_files:

            st.error("Choisis au moins un fichier.")

        else:

            imported = 0

            for uploaded_file in uploaded_files:

                name = (
                    structure_name.strip()
                    if len(uploaded_files) == 1 and structure_name.strip()
                    else uploaded_file.name.rsplit(".", 1)[0]
                )

                # "PALMCI" rejoint la structure "PALM CI" deja en base.
                name = match_structure_name(name)

                try:

                    symbol, import_report = save_uploaded_structure(
                        uploaded_file,
                        name
                    )

                except ValueError as error:

                    st.error(f"{uploaded_file.name} : {error}")

                    continue

                imported += 1

                # st.toast : survit au rerun ci-dessous, contrairement a
                # st.success.
                st.toast(
                    (
                        f"{import_report['name']} mise à jour : "
                        f"{import_report['rows_added']} nouvelle(s) "
                        f"séance(s), {import_report['rows_out']} au total."
                        if import_report["updated"]
                        else f"{import_report['name']} importée : "
                        f"{import_report['rows_out']} séances."
                    )
                    + (
                        " Jour et mois étaient inversés dans le fichier, "
                        "les dates ont été rétablies."
                        if import_report.get("day_month_swapped")
                        else ""
                    ),
                    icon=":material/check_circle:"
                )

            if imported:

                load_prepared.clear()
                load_signal_backtest.clear()

                # Rien a relancer si tout a echoue : les erreurs doivent
                # rester a l'ecran.
                if imported == len(uploaded_files):
                    st.rerun()


structures = get_structures()

if not structures:

    st.error(
        "Aucun historique dans le dossier data/."
    )

    st.info(
        "Utilise « Ajouter des structures » dans la barre latérale pour "
        "importer un fichier Excel de cotations."
    )

    st.stop()


# Une page (ex. app_pages/marche.py) qui veut changer la structure
# selectionnee ne peut pas ecrire directement dans st.session_state
# ["selected_symbol"] : ce script a deja instancie le widget de ce nom
# ci-dessous a chaque rerun, et Streamlit interdit de modifier apres coup
# le session_state d'un widget deja cree. Elle depose donc la cible dans
# "pending_symbol" et declenche un rerun (st.switch_page) ; on l'applique
# ici, avant la creation du widget, ou c'est encore autorise.
if "pending_symbol" in st.session_state:

    st.session_state["selected_symbol"] = st.session_state.pop("pending_symbol")


st.sidebar.selectbox(
    "Choisir une structure",
    options=list(structures.keys()),
    format_func=lambda symbol: structures[symbol]["name"],
    key="selected_symbol"
)


page.run()
