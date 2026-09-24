import streamlit as st

from config import DEFAULT_WEIGHTS, INDICATOR_DEFAULTS
from services.loaders import load_prepared, load_watchlist
from services.market_data import get_structures, save_uploaded_structure
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
# eu l'occasion de tourner au moins une fois dans la session.
st.session_state.setdefault("theme_name", DEFAULT_THEME)
st.session_state.setdefault("selected_parameters", INDICATOR_DEFAULTS)
st.session_state.setdefault("weights", DEFAULT_WEIGHTS)


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


with st.sidebar.expander("Ajouter une structure", icon=":material/upload_file:"):

    uploaded_file = st.file_uploader(
        "Historique Excel (.xlsx)",
        type=["xlsx"]
    )

    structure_name = st.text_input(
        "Nom de la structure"
    )

    if st.button("Importer", icon=":material/file_upload:", width="stretch"):

        if uploaded_file is None:

            st.error("Choisis un fichier.")

        elif not structure_name.strip():

            st.error("Donne un nom à la structure.")

        else:

            try:

                symbol, import_report = save_uploaded_structure(
                    uploaded_file,
                    structure_name
                )

            except ValueError as error:

                st.error(str(error))

            else:

                load_prepared.clear()
                load_watchlist.clear()

                st.success(
                    f"{import_report['name']} importée : "
                    f"{import_report['rows_out']} séances.",
                    icon=":material/check_circle:"
                )

                if import_report.get("day_month_swapped"):

                    st.info(
                        "Jour et mois étaient inversés dans le fichier, "
                        "les dates ont été rétablies."
                    )

                st.rerun()


structures = get_structures()

if not structures:

    st.error(
        "Aucun historique dans le dossier data/."
    )

    st.info(
        "Utilise « Ajouter une structure » dans la barre latérale pour "
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
