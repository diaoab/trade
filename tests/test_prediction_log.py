"""Tests de services/prediction_log.py, sur un fichier temporaire pour ne
jamais toucher au vrai journal (results/prediction_log.csv)."""

import pandas as pd
import pytest

from services import prediction_log


@pytest.fixture
def log_path(tmp_path, monkeypatch):

    path = tmp_path / "prediction_log.csv"

    monkeypatch.setattr(prediction_log, "PREDICTION_LOG_PATH", path)

    return path


def _fake_result(**overrides):

    result = {
        "decision": "CONSERVER",
        "score": 55.0,
        "confidence": 60.0,
        "technical_score": 60.0,
        "ml_score": 50.0,
        "risk_score": 70.0
    }

    result.update(overrides)

    return result


def test_load_prediction_log_is_empty_before_any_analysis(log_path):

    log = prediction_log.load_prediction_log()

    assert log.empty
    assert list(log.columns) == prediction_log.LOG_COLUMNS


def test_log_prediction_creates_file_with_one_row(log_path):

    prediction_log.log_prediction(
        symbol="CORIS_1",
        structure_name="Coris_1",
        session_date=pd.Timestamp("2025-12-31"),
        close=10780.0,
        result=_fake_result(),
        ml_result={"probability_up": 0.58},
        weights={"Technique": 40, "Machine Learning": 40, "Risque": 20}
    )

    assert log_path.exists()

    log = prediction_log.load_prediction_log()

    assert len(log) == 1
    assert log.iloc[0]["symbol"] == "CORIS_1"
    assert log.iloc[0]["decision"] == "CONSERVER"
    assert log.iloc[0]["probability_up"] == pytest.approx(0.58)


def test_log_prediction_appends_without_overwriting(log_path):

    for score in (55.0, 62.0):

        prediction_log.log_prediction(
            symbol="CORIS_1",
            structure_name="Coris_1",
            session_date=pd.Timestamp("2025-12-31"),
            close=10780.0,
            result=_fake_result(score=score),
            ml_result={"probability_up": 0.58},
            weights={"Technique": 40, "Machine Learning": 40, "Risque": 20}
        )

    log = prediction_log.load_prediction_log()

    assert len(log) == 2
    assert list(log["score"]) == [55.0, 62.0]


def test_log_prediction_handles_missing_session_date(log_path):
    """Un historique sans colonne Date (cas rare, cf. app.py) ne doit pas
    faire planter le journal."""

    prediction_log.log_prediction(
        symbol="CORIS_1",
        structure_name="Coris_1",
        session_date=None,
        close=10780.0,
        result=_fake_result(),
        ml_result={"probability_up": 0.58},
        weights={"Technique": 40, "Machine Learning": 40, "Risque": 20}
    )

    log = prediction_log.load_prediction_log()

    assert pd.isna(log.iloc[0]["session_date"])
