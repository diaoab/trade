import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

from config import DEFAULT_WEIGHTS
from services.assistant_chat import (
    AssistantUnavailable,
    build_context,
    stream_answer
)
from services.avatar import avatar_html
from services.analysis import analyse_session, relative_performance
from services.loaders import load_prepared
from services.market_data import cutoff_date, get_structures
from services.narration import build_narration
from services.predictor import load_model_metadata
from services.prediction_log import log_prediction
from services.targets import FUTURE_HORIZON_DAYS
from services.themes import CHART_COLORS, THEMES


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

adjust_dividends = st.session_state.get("adjust_dividends", True)

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

    df, report = load_prepared(selected_symbol, adjust_dividends)

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


# =========================================================
# DIVIDENDES
# =========================================================

dividends = [
    {
        "ex_date": pd.Timestamp(dividend["ex_date"]),
        "amount": dividend["amount"]
    }
    for dividend in structures[selected_symbol]["dividends"]
]

# Le prochain detachement se lit par rapport a la seance analysee, pas a la
# date du jour : rejouer une seance passee montre ce qu'on savait ce jour-la.
upcoming_dividends = (
    [
        dividend
        for dividend in dividends
        if dividend["ex_date"] > latest["Date"]
    ]
    if "Date" in clean_df.columns
    else []
)

# Repris par l'assistant vocal dans son resume (cf. services.narration).
dividend_notice = None

if upcoming_dividends:

    next_dividend = upcoming_dividends[0]

    dividend_cutoff = cutoff_date(next_dividend["ex_date"])

    days_left = (dividend_cutoff - latest["Date"].normalize()).days

    if days_left > 0:
        countdown = f"dans {days_left} jour{'s' if days_left > 1 else ''}"
    elif days_left == 0:
        countdown = "c'est la séance analysée"
    else:
        countdown = "dépassée"

    dividend_yield = (
        next_dividend["amount"]
        / latest.get("Close_Raw", latest["Close"])
        * 100
    )

    dividend_notice = {
        "cutoff": dividend_cutoff,
        "ex_date": next_dividend["ex_date"],
        "amount": next_dividend["amount"],
        "days_left": days_left
    }

    st.info(
        f"**Date butoir dividende : {dividend_cutoff:%d/%m/%Y}** "
        f"({countdown}) — dernière séance pour acheter avec droit au "
        f"dividende de {next_dividend['amount']:g} FCFA par action "
        f"(rendement {dividend_yield:.1f} %). Détachement le "
        f"{next_dividend['ex_date']:%d/%m/%Y} : le cours baisse "
        "mécaniquement du montant du dividende ce jour-là.",
        icon=":material/event:"
    )

