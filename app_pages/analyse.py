import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config import DEFAULT_WEIGHTS
from services.decision_engine import analyze
from services.loaders import load_prepared
from services.market_data import get_structures
from services.predictor import ModelUnavailable, load_model_metadata, predict_row
from services.prediction_log import log_prediction
from services.themes import THEMES


# Colonnes sans lesquelles ni le graphique ni le moteur de decision ne
# peuvent fonctionner.
CORE_INDICATORS = [
    "MM20",
    "MM50",
    "RSI",
    "MACD",
    "MACD_Signal"
]

CHART_RANGE_DAYS = {
    "1M": 30,
    "3M": 90,
    "6M": 182,
    "1A": 365
}


structures = get_structures()

selected_symbol = st.session_state["selected_symbol"]

selected_parameters = st.session_state.get("selected_parameters", [])

weights = st.session_state.get("weights", DEFAULT_WEIGHTS)

technical_weight = weights.get("Technique", 0)
ml_weight = weights.get("Machine Learning", 0)
risk_weight = weights.get("Risque", 0)
total_weight = technical_weight + ml_weight + risk_weight

active_theme = THEMES[st.session_state["theme_name"]]


# =========================================================
# TITRE
# =========================================================

st.title("Analyse")

st.caption(
    "Assistant expérimental d'analyse des structures cotées."
)

st.warning(
    "Les résultats sont expérimentaux et ne constituent "
    "pas une recommandation financière personnalisée.",
    icon=":material/warning:"
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

# Séance precedente dans l'historique (pas forcement la veille naturelle,
# ex. weekends) : sert de reference pour la variation affichee sur chaque
# metrique et pour les mini-graphiques de tendance.
SPARKLINE_WINDOW = 20

latest_position = clean_df.index.get_loc(latest.name)

previous = (
    clean_df.iloc[latest_position - 1]
    if latest_position > 0
    else None
)

recent_window = clean_df.iloc[
    max(0, latest_position - SPARKLINE_WINDOW + 1):latest_position + 1
]


def _delta(column):
    if previous is None:
        return None
    return f"{latest[column] - previous[column]:.2f}"


with st.container(horizontal=True, horizontal_alignment="distribute", wrap=False):
    st.metric(
        "Cours",
        f"{latest['Close']:.2f}",
        delta=_delta("Close"),
        border=True,
        chart_data=recent_window["Close"],
        chart_type="line"
    )
    st.metric(
        "MM20",
        f"{latest['MM20']:.2f}",
        delta=_delta("MM20"),
        border=True,
        chart_data=recent_window["MM20"],
        chart_type="line"
    )
    st.metric(
        "MM50",
        f"{latest['MM50']:.2f}",
        delta=_delta("MM50"),
        border=True,
        chart_data=recent_window["MM50"],
        chart_type="line"
    )
    st.metric(
        "RSI",
        f"{latest['RSI']:.2f}",
        delta=_delta("RSI"),
        border=True,
        chart_data=recent_window["RSI"],
        chart_type="line"
    )


# =========================================================
# MODELE
# =========================================================

with st.container(border=True):

    st.markdown("**:material/psychology: Modèle ML**")

    model_metadata = load_model_metadata()

    if model_metadata is None:

        st.caption(
            "Pas encore entraîné : lance python -m training.train."
        )

    else:

        trained_at = pd.to_datetime(model_metadata["trained_at"])

        with st.container(horizontal=True, wrap=False):

            st.metric(
                "ROC AUC (test)",
                f"{model_metadata['test_scores']['roc_auc']:.2f}"
            )

            st.metric(
                "Vs référence naïve",
                "Bat" if model_metadata["beats_baseline"] else "Ne bat pas"
            )

        st.caption(
            f"{model_metadata['model']} · "
            f"entraîné le {trained_at:%d/%m/%Y}"
        )


# =========================================================
# ANALYSER
# =========================================================

analyze_button = st.button(
    "Analyser",
    icon=":material/query_stats:",
    type="primary"
)

if total_weight == 0 or not selected_parameters:

    st.caption(
        "Configure au moins un indicateur et un poids non nul dans "
        "**Paramètres** avant d'analyser."
    )

    st.page_link(
        "app_pages/parametres.py",
        label="Aller aux paramètres",
        icon=":material/tune:"
    )


# =========================================================
# GRAPHIQUE
# =========================================================

st.subheader(":material/show_chart: Évolution du cours")

chart_range = st.pills(
    "Période affichée",
    list(CHART_RANGE_DAYS.keys()) + ["Tout"],
    default="1A",
    key="chart_range",
    label_visibility="collapsed"
)


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
# debut de la periode affichee : seul l'affichage est restreint, pour que la
# courbe du cours et celles des moyennes mobiles demarrent ensemble, sans
# trou du a une fenetre de calcul incomplete.
if "Date" in df.columns and chart_range in CHART_RANGE_DAYS:

    window_start = latest["Date"] - pd.Timedelta(
        days=CHART_RANGE_DAYS[chart_range]
    )

    display_df = df[df["Date"] >= window_start]

    if display_df.empty:
        display_df = df

else:

    display_df = df


x_axis = (
    display_df["Date"]
    if "Date" in display_df.columns
    else display_df.index
)


def _fill_color(hex_color, alpha):
    """Convertit #RRGGBB en rgba(...) pour le degrade sous la courbe."""

    hex_color = hex_color.lstrip("#")

    red, green, blue = (
        int(hex_color[index:index + 2], 16)
        for index in (0, 2, 4)
    )

    return f"rgba({red}, {green}, {blue}, {alpha})"


fig = make_subplots(
    rows=rows,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.04,
    row_heights=row_heights
)


# Ligne de base invisible juste sous le plus bas de la periode affichee :
# sert uniquement de repere pour le degrade sous la courbe du cours
# (fill="tonexty" ci-dessous), sans tirer l'axe des prix jusqu'a zero.
close_baseline = display_df["Close"].min() * 0.98

fig.add_trace(
    go.Scatter(
        x=x_axis,
        y=[close_baseline] * len(display_df),
        name="_baseline",
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip"
    ),
    row=1,
    col=1
)

fig.add_trace(
    go.Scatter(
        x=x_axis,
        y=display_df["Close"],
        name="Cours",
        mode="lines",
        line=dict(color=active_theme["text"]),
        fill="tonexty",
        fillcolor=_fill_color(active_theme["primary"], 0.18)
    ),
    row=1,
    col=1
)


for column, label, color in [
    ("MM20", "MM20", active_theme["primary"]),
    ("MM50", "MM50", active_theme["accent_a"])
]:

    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=display_df[column],
            name=label,
            mode="lines",
            line=dict(color=color)
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
                line=dict(dash="dot", color=active_theme["accent_c"])
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
            line=dict(color=active_theme["accent_b"])
        ),
        row=current_row,
        col=1
    )

    for level in (30, 70):

        fig.add_hline(
            y=level,
            line_dash="dot",
            line_color=active_theme["border"],
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
        active_theme["green"] if value >= 0 else active_theme["red"]
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
            line=dict(color=active_theme["accent_a"])
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
            line=dict(color=active_theme["accent_c"])
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
        x=0,
        font=dict(color=active_theme["text"])
    ),
    margin=dict(t=40),
    paper_bgcolor=active_theme["secondary_bg"],
    plot_bgcolor=active_theme["secondary_bg"],
    font=dict(color=active_theme["text"]),
    hoverlabel=dict(
        bgcolor=active_theme["bg"],
        font_color=active_theme["text"],
        bordercolor=active_theme["border"]
    )
)

