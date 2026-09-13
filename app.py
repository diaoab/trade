import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from services.market_data import (
    get_structures,
    load_structure,
    save_uploaded_structure
)

from services.indicators import calculate_indicators

from services.predictor import ModelUnavailable, load_model_metadata, predict_row

from services.decision_engine import analyze


# =========================================================
# CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Financial AI Advisor",
    page_icon=":material/monitoring:",
    layout="wide"
)


# Colonnes sans lesquelles ni le graphique ni le moteur de decision ne
# peuvent fonctionner.
CORE_INDICATORS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "MACD_Signal"
]


# =========================================================
# CHARGEMENT MIS EN CACHE
# =========================================================

@st.cache_data(show_spinner=False)
def load_prepared(symbol):
    """Charge un titre et calcule ses indicateurs.

    Mis en cache : sans cela, chaque case cochee dans la barre laterale
    relancerait la lecture du classeur Excel et tout le calcul.
    """

    df, report = load_structure(
        symbol,
        with_report=True
    )

    return calculate_indicators(df), report


# =========================================================
# TITRE
# =========================================================

st.title("Financial AI Advisor")

st.caption(
    "Assistant expérimental d'analyse des structures cotées."
)

st.warning(
    "Les résultats sont expérimentaux et ne constituent "
    "pas une recommandation financière personnalisée.",
    icon=":material/warning:"
)


# =========================================================
# STRUCTURES
# =========================================================

structures = get_structures()

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


if not structures:

    st.error(
        "Aucun historique dans le dossier data/."
    )

    st.info(
        "Utilise « Ajouter une structure » dans la barre latérale pour "
        "importer un fichier Excel de cotations."
    )

    st.stop()


selected_symbol = st.sidebar.selectbox(
    "Choisir une structure",
    options=list(structures.keys()),
    format_func=lambda symbol: structures[symbol]["name"]
)


# =========================================================
# PARAMETRES
# =========================================================

st.sidebar.header(":material/tune: Paramètres")

st.sidebar.subheader("Indicateurs")


INDICATOR_OPTIONS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "Bollinger",
    "Momentum",
    "Volatilité"
]

INDICATOR_DEFAULTS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "Momentum",
    "Volatilité"
]


selected_parameters = st.sidebar.pills(
    "Indicateurs",
    INDICATOR_OPTIONS,
    selection_mode="multi",
    default=INDICATOR_DEFAULTS,
    label_visibility="collapsed"
) or []


# =========================================================
# POIDS
# =========================================================

st.sidebar.subheader(":material/balance: Poids de l'analyse")