if report.get("dividends_applied"):

    st.caption(
        f"Cours ajustés de {len(report['dividends_applied'])} détachement(s) "
        "de dividende : l'historique antérieur est recalé pour que la baisse "
        "mécanique du jour ex-dividende ne fausse pas les indicateurs. "
        "La carte « Cours » affiche le cours réellement coté."
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


# Cours reellement cote : Close_Raw existe des que l'historique a ete ajuste
# d'un dividende (cf. services.market_data.adjust_for_dividends).
quoted_close = "Close_Raw" if "Close_Raw" in clean_df.columns else "Close"


with st.container(horizontal=True, horizontal_alignment="distribute"):
    st.metric(
        "Cours",
        f"{latest[quoted_close]:.2f}",
        delta=_delta(quoted_close),
        border=True,
        chart_data=recent_window[quoted_close],
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
# COMPARAISON A L'INDICE
# =========================================================

benchmark_symbol = st.session_state.get("benchmark_symbol")

if (
    benchmark_symbol in structures
    and benchmark_symbol != selected_symbol
    and "Date" in clean_df.columns
):

    try:

        benchmark_df, _ = load_prepared(benchmark_symbol, adjust_dividends)

    except (FileNotFoundError, ValueError):

        benchmark_df = None

    comparison = (
        relative_performance(df, benchmark_df, latest["Date"])
        if benchmark_df is not None and "Date" in benchmark_df.columns
        else []
    )

    if comparison:

        benchmark_name = structures[benchmark_symbol]["name"]

        with st.container(border=True):

            st.markdown(
                f"**:material/leaderboard: Face à l'indice {benchmark_name}**"
            )

            with st.container(horizontal=True):

                for row in comparison:

                    st.metric(
                        f"{row['period']} · indice "
                        f"{row['benchmark'] * 100:+.1f} %",
                        f"{row['stock'] * 100:+.1f} %",
                        delta=f"{row['gap'] * 100:+.1f} pts vs indice"
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

        with st.container(horizontal=True):

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
        "Sélectionne au moins un indicateur dans **Paramètres** avant "
        "d'analyser."
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
#
# Le graphique s'arrete a la seance analysee : rejouer une seance passee
# doit montrer ce qu'on voyait ce jour-la, pas la suite du cours.
history_df = (
    df[df["Date"] <= latest["Date"]]
    if "Date" in df.columns
    else df
)

if "Date" in df.columns and chart_range in CHART_RANGE_DAYS:

    window_start = latest["Date"] - pd.Timedelta(
        days=CHART_RANGE_DAYS[chart_range]
    )

    display_df = history_df[history_df["Date"] >= window_start]

    if display_df.empty:
        display_df = history_df

else:

    display_df = history_df


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
    ("MM50", "MM50", CHART_COLORS["mm50"])
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

    # Bande basse puis bande haute, dans cet ordre : fill="tonexty" remplit
    # jusqu'a la trace precedente, ce qui colore le canal entre les deux.
    # La bande mediane n'est pas retracee : c'est la MM20, deja affichee.
    for column, label, fill in [
        ("Bollinger_Lower", "Bollinger basse", None),
        ("Bollinger_Upper", "Bollinger haute", "tonexty")
    ]:

        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=display_df[column],
                name=label,
                mode="lines",
                line=dict(width=1, color=CHART_COLORS["bollinger"]),
                fill=fill,
                fillcolor=_fill_color(CHART_COLORS["bollinger"], 0.12)
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
            line=dict(color=CHART_COLORS["rsi"])
        ),
        row=current_row,
        col=1
    )

    for level in (30, 70):

        fig.add_hline(
            y=level,
            line_dash="dot",
            line_color=active_theme["text"],
            opacity=0.35,
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
            line=dict(color=CHART_COLORS["macd"])
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
            line=dict(color=CHART_COLORS["macd_signal"])
        ),
        row=current_row,
        col=1
    )

    fig.add_hline(
        y=0,
        line_color=active_theme["text"],
        opacity=0.35,
        row=current_row,
        col=1
    )

    fig.update_yaxes(
        title_text="MACD",
        row=current_row,
        col=1
    )


# Detachements de dividende visibles sur la periode : un trait vertical sur
# toute la hauteur, pour relier d'un coup d'oeil un decrochage du cours ou
# des indicateurs a sa cause.
if "Date" in display_df.columns:

    for dividend in dividends:

        if not (
            display_df["Date"].iloc[0]
            <= dividend["ex_date"]
            <= display_df["Date"].iloc[-1]
        ):
            continue

        fig.add_shape(
            type="line",
            x0=dividend["ex_date"],
            x1=dividend["ex_date"],
            y0=0,
            y1=1,
            xref="x",
            yref="paper",
            line=dict(color=CHART_COLORS["dividend"], width=1, dash="dash")
        )

        fig.add_annotation(
            x=dividend["ex_date"],
            y=1,
            xref="x",
            yref="paper",
            text=f"Ex-div. {dividend['amount']:g}",
            showarrow=False,
            yanchor="bottom",
            font=dict(color=CHART_COLORS["dividend"], size=11)
        )