fig.update_xaxes(
    showspikes=True,
    spikemode="across",
    spikesnap="cursor",
    spikethickness=1,
    spikecolor=active_theme["primary"],
    spikedash="dot",
    gridcolor=active_theme["border"],
    zerolinecolor=active_theme["border"]
)

fig.update_yaxes(
    gridcolor=active_theme["border"],
    zerolinecolor=active_theme["border"]
)

fig.update_yaxes(
    title_text="Prix",
    row=1,
    col=1
)


# theme=None : on pilote nous-memes toutes les couleurs du graphique
# (cf. ci-dessus) pour qu'il suive la palette choisie dans Parametres
# plutot que le theme statique de config.toml.
st.plotly_chart(fig, width="stretch", theme=None)


# =========================================================
# ANALYSE
# =========================================================

if analyze_button:

    if not selected_parameters:

        st.error("Sélectionne au moins un indicateur dans Paramètres.")

        st.stop()

    if total_weight == 0:

        st.error("Attribue au moins un poids non nul dans Paramètres.")

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

    # Trace de cette analyse, avant que le resultat reel ne soit connu : seule
    # base possible pour mesurer plus tard une performance en conditions
    # reelles (cf. services/prediction_log.py).
    log_prediction(
        symbol=selected_symbol,
        structure_name=structures[selected_symbol]["name"],
        session_date=latest["Date"] if "Date" in clean_df.columns else None,
        close=latest["Close"],
        result=result,
        ml_result=ml_result,
        weights=weights
    )

    st.header(":material/query_stats: Résultat de l'analyse", divider=True)

    if model_metadata is not None:

        st.caption(
            f"Modèle ML : {model_metadata['model']} "
            f"· entraîné le {trained_at:%d/%m/%Y} "
            f"· ROC AUC (test) {model_metadata['test_scores']['roc_auc']:.2f} "
            f"· {'bat' if model_metadata['beats_baseline'] else 'ne bat pas'} "
            "la référence naïve"
        )

    decision = result["decision"]

    if decision == "ACHETER":
        st.success(decision, icon=":material/trending_up:")

    elif decision == "VENDRE":
        st.error(decision, icon=":material/trending_down:")

    else:
        st.warning(decision, icon=":material/trending_flat:")


    with st.container(horizontal=True, wrap=False):
        st.metric(
            "Score global",
            f"{result['score']}/100",
            icon=":material/speed:",
            border=True
        )
        st.metric(
            "Confiance",
            f"{result['confidence']}%",
            icon=":material/verified:",
            border=True
        )
        st.metric(
            "Probabilité ML (forte perf. à 5j)",
            f"{ml_result['probability_up'] * 100:.1f}%",
            icon=":material/psychology:",
            border=True
        )


    # =====================================================
    # SCORES
    # =====================================================

    st.subheader(":material/donut_small: Détail des scores")

    with st.container(horizontal=True, wrap=False):
        st.metric(
            "Analyse technique",
            f"{result['technical_score']}/100",
            icon=":material/show_chart:",
            border=True
        )
        st.metric(
            "Machine Learning",
            f"{result['ml_score']}/100",
            icon=":material/psychology:",
            border=True
        )
        st.metric(
            "Risque",
            f"{result['risk_score']}/100"
            if result["risk_score"] is not None
            else "non mesuré",
            icon=":material/shield:",
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
