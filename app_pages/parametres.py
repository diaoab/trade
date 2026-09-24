import streamlit as st

from config import INDICATOR_OPTIONS
from services.preferences import save_preferences
from services.themes import THEMES, theme_swatch_html


st.title("Paramètres")

st.caption(
    "Apparence, indicateurs techniques et pondération de l'analyse — "
    "utilisés par la page Analyse. Rien ne prend effet tant que tu n'as "
    "pas cliqué sur « Enregistrer »."
)


# Brouillon distinct des valeurs appliquees (session_state["theme_name"],
# ["selected_parameters"], ["weights"], lues par app.py et par la page
# Analyse) : les widgets ci-dessous editent ce brouillon, et seul le clic
# sur "Enregistrer" le recopie dans les valeurs appliquees. Initialise a
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
# POIDS
# =========================================================

st.subheader(":material/balance: Poids de l'analyse")


def weight_control(label, key, default):
    """Curseur + champ numérique synchronisés sur le même poids.

    Les deux widgets partagent leur valeur via session_state : modifier
    l'un met l'autre à jour au prochain rendu. Ce sont deja des brouillons
    page-locaux : ils n'affectent le poids reellement utilise par l'analyse
    qu'une fois recopies dans session_state["weights"] par "Enregistrer".
    """

    slider_key = f"{key}_weight_slider"
    input_key = f"{key}_weight_input"

    if slider_key not in st.session_state:
        st.session_state[slider_key] = default
        st.session_state[input_key] = default

    def sync_from_slider():
        st.session_state[input_key] = st.session_state[slider_key]

    def sync_from_input():
        st.session_state[slider_key] = st.session_state[input_key]

    col_slider, col_input = st.columns([3, 1])

    with col_slider:
        st.slider(
            label,
            0,
            100,
            key=slider_key,
            on_change=sync_from_slider
        )

    with col_input:
        st.number_input(
            label,
            min_value=0,
            max_value=100,
            key=input_key,
            on_change=sync_from_input,
            label_visibility="collapsed"
        )

    return st.session_state[slider_key]


technical_weight_draft = weight_control("Technique", "technical", 40)

ml_weight_draft = weight_control("Machine Learning", "ml", 40)

risk_weight_draft = weight_control("Risque", "risk", 20)


weights_draft = {
    "Technique": technical_weight_draft,
    "Machine Learning": ml_weight_draft,
    "Risque": risk_weight_draft
}


total_weight_draft = (
    technical_weight_draft
    + ml_weight_draft
    + risk_weight_draft
)

st.write(f"Total : {total_weight_draft}%")


if total_weight_draft == 0:

    st.warning(
        "Tous les poids sont à zéro : aucune analyse n'est possible.",
        icon=":material/warning:"
    )

elif total_weight_draft != 100:

    st.caption(
        "Le total n'est pas 100 % : les poids sont ramenés à cette échelle."
    )


st.divider()


# =========================================================
# ENREGISTRER
# =========================================================

has_unsaved_changes = (
    theme_name_draft != st.session_state["theme_name"]
    or selected_parameters_draft != st.session_state["selected_parameters"]
    or weights_draft != st.session_state["weights"]
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
    st.session_state["weights"] = weights_draft

    # Sur disque, pas seulement en session_state : sans ca, un simple
    # rechargement de page (F5) ouvre une nouvelle session et revient aux
    # reglages par defaut malgre ce clic.
    save_preferences({
        "theme_name": theme_name_draft,
        "selected_parameters": selected_parameters_draft,
        "weights": weights_draft
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