fig.update_layout(
    height=350 * rows,
    hovermode="x unified",
    xaxis_title="Date" if rows == 1 else None,
    # Legende sous le graphique : au-dessus, elle passe sur plusieurs lignes
    # des que la page est etroite et vient recouvrir les courbes.
    legend=dict(
        orientation="h",
        yanchor="top",
        y=-0.08,
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
st.plotly_chart(fig, theme=None)


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

    # Modele absent, ou modele qui ne bat pas la reference naive : geres
    # par analyse_session, et signales plus bas avec le resultat.
    result, ml_result, weights = analyse_session(
        latest,
        selected_parameters,
        weights,
        model_metadata
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

    # Conserve en session : sans cela le resultat disparaitrait au premier
    # rerun (changer la periode du graphique, par exemple). "session" sert a
    # ne le reafficher que pour la structure et la seance qu'il decrit.
    st.session_state["last_analysis"] = {
        "symbol": selected_symbol,
        "session": latest.name,
        "adjust_dividends": adjust_dividends,
        "result": result,
        "ml_result": ml_result,
        "selected_parameters": selected_parameters,
        "weights": weights
    }


last_analysis = st.session_state.get("last_analysis")

if (
    last_analysis is not None
    and last_analysis["symbol"] == selected_symbol
    and last_analysis["session"] == latest.name
    and last_analysis["adjust_dividends"] == adjust_dividends
):

    result = last_analysis["result"]
    ml_result = last_analysis["ml_result"]

    st.header(":material/query_stats: Résultat de l'analyse", divider=True)

    # =====================================================
    # ASSISTANT VOCAL
    # =====================================================

    analysed_session = latest["Date"] if "Date" in clean_df.columns else None

    components.html(
        avatar_html(
            build_narration(
                structure_name=structures[selected_symbol]["name"],
                session_date=analysed_session,
                result=result,
                dividend=dividend_notice
            ),
            active_theme
        ),
        height=230
    )

    # =====================================================
    # ASSISTANT CONVERSATIONNEL
    # =====================================================

    # La conversation vit avec l'analyse qu'elle commente : relancer une
    # analyse repart d'une conversation vide.
    chat = last_analysis.setdefault("chat", {"history": [], "shown": []})

    with st.container(border=True):

        st.markdown("**:material/forum: Poser une question sur ce résultat**")

        st.caption(
            "L'assistant répond à partir du résultat ci-dessus, sans rien "
            "recalculer. Il passe par l'API Claude : service payant, clé "
            "`ANTHROPIC_API_KEY` requise."
        )

        for role, text in chat["shown"]:

            with st.chat_message(role):
                st.write(text)

        question = st.chat_input(
            "Ex. : pourquoi ce signal ? Que veut dire le MACD ici ?",
            key="assistant_question"
        )

        if question:

            with st.chat_message("user"):
                st.write(question)

            chat["history"].append({"role": "user", "content": question})

            try:

                with st.chat_message("assistant"):

                    answer = st.write_stream(
                        stream_answer(
                            build_context(
                                structures[selected_symbol]["name"],
                                analysed_session,
                                result,
                                ml_result,
                                dividend_notice
                            ),
                            chat["history"]
                        )
                    )

            except AssistantUnavailable as error:

                # Question sans reponse : on la retire, sinon le prochain
                # envoi enchainerait deux messages utilisateur.
                chat["history"].pop()

                st.warning(str(error), icon=":material/warning:")

            else:

                chat["shown"] += [("user", question), ("assistant", answer)]

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


    with st.container(horizontal=True):
        st.metric(
            ":material/speed: Score global",
            f"{result['score']}/100",
            border=True
        )
        st.metric(
            ":material/verified: Confiance",
            f"{result['confidence']}%",
            border=True
        )
        st.metric(
            ":material/psychology: Probabilité ML (forte perf. à "
            f"{FUTURE_HORIZON_DAYS} séances)",
            f"{ml_result['probability_up'] * 100:.1f}%"
            if ml_result is not None
            else "indisponible",
            border=True
        )

    # .get : un resultat conserve en session avant l'ajout de ce champ.
    if result.get("liquidity_warnings"):

        st.warning(
            "**Liquidité faible.** "
            + " ".join(result["liquidity_warnings"])
            + " Les signaux techniques sont moins fiables sur un titre qui "
            "s'échange peu.",
            icon=":material/water_drop:"
        )

    if ml_result is None:

        st.warning(
            "Modèle ML indisponible : la décision repose sur l'analyse "
            "technique seule. Lance `python -m training.train` pour "
            "l'entraîner.",
            icon=":material/warning:"
        )

    elif last_analysis["weights"]["Machine Learning"] == 0:

        st.warning(
            "Le modèle ML ne bat pas la référence naïve sur son jeu de "
            "test : sa probabilité est affichée à titre indicatif, mais "
            "elle est exclue du score global.",
            icon=":material/warning:"
        )


    # =====================================================
    # SCORES
    # =====================================================

    st.subheader(":material/donut_small: Détail des scores")

    with st.container(horizontal=True):
        st.metric(
            ":material/show_chart: Analyse technique",
            f"{result['technical_score']}/100",
            border=True
        )
        st.metric(
            ":material/psychology: Machine Learning",
            f"{result['ml_score']}/100"
            if result["ml_score"] is not None
            else "indisponible",
            border=True
        )
        st.metric(
            ":material/shield: Risque",
            f"{result['risk_score']}/100"
            if result["risk_score"] is not None
            else "non mesuré",
            border=True
        )


    def _signals(count, singular):
        return f"{count} {singular}{'s' if count > 1 else ''}"

    st.caption(
        "Signaux techniques : "
        f"{_signals(result['positive'], 'favorable')} · "
        f"{_signals(result['negative'], 'défavorable')} · "
        f"{_signals(result['neutral'], 'neutre')}"
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

        st.write(", ".join(last_analysis["selected_parameters"]))

        st.markdown("**Pondération**")

        st.write(
            " · ".join(
                f"{name} : {weight} %"
                for name, weight in last_analysis["weights"].items()
            )
        )

        st.markdown("**Dividendes**")

        st.write(
            f"{len(report['dividends_applied'])} détachement(s) neutralisé(s) "
            "dans l'historique."
            if report.get("dividends_applied")
            else "Cours bruts, sans ajustement de dividende."
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
