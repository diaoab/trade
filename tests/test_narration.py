"""Tests du resume lu par l'assistant vocal (services/narration.py)."""

import pandas as pd

from services.narration import build_narration


RESULT = {
    "decision": "CONSERVER",
    "score": 58.4,
    "confidence": 50.0,
    "technical_score": 62.0,
    "ml_score": 55.25,
    "risk_score": None,
    "positive": 2,
    "negative": 1,
    "neutral": 0,
    "reasons": [
        "Le cours est supérieur à la MM20.",
        "Le modèle ML estime une probabilité de hausse de 57.0% "
        "(position dans son historique : 64.2/100)."
    ]
}


def _narration(dividend=None):

    return " ".join(
        build_narration(
            structure_name="BIBI CI",
            session_date=pd.Timestamp("2025-06-01"),
            result=RESULT,
            dividend=dividend
        )
    )


def test_narration_states_decision_scores_and_reasons_for_the_ear():

    text = _narration()

    assert "BIBI CI, séance du 1er juin 2025" in text
    assert "le signal est de conserver" in text
    assert "58,4 sur 100" in text
    assert "Le risque n'a pas été mesuré" in text
    assert "2 favorables, 1 défavorable, 0 neutre" in text
    assert "Le cours est supérieur à la moyenne mobile 20." in text
    assert "hausse de 57 pour cent (position" in text
    assert "64,2 sur 100" in text
    assert "modèle d'apprentissage estime" in text
    assert "ne constitue pas une recommandation" in text
    assert "dividende" not in text


def test_narration_mentions_an_upcoming_dividend_cutoff():

    dividend = {
        "cutoff": pd.Timestamp("2025-06-04"),
        "ex_date": pd.Timestamp("2025-06-05"),
        "amount": 450.0,
        "days_left": 3
    }

    text = _narration(dividend)

    assert "450 francs par action est le 4 juin 2025, dans 3 jours" in text

    # Date butoir deja passee a la seance analysee : plus rien a annoncer.
    assert "dividende" not in _narration({**dividend, "days_left": -1})
