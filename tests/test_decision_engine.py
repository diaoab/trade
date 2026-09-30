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
        RSI=90.0,
        RSI_Reading=1,
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


def test_confidence_grows_with_distance_from_neutral_and_is_capped():

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

    # Score pile a 50 : aucune conviction, et surtout pas un plancher a 50 %.
    assert neutral_confidence == 0.0


def test_analysis_runs_without_a_model():

    result = analyze(
        _base_row(Close=120.0),
        None,
        ["MM20", "MM50"],
        {"Technique": 40, "Machine Learning": 40, "Risque": 20}
    )

    assert result["ml_score"] is None
    # Seule composante mesuree : le score global est le score technique.
    assert result["score"] == result["technical_score"] == 68


def test_zero_weight_model_is_reported_as_indicative_only():

    result = analyze(
        _base_row(),
        {"probability_up": 0.9},
        ["RSI"],
        {"Technique": 100, "Machine Learning": 0, "Risque": 0}
    )

    assert result["score"] == 50
    assert any("à titre indicatif" in reason for reason in result["reasons"])


TECHNICAL_ONLY = {"Technique": 100, "Machine Learning": 0, "Risque": 0}


def test_bollinger_is_neutral_inside_the_bands_and_says_so():

    result = analyze(
        _base_row(),
        NEUTRAL_ML_RESULT,
        ["Bollinger"],
        TECHNICAL_ONLY
    )

    assert result["neutral"] == 1
    assert result["technical_score"] == 50
    assert any("Bollinger" in reason for reason in result["reasons"])


def test_bollinger_signals_only_outside_the_bands():

    def breakout(close, reading):

        return analyze(
            _base_row(Close=close, Bollinger_Reading=reading),
            NEUTRAL_ML_RESULT,
            ["Bollinger"],
            TECHNICAL_ONLY
        )

    # Titre dont les exces se prolongent : la sortie par le haut est
    # favorable, la sortie par le bas defavorable.
    assert breakout(115.0, 1)["positive"] == 1
    assert breakout(85.0, 1)["negative"] == 1

    # Titre dont les exces se corrigent : lecture inverse.
    assert breakout(115.0, -1)["negative"] == 1
    assert breakout(85.0, -1)["positive"] == 1

    # Historique qui ne tranche pas : l'extreme est signale, sans peser.
    undecided = breakout(115.0, 0)

    assert undecided["neutral"] == 1
    assert undecided["technical_score"] == 50
    assert any("ne permet pas" in reason for reason in undecided["reasons"])


def test_flat_prices_give_no_bollinger_macd_or_momentum_signal():
    """Cours fige : bandes confondues avec le cours, MACD egal a son signal,
    rendement nul. Aucun de ces cas ne doit compter comme un signal."""

    result = analyze(
        _base_row(Bollinger_Upper=100.0, Bollinger_Lower=100.0),
        NEUTRAL_ML_RESULT,
        ["MACD", "Bollinger", "Momentum"],
        TECHNICAL_ONLY
    )

    assert result["positive"] == 0
    assert result["negative"] == 0
    assert result["neutral"] == 3
    assert result["technical_score"] == 50


def test_illiquid_sessions_are_flagged_without_moving_the_score():

    liquid = analyze(
        _base_row(Flat_Share_20D=0.1, Volume_Ratio=1.0),
        NEUTRAL_ML_RESULT,
        ["RSI"],
        TECHNICAL_ONLY
    )

    illiquid = analyze(
        _base_row(Flat_Share_20D=0.7, Volume_Ratio=0.01),
        NEUTRAL_ML_RESULT,
        ["RSI"],
        TECHNICAL_ONLY
    )

    assert liquid["liquidity_warnings"] == []
    assert len(illiquid["liquidity_warnings"]) == 2
    assert illiquid["score"] == liquid["score"]

    # Historique sans colonne Volume : pas d'avertissement invente.
    assert analyze(
        _base_row(), NEUTRAL_ML_RESULT, ["RSI"], TECHNICAL_ONLY
    )["liquidity_warnings"] == []


def test_risk_tempers_conviction_without_giving_a_direction():
    """Meme analyse technique baissiere, deux niveaux de volatilite : le
    titre calme ne doit pas ressortir plus "acheteur", seulement moins
    tempere."""

    bearish = dict(Close=80.0, MM20=100.0, MM50=100.0)

    weights = {"Technique": 40, "Machine Learning": 0, "Risque": 20}

    calm = analyze(
        _base_row(Volatility_10D=0.001, **bearish),
        None,
        ["MM20", "MM50", "Volatilité"],
        weights
    )

    nervous = analyze(
        _base_row(Volatility_10D=0.5, **bearish),
        None,
        ["MM20", "MM50", "Volatilité"],
        weights
    )

    assert calm["technical_score"] == nervous["technical_score"] == 32

    # Les deux restent sous 50 ; le titre agite est ramene plus pres de 50.
    assert calm["score"] < nervous["score"] < 50
    assert calm["decision"] == "VENDRE"
