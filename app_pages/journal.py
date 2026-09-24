import streamlit as st

from services.prediction_log import load_prediction_log


st.title("Journal des analyses")

st.caption(
    "Chaque « Analyser » est enregistré ici avant que le résultat réel ne "
    "soit connu — la seule base fiable pour mesurer, dans le temps, si les "
    "décisions passées se sont avérées justes."
)


prediction_log = load_prediction_log()

if prediction_log.empty:

    st.info(
        "Aucune analyse enregistrée pour l'instant. Clique sur « Analyser » "
        "depuis la page Analyse pour commencer le suivi.",
        icon=":material/info:"
    )

else:

    st.dataframe(
        prediction_log.sort_values("logged_at", ascending=False),
        width="stretch",
        hide_index=True
    )
