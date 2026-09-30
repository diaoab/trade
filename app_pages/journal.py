import streamlit as st

from services.backtest import (
    HORIZONS as BACKTEST_HORIZONS,
    summarize_scores,
    summarize_signals
)
from services.loaders import load_signal_backtest
from services.market_data import get_structures
from services.prediction_log import (
    HORIZON_SESSIONS,
    evaluate_predictions,
    load_prediction_log,
    summarize_performance
)


st.title("Journal des analyses")

st.caption(
    "Chaque « Analyser » est enregistré ici avant que le résultat réel ne "
    "soit connu, puis confronté au cours "
    f"{HORIZON_SESSIONS} séances plus tard dès que l'historique importé "
    "va assez loin."
)


prediction_log = load_prediction_log()

if prediction_log.empty:

    st.info(
        "Aucune analyse enregistrée pour l'instant. Clique sur « Analyser » "
        "depuis la page Analyse pour commencer le suivi.",
        icon=":material/info:"
    )

else:

    evaluated = evaluate_predictions(prediction_log)

    summary = summarize_performance(evaluated)


    # =========================================================
    # BILAN
    # =========================================================

    st.subheader(":material/fact_check: Bilan")

    if not summary:

        st.info(
            "Aucune analyse n'a encore d'issue connue : il faut au moins "
            f"{HORIZON_SESSIONS} séances d'historique après la séance analysée. "
            "Importe un fichier de cotations plus récent pour la structure "
            "concernée, ou analyse une séance plus ancienne.",
            icon=":material/hourglass_top:"
        )

    else:

        with st.container(horizontal=True):

            for decision in ("ACHETER", "CONSERVER", "VENDRE"):

                stats = summary.get(decision)

                if stats is None:
                    continue

                st.metric(
                    f"{decision} · {stats['count']} séance(s)",
                    f"{stats['hit_rate'] * 100:.0f} % justes"
                    if stats["hit_rate"] is not None
                    else "non jugé",
                    delta=f"{stats['mean_return'] * 100:+.2f} % en moyenne",
                    delta_color="off",
                    border=True
                )

        st.caption(
            "ACHETER est juste si le cours a monté, VENDRE s'il a baissé ; "
            "CONSERVER n'est pas jugé. Variation mesurée sur les cours ajustés "
            "des dividendes ; une séance analysée plusieurs fois ne compte "
            "qu'une fois."
        )


    # =========================================================
    # DETAIL
    # =========================================================

    st.subheader(":material/history: Détail")

    detail = evaluated.sort_values("logged_at", ascending=False).copy()

    detail["realized_return"] = detail["realized_return"] * 100

    st.dataframe(
        detail[[
            "session_date",
            "structure_name",
            "decision",
            "score",
            "close",
            "future_close",
            "realized_return",
            "outcome",
            "technical_score",
            "ml_score",
            "risk_score",
            "logged_at"
        ]],
        column_config={
            "session_date": st.column_config.DateColumn(
                "Séance", format="DD/MM/YYYY"
            ),
            "structure_name": "Structure",
            "decision": "Décision",
            "score": "Score",
            "close": "Cours",
            "future_close": f"Cours à +{HORIZON_SESSIONS} séances",
            "realized_return": st.column_config.NumberColumn(
                "Variation", format="%+.2f %%"
            ),
            "outcome": "Issue",
            "technical_score": "Technique",
            "ml_score": "ML",
            "risk_score": "Risque",
            "logged_at": "Enregistrée le"
        },
        width="stretch",
        hide_index=True
    )


# =========================================================
# BACKTEST DES SIGNAUX
# =========================================================

st.subheader(":material/science: Fiabilité historique des signaux")

fee = st.session_state.get("round_trip_fee", 0.0)

st.caption(
    "Ce que le cours a fait après chaque signal technique, sur tout "
    "l'historique des structures du catalogue. Un signal n'apporte quelque "
    "chose que s'il s'écarte nettement de la première ligne, et n'est "
    "exploitable que si sa variation reste positive une fois les frais "
    f"d'un aller-retour déduits ({fee:g} %, réglable dans Paramètres)."
)

horizon = st.pills(
    "Horizon",
    BACKTEST_HORIZONS,
    default=BACKTEST_HORIZONS[1],
    format_func=lambda sessions: f"{sessions} séances",
    key="backtest_horizon",
    label_visibility="collapsed"
) or BACKTEST_HORIZONS[1]

replayed = load_signal_backtest(tuple(get_structures().keys()))

if replayed.empty:

    st.info(
        "Pas assez d'historique pour rejouer les signaux.",
        icon=":material/info:"
    )

else:

    percent = st.column_config.NumberColumn(format="%.1f")

    signed = st.column_config.NumberColumn(format="%+.2f")

    columns = {
        "Hausse ensuite (%)": percent,
        "Baisse ensuite (%)": percent,
        "Variation moyenne (%)": signed,
        "Net de frais (%)": signed
    }

    st.dataframe(
        summarize_signals(replayed, horizon, fee),
        column_config=columns,
        width="stretch",
        hide_index=True
    )

    st.dataframe(
        summarize_scores(replayed, horizon, fee),
        column_config=columns,
        width="stretch",
        hide_index=True
    )

    st.caption(
        f"{len(replayed)} séances rejouées. « Net de frais » : ce qu'il "
        "serait resté en moyenne à qui aurait acheté à chacune de ces "
        "séances et revendu à l'horizon choisi. Les extrêmes du RSI et de "
        "Bollinger sont lus titre par titre, avec ce qui était connu ce "
        "jour-là ; le MACD est indicatif et n'entre pas dans le score. La "
        "composante ML n'est pas rejouée ici."
    )
