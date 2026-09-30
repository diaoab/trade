import streamlit as st

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

    st.stop()


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
