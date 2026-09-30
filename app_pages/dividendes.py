import pandas as pd
import streamlit as st

from services.loaders import market_overview


st.title("Dividendes")

st.caption(
    "Rendement et calendrier des détachements, d'après les dividendes "
    "saisis dans Paramètres. Rendement = dividendes détachés sur les douze "
    "mois précédant la dernière séance, rapportés au dernier cours."
)


overview = market_overview()

rows = []

calendar = []

for row in overview:

    if row["date"] is None:
        continue

    year_ago = row["date"] - pd.DateOffset(years=1)

    trailing = sum(
        dividend["amount"]
        for dividend in row["dividends"]
        if year_ago < pd.Timestamp(dividend["ex_date"]) <= row["date"]
    )

    last = [
        dividend
        for dividend in row["dividends"]
        if pd.Timestamp(dividend["ex_date"]) <= row["date"]
    ]

    rows.append({
        "Structure": row["name"],
        "Dernier cours": row["close"],
        "Dividendes 12 mois (FCFA)": trailing if row["dividends"] else None,
        "Rendement (%)": (
            trailing / row["close"] * 100
            if row["dividends"]
            else None
        ),
        "Dernier détachement": (
            pd.Timestamp(last[-1]["ex_date"]) if last else None
        ),
        "Dividendes saisis": len(row["dividends"])
    })

    if row["dividend"] is not None:

        calendar.append({
            "Structure": row["name"],
            "Date butoir d'achat": row["dividend"]["cutoff"],
            "Détachement": row["dividend"]["ex_date"],
            "Dividende par action (FCFA)": row["dividend"]["amount"],
            "Rendement de ce dividende (%)": (
                row["dividend"]["amount"] / row["close"] * 100
            ),
            "Jours restants": row["dividend"]["days_left"]
        })


# =========================================================
# CALENDRIER
# =========================================================

st.subheader(":material/event: Prochains détachements")

if calendar:

    st.dataframe(
        pd.DataFrame(calendar).sort_values("Date butoir d'achat"),
        column_config={
            "Date butoir d'achat": st.column_config.DateColumn(
                format="DD/MM/YYYY"
            ),
            "Détachement": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Rendement de ce dividende (%)": st.column_config.NumberColumn(
                format="%.2f"
            )
        },
        width="stretch",
        hide_index=True
    )

    st.caption(
        "Jours restants comptés depuis la dernière séance de l'historique "
        "de chaque titre, pas depuis aujourd'hui."
    )

else:

    st.caption(
        "Aucun détachement à venir n'est enregistré. Les dates annoncées "
        "par les sociétés se saisissent dans Paramètres, structure par "
        "structure."
    )


# =========================================================
# RENDEMENT
# =========================================================

st.subheader(":material/percent: Rendement par structure")

if not rows:

    st.caption("Aucune structure dans le catalogue.")

else:

    st.dataframe(
        pd.DataFrame(rows).sort_values(
            "Rendement (%)",
            ascending=False,
            na_position="last"
        ),
        column_config={
            "Dernier cours": st.column_config.NumberColumn(format="%.0f"),
            "Rendement (%)": st.column_config.NumberColumn(format="%.2f"),
            "Dernier détachement": st.column_config.DateColumn(
                format="DD/MM/YYYY"
            )
        },
        width="stretch",
        hide_index=True
    )

    if not any(row["Dividendes saisis"] for row in rows):

        st.info(
            "Aucun dividende n'est encore saisi : le rendement ne peut pas "
            "être calculé. Ajoute-les dans Paramètres.",
            icon=":material/info:"
        )

        st.page_link(
            "app_pages/parametres.py",
            label="Aller aux paramètres",
            icon=":material/tune:"
        )
