"""Tests du moteur de decision (services/decision_engine.py).

analyze() ne lit ses arguments que par indexation ("row['Close']", ...) : un
simple dict suffit donc a simuler une seance, sans construire un DataFrame.
"""

from services.decision_engine import analyze


NEUTRAL_ML_RESULT = {"probability_up": 0.5}


def _base_row(**overrides):

    row = {
        "Close": 100.0,
        "MM20": 100.0,
        "MM50": 100.0,
        "RSI": 50.0,
        "MACD": 0.0,
        "MACD_Signal": 0.0,
        "Bollinger_Upper": 110.0,
        "Bollinger_Lower": 90.0,
        "Return_5D": 0.0,
        "Volatility_10D": 0.01
    }

    row.update(overrides)

    return row


def test_technical_score_stays_within_bounds_even_with_all_signals_bullish():

    row = _base_row(
        Close=120.0,
        MM20=100.0,
        MM50=100.0,
        RSI=10.0,
        MACD=5.0,
        MACD_Signal=1.0,
        Return_5D=0.1
    )

    result = analyze(
        row,
        NEUTRAL_ML_RESULT,
        ["MM20", "MM50", "RSI", "MACD", "Momentum"],
        {"Technique": 100, "Machine Learning": 0, "Risque": 0}
    )

    assert 0 <= result["technical_score"] <= 100
    assert result["positive"] == 5
    assert result["negative"] == 0


def test_risk_score_is_none_when_volatility_not_selected():

    row = _base_row()

    result = analyze(
        row,
        NEUTRAL_ML_RESULT,
        ["RSI"],
        {"Technique": 50, "Machine Learning": 50, "Risque": 50}
    )

    assert result["risk_score"] is None


def test_risk_score_reflects_volatility_level():

    low_vol = analyze(
        _base_row(Volatility_10D=0.001),
        NEUTRAL_ML_RESULT,
        ["Volatilité"],
        {"Technique": 0, "Machine Learning": 0, "Risque": 100}
    )

    high_vol = analyze(
        _base_row(Volatility_10D=0.5),
        NEUTRAL_ML_RESULT,
        ["Volatilité"],
        {"Technique": 0, "Machine Learning": 0, "Risque": 100}
    )

    assert low_vol["risk_score"] > high_vol["risk_score"]


def test_decision_thresholds_follow_ml_score_when_alone_weighted():
    """Poids technique et risque a zero : le score final egale exactement le
    score ML, ce qui permet de verifier les seuils de decision sans
    interference du scoring technique."""

    def decide(probability_up):

        result = analyze(
            _base_row(),
            {"probability_up": probability_up},
            ["RSI"],
            {"Technique": 0, "Machine Learning": 100, "Risque": 0}
        )

        return result["decision"], result["score"]

    decision, score = decide(0.9)
    assert decision == "ACHETER"
    assert score == 90.0

    decision, score = decide(0.5)
    assert decision == "CONSERVER"
    assert score == 50.0

    decision, score = decide(0.1)
    assert decision == "VENDRE"
    assert score == 10.0


def test_all_weights_zero_returns_neutral_score():

    result = analyze(
        _base_row(),
        NEUTRAL_ML_RESULT,
        ["RSI"],
        {"Technique": 0, "Machine Learning": 0, "Risque": 0}
    )

    assert result["score"] == 50.0
    assert result["decision"] == "CONSERVER"


def test_confidence_is_clamped_between_50_and_95():

    extreme_confidence = analyze(
        _base_row(),
        {"probability_up": 1.0},
        ["RSI"],
        {"Technique": 0, "Machine Learning": 100, "Risque": 0}
    )["confidence"]

    # score=100 -> |100-50|*2 = 100, plafonne a CONFIDENCE_MAX (95).
    assert extreme_confidence == 95.0

    neutral_confidence = analyze(
        _base_row(),
        NEUTRAL_ML_RESULT,
        ["RSI"],
        {"Technique": 0, "Machine Learning": 100, "Risque": 0}
    )["confidence"]

    assert neutral_confidence == 50.0
