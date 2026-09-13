"""Tests de services/predictor.py, sans dependre d'un modele reellement
entraine sur disque : un faux modele scikit-learn-like (predict/predict_proba)
suffit a exercer predict_row()."""

import numpy as np
import pandas as pd
import pytest

from services import predictor
from services.predictor import ModelUnavailable, predict_row


FEATURES = ["RSI", "Distance_MM20"]


class FakeModel:
    """Renvoie toujours la meme prediction/probabilite, quelle que soit
    l'entree -- suffisant pour tester le cablage de predict_row(), pas
    l'exactitude d'un vrai modele."""

    def __init__(self, prediction=1, probability_up=0.7):

        self.prediction = prediction
        self.probability_up = probability_up

    def predict(self, X):
        return np.array([self.prediction])

    def predict_proba(self, X):
        return np.array([[1 - self.probability_up, self.probability_up]])


def _row(**overrides):

    values = {"RSI": 50.0, "Distance_MM20": 0.01}
    values.update(overrides)

    return pd.Series(values)


def test_predict_row_raises_when_feature_missing():

    row = pd.Series({"RSI": 50.0})  # Distance_MM20 absente

    with pytest.raises(ModelUnavailable, match="Distance_MM20"):

        predict_row(row, model=FakeModel(), features=FEATURES)


def test_predict_row_raises_when_value_is_nan():

    row = _row(Distance_MM20=float("nan"))

    with pytest.raises(ModelUnavailable, match="Distance_MM20"):

        predict_row(row, model=FakeModel(), features=FEATURES)


def test_predict_row_returns_raw_probabilities(monkeypatch):

    monkeypatch.setattr(predictor, "load_probability_reference", lambda: None)

    result = predict_row(
        _row(),
        model=FakeModel(prediction=1, probability_up=0.7),
        features=FEATURES
    )

    assert result["prediction"] == 1
    assert result["probability_up"] == pytest.approx(0.7)
    assert result["probability_down"] == pytest.approx(0.3)


def test_predict_row_omits_ml_score_without_reference(monkeypatch):
    """Un modele plus ancien, entraine avant l'ajout de la distribution de
    reference, ne doit pas faire planter predict_row -- juste omettre le
    percentile."""

    monkeypatch.setattr(predictor, "load_probability_reference", lambda: None)

    result = predict_row(_row(), model=FakeModel(), features=FEATURES)

    assert "ml_score" not in result
    assert "ml_percentile" not in result


def test_predict_row_adds_percentile_when_reference_available(monkeypatch):

    # Distribution de reference connue : 9 valeurs regulierement espacees.
    reference = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])

    monkeypatch.setattr(
        predictor,
        "load_probability_reference",
        lambda: reference
    )

    result = predict_row(
        _row(),
        model=FakeModel(probability_up=0.65),
        features=FEATURES
    )

    # searchsorted(reference, 0.65, side="left") == 6 (0.65 s'insere apres
    # 0.6, avant 0.7) -> percentile = 6/9*100.
    expected_percentile = 6 / 9 * 100

    assert result["ml_percentile"] == pytest.approx(expected_percentile)
    assert result["ml_score"] == pytest.approx(expected_percentile)


def test_predict_row_ignores_empty_reference(monkeypatch):

    monkeypatch.setattr(
        predictor,
        "load_probability_reference",
        lambda: np.array([])
    )

    result = predict_row(_row(), model=FakeModel(), features=FEATURES)

    assert "ml_score" not in result