def weight_control(label, key, default):
    """Curseur + champ numérique synchronisés sur le même poids.

    Les deux widgets partagent leur valeur via session_state : modifier
    l'un met l'autre à jour au prochain rendu.
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

    col_slider, col_input = st.sidebar.columns([3, 1])

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


technical_weight = weight_control("Technique", "technical", 40)

ml_weight = weight_control("Machine Learning", "ml", 40)

risk_weight = weight_control("Risque", "risk", 20)


weights = {
    "Technique": technical_weight,
    "Machine Learning": ml_weight,
    "Risque": risk_weight
}


total_weight = (
    technical_weight
    + ml_weight
    + risk_weight
)

st.sidebar.write(f"Total : {total_weight}%")


if total_weight == 0:

    st.sidebar.warning(
        "Tous les poids sont à zéro : aucune analyse n'est possible.",
        icon=":material/warning:"
    )

elif total_weight != 100:

    st.sidebar.caption(
        "Le total n'est pas 100 % : les poids sont ramenés à cette échelle."
    )


analyze_button = st.sidebar.button(
    "Analyser",
    icon=":material/query_stats:",
    type="primary",
    width="stretch"
)


# =========================================================
# CHARGEMENT
# =========================================================

try:

    df, report = load_prepared(selected_symbol)

except FileNotFoundError as error:

    st.error(str(error))

    st.stop()

except ValueError as error:

    st.error(f"Fichier inexploitable : {error}")

    st.stop()


clean_df = df.dropna(subset=CORE_INDICATORS)


if clean_df.empty:

    st.error(
        f"Pas assez d'historique pour calculer les indicateurs : "
        f"{report['rows_out']} séances disponibles, il en faut au moins 50."
    )

    st.stop()


# =========================================================
# HEADER
# =========================================================

st.header(
    f"{structures[selected_symbol]['name']} — Analyse"
)


# La seance analysee vient du selecteur de date ci-dessous (la plus recente
# par defaut), et alimente aussi bien les indicateurs affiches que l'analyse
# technique et le modele.
if "Date" in clean_df.columns:

    available_dates = clean_df["Date"].dt.date.tolist()

    selected_date = st.selectbox(
        "Séance analysée",
        options=available_dates,
        index=len(available_dates) - 1,
        format_func=lambda value: value.strftime("%d/%m/%Y")
    )

    latest = clean_df.loc[
        clean_df["Date"].dt.date == selected_date
    ].iloc[-1]

    st.caption(f"{report['rows_out']} séances dans l'historique")

else:

    latest = clean_df.iloc[-1]


if report.get("day_month_swapped"):

    st.info(
        "Le fichier source inversait le jour et le mois sur une partie des "
        "dates. Elles ont été rétablies au chargement."
    )


ohlc_issues = report.get("ohlc_issues") or {}

if ohlc_issues.get("inconsistent"):

    st.warning(
        f"{ohlc_issues['inconsistent']} séances où le plus bas ou le plus "
        "haut contredit l'ouverture ou la clôture, sans explication connue. "
        "Ces colonnes ne sont pas utilisées dans l'analyse, mais le fichier "
        "source mérite vérification.",
        icon=":material/warning:"
    )

if ohlc_issues.get("flat_day_quirk"):

    st.caption(
        f"{ohlc_issues['flat_day_quirk']} séances sans mouvement où plus "
        "haut/plus bas diffèrent de l'ouverture/clôture — une convention "
        "récurrente de cet export, sans impact sur l'analyse."
    )


# =========================================================
# COURS
# =========================================================

with st.container(horizontal=True):
    st.metric("Cours", f"{latest['Close']:.2f}", border=True)
    st.metric("MM20", f"{latest['MM20']:.2f}", border=True)
    st.metric("MM50", f"{latest['MM50']:.2f}", border=True)
    st.metric("RSI", f"{latest['RSI']:.2f}", border=True)


# =========================================================
# GRAPHIQUE
# =========================================================

st.subheader(":material/show_chart: Évolution du cours")


show_rsi = "RSI" in selected_parameters
show_macd = "MACD" in selected_parameters

rows = 1 + show_rsi + show_macd

row_heights = {
    1: [1.0],
    2: [0.7, 0.3],
    3: [0.6, 0.2, 0.2]
}[rows]


# Les indicateurs (MM20/MM50/RSI/MACD) sont calcules sur tout l'historique,
# donc ils ont deja leurs jours de recul necessaires (50 pour MM50) avant le
# 1er janvier. Seul l'affichage est restreint a l'annee en cours, pour que la
# courbe du cours et celles des moyennes mobiles demarrent ensemble, sans
# trou du a une fenetre de calcul incomplete.
if "Date" in df.columns:

    year_start = pd.Timestamp(
        year=latest["Date"].year,
        month=1,
        day=1
    )

    display_df = df[df["Date"] >= year_start]

    if display_df.empty:
        display_df = df

else:

    display_df = df


x_axis = (
    display_df["Date"]
    if "Date" in display_df.columns
    else display_df.index
)


fig = make_subplots(
    rows=rows,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.04,
    row_heights=row_heights
)


for column, label in [
    ("Close", "Cours"),
    ("MM20", "MM20"),
    ("MM50", "MM50")
]:

    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=display_df[column],
            name=label,
            mode="lines"
        ),
        row=1,
        col=1
    )


if "Bollinger" in selected_parameters:

    for column, label in [
        ("Bollinger_Upper", "Bollinger haute"),
        ("Bollinger_Lower", "Bollinger basse")
    ]:

        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=display_df[column],
                name=label,
                mode="lines",
                line=dict(dash="dot")
            ),
            row=1,
            col=1
        )


current_row = 1


if show_rsi:

    current_row += 1

    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=display_df["RSI"],
            name="RSI",
            mode="lines",
            line=dict(color="#8e44ad")
        ),
        row=current_row,
        col=1
    )

    for level in (30, 70):

        fig.add_hline(
            y=level,
            line_dash="dot",
            line_color="gray",
            row=current_row,
            col=1
        )

    fig.update_yaxes(
        title_text="RSI",
        range=[0, 100],
        row=current_row,
        col=1
    )


if show_macd:

    current_row += 1

    histogram_colors = [
        "#27ae60" if value >= 0 else "#c0392b"
        for value in display_df["MACD_Hist"]
    ]

    fig.add_trace(
        go.Bar(
            x=x_axis,
            y=display_df["MACD_Hist"],
            name="Histogramme",
            marker_color=histogram_colors
        ),
        row=current_row,
        col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=display_df["MACD"],
            name="MACD",
            mode="lines",
            line=dict(color="#2980b9")
        ),
        row=current_row,
        col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=display_df["MACD_Signal"],
            name="Signal",
            mode="lines",
            line=dict(color="#e67e22")
        ),
        row=current_row,
        col=1
    )

    fig.update_yaxes(
        title_text="MACD",
        row=current_row,
        col=1
    )


fig.update_layout(
    height=350 * rows,
    hovermode="x unified",
    xaxis_title="Date" if rows == 1 else None,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0
    ),
    margin=dict(t=40)
)

fig.update_xaxes(
    showspikes=True,
    spikemode="across",
    spikesnap="cursor",
    spikethickness=1,
    spikecolor="#999999",
    spikedash="dot"
)

fig.update_yaxes(
    title_text="Prix",
    row=1,
    col=1
)


st.plotly_chart(fig, width="stretch")


# =========================================================
# ANALYSE
# =========================================================

if analyze_button:

    if not selected_parameters:

        st.error("Sélectionne au moins un paramètre.")

        st.stop()

    if total_weight == 0:

        st.error("Attribue au moins un poids non nul.")

        st.stop()

    try:

        ml_result = predict_row(latest)

    except ModelUnavailable as error:

        st.error(f"Modèle indisponible : {error}")

        st.stop()

    result = analyze(
        latest,
        ml_result,
        selected_parameters,
        weights
    )

    st.header(":material/query_stats: Résultat de l'analyse", divider=True)

    model_metadata = load_model_metadata()

    if model_metadata is not None:

        trained_at = pd.to_datetime(model_metadata["trained_at"])

        baseline_note = (
            "bat la référence naïve"
            if model_metadata["beats_baseline"]
            else "ne bat pas la référence naïve"
        )

        st.caption(
            f"Modèle ML : {model_metadata['model']} "
            f"· entraîné le {trained_at:%d/%m/%Y} "
            f"· ROC AUC (test) {model_metadata['test_scores']['roc_auc']:.2f} "
            f"· {baseline_note}"
        )

    decision = result["decision"]

    if decision == "ACHETER":
        st.success(decision, icon=":material/trending_up:")

    elif decision == "VENDRE":
        st.error(decision, icon=":material/trending_down:")

    else:
        st.warning(decision, icon=":material/trending_flat:")


    with st.container(horizontal=True):
        st.metric("Score global", f"{result['score']}/100", border=True)
        st.metric("Confiance", f"{result['confidence']}%", border=True)
        st.metric(
            "Probabilité ML (forte perf. à 5j)",
            f"{ml_result['probability_up'] * 100:.1f}%",
            border=True
        )


    # =====================================================
    # SCORES
    # =====================================================

    st.subheader(":material/donut_small: Détail des scores")

    with st.container(horizontal=True):
        st.metric(
            "Analyse technique",
            f"{result['technical_score']}/100",
            border=True
        )
        st.metric(
            "Machine Learning",
            f"{result['ml_score']}/100",
            border=True
        )
        st.metric(
            "Risque",
            f"{result['risk_score']}/100"
            if result["risk_score"] is not None
            else "non mesuré",
            border=True
        )


    st.caption(
        f"Signaux techniques : {result['positive']} favorables · "
        f"{result['negative']} défavorables · {result['neutral']} neutres"
    )


    # =====================================================
    # EXPLICATION
    # =====================================================

    st.subheader(":material/lightbulb: Pourquoi cette décision ?")

    for reason in result["reasons"]:

        st.write(f"• {reason}")


    # =====================================================
    # PARAMETRES UTILISES
    # =====================================================

    with st.container(border=True):

        st.markdown("**Paramètres utilisés**")

        st.write(", ".join(selected_parameters))

        st.markdown("**Pondération**")

        st.write(
            f"Technique : {technical_weight} % · "
            f"Machine Learning : {ml_weight} % · "
            f"Risque : {risk_weight} %"
        )


else:

    st.info(
        "Sélectionne tes paramètres puis clique sur "
        "« Analyser » pour obtenir une décision.",
        icon=":material/info:"
    )


# =========================================================
# DONNEES
# =========================================================

with st.expander("Voir les données", icon=":material/table_chart:"):

    st.dataframe(
        df.tail(30),
        width="stretch"
    )
