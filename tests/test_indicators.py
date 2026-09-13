"""Tests des indicateurs techniques (services/indicators.py).

Verifient les proprietes mathematiques attendues (bornes, coherence entre
colonnes derivees) plutot que des valeurs exactes recalculees a la main.
"""

import numpy as np
import pandas as pd

from services.indicators import calculate_indicators


def _make_close_series(n=80, seed=0):
    """Serie de cours synthetique, assez longue pour depasser toutes les
    fenetres glissantes utilisees par calculate_indicators (au plus 50)."""

    rng = np.random.default_rng(seed)

    steps = rng.normal(loc=0.0, scale=1.0, size=n)

    prices = 100 + np.cumsum(steps)

    # Aucun cours ne doit etre negatif ou nul, sinon Return_1D exploserait.
    prices = np.abs(prices) + 50

    return pd.DataFrame({"Close": prices})


def test_moving_averages_match_pandas_rolling():

    df = calculate_indicators(_make_close_series())

    expected_mm20 = df["Close"].rolling(20).mean()
    expected_mm50 = df["Close"].rolling(50).mean()

    pd.testing.assert_series_equal(
        df["MM20"], expected_mm20, check_names=False
    )

    pd.testing.assert_series_equal(
        df["MM50"], expected_mm50, check_names=False
    )


def test_rsi_is_bounded_between_0_and_100():

    df = calculate_indicators(_make_close_series())

    valid_rsi = df["RSI"].dropna()

    assert (valid_rsi >= 0).all()
    assert (valid_rsi <= 100).all()


def test_rsi_is_neutral_on_flat_prices():
    """Cours constant : ni hausse ni baisse, le RSI doit valoir 50 plutot que
    NaN (0/0), comme documente dans calculate_indicators."""

    flat = pd.DataFrame({"Close": [100.0] * 40})

    df = calculate_indicators(flat)

    valid_rsi = df["RSI"].dropna()

    assert (valid_rsi == 50).all()


def test_bollinger_bands_are_ordered():

    df = calculate_indicators(_make_close_series())

    valid = df.dropna(
        subset=["Bollinger_Upper", "Bollinger_Middle", "Bollinger_Lower"]
    )

    assert (valid["Bollinger_Upper"] >= valid["Bollinger_Middle"]).all()
    assert (valid["Bollinger_Middle"] >= valid["Bollinger_Lower"]).all()


def test_macd_histogram_equals_macd_minus_signal():

    df = calculate_indicators(_make_close_series())

    expected = df["MACD"] - df["MACD_Signal"]

    pd.testing.assert_series_equal(
        df["MACD_Hist"], expected, check_names=False
    )


def test_distance_to_moving_average_matches_definition():

    df = calculate_indicators(_make_close_series())

    valid = df.dropna(subset=["Distance_MM20"])

    expected = valid["Close"] / valid["MM20"] - 1

    pd.testing.assert_series_equal(
        valid["Distance_MM20"], expected, check_names=False
    )


def test_volume_ratio_only_added_when_volume_present():

    without_volume = calculate_indicators(_make_close_series())

    assert "Volume_Ratio" not in without_volume.columns

    with_volume = _make_close_series()

    with_volume["Volume"] = 1000

    with_volume = calculate_indicators(with_volume)

    assert "Volume_Ratio" in with_volume.columns
